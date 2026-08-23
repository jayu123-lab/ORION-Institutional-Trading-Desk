"""Low-latency OHLC feature engine.

The engine never fabricates order-flow fields: those fields are explicitly marked
NOT_AVAILABLE unless a provider supplies the required observations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import sqrt
from statistics import mean, pstdev


@dataclass(frozen=True)
class FeatureValue:
    value: float | str | None
    timestamp: str
    source: str
    provenance: str
    quality: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeatureSnapshot:
    symbol: str
    timeframe: str
    timestamp: str
    values: dict[str, FeatureValue]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "features": {key: value.to_dict() for key, value in self.values.items()},
        }

    def value(self, name: str):
        item = self.values.get(name)
        return item.value if item else None


def _value(
    value, ts: str, source: str, quality: str = "A", provenance: str = "DERIVED"
) -> FeatureValue:
    return FeatureValue(value, ts, source, provenance, quality)


def _atr(candles: Sequence, period: int) -> float | None:
    if len(candles) < 2:
        return None
    trs = []
    window = candles[-(period + 1) :]
    for previous, current in zip(window[:-1], window[1:], strict=True):
        trs.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return mean(trs) if trs else None


def _adx(candles: Sequence, period: int = 14) -> tuple[float | None, float | None, float | None]:
    if len(candles) < period * 2 + 1:
        return None, None, None
    trs: list[float] = []
    plus: list[float] = []
    minus: list[float] = []
    for previous, current in zip(
        candles[-(period * 2) : -1], candles[-(period * 2) + 1 :], strict=True
    ):
        up = current.high - previous.high
        down = previous.low - current.low
        trs.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)
    dx: list[float] = []
    latest_plus = latest_minus = 0.0
    for idx in range(period, len(trs) + 1):
        tr = sum(trs[idx - period : idx])
        p = 100 * sum(plus[idx - period : idx]) / tr if tr else 0.0
        m = 100 * sum(minus[idx - period : idx]) / tr if tr else 0.0
        latest_plus, latest_minus = p, m
        dx.append(100 * abs(p - m) / (p + m) if p + m else 0.0)
    if not dx:
        return None, None, None
    adx = mean(dx[-period:])
    return adx, latest_plus, latest_minus


def calculate_features(
    candles: Sequence,
    symbol: str,
    timeframe: str = "H1",
    source: str = "stored-candles",
    now: datetime | None = None,
) -> FeatureSnapshot:
    """Calculate incremental-ready features from chronological candles."""
    stamp = (now or datetime.now(UTC)).isoformat()
    values: dict[str, FeatureValue] = {}
    last = candles[-1] if candles else None
    if not last:
        return FeatureSnapshot(symbol, timeframe, stamp, values)
    atr = _atr(candles, 14)
    adx, plus_di, minus_di = _adx(candles)
    previous_adx = _adx(candles[:-1])[0] if len(candles) > 30 else None
    prior_adx = _adx(candles[:-2])[0] if len(candles) > 31 else None
    closes = [float(c.close) for c in candles[-21:]]
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]
    realized = pstdev(returns) * sqrt(252) if len(returns) > 1 else None
    range_now = float(last.high - last.low)
    ranges = [float(c.high - c.low) for c in candles[-20:]]
    volume = getattr(last, "volume", None)
    volumes = [float(c.volume) for c in candles[-20:] if getattr(c, "volume", None) is not None]

    def add(name, value, quality="A", provenance="DERIVED"):
        values[name] = _value(value, stamp, source, quality, provenance)

    add("price", float(last.close))
    add("atr", atr)
    add("price_velocity", (last.close - candles[-2].close) if len(candles) > 1 else None)
    add("return_velocity", returns[-1] if returns else None)
    add(
        "range_expansion",
        range_now / mean(ranges[:-1]) if len(ranges) > 1 and mean(ranges[:-1]) else None,
    )
    add("realized_volatility", realized)
    add("adx", adx)
    add(
        "adx_slope",
        adx - previous_adx if adx is not None and previous_adx is not None else None,
    )
    add("adx_bucket", classify_adx(adx))
    add(
        "adx_acceleration",
        (adx - previous_adx) - (previous_adx - prior_adx)
        if adx is not None and previous_adx is not None and prior_adx is not None
        else None,
    )
    add("plus_di", plus_di)
    add("minus_di", minus_di)
    add("di_spread", plus_di - minus_di if plus_di is not None and minus_di is not None else None)
    add(
        "volume",
        float(volume) if volume is not None else None,
        "A" if volume is not None else "UNKNOWN",
    )
    add(
        "relative_volume",
        float(volume) / mean(volumes[:-1])
        if volume is not None and len(volumes) > 1 and mean(volumes[:-1])
        else None,
    )
    add(
        "volume_acceleration",
        float(volume) - mean(volumes[:-1]) if volume is not None and len(volumes) > 1 else None,
    )
    average_volume = mean(volumes[:-1]) if len(volumes) > 1 else None
    volume_std = pstdev(volumes[:-1]) if len(volumes) > 2 else None
    volume_z = (
        (float(volume) - average_volume) / volume_std
        if volume is not None and average_volume is not None and volume_std
        else None
    )
    add("average_volume", average_volume)
    add("volume_z_score", volume_z)
    add("volume_class", classify_volume(volume_z))
    add("vwap", None, "UNKNOWN", "NOT_AVAILABLE")
    add("delta", None, "UNKNOWN", "NOT_AVAILABLE")
    add("cvd", None, "UNKNOWN", "NOT_AVAILABLE")
    add("ofi", None, "UNKNOWN", "NOT_AVAILABLE")
    add("bid_ask_imbalance", None, "UNKNOWN", "NOT_AVAILABLE")
    add("microprice", None, "UNKNOWN", "NOT_AVAILABLE")
    add("order_book_imbalance", None, "UNKNOWN", "NOT_AVAILABLE")
    return FeatureSnapshot(symbol, timeframe, stamp, values)


def classify_adx(adx: float | None) -> str:
    if adx is None:
        return "INSUFFICIENT_DATA"
    if adx < 15:
        return "LOW TREND ENERGY"
    if adx < 20:
        return "DEVELOPING"
    if adx < 25:
        return "TREND BUILDING"
    if adx < 35:
        return "STRONG TREND"
    if adx < 50:
        return "VERY STRONG"
    return "EXTREME / POSSIBLE LATE TREND"


def classify_volume(z_score: float | None) -> str:
    if z_score is None:
        return "NOT_AVAILABLE"
    if z_score < -0.75:
        return "LOW"
    if z_score < 1.0:
        return "NORMAL"
    if z_score < 2.0:
        return "HIGH"
    return "EXTREME"
