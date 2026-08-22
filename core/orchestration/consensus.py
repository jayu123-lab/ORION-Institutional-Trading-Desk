"""Weighted consensus (spec §34): NOT majority voting.

Weights are configurable per role and vary by asset class / market regime
(config/consensus_weights.json). Dissent is surfaced, not averaged away.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "_default": {
        "macro": 0.20,
        "technical": 0.15,
        "liquidity": 0.20,
        "order_flow": 0.20,
        "news": 0.10,
        "quant": 0.15,
    },
    "metal": {
        "macro": 0.25,
        "technical": 0.15,
        "liquidity": 0.25,
        "order_flow": 0.20,
        "news": 0.05,
        "quant": 0.10,
    },
    "crypto": {
        "macro": 0.10,
        "technical": 0.15,
        "liquidity": 0.25,
        "order_flow": 0.30,
        "news": 0.10,
        "quant": 0.10,
    },
}

STANCE_SIGN = {"LONG": 1.0, "SHORT": -1.0, "WAIT": 0.0, "NEUTRAL": 0.0, "NO_ENTRY": 0.0}


@dataclass(frozen=True)
class ConsensusInput:
    agent: str  # e.g. "metals-analyst"
    role: str  # weight key: macro|technical|liquidity|order_flow|news|quant|risk
    stance: str  # LONG|SHORT|WAIT|...
    strength: float  # 0..100


@dataclass(frozen=True)
class ConsensusResult:
    score: float  # -1..+1 weighted directional score
    label: str  # STRONG BUY BIAS ... STRONG SELL BIAS (internal tag only)
    agreement: float  # 0..1 — low value signals visible dissent
    dissent: list[tuple[str, str]]  # (agent, stance) that oppose consensus
    weights_used: dict[str, float]
    n_inputs: int

    @property
    def has_dissent(self) -> bool:
        return len(self.dissent) > 0


def load_weights(path: Path | None = None, asset_class: str | None = None) -> dict[str, float]:
    data = DEFAULT_WEIGHTS
    if path and path.exists():
        try:
            data = {**DEFAULT_WEIGHTS, **json.loads(path.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            pass  # fall back to defaults; config errors must not crash the desk
    return data.get(asset_class or "_default") or data["_default"]


def compute_consensus(
    inputs: list[ConsensusInput],
    asset_class: str | None = None,
    weights_path: Path | None = None,
) -> ConsensusResult:
    if not inputs:
        return ConsensusResult(0.0, "NEUTRAL", 0.0, [], {}, 0)

    weights = load_weights(weights_path, asset_class)
    total_w = 0.0
    acc = 0.0
    signed = []
    used: dict[str, float] = {}
    for item in inputs:
        w = weights.get(item.role, 0.05)
        s = STANCE_SIGN.get(item.stance.upper(), 0.0)
        acc += w * (item.strength / 100.0) * s
        total_w += w
        signed.append((item.agent, item.stance, item.strength * s))
        used[item.role] = round(w, 3)

    score = acc / total_w if total_w > 0 else 0.0

    # agreement: share of directional participants aligned with the score sign
    directional = [(a, st, c) for a, st, c in signed if c != 0]
    if directional:
        aligned = sum(1 for _, _, c in directional if (c > 0) == (score >= 0))
        agreement = aligned / len(directional)
    else:
        agreement = 1.0

    dissent = [(a, st) for a, st, c in directional if (c > 0) != (score >= 0)]

    if score >= 0.5:
        label = "STRONG BUY BIAS"
    elif score >= 0.2:
        label = "BUY BIAS"
    elif score <= -0.5:
        label = "STRONG SELL BIAS"
    elif score <= -0.2:
        label = "SELL BIAS"
    else:
        label = "NEUTRAL"

    return ConsensusResult(
        score=round(score, 3),
        label=label,
        agreement=round(agreement, 2),
        dissent=dissent,
        weights_used=used,
        n_inputs=len(inputs),
    )
