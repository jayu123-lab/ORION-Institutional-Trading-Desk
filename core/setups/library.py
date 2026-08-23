from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

SETUP_NAMES = (
    "LIQUIDITY_SWEEP_REVERSAL",
    "BREAKOUT_RETEST_CONTINUATION",
    "TREND_PULLBACK",
    "VWAP_RECLAIM",
    "VWAP_REJECTION",
    "FAILED_AUCTION",
    "RANGE_EXTREME_REVERSAL",
    "ORION_RANGE_2_6_REACTION",
    "HIGH_VOLUME_BREAKOUT",
    "ABSORPTION_REVERSAL",
)
STATES = ("WATCHING", "ARMED", "CONFIRMED", "INVALIDATED", "CANCELLED")


@dataclass
class SetupCandidate:
    setup_id: str
    symbol: str
    setup: str
    direction: str
    state: str = "WATCHING"
    score: float = 0.0
    features: dict = field(default_factory=dict)
    reason: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {**self.__dict__, "updated_at": self.updated_at.isoformat()}


def transition(
    candidate: SetupCandidate,
    *,
    in_zone: bool,
    reaction: bool,
    valid: bool = True,
    score: float | None = None,
) -> SetupCandidate:
    """Deterministic state machine; confirmation requires reaction and valid data."""
    if not valid:
        candidate.state = "INVALIDATED"
    elif candidate.state == "WATCHING" and in_zone:
        candidate.state = "ARMED"
    elif candidate.state == "ARMED" and reaction and (score or candidate.score) >= 82:
        candidate.state = "CONFIRMED"
    elif candidate.state in {"WATCHING", "ARMED"} and not in_zone:
        candidate.state = "CANCELLED" if candidate.state == "ARMED" else "WATCHING"
    if score is not None:
        candidate.score = score
    candidate.updated_at = datetime.now(UTC)
    return candidate


def opportunity_score(subscores: dict[str, float | None], data_quality: str = "A") -> dict:
    weights = {
        "context": 0.10,
        "location": 0.10,
        "liquidity": 0.10,
        "volume": 0.08,
        "order_flow": 0.08,
        "structure": 0.10,
        "trend_energy": 0.08,
        "volatility": 0.07,
        "cross_asset": 0.07,
        "news": 0.05,
        "statistical_edge": 0.08,
        "rr": 0.06,
        "data_quality": 0.03,
    }
    available = {k: v for k, v in subscores.items() if isinstance(v, (int, float))}
    total_weight = sum(weights[k] for k in available if k in weights)
    total = (
        round(
            sum(float(available[k]) * weights[k] for k in available if k in weights) / total_weight,
            2,
        )
        if total_weight
        else 0.0
    )
    return {
        "total": total,
        "subscores": subscores,
        "weights_used": {k: weights[k] / total_weight for k in available if k in weights},
        "data_quality": data_quality,
    }
