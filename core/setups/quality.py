"""Critical-input gates and score caps for scanner candidates."""

from __future__ import annotations

from dataclasses import dataclass

CRITICAL_INPUTS: dict[str, tuple[str, ...]] = {
    "LIQUIDITY_SWEEP_REVERSAL": (
        "price",
        "liquidity_level",
        "sweep_evidence",
        "reaction_evidence",
        "atr",
        "adx",
        "structure",
        "entry_zone",
        "entry",
        "invalidation",
        "target",
        "rr",
        "fresh_data",
    ),
}


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    state: str
    missing: tuple[str, ...]
    score_cap: float
    reasons: tuple[str, ...]


class SetupQualityGate:
    def evaluate(self, setup: str, inputs: dict, score: float) -> QualityGateResult:
        required = CRITICAL_INPUTS.get(setup, ())
        missing = tuple(name for name in required if inputs.get(name) in (None, False, ""))
        cap = 100.0
        reasons: list[str] = []
        if inputs.get("fresh_data") is False:
            cap = min(cap, 39.0)
            reasons.append("stale data caps score at 39")
        if inputs.get("rr") is None:
            cap = min(cap, 49.0)
            reasons.append("R:R unavailable caps score at 49")
        elif float(inputs["rr"]) < 2.0:
            cap = min(cap, 49.0)
            reasons.append("R:R below ORION minimum 2.0")
        if not inputs.get("reaction_evidence"):
            cap = min(cap, 59.0)
            reasons.append("reaction not confirmed caps score at 59")
        if setup == "LIQUIDITY_SWEEP_REVERSAL" and inputs.get("adx") is None:
            cap = min(cap, 59.0)
            reasons.append("ADX insufficient for this setup")
        capped = min(score, cap)
        if missing:
            state = (
                "INSUFFICIENT_DATA"
                if any(name in missing for name in ("price", "atr", "adx", "fresh_data"))
                else "WATCHING"
            )
        elif float(inputs.get("rr", 0)) < 2.0:
            state = "REJECTED"
        else:
            state = "ELIGIBLE"
        return QualityGateResult(
            not missing and state == "ELIGIBLE", state, missing, capped, tuple(reasons)
        )
