"""Liquidity Map (P6-P7).

Derives BUY-SIDE / SELL-SIDE liquidity pools from real stored candles:
swing highs/lows, equal highs/lows, session extremes, PDH/PDL/PWH/PWL,
range extremes. These are DERIVED reference pools — the desk does NOT
claim they are confirmed institutional orders.

Sweep detection (P7): a wick through a mapped pool that closes back
inside = sweep of that side. A SWEEP IS NOT AN ENTRY: reaction,
displacement, structure shift and confirmation must follow.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LiquidityPool:
    price: float
    kind: str            # SWING_HIGH | SWING_LOW | EQH | EQL | PDH | PDL | PWH | PWL | ...
    side: str            # BUY_SIDE (above price) | SELL_SIDE (below price)
    touched_count: int = 1
    ts: str | None = None

    def to_dict(self) -> dict:
        return {
            "price": round(self.price, 6), "kind": self.kind, "side": self.side,
            "touched_count": self.touched_count, "ts": self.ts,
        }


@dataclass
class LiquidityMap:
    buy_side: list[LiquidityPool] = field(default_factory=list)
    sell_side: list[LiquidityPool] = field(default_factory=list)
    provenance: str = "DERIVED"
    source: str = "db:candles"
    note: str = ("derived liquidity pools from stored bars — NOT confirmed "
                 "institutional orders")

    def to_dict(self) -> dict:
        return {
            "buy_side": [p.to_dict() for p in self.buy_side],
            "sell_side": [p.to_dict() for p in self.sell_side],
            "provenance": self.provenance,
            "source": self.source,
            "note": self.note,
        }

    def nearest(self, price: float, side: str) -> LiquidityPool | None:
        pools = self.buy_side if side == "BUY_SIDE" else self.sell_side
        return min(pools, key=lambda p: abs(p.price - price)) if pools else None

    def all_levels(self) -> list[float]:
        return [p.price for p in self.buy_side + self.sell_side]


def _swings(candles: list, k: int = 2) -> tuple[list[int], list[int]]:
    """Fractal pivots: index lists of swing highs and swing lows."""
    highs_i: list[int] = []
    lows_i: list[int] = []
    for i in range(k, len(candles) - k):
        window_h = [candles[j].high for j in range(i - k, i + k + 1) if j != i]
        window_l = [candles[j].low for j in range(i - k, i + k + 1) if j != i]
        if candles[i].high > max(window_h):
            highs_i.append(i)
        if candles[i].low < min(window_l):
            lows_i.append(i)
    return highs_i, lows_i


def build_liquidity_map(
    candles: list,
    last_price: float | None,
    session_levels: dict[str, float] | None = None,
    atr: float | None = None,
) -> LiquidityMap:
    """Assemble the map. `candles` ascending; session_levels optional extras."""
    out = LiquidityMap()
    if not candles or last_price is None:
        return out

    tol = (atr * 0.15) if atr and atr > 0 else last_price * 0.0005
    pools: list[LiquidityPool] = []

    hi_idx, lo_idx = _swings(candles)
    for i in hi_idx:
        pools.append(LiquidityPool(candles[i].high, "SWING_HIGH", "BUY_SIDE",
                                   ts=candles[i].ts_open.isoformat()))
    for i in lo_idx:
        pools.append(LiquidityPool(candles[i].low, "SWING_LOW", "SELL_SIDE",
                                   ts=candles[i].ts_open.isoformat()))

    # equal highs / lows (cluster within tolerance)
    def _cluster(indices: list[int], attr: str, eq_kind: str) -> None:
        values = sorted(getattr(candles[i], attr) for i in indices)
        cluster: list[float] = []
        for v in values:
            if cluster and abs(v - cluster[-1]) <= tol:
                cluster.append(v)
            else:
                if len(cluster) >= 2:
                    pools.append(LiquidityPool(
                        sum(cluster) / len(cluster), eq_kind,
                        "BUY_SIDE" if attr == "high" else "SELL_SIDE",
                        touched_count=len(cluster)))
                cluster = [v]
        if len(cluster) >= 2:
            pools.append(LiquidityPool(
                sum(cluster) / len(cluster), eq_kind,
                "BUY_SIDE" if attr == "high" else "SELL_SIDE",
                touched_count=len(cluster)))

    _cluster(hi_idx, "high", "EQH")
    _cluster(lo_idx, "low", "EQL")

    # range extremes of the lookback
    pools.append(LiquidityPool(max(c.high for c in candles), "RANGE_HIGH", "BUY_SIDE"))
    pools.append(LiquidityPool(min(c.low for c in candles), "RANGE_LOW", "SELL_SIDE"))

    for name, kind, side in (("PDH", "PDH", "BUY_SIDE"), ("PDL", "PDL", "SELL_SIDE"),
                             ("PWH", "PWH", "BUY_SIDE"), ("PWL", "PWL", "SELL_SIDE"),
                             ("ASIA_HIGH", "ASIA_HIGH", "BUY_SIDE"),
                             ("ASIA_LOW", "ASIA_LOW", "SELL_SIDE"),
                             ("LONDON_HIGH", "LONDON_HIGH", "BUY_SIDE"),
                             ("LONDON_LOW", "LONDON_LOW", "SELL_SIDE")):
        val = (session_levels or {}).get(name)
        if val is not None:
            pools.append(LiquidityPool(val, kind, side))

    # dedupe near-identical prices keeping highest touched_count
    merged: list[LiquidityPool] = []
    for p in sorted(pools, key=lambda x: x.price):
        if merged and abs(p.price - merged[-1].price) <= tol:
            prev = merged[-1]
            merged[-1] = LiquidityPool(
                (prev.price + p.price) / 2, prev.kind, prev.side,
                max(prev.touched_count, p.touched_count), prev.ts)
            continue
        merged.append(p)

    out.buy_side = sorted((p for p in merged if p.price >= last_price),
                          key=lambda p: p.price)
    out.sell_side = sorted((p for p in merged if p.price < last_price),
                           key=lambda p: -p.price)
    return out


@dataclass(frozen=True)
class SweepEvent:
    side: str          # HIGH | LOW
    level: float
    bar_ts: str
    kind: str          # SWEEP_HIGH | SWEEP_LOW | FAILED_BREAKOUT
    note: str = "sweep is NOT an entry — await reaction/confirmation"

    def to_dict(self) -> dict:
        return {"side": self.side, "level": round(self.level, 6),
                "bar_ts": self.bar_ts, "kind": self.kind, "note": self.note}


def detect_sweeps(candles: list, lq_map: LiquidityMap, lookback: int = 3) -> list[SweepEvent]:
    """Wick beyond a pool with close back inside = sweep of that pool."""
    if len(candles) < 2 or not lq_map.all_levels():
        return []
    events: list[SweepEvent] = []
    levels = lq_map.all_levels()
    for c in candles[-lookback:]:
        rng = c.high - c.low
        if rng <= 0:
            continue
        for lv in levels:
            tol = rng * 0.02
            # swept high: wick above level, close back below it
            if c.high >= lv + tol and c.close < lv:
                events.append(SweepEvent("HIGH", lv, c.ts_open.isoformat(),
                                         "SWEEP_HIGH"))
                break
            # swept low: wick below level, close back above it
            if c.low <= lv - tol and c.close > lv:
                events.append(SweepEvent("LOW", lv, c.ts_open.isoformat(), "SWEEP_LOW"))
                break
    return events
