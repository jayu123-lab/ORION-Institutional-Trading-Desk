"""ORION Executable Pricing Engine.

Computes executable prices for YES/NO outcomes based on orderbook depth walks,
VWAP, partial fill handling, and combined YES/NO cost with fee support.

Design notes:
- Depth walk fills from best price down
- VWAP is weighted average of filled levels
- Partial fills return PARTIAL status with remaining quantity
- NO_LIQUIDITY status when no levels available
- Fees configurable in basis points (bps)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from core.config import get_settings
from core.orderbook import PolymarketOrderBookEngine

logger = logging.getLogger("orian.executable")


# ─── Executable Price ────────────────────────────────────────────

class ExecutablePrice:
    """Result of an executable price computation.

    Parameters
    ----------
    filled_quantity : float
        Quantity filled from the orderbook.
    filled_vwap : float
        Weighted average price of filled levels.
    remaining_quantity : float
        Quantity not yet filled (remaining to reach requested amount).
    status : str
        One of: FILLED, PARTIAL, NO_LIQUIDITY.
    depth_walked : int
        Number of orderbook levels walked during pricing.
    timestamp : datetime
        Time of price computation.
    """

    __slots__ = (
        "filled_quantity",
        "filled_vwap",
        "remaining_quantity",
        "status",
        "depth_walked",
        "timestamp",
    )

    def __init__(
        self,
        filled_quantity: float = 0.0,
        filled_vwap: float = 0.0,
        remaining_quantity: float = 0.0,
        status: str = "NO_LIQUIDITY",
        depth_walked: int = 0,
        timestamp: datetime | None = None,
    ) -> None:
        self.filled_quantity = filled_quantity
        self.filled_vwap = filled_vwap
        self.remaining_quantity = remaining_quantity
        self.status = status
        self.depth_walked = depth_walked
        self.timestamp = timestamp if timestamp else datetime.now(UTC)


def _walk_levels(
    levels: list[dict[str, float]],
    side: str,
    quantity: float,
    max_depth: int | None = None,
) -> ExecutablePrice | None:
    """Walk orderbook levels to fill a given quantity.

    Parameters
    ----------
    levels : list[dict[str, float]]
        Orderbook levels as [{"price": p, "size": s}, ...], sorted by side.
    side : str
        "ask" (walk down) or "bid" (walk up).
    quantity : float
        Target quantity to fill.
    max_depth : int, optional
        Max levels to walk. Defaults to all available.

    Returns
    -------
    ExecutablePrice | None
        Price result and number of levels walked.
    """
    filled = 0.0
    vwap_sum = 0.0
    levels_walked = 0

    for _i, level in enumerate(levels):
        if max_depth is not None and levels_walked >= max_depth:
            break

        price = level["price"]
        size = level["size"]

        if size <= 0:
            continue

        if side == "ask":
            # Asks: walk from lowest price up
            can_fill = min(size, quantity - filled)
            filled += can_fill
            vwap_sum += price * can_fill
        else:
            # Bids: walk from highest price down
            can_fill = min(size, quantity - filled)
            filled += can_fill
            vwap_sum += price * can_fill

        levels_walked += 1

        if filled >= quantity:
            vwap = vwap_sum / filled if filled > 0 else 0.0
            return ExecutablePrice(
                filled_quantity=filled,
                filled_vwap=float(vwap),
                remaining_quantity=0.0,
                status="FILLED",
                depth_walked=levels_walked,
            )

    # If we get here, we didn't fill the full quantity
    if filled > 0:
        vwap = vwap_sum / filled if filled > 0 else 0.0
        return ExecutablePrice(
            filled_quantity=filled,
            filled_vwap=float(vwap),
            remaining_quantity=quantity - filled,
            status="PARTIAL",
            depth_walked=levels_walked,
        )

    # No liquidity at all
    return ExecutablePrice(
        filled_quantity=0.0,
        filled_vwap=0.0,
        remaining_quantity=quantity,
        status="NO_LIQUIDITY",
        depth_walked=levels_walked,
    )


def get_executable_price(
    market_id: str,
    outcome: str,
    quantity: float,
    engine: PolymarketOrderBookEngine | None = None,
) -> ExecutablePrice | None:
    """Get the executable price for a given quantity of YES or NO tokens.

    Parameters
    ----------
    market_id : str
        The market token identifier.
    outcome : str
        "YES" or "NO" indicating which outcome side to walk.
    quantity : float
        Target quantity to fill.
    engine : PolymarketOrderBookEngine, optional
        Orderbook engine instance. Creates a new one if not provided.

    Returns
    -------
    ExecutablePrice | None
        Price result with filled quantity, VWAP, remaining quantity, and status.
    """
    engine = engine or PolymarketOrderBookEngine()
    book = engine.book(market_id)

    if outcome == "YES":
        # YES outcome: walk the asks (sell side)
        levels = book.get("asks", [])
    else:
        # NO outcome: walk the bids (buy side)
        levels = book.get("bids", [])

    # Normalize levels to {"price": p, "size": s} format if needed
    normalized: list[dict[str, float]] = []
    for level in levels:
        if isinstance(level, dict):
            normalized.append({"price": level["price"], "size": level["size"]})
        elif isinstance(level, (list, tuple)) and len(level) >= 2:
            normalized.append({"price": float(level[0]), "size": float(level[1])})

    result = _walk_levels(normalized, outcome, quantity)
    if result is not None:
        result.depth_walked = _walk_levels.__defaults__[0] if _walk_levels.__defaults__ else 0
    return result


def combined_yes_no_cost(
    yes_quantity: float,
    no_quantity: float,
    engine: PolymarketOrderBookEngine | None = None,
    fee_bps: float | None = None,
) -> dict[str, Any]:
    """Calculate the combined executable cost for YES + NO outcomes.

    Parameters
    ----------
    yes_quantity : float
        Quantity of YES tokens.
    no_quantity : float
        Quantity of NO tokens.
    engine : PolymarketOrderBookEngine, optional
        Orderbook engine instance. Creates a new one if not provided.
    fee_bps : float, optional
        Fee in basis points. Defaults to config setting or 10 bps.

    Returns
    -------
    dict[str, Any]
        Dictionary with 'yes_cost', 'no_cost', 'combined_cost', and 'status'.
    """
    engine = engine or PolymarketOrderBookEngine()
    if fee_bps is None:
        # Default: read from settings, fall back to 10 bps
        try:
            s = get_settings()
            fee_bps = getattr(s, "orion_fee_bps", 10.0)
        except Exception:
            fee_bps = 10.0

    yes_price = get_executable_price(
        market_id="UNKNOWN", outcome="YES", quantity=yes_quantity, engine=engine
    )
    no_price = get_executable_price(
        market_id="UNKNOWN", outcome="NO", quantity=no_quantity, engine=engine
    )

    yes_filled = yes_price.filled_quantity if yes_price is not None else 0
    yes_vwap = yes_price.filled_vwap if yes_price is not None else 0.0
    no_filled = no_price.filled_quantity if no_price is not None else 0
    no_vwap = no_price.filled_vwap if no_price is not None else 0.0

    yes_cost = yes_filled * yes_vwap if yes_filled > 0 else 0.0
    no_cost = no_filled * no_vwap if no_filled > 0 else 0.0
    combined_cost = yes_cost + no_cost

    # Apply fee to combined cost
    fee_amount = combined_cost * (fee_bps / 10000.0) if fee_bps else 0.0
    combined_cost_with_fee = combined_cost + fee_amount

    status_filled = (
        yes_price is not None
        and yes_price.status == "FILLED"
        and no_price is not None
        and no_price.status == "FILLED"
    )

    return {
        "yes_cost": round(yes_cost, 2),
        "no_cost": round(no_cost, 2),
        "combined_cost": round(combined_cost_with_fee, 2),
        "combined_cost_no_fee": round(combined_cost, 2),
        "fee_bps": fee_bps,
        "fee_amount": round(fee_amount, 2),
        "status": "SUFFICIENT_LIQUIDITY" if status_filled else "INSUFFICIENT_LIQUIDITY",
    }