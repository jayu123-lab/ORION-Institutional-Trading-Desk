"""CFTC Commitments of Traders provider — REAL institutional positioning data.

Source: CFTC public Socrata API (publicreporting.cftc.gov), official and free.
Datasets used (verified live 2026-08-23):
- Disaggregated Futures Only  : https://dev.socrata.com/foundry/publicreporting.cftc.gov/72hh-3qpy
- Legacy Futures Only         : https://dev.socrata.com/foundry/publicreporting.cftc.gov/6dca-aqww

Verified market records (2026-08-18 report date):
- GOLD   - COMMODITY EXCHANGE INC.        (disaggregated, m_money fields)
- SILVER - COMMODITY EXCHANGE INC.        (disaggregated)
- MICRO BITCOIN - CHICAGO MERCANTILE EXCHANGE (legacy, noncomm fields)

Reports are weekly (Tuesday publication, Saturday snapshot). Anything else the
desk needs (dealer gamma, ETF flows, funding) is explicitly NOT AVAILABLE here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

logger = logging.getLogger("orion.cftc")

DISAGG_FUTURES_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
LEGACY_FUTURES_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
REQUEST_TIMEOUT = 20.0

# symbol → (exact CFTC market name, dataset) — only VERIFIED names allowed here
CFTC_MARKET_MAP: dict[str, tuple[str, str]] = {
    "XAUUSD": ("GOLD - COMMODITY EXCHANGE INC.", "disaggregated"),
    "GC": ("GOLD - COMMODITY EXCHANGE INC.", "disaggregated"),
    "MGC": ("GOLD - COMMODITY EXCHANGE INC.", "disaggregated"),
    "XAGUSD": ("SILVER - COMMODITY EXCHANGE INC.", "disaggregated"),
    "SI": ("SILVER - COMMODITY EXCHANGE INC.", "disaggregated"),
    "BTCUSD": ("MICRO BITCOIN - CHICAGO MERCANTILE EXCHANGE", "legacy"),
}


@dataclass(frozen=True)
class CotRecord:
    symbol: str
    cftc_market: str
    report_date: str  # ISO yyyy-mm-dd
    open_interest: int
    # disaggregated fields (None when the dataset doesn't provide them)
    managed_money_long: int | None = None
    managed_money_short: int | None = None
    swap_long: int | None = None
    swap_short: int | None = None
    producer_long: int | None = None
    # legacy fields
    noncommercial_long: int | None = None
    noncommercial_short: int | None = None
    commercial_long: int | None = None
    commercial_short: int | None = None

    @property
    def managed_money_net(self) -> int | None:
        if self.managed_money_long is None or self.managed_money_short is None:
            return None
        return self.managed_money_long - self.managed_money_short

    @property
    def noncommercial_net(self) -> int | None:
        if self.noncommercial_long is None or self.noncommercial_short is None:
            return None
        return self.noncommercial_long - self.noncommercial_short

    @property
    def dataset(self) -> str:
        return "disaggregated" if self.managed_money_long is not None else "legacy"

    @property
    def report_age_days(self) -> float:
        dt = datetime.strptime(self.report_date, "%Y-%m-%d").replace(tzinfo=UTC)
        return max(0.0, (datetime.now(UTC) - dt).total_seconds() / 86400)


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_disaggregated(symbol: str, row: dict) -> CotRecord:
    return CotRecord(
        symbol=symbol,
        cftc_market=row.get("market_and_exchange_names", ""),
        report_date=str(row.get("report_date_as_yyyy_mm_dd", ""))[:10],
        open_interest=_to_int(row.get("open_interest_all")) or 0,
        managed_money_long=_to_int(row.get("m_money_positions_long_all")),
        managed_money_short=_to_int(row.get("m_money_positions_short_all")),
        swap_long=_to_int(row.get("swap_positions_long_all")),
        swap_short=_to_int(row.get("swap__positions_short_all")),
        producer_long=_to_int(row.get("producer_merchant_merchant_positions_long_all")),
    )


def parse_legacy(symbol: str, row: dict) -> CotRecord:
    return CotRecord(
        symbol=symbol,
        cftc_market=row.get("market_and_exchange_names", ""),
        report_date=str(row.get("report_date_as_yyyy_mm_dd", ""))[:10],
        open_interest=_to_int(row.get("open_interest_all")) or 0,
        noncommercial_long=_to_int(row.get("noncomm_positions_long_all")),
        noncommercial_short=_to_int(row.get("noncomm_positions_short_all")),
        commercial_long=_to_int(row.get("comm_positions_long_all")),
        commercial_short=_to_int(row.get("comm_positions_short_all")),
    )


async def fetch_cot(
    symbol: str,
    client: httpx.AsyncClient,
) -> CotRecord | None:
    """Fetch the latest COT record for a mapped symbol. Unmapped → None."""
    mapping = CFTC_MARKET_MAP.get(symbol.upper())
    if mapping is None:
        return None
    market_name, dataset = mapping
    url = DISAGG_FUTURES_URL if dataset == "disaggregated" else LEGACY_FUTURES_URL
    params: dict[str, str | int] = {
        "$limit": 1,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "market_and_exchange_names": market_name,
    }
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        logger.warning("CFTC: no rows for %s (%s)", symbol, market_name)
        return None
    if dataset == "disaggregated":
        return parse_disaggregated(symbol.upper(), rows[0])
    return parse_legacy(symbol.upper(), rows[0])
