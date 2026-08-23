"""MarketState — deterministic output contract of the Market Brain.

Every component carries its own provenance so downstream consumers (CIO,
debate engine, dashboards) can distinguish verified feeds from derived math
from unavailable inputs. The brain NEVER fabricates: an input that is missing
yields value=None with provenance=INSUFFICIENT_EVIDENCE-style detail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.provenance import ProvenanceType


class VolatilityState(StrEnum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class RiskMode(StrEnum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"


class RegimeLabel(StrEnum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ComponentScore(BaseModel):
    """A single scalar output with full audit trail."""

    name: str
    value: float | None  # None = not computable from available data
    scale: str  # "0_1" | "-1_1" | "raw"
    provenance: ProvenanceType
    detail: dict[str, Any] = Field(default_factory=dict)


class MarketState(BaseModel):
    scope: str  # asset symbol or "GLOBAL"
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    method: str = "market-brain-v1"

    # headline fields (spec §PRIORITY 6 example shape)
    regime: RegimeLabel = RegimeLabel.INSUFFICIENT_DATA
    risk_mode: RiskMode = RiskMode.RISK_ON
    volatility: VolatilityState = VolatilityState.NORMAL
    macro_score: float | None = None        # -1..1  (negative = stress)
    liquidity_score: float | None = None    #  0..1
    positioning_score: float | None = None  #  0..1  (None until real COT/OI feed)
    risk_score: float | None = None         # -1..1  (negative = elevated risk)
    momentum_score: float | None = None     # -1..1
    data_quality: float = 0.0               #  0..1

    components: list[ComponentScore] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        return d


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
