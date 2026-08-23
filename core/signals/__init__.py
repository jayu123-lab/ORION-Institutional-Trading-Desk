"""Signal contract (spec PRIORITY 8)."""

from core.signals.format import (
    OrionSignal,
    SignalState,
    ValidationResult,
    validate_or_invalid,
    validate_signal,
)

__all__ = [
    "OrionSignal",
    "SignalState",
    "ValidationResult",
    "validate_or_invalid",
    "validate_signal",
]
