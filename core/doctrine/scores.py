"""ORION INSTITUTIONAL BIAS SCORE (P11) and TRADE QUALITY SCORE (P12).

Two SEPARATE instruments:
- BiasScore 0-100: directional context. NEVER an entry signal.
- TradeQualityScore 0-100: is there a tradeable situation NOW?

Correct output shape example:
    BIAS: BULLISH 79
    TRADE QUALITY: 31
    DECISION: WAIT
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_BIAS_WEIGHTS: dict[str, float] = {
    "macro": 0.20,
    "cross_asset": 0.15,
    "positioning": 0.15,
    "regime": 0.15,
    "liquidity": 0.10,
    "structure": 0.15,
    "news_event_risk": 0.10,
}


def classify_bias(total: float) -> str:
    if total <= 30:
        return "STRONG_BEARISH"
    if total <= 45:
        return "BEARISH"
    if total <= 54:
        return "NEUTRAL"
    if total <= 69:
        return "BULLISH"
    return "STRONG_BULLISH"


@dataclass
class ScoreResult:
    total: int
    subscores: dict[str, float] = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)
    band: str | None = None       # bias score only
    weights_used: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "subscores": {k: round(v, 1) for k, v in self.subscores.items()},
            "missing_inputs": self.missing_inputs,
            "band": self.band,
            "weights_used": {k: round(v, 3) for k, v in self.weights_used.items()},
            "provenance": "DERIVED",
        }


def compute_bias_score(
    components: dict[str, dict],   # name -> {"value": 0..100} or {} when unavailable
    weights: dict[str, float] | None = None,
) -> ScoreResult:
    """Weighted 0-100 bias. Missing components are excluded and REPORTED;
    remaining weights are renormalized so the score never pretends data
    that is not there."""
    w = dict(weights or DEFAULT_BIAS_WEIGHTS)
    subscores: dict[str, float] = {}
    missing: list[str] = []
    weight_sum = 0.0
    weighted = 0.0
    for name, spec in w.items():
        block = components.get(name) or {}
        val = block.get("value")
        if not isinstance(val, (int, float)) or not 0 <= val <= 100:
            missing.append(name)
            continue
        subscores[name] = float(val)
        weighted += float(val) * spec
        weight_sum += spec
    if weight_sum <= 0:
        return ScoreResult(50, {}, sorted(missing), "NEUTRAL", {})
    renorm = {k: v / weight_sum for k, v in w.items() if k in subscores}
    total = round(weighted / weight_sum)
    return ScoreResult(int(total), subscores, sorted(missing), classify_bias(total), renorm)


# --------------------------------------------------------------------- P12
DEFAULT_TQ_WEIGHTS: dict[str, float] = {
    "location": 0.15,
    "reaction": 0.15,
    "confirmation": 0.15,
    "rr": 0.12,
    "liquidity_conditions": 0.08,
    "data_freshness": 0.10,
    "event_risk": 0.10,
    "extension": 0.10,
    "risk_state": 0.05,
}


def compute_trade_quality(inputs: dict[str, dict]) -> ScoreResult:
    """inputs: component name -> {"score": 0..100}. Missing inputs are reported.

    Component scorers (rules of thumb, all deterministic):
      location          distance to mapped level/zone in ATRs
      reaction          reaction observed at level?
      confirmation      structure shift / displacement confirmed?
      rr                reward:risk ratio
      liquidity_conditions spread/trading conditions acceptable?
      data_freshness    quote freshness state
      event_risk        high-impact event imminent?
      extension         ATR extension from reference (no-chase rule)
      risk_state        desk risk verdict
    """
    subscores: dict[str, float] = {}
    missing: list[str] = []
    weighted = 0.0
    weight_sum = 0.0
    for name, spec in DEFAULT_TQ_WEIGHTS.items():
        block = inputs.get(name) or {}
        val = block.get("score")
        if not isinstance(val, (int, float)) or not 0 <= val <= 100:
            missing.append(name)
            continue
        subscores[name] = float(val)
        weighted += float(val) * spec
        weight_sum += spec
    if weight_sum <= 0:
        return ScoreResult(0, {}, sorted(missing), None, {})
    renorm = {k: v / weight_sum for k, v in DEFAULT_TQ_WEIGHTS.items() if k in subscores}
    return ScoreResult(round(weighted / weight_sum), subscores, sorted(missing),
                       None, renorm)


def rr_score(rr: float | None) -> float:
    if rr is None:
        raise ValueError("rr required")
    if rr < 2:
        return max(0.0, rr * 20.0)     # 2:1 -> 40
    return min(100.0, 40.0 + (rr - 2) * 30.0)


def extension_score(extension_atr: float | None) -> float:
    if extension_atr is None:
        raise ValueError("extension_atr required")
    if extension_atr <= 0.5:
        return 90.0
    if extension_atr >= MAX_EXT:
        return 10.0
    return max(10.0, 90.0 - (extension_atr - 0.5) * (80.0 / (MAX_EXT - 0.5)))


MAX_EXT = 2.5


def freshness_score(status: str | None) -> float:
    return {"LIVE": 95.0, "STALE": 25.0, "DISCONNECTED": 5.0}.get((status or "").upper(),
                                                                  40.0)


def risk_state_score(verdict: str | None) -> float:
    return {"GREEN_LIGHT": 90.0, "CAUTION": 45.0, "RED_LIGHT": 0.0}.get(
        (verdict or "").upper(), 40.0)
