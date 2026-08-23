"""Calibratable statistics helpers with minimum-sample and temporal guards."""

from __future__ import annotations

from dataclasses import dataclass


def sample_confidence(sample_size: int) -> str:
    if sample_size < 30:
        return "INSUFFICIENT_SAMPLE"
    if sample_size < 100:
        return "LOW_CONFIDENCE"
    if sample_size < 500:
        return "MODERATE"
    return "ROBUST"


def conditional_probability(
    wins: int, losses: int, prior: tuple[float, float] = (1.0, 1.0)
) -> dict:
    """Posterior mean and interval proxy using a Beta prior, not additive scores."""
    alpha, beta = prior[0] + max(0, wins), prior[1] + max(0, losses)
    total = alpha + beta
    return {
        "probability": round(alpha / total * 100, 2),
        "sample_size": wins + losses,
        "confidence": sample_confidence(wins + losses),
        "prior": list(prior),
    }


def temporal_split(rows: list, train_ratio: float = 0.6, validation_ratio: float = 0.2) -> dict:
    """Split already chronological rows without shuffle or future leakage."""
    if (
        not 0 < train_ratio < 1
        or not 0 < validation_ratio < 1
        or train_ratio + validation_ratio >= 1
    ):
        raise ValueError("ratios must leave a non-empty forward-test segment")
    first = int(len(rows) * train_ratio)
    second = first + int(len(rows) * validation_ratio)
    return {"train": rows[:first], "validate": rows[first:second], "forward_test": rows[second:]}


@dataclass(frozen=True)
class SetupOutcome:
    setup: str
    sample_size: int
    wins: int
    losses: int
    expectancy_r: float | None
