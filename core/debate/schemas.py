"""Formal debate schemas (spec PRIORITY 7).

AgentOpinionSchema mirrors the spec contract exactly; DeskDebate is the full
transcript of one desk convening, including the audit layer verdicts and the
CIO synthesis. Dissenting opinions are NEVER hidden.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

BIAS_VALUES = ("LONG", "SHORT", "WAIT", "NEUTRAL")
CONFIDENCE_VALUES = ("LOW", "MODERATE", "HIGH", "VERY HIGH")


class DataSourceRefModel(BaseModel):
    symbol: str
    provider: str | None = None
    ts: str | None = None  # ISO-8601 of the underlying datum
    price: float | None = None


class AgentOpinionSchema(BaseModel):
    agent: str
    asset: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bias: str  # LONG|SHORT|WAIT|NEUTRAL
    confidence: str  # LOW|MODERATE|HIGH|VERY HIGH
    strength: float = Field(ge=0, le=100)  # numeric conviction for consensus
    time_horizon: str  # INTRADAY|SWING|POSITION|N/A
    arguments: list[str]
    counter_arguments: list[str]
    required_conditions: list[str]
    invalidation: str
    data_sources: list[DataSourceRefModel] = Field(default_factory=list)
    data_quality: float | None = None  # 0..1 if computable

    # filled by the audit layer post-hoc
    verification_state: str | None = None  # VerificationState value

    def validate_bias(self) -> None:
        if self.bias not in BIAS_VALUES:
            raise ValueError(f"invalid bias {self.bias}")
        if self.confidence not in CONFIDENCE_VALUES:
            raise ValueError(f"invalid confidence {self.confidence}")


class CioSynthesis(BaseModel):
    bias_label: str  # consensus label (internal tag, never advice)
    scenario: str
    key_conditions: list[str]
    dissent_summary: str
    provenance: str = "INFERRED"  # synthesis is interpretation, not verified fact


class RiskConstraints(BaseModel):
    verdict: str | None = None  # latest risk snapshot verdict if any
    notes: list[str] = Field(default_factory=list)


class DeskDebate(BaseModel):
    debate_id: str
    asset: str
    convened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    market_state: dict[str, Any]
    opinions: list[AgentOpinionSchema]
    consensus: dict[str, Any]
    risk_constraints: RiskConstraints
    audit_overall: str
    discrepancies: list[str] = Field(default_factory=list)
    cio_synthesis: CioSynthesis
