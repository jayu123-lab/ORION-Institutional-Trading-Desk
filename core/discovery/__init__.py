"""ORION Polymarket Market Discovery.

Uses the public Gamma API (no auth required) to discover and classify
active, unresolved, tradeable markets from Polymarket.

Design principles:
1. Reuse existing PolymarketAdapter Gamma endpoints
2. Classify markets dynamically based on metadata
3. Filter by active/unresolved/tradeable status
4. Return normalized market summaries for the radar/engine
5. No authentication required — public endpoints only
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from core.config import get_settings  # noqa: F401

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from providers.polymarket.adapter import MarketSummary, PolymarketAdapter, PolymarketError

logger = logging.getLogger("orion.discovery")

# ─── Classification ───────────────────────────────────────────────

CRYPTO_KEYWORDS = {
    "BTC": ("bitcoin", "btc"),
    "ETH": ("ethereum", "eth"),
    "XRP": ("xrp", "ripple"),
    "SOL": ("solana", "sol"),
}

MACRO_KEYWORDS = (
    "inflation",
    "cpi",
    "pce",
    "federal reserve",
    "fed",
    "interest rate",
    "employment",
    "payroll",
    "nfp",
    "gdp",
    "ppi",
)

FED_KEYWORDS = (
    "federal reserve",
    "fed",
    "rate decision",
    "fomc",
)

ECONOMY_KEYWORDS = (
    "gdp",
    "cpi",
    "ppi",
    "employment",
    "payroll",
    "inflation",
)

GEOPOLITICS_KEYWORDS = (
    "war",
    "sanction",
    "election",
    "geopolit",
    "referendum",
)

POLITICS_KEYWORDS = (
    "president",
    "senate",
    "congress",
    "election",
    "primaries",
    "debate",
)

OTHER_KEYWORDS = (
    "metals",
    "commodities",
    "indices",
    "volatility",
)


def _classify_market(question: str, slug: str) -> str:
    """Classify a market dynamically based on its question and slug."""
    q_lower = question.lower()
    s_lower = slug.lower()

    # Check crypto first (highest priority)
    for _symbol, words in CRYPTO_KEYWORDS.items():
        if any(word in q_lower or word in s_lower for word in words):
            return "CRYPTO"

    # Check politics
    if any(word in q_lower or word in s_lower for word in POLITICS_KEYWORDS):
        return "POLITICS"

    # Check geopolitics
    if any(word in q_lower or word in s_lower for word in GEOPOLITICS_KEYWORDS):
        return "GEOPOLITICS"

    # Check FED
    if any(word in q_lower or word in s_lower for word in FED_KEYWORDS):
        return "FED"

    # Check macro
    if any(word in q_lower or word in s_lower for word in MACRO_KEYWORDS):
        return "MACRO"

    # Check economy
    if any(word in q_lower or word in s_lower for word in ECONOMY_KEYWORDS):
        return "ECONOMY"

    return "OTHER"


def _extract_assets(question: str, slug: str) -> list[str]:
    """Extract crypto asset symbols from question/slug."""
    assets = []
    q_lower = question.lower()
    s_lower = slug.lower()

    for _symbol, words in CRYPTO_KEYWORDS.items():
        if any(word in q_lower or word in s_lower for word in words):
            assets.append(_symbol)

    return assets


# ─── Market Discovery ─────────────────────────────────────────────

async def discover_markets(
    limit: int = 50,
    closed: bool = False,
    adapter: PolymarketAdapter | None = None,
) -> list[dict[str, Any]]:
    """Discover active Markets from Polymarket Gamma API.

    Returns normalized market dicts with classification, asset extraction,
    and tradeability flags.

    Parameters
    ----------
    limit : int
        Max number of markets to return (default 50)
    closed : bool
        If True, include closed markets (default False)
    adapter : PolymarketAdapter
        Optional adapter instance (creates one if not provided)

    Returns
    -------
    List[Dict]
        Normalized market dictionaries including:
        - market_id, condition_id, question, slug
        - category (CRYPTO/MACRO/FED/ECONOMY/GEOPOLITICS/POLITICS/OTHER)
        - outcomes, token_ids
        - liquidity, volume
        - end_time (datetime)
        - active, unresolved, tradeable flags
        - assets extracted from question/slug
    """
    _adapter = adapter or PolymarketAdapter()

    try:
        markets_summary = await _adapter.list_markets(
            closed=closed, limit=limit, order="volumeNum", ascending=False
        )
    except PolymarketError as e:
        logger.warning(f"Gamma API error during market discovery: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error during market discovery: {e}")
        return []

    normalized: list[dict[str, Any]] = []

    for summary in markets_summary:
        try:
            market_dict = _normalize_market(summary)
            if market_dict is None:
                continue

            # Classify and extract assets
            category = _classify_market(
                market_dict.get("question", ""), market_dict.get("slug", "")
            )
            assets = _extract_assets(
                market_dict.get("question", ""), market_dict.get("slug", "")
            )

            # Determine tradeability
            active = market_dict.get("active", False)
            unresolved = not market_dict.get("closed", True)
            tradeable = active and unresolved

            entry = {
                "market_id": market_dict.get("id"),
                "condition_id": market_dict.get("condition_id", market_dict.get("id")),
                "question": market_dict.get("question", ""),
                "slug": market_dict.get("slug", ""),
                "category": category,
                "outcomes": market_dict.get("outcomes", []),
                "token_ids": market_dict.get("token_ids", []),
                "liquidity": market_dict.get("liquidity"),
                "volume": market_dict.get("volume"),
                "end_time": _parse_end_time(market_dict.get("end_date")),
                "active": active,
                "unresolved": unresolved,
                "tradeable": tradeable,
                "assets": assets,
                "yes_price": market_dict.get("yes_price"),
                "no_price": market_dict.get("no_price"),
                "spread": market_dict.get("spread"),
            }
            normalized.append(entry)

        except Exception as e:
            logger.warning(f"Failed to normalize market {summary.get('id', 'unknown')}: {e}")
            continue

    # Sort: active first, then by volume, then by liquidity
    normalized.sort(key=lambda m: (
        not m["active"],  # active first
        m.get("volume") or 0,  # then by volume desc
        m.get("liquidity") or 0,
    ))

    _count = sum(1 for m in normalized if m["active"])
    logger.info(f"Discovered {len(normalized)} markets (active={_count})")
    return normalized


def _normalize_market(summary: MarketSummary) -> dict[str, Any] | None:
    """Normalize a Gamma MarketSummary into a dict with core fields."""
    if not isinstance(summary, MarketSummary):
        return None

    # Build a minimal dict from what's available
    return {
        "id": summary.id,
        "condition_id": summary.id,
        "question": summary.question,
        "slug": summary.slug,
        "outcomes": summary.token_ids or [],
        "yes_price": summary.yes_price,
        "no_price": summary.no_price,
        "spread": summary.spread,
        "volume": summary.volume,
        "liquidity": summary.liquidity,
        "end_date": summary.end_date,
    }


def _parse_end_time(end_date: str | None) -> datetime | None:
    """Parse end_date string into a timezone-aware datetime."""
    if not end_date:
        return None
    try:
        # Polymarket endDate format: ISO 8601 or similar
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        logger.warning(f"Could not parse end_date: {end_date}")
        return None


# ─── Convenience ──────────────────────────────────────────────────

def get_active_markets(
    limit: int = 50,
    adapter: PolymarketAdapter | None = None,
) -> list[dict[str, Any]]:
    """Synchronous wrapper — returns only active (open) markets."""
    return asyncio.run(discover_markets(limit=limit, closed=False, adapter=adapter))


def get_markets_by_category(
    category: str,
    limit: int = 50,
    adapter: PolymarketAdapter | None = None,
) -> list[dict[str, Any]]:
    """Return markets filtered by category."""
    all_markers = asyncio.run(discover_markets(limit=limit, adapter=adapter))
    return [m for m in all_markers if m.get("category") == category]


# ─── Exported symbols ────────────────────────────────────────────

__all__ = [
    "discover_markets",
    "get_active_markets",
    "get_markets_by_category",
    "CRYPTO_KEYWORDS",
    "MACRO_KEYWORDS",
    "FED_KEYWORDS",
    "ECONOMY_KEYWORDS",
    "GEOPOLITICS_KEYWORDS",
    "POLITICS_KEYWORDS",
    "OTHER_KEYWORDS",
    "_classify_market",
    "_extract_assets",
    "_normalize_market",
    "_parse_end_time",
]