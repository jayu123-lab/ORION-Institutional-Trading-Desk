"""Market regime classification (spec §18).

Phase 1: transparent heuristics on OHLCV candles — no black box, honest about
method. Phase 3 roadmap item upgrades to statistical models (HMM/clustering).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from core.market_data.base import Candle


@dataclass(frozen=True)
class Regime:
    symbol: str
    trend: str  # TRENDING | RANGING
    volatility: str  # HIGH_VOLATILITY | LOW_VOLATILITY | NORMAL
    risk: str  # RISK_ON | RISK_OFF
    method: str
    confidence: float  # 0..1
    ts: datetime

    @property
    def label(self) -> str:
        return f"{self.trend}/{self.volatility}/{self.risk}"


def _atr_pct(candles: list[Candle], period: int = 14) -> float:
    trs = []
    for prev, cur in zip(candles[-(period + 1) :], candles[-period:], strict=False):
        tr = max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )
        trs.append(tr / cur.close if cur.close else 0.0)
    return sum(trs) / len(trs) if trs else 0.0


def _efficiency_ratio(candles: list[Candle], lookback: int = 20) -> float:
    """Kaufman efficiency ratio: net move / path length ∈ [0,1]. ~1 = trending."""
    seg = candles[-lookback:]
    if len(seg) < 3:
        return 0.0
    net = abs(seg[-1].close - seg[0].close)
    path = sum(abs(b.close - a.close) for a, b in zip(seg, seg[1:], strict=False))
    return net / path if path else 0.0


def classify(symbol: str, candles: list[Candle], risk_assets_down: bool | None = None) -> Regime:
    """
    risk_assets_down: optional cross-asset input (e.g., SPX falling) for RISK_OFF.
    """
    now = datetime.now(UTC)
    if len(candles) < 30:
        return Regime(
            symbol=symbol,
            trend="RANGING",
            volatility="NORMAL",
            risk="RISK_ON" if not risk_assets_down else "RISK_OFF",
            method="insufficient-data-default",
            confidence=0.2,
            ts=now,
        )

    er = _efficiency_ratio(candles)
    atr = _atr_pct(candles)

    trending = er > 0.35
    vol_state = "HIGH_VOLATILITY" if atr > 0.02 else ("LOW_VOLATILITY" if atr < 0.006 else "NORMAL")
    risk = "RISK_OFF" if risk_assets_down else "RISK_ON"

    conf = min(1.0, max(0.3, (abs(er - 0.35) * 2)))
    return Regime(
        symbol=symbol,
        trend="TRENDING" if trending else "RANGING",
        volatility=vol_state,
        risk=risk,
        method="efficiency-ratio+atr-heuristic-v1",
        confidence=round(conf, 2),
        ts=now,
    )
