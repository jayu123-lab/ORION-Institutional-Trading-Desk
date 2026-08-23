"""Point-in-time dataset collection helpers."""

from __future__ import annotations

from datetime import datetime

from core.memory.models import FeatureDatasetRow


def dataset_row(*, asset: str, timeframe: str, timestamp: datetime, features: dict,
                setup: str | None = None, trigger: str | None = None) -> FeatureDatasetRow:
    """Create a feature row from information available at `timestamp` only."""
    return FeatureDatasetRow(timestamp=timestamp, asset=asset, timeframe=timeframe,
                             features=dict(features), setup=setup, trigger=trigger)
