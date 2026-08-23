"""Market Brain — deterministic market-state computation (spec PRIORITY 6).

No LLM here. Everything is reproducible math with declared provenance.
"""

from core.market_brain.brain import MarketBrain
from core.market_brain.engines import (
    liquidity_score,
    macro_score,
    momentum_score,
    pearson,
    rolling_correlation,
    zscore,
)
from core.market_brain.state import (
    ComponentScore,
    MarketState,
    RegimeLabel,
    RiskMode,
    VolatilityState,
)

__all__ = [
    "ComponentScore",
    "MarketBrain",
    "MarketState",
    "RegimeLabel",
    "RiskMode",
    "VolatilityState",
    "liquidity_score",
    "macro_score",
    "momentum_score",
    "pearson",
    "rolling_correlation",
    "zscore",
]
