"""ORION RANGE 2.6 (P8).

For a significant range/leg, range / 2.6 measured from the extreme
defines a possible reaction zone. The zone is ONLY meaningful with
confluence: structure, mapped liquidity, session level or volume area
when a real volume feed exists. Price touching the zone alone is never
an entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SIGNIFICANCE_ATR = 3.0   # range must be at least 3x ATR to count as significant


@dataclass
class RangeZone:
    high: float
    low: float
    zone_price: float          # high - range / 2.6
    zone_band: tuple[float, float]
    confluences: list[str] = field(default_factory=list)
    provenance: str = "DERIVED"
    source: str = "db:candles"
    note: str = "touching the zone alone is NOT an entry — confluence + reaction required"

    def to_dict(self) -> dict:
        return {
            "range_high": round(self.high, 6), "range_low": round(self.low, 6),
            "zone_price": round(self.zone_price, 6),
            "zone_band": [round(self.zone_band[0], 6), round(self.zone_band[1], 6)],
            "confluences": self.confluences,
            "provenance": self.provenance, "source": self.source, "note": self.note,
        }


def orion_range_zone(
    candles: list,
    atr: float | None = None,
    lookback: int = 40,
    liquidity_levels: list[float] | None = None,
    session_levels: dict[str, float] | None = None,
) -> RangeZone | None:
    """Build the ORION_RANGE_2_6 reaction zone from real stored bars.

    Returns None when no significant range exists in the lookback.
    """
    if len(candles) < 5:
        return None
    window = candles[-lookback:]
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    rng = hi - lo
    if rng <= 0:
        return None
    if atr is not None and atr > 0 and rng < SIGNIFICANCE_ATR * atr:
        return None

    zone = hi - rng / 2.6
    band_half = (atr * 0.25) if atr and atr > 0 else rng * 0.01

    confluences: list[str] = []
    tol = band_half * 2
    for lv in liquidity_levels or []:
        if abs(lv - zone) <= tol:
            confluences.append(f"liquidity pool @ {lv:.6g}")
            break
    for name, val in (session_levels or {}).items():
        if val is not None and abs(val - zone) <= tol:
            confluences.append(f"session level {name} @ {val:.6g}")
            break

    return RangeZone(high=hi, low=lo, zone_price=zone,
                     zone_band=(zone - band_half, zone + band_half),
                     confluences=confluences)
