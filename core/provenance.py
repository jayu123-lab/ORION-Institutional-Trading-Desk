"""Source provenance taxonomy (spec §28 extension).

Every institutional datum carries provenance. Rules:

- VERIFIED   → read directly from a live provider feed (exchange/broker/API).
- DERIVED    → computed deterministically from verified inputs (math on OI,
               candles, spreads). Method must be declared.
- INFERRED   → interpretation produced by an LLM or heuristic judgement.
- SIMULATED  → paper trading, backtests or synthetic data.

Hard rule: DERIVED / INFERRED / SIMULATED must NEVER be presented to the user
as VERIFIED. `presentation_label` enforces the visible tag.
"""

from __future__ import annotations

from enum import StrEnum


class ProvenanceType(StrEnum):
    VERIFIED = "VERIFIED"
    DERIVED = "DERIVED"
    INFERRED = "INFERRED"
    SIMULATED = "SIMULATED"


class VerificationState(StrEnum):
    """Audit/verification outcome for claims and datasets."""

    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING_DATA = "CONFLICTING_DATA"
    STALE_DATA = "STALE_DATA"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# provenance levels that are safe to show without an explicit caveat
PRESENTABLE_AS_VERIFIED = frozenset({ProvenanceType.VERIFIED})


def presentation_label(provenance: ProvenanceType) -> str:
    """User-facing tag. Non-verified data always shows its true nature."""
    if provenance == ProvenanceType.VERIFIED:
        return "VERIFIED"
    return f"{provenance.value} (not verified)"


def can_present_as_verified(provenance: ProvenanceType) -> bool:
    return provenance in PRESENTABLE_AS_VERIFIED


def provenance_for_source_kind(kind: str) -> ProvenanceType:
    """Map a source kind to its provenance level.

    kind: 'live_feed' | 'derived_calc' | 'llm_interpretation' | 'simulated'
    """
    mapping = {
        "live_feed": ProvenanceType.VERIFIED,
        "derived_calc": ProvenanceType.DERIVED,
        "llm_interpretation": ProvenanceType.INFERRED,
        "simulated": ProvenanceType.SIMULATED,
    }
    if kind not in mapping:
        raise ValueError(f"unknown source kind: {kind}")
    return mapping[kind]
