"""MarketDataProvider contract.

Every datum declares its quality (spec §28). A provider that cannot answer
must raise/return nothing — never fabricate. Implementations must document the
official API docs URL and verification date in their docstring.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from core.provenance import ProvenanceType


class DataStatus(StrEnum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    SIMULATED = "SIMULATED"


class DataQuality(BaseModel):
    provider: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latency_ms: int | None = None
    quality: Literal["A", "B", "C", "UNKNOWN"] = "UNKNOWN"
    status: DataStatus = DataStatus.LIVE
    provenance: ProvenanceType | None = None


class Quote(BaseModel):
    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    ts_source: datetime  # exchange-reported time
    quality: DataQuality


class Candle(BaseModel):
    symbol: str
    timeframe: str  # M1 M5 M15 H1 H4 D1
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    ts_open: datetime
    quality: DataQuality


def is_stale(ts_source: datetime, staleness_sec: int, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    ts = ts_source if ts_source.tzinfo else ts_source.replace(tzinfo=UTC)
    return (now - ts).total_seconds() > staleness_sec


class MarketDataProvider(ABC):
    """Base class for all data adapters."""

    name: str = "base"

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Return current quote or raise ProviderUnavailable."""

    @abstractmethod
    async def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        """Return historical candles oldest→newest or raise ProviderUnavailable."""


class ProviderUnavailable(Exception):
    pass
