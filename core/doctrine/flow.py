"""Volume / Order Flow & Dealer data (P9-P10).

ORION only reports these metrics when a REAL feed exists. Today none of
them have a verified provider in this repo, so every accessor returns
NOT_AVAILABLE with an explicit reason. NEVER fabricate volume profile,
delta, CVD, DOM, GEX or dealer zones from OHLC.
"""

from __future__ import annotations

from core.desk.context import not_available

VOLUME_FLOW_FIELDS: tuple[str, ...] = (
    "VPOC", "POC", "HVN", "LVN", "DELTA", "CVD",
    "VOLUME_PROFILE", "TPO", "DOM", "GEX",
)

DEALER_FIELDS: tuple[str, ...] = (
    "DEALER_BUY_ZONES", "DEALER_SELL_ZONES", "GAMMA_WALLS",
    "OPEN_INTEREST", "LIQUIDITY_POOLS_INSTITUTIONAL",
    "DEALER_TARGET_OF_DAY", "ETF_FLOWS",
)


def volume_flow_block() -> dict:
    """Honest availability report for order-flow metrics."""
    reason = ("no verified order-flow/volume feed configured; refusing to "
              "fabricate from OHLC")
    return {
        field: not_available(reason) for field in VOLUME_FLOW_FIELDS
    }


def dealer_block() -> dict:
    """P10 — dealer/institutional data support, values only with verified source."""
    reason = "NOT AVAILABLE — VERIFIED SOURCE REQUIRED"
    return {field: not_available(reason) for field in DEALER_FIELDS}
