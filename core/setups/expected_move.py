"""Historical expected excursion; no distribution means no numeric estimate."""

from __future__ import annotations

from statistics import median


def expected_move(excursions: list[float], minimum_sample: int = 30) -> dict:
    if len(excursions) < minimum_sample:
        return {
            "status": "INSUFFICIENT_SAMPLE",
            "sample_size": len(excursions),
            "expected_move_25": None,
            "expected_move_50": None,
            "expected_move_75": None,
        }
    values = sorted(excursions)
    return {
        "status": "CALCULATED",
        "sample_size": len(values),
        "expected_move_25": values[len(values) // 4],
        "expected_move_50": median(values),
        "expected_move_75": values[(len(values) * 3) // 4],
    }
