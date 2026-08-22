"""Confidence engine (spec §35): LOW/MODERATE/HIGH/VERY HIGH + optional numeric.

Calibration tracking: predictions are stored with their label/probability and
later compared against outcomes so the desk can measure whether "70%" means ~70%.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ConfidenceLabel = Literal["LOW", "MODERATE", "HIGH", "VERY HIGH"]

LABEL_BANDS: dict[ConfidenceLabel, tuple[float, float]] = {
    "LOW": (0.0, 40.0),
    "MODERATE": (40.0, 60.0),
    "HIGH": (60.0, 80.0),
    "VERY HIGH": (80.0, 100.0),
}


def label_to_probability(label: str) -> float:
    """Mid-point of the band — avoids false precision."""
    bands = {"LOW": 20.0, "MODERATE": 50.0, "HIGH": 70.0, "VERY HIGH": 90.0}
    return bands.get(label.upper(), 0.0)


def probability_to_label(p: float) -> ConfidenceLabel:
    for label, (lo, hi) in LABEL_BANDS.items():
        if lo <= p < hi or (label == "VERY HIGH" and p == 100):
            return label
    return "LOW"


@dataclass(frozen=True)
class Prediction:
    subject: str  # e.g. "XAUUSD>2400 before Friday"
    probability: float  # declared 0..100
    ts: datetime


@dataclass(frozen=True)
class Outcome:
    occurred: bool
    ts: datetime


@dataclass(frozen=True)
class CalibrationReport:
    n_predictions: int
    mean_declared: float
    hit_rate: float
    bias_pp: float  # hit_rate - mean_declared; positive = under-confident

    @property
    def calibrated(self) -> bool:
        return abs(self.bias_pp) <= 10.0


class ConfidenceEngine:
    def __init__(self) -> None:
        self._history: list[tuple[Prediction, Outcome | None]] = []

    def register(self, prediction: Prediction) -> None:
        self._history.append((prediction, None))

    def resolve(self, subject: str, outcome: Outcome) -> bool:
        for i, (pred, out) in enumerate(self._history):
            if pred.subject == subject and out is None:
                self._history[i] = (pred, outcome)
                return True
        return False

    def calibration(self) -> CalibrationReport | None:
        resolved = [(p, o) for p, o in self._history if o is not None]
        if not resolved:
            return None
        hits = sum(1 for _, o in resolved if o.occurred)  # type: ignore[union-attr]
        n = len(resolved)
        mean_declared = sum(p.probability for p, _ in resolved) / n
        hit_rate = hits / n * 100
        return CalibrationReport(
            n_predictions=n,
            mean_declared=round(mean_declared, 1),
            hit_rate=round(hit_rate, 1),
            bias_pp=round(hit_rate - mean_declared, 1),
        )
