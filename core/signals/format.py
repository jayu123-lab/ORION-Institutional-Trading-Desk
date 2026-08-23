"""orion-signal-format — validated signal contract (spec PRIORITY 8).

Every trade signal must satisfy this schema. Missing critical fields or
incoherent numbers => SIGNAL_INVALID with explicit reasons. The validator is
pure: it never touches the network and never invents defaults.

Provenance rule (PRIORITY 2) applies: price_source / sources must carry real
provider references; a signal whose data_quality < 0.5 cannot be VALID.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

SIGNAL_STATES = ("VALID", "INVALID")

MIN_DATA_QUALITY = 0.5
RR_TOLERANCE = 0.15  # claimed R:R must match recomputed within 15%

CRITICAL_FIELDS = (
    "asset",
    "timestamp",
    "price",
    "price_source",
    "data_quality",
    "direction",
    "entry_type",
    "entry",
    "stop",
    "targets",
    "risk_reward",
    "confidence",
    "market_regime",
    "technical_reason",
    "fundamental_reason",
    "liquidity_reason",
    "positioning_reason",
    "news_risk",
    "invalidation",
    "no_trade_conditions",
    "sources",
)


class SignalState(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"


class OrionSignal(BaseModel):
    asset: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    price: float  # current market price when the signal was produced
    price_source: str  # provider name, e.g. 'polymarket-rtds' / 'yahoo'
    data_quality: float = Field(ge=0.0, le=1.0)
    direction: str  # LONG | SHORT | FLAT
    entry_type: str  # MARKET | LIMIT | STOP_LIMIT | CONDITIONAL
    entry: float
    stop: float
    targets: list[float] = Field(min_length=3)
    risk_reward: float  # claimed R:R vs TP1
    confidence: str  # LOW|MODERATE|HIGH|VERY HIGH
    market_regime: str  # TRENDING|RANGING|HIGH_VOLATILITY...
    technical_reason: str
    fundamental_reason: str  # may be "N/A — <reason>"
    liquidity_reason: str
    positioning_reason: str  # may be "NOT AVAILABLE — no feed"
    news_risk: str
    invalidation: str
    no_trade_conditions: list[str] = Field(min_length=1)
    sources: list[str] = Field(min_length=1)


class ValidationResult(BaseModel):
    state: SignalState
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.state == SignalState.VALID


def validate_signal(signal: OrionSignal) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    # --- structural completeness (pydantic enforces types; check N/A abuse)
    for f in CRITICAL_FIELDS:
        value = getattr(signal, f)
        if value is None:
            errors.append(f"missing critical field: {f}")

    # --- enum-ish fields
    if signal.direction not in ("LONG", "SHORT", "FLAT"):
        errors.append(f"invalid direction {signal.direction}")
    if signal.confidence not in ("LOW", "MODERATE", "HIGH", "VERY HIGH"):
        errors.append(f"invalid confidence {signal.confidence}")
    if signal.entry_type not in ("MARKET", "LIMIT", "STOP_LIMIT", "CONDITIONAL"):
        errors.append(f"invalid entry_type {signal.entry_type}")

    # --- honesty gates
    if signal.data_quality < MIN_DATA_QUALITY:
        errors.append(
            f"data_quality {signal.data_quality} below institutional minimum "
            f"{MIN_DATA_QUALITY}"
        )
    if signal.positioning_reason.startswith("NOT AVAILABLE") and signal.direction != "FLAT":
        warnings.append("directional signal without positioning data")

    # --- numeric coherence
    if signal.direction == "LONG":
        if signal.stop >= signal.entry:
            errors.append("LONG stop must be below entry")
        for i, tp in enumerate(signal.targets, 1):
            if tp <= signal.entry:
                errors.append(f"LONG target TP{i} ({tp}) must be above entry")
    elif signal.direction == "SHORT":
        if signal.stop <= signal.entry:
            errors.append("SHORT stop must be above entry")
        for i, tp in enumerate(signal.targets, 1):
            if tp >= signal.entry:
                errors.append(f"SHORT target TP{i} ({tp}) must be below entry")

    if signal.targets != sorted(signal.targets):
        warnings.append("targets not in ascending order")

    if signal.entry > 0 and signal.stop != signal.entry:
        rr_tp1 = abs(signal.targets[0] - signal.entry) / abs(signal.entry - signal.stop)
        if abs(rr_tp1 - signal.risk_reward) / max(rr_tp1, 1e-9) > RR_TOLERANCE:
            errors.append(
                f"claimed R:R {signal.risk_reward:.2f} does not match recomputed "
                f"TP1 R:R {rr_tp1:.2f}"
            )

    # --- provenance sanity
    if not signal.sources:
        errors.append("sources empty — every signal needs provider references")

    state = SignalState.INVALID if errors else SignalState.VALID
    return ValidationResult(state=state, errors=errors, warnings=warnings)


def validate_or_invalid(signal_dict: dict) -> dict:
    """Convenience for API/LLM paths: parse raw dict → validation payload."""
    try:
        sig = OrionSignal(**signal_dict)
    except Exception as exc:  # pydantic ValidationError
        missing = [
            k
            for k in CRITICAL_FIELDS
            if k not in signal_dict or signal_dict[k] in (None, "", [])
        ]
        return {
            "state": "SIGNAL_INVALID",
            "errors": [f"schema violation: {exc}"],
            "missing_critical": missing,
        }
    result = validate_signal(sig)
    payload = {"state": f"SIGNAL_{result.state.value}", "errors": result.errors,
               "warnings": result.warnings}
    return payload
