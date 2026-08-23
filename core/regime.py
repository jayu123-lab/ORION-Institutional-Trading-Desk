"""Market regime classification (spec §18, upgraded v2).

Multi-factor deterministic detector over real OHLCV candles. No black box:
every component is reported in Regime.metrics.

Components
----------
- ATR% (Wilder-style simple mean)          → volatility level
- realized volatility (std of log rets)    → volatility level + expansion
- ADX (simplified Wilder smoothing)        → trend strength
- Kaufman efficiency ratio                 → price efficiency (trend quality)
- trend persistence (signed close runs)    → directional consistency
- range expansion (recent vs baseline TR)  → vol regime transition
- relative volume (if volume present)      → participation confirmation

Verdicts: TRENDING/RANGING × HIGH_VOLATILITY/NORMAL/LOW_VOLATILITY,
plus RISK_ON/RISK_OFF from optional cross-asset input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from core.market_data.base import Candle

MIN_CANDLES = 30
ADX_PERIOD = 14


@dataclass(frozen=True)
class Regime:
    symbol: str
    trend: str  # TRENDING | RANGING
    volatility: str  # HIGH_VOLATILITY | LOW_VOLATILITY | NORMAL
    risk: str  # RISK_ON | RISK_OFF
    method: str = "atr+rvol+adx+persistence+efficiency-v2"
    confidence: float = 0.2  # 0..1
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.trend}/{self.volatility}/{self.risk}"


# --------------------------------------------------------------- components


def true_range(prev: Candle, cur: Candle) -> float:
    return max(
        cur.high - cur.low,
        abs(cur.high - prev.close),
        abs(cur.low - prev.close),
    )


def atr_pct(candles: list[Candle], period: int = 14) -> float:
    """Mean True Range as % of close over the last `period` bars."""
    window = candles[-(period + 1) :]
    if len(window) < 2:
        return 0.0
    trs = [
        true_range(p, c) / c.close for p, c in zip(window, window[1:], strict=False) if c.close
    ]
    return sum(trs) / len(trs) if trs else 0.0


def realized_vol(candles: list[Candle], lookback: int = 20) -> float:
    """Std-dev of per-bar log returns over the lookback window."""
    seg = candles[-(lookback + 1) :]
    rets = [
        math.log(b.close / a.close)
        for a, b in zip(seg, seg[1:], strict=False)
        if a.close > 0 and b.close > 0
    ]
    if len(rets) < 5:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return var**0.5


def adx(candles: list[Candle], period: int = ADX_PERIOD) -> float:
    """Simplified Wilder ADX. Needs ~2*period bars; returns 0..100."""
    if len(candles) < period * 2 + 1:
        return 0.0
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    trs: list[float] = []
    for prev, cur in zip(candles[-(period * 2 + 1) :], candles[-(period * 2) :], strict=False):
        up = cur.high - prev.high
        down = prev.low - cur.low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(true_range(prev, cur))
    atr = sum(trs[:period]) / period
    s_plus = sum(plus_dm[:period]) / period
    s_minus = sum(minus_dm[:period]) / period
    dxs: list[float] = []
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
        s_plus = (s_plus * (period - 1) + plus_dm[i]) / period
        s_minus = (s_minus * (period - 1) + minus_dm[i]) / period
        if atr > 0:
            pdi = 100 * s_plus / atr
            mdi = 100 * s_minus / atr
            denom = pdi + mdi
            dxs.append(100 * abs(pdi - mdi) / denom if denom else 0.0)
    return sum(dxs) / len(dxs) if dxs else 0.0


def efficiency_ratio(candles: list[Candle], lookback: int = 20) -> float:
    """Kaufman ER: net move / path length ∈ [0,1]. ~1 = trending."""
    seg = candles[-lookback:]
    if len(seg) < 3:
        return 0.0
    net = abs(seg[-1].close - seg[0].close)
    path = sum(abs(b.close - a.close) for a, b in zip(seg, seg[1:], strict=False))
    return net / path if path else 0.0


def trend_persistence(candles: list[Candle], lookback: int = 20) -> float:
    """|mean sign of bar-to-bar closes| ∈ [0,1]: 1 = every bar same direction."""
    seg = candles[-(lookback + 1) :]
    moves = [b.close - a.close for a, b in zip(seg, seg[1:], strict=False)]
    moves = [m for m in moves if m != 0]
    if not moves:
        return 0.0
    signs = [1.0 if m > 0 else -1.0 for m in moves]
    return abs(sum(signs) / len(signs))


def range_expansion(candles: list[Candle], recent: int = 5, baseline: int = 50) -> float:
    """Avg TR of last `recent` bars ÷ avg TR of `baseline` window. >1 = expanding."""
    if len(candles) < baseline + 1:
        return 1.0
    def avg_tr(window: list[Candle]) -> float:
        trs = [true_range(p, c) for p, c in zip(window, window[1:], strict=False)]
        return sum(trs) / len(trs) if trs else 0.0
    base = avg_tr(candles[-baseline:])
    rec = avg_tr(candles[-recent:])
    return rec / base if base > 0 else 1.0


def relative_volume(candles: list[Candle], lookback: int = 20) -> float | None:
    """Last bar volume vs lookback mean. None when volume data absent."""
    vols = [c.volume for c in candles[-(lookback + 1) :] if c.volume]
    if len(vols) < 5:
        return None
    avg = sum(vols[:-1]) / (len(vols) - 1)
    return vols[-1] / avg if avg > 0 else None


# ------------------------------------------------------------------ classify


def classify(
    symbol: str,
    candles: list[Candle],
    risk_assets_down: bool | None = None,
) -> Regime:
    now = datetime.now(UTC)
    if len(candles) < MIN_CANDLES:
        return Regime(
            symbol=symbol,
            trend="RANGING",
            volatility="NORMAL",
            risk="RISK_OFF" if risk_assets_down else "RISK_ON",
            method="insufficient-data-default",
            confidence=0.2,
            ts=now,
            metrics={"candles": float(len(candles))},
        )

    er = efficiency_ratio(candles)
    persist = trend_persistence(candles)
    adx_v = adx(candles)
    atr = atr_pct(candles)
    rvol_std = realized_vol(candles)
    expansion = range_expansion(candles)
    rel_vol = relative_volume(candles)

    # --- trend score: weighted composite ∈ [0,1]
    er_component = min(er / 0.45, 1.0)              # ER 0.45+ → full credit
    adx_component = min(max((adx_v - 15.0) / 25.0, 0.0), 1.0)  # ADX 15→40
    persistence_component = min(max((persist - 0.15) / 0.55, 0.0), 1.0)
    trend_score = (
        0.40 * er_component + 0.35 * adx_component + 0.25 * persistence_component
    )
    trending = trend_score >= 0.5

    # --- volatility state: absolute ATR% guardrails + RVOL context
    if atr > 0.02 or (rvol_std > 3.5 * atr and expansion > 1.4):
        vol_state = "HIGH_VOLATILITY"
    elif atr < 0.006 and expansion < 1.1:
        vol_state = "LOW_VOLATILITY"
    else:
        vol_state = "NORMAL"

    risk = "RISK_OFF" if risk_assets_down else "RISK_ON"

    # --- confidence: distance from decision boundaries, participation bonus
    conf = 0.3 + 0.5 * min(abs(trend_score - 0.5) / 0.3, 1.0)
    if rel_vol is not None and rel_vol > 1.2:
        conf += 0.10
    conf = round(min(conf, 0.95), 2)

    metrics = {
        "efficiency_ratio": round(er, 4),
        "adx": round(adx_v, 2),
        "persistence": round(persist, 4),
        "atr_pct": round(atr, 6),
        "realized_vol": round(rvol_std, 6),
        "range_expansion": round(expansion, 4),
        "relative_volume": round(rel_vol, 4) if rel_vol is not None else 0.0,
        "trend_score": round(trend_score, 4),
    }

    return Regime(
        symbol=symbol,
        trend="TRENDING" if trending else "RANGING",
        volatility=vol_state,
        risk=risk,
        method="atr+rvol+adx+persistence+efficiency-v2",
        confidence=conf,
        ts=now,
        metrics=metrics,
    )
