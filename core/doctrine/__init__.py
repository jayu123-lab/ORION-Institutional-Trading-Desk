"""ORION Trading Doctrine — shared source of truth for every desk agent."""

from core.doctrine.doctrine import (
    HIERARCHY,
    MIN_RR,
    OPERATING_SEQUENCE,
    DoctrineDecision,
    ORIONTradingDoctrine,
)
from core.doctrine.scores import (
    classify_bias,
    compute_bias_score,
    compute_trade_quality,
)

__all__ = [
    "HIERARCHY",
    "MIN_RR",
    "OPERATING_SEQUENCE",
    "DoctrineDecision",
    "ORIONTradingDoctrine",
    "classify_bias",
    "compute_bias_score",
    "compute_trade_quality",
]
