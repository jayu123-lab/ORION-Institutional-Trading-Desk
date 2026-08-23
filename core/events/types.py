"""Domain event types for the ORION event bus."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# Canonical event names (spec §32)
PRICE_UPDATE = "PRICE_UPDATE"
NEWS_EVENT = "NEWS_EVENT"
MACRO_EVENT = "MACRO_EVENT"
LIQUIDITY_EVENT = "LIQUIDITY_EVENT"
SIGNAL_CREATED = "SIGNAL_CREATED"
TRADE_PROPOSED = "TRADE_PROPOSED"
TRADE_APPROVED = "TRADE_APPROVED"
TRADE_REJECTED = "TRADE_REJECTED"
ORDER_UPDATE = "ORDER_UPDATE"
POSITION_UPDATE = "POSITION_UPDATE"
RISK_LIMIT = "RISK_LIMIT"
FEED_DISCONNECTED = "FEED_DISCONNECTED"
FEED_CONNECTED = "FEED_CONNECTED"
FEED_DIVERGENCE = "FEED_DIVERGENCE"
REGIME_CHANGE = "REGIME_CHANGE"
DATA_STALE = "DATA_STALE"
ALERT_TRIGGERED = "ALERT_TRIGGERED"

ALL_EVENTS: tuple[str, ...] = (
    PRICE_UPDATE,
    NEWS_EVENT,
    MACRO_EVENT,
    LIQUIDITY_EVENT,
    SIGNAL_CREATED,
    TRADE_PROPOSED,
    TRADE_APPROVED,
    TRADE_REJECTED,
    ORDER_UPDATE,
    POSITION_UPDATE,
    RISK_LIMIT,
    FEED_DISCONNECTED,
    FEED_CONNECTED,
    FEED_DIVERGENCE,
    REGIME_CHANGE,
    DATA_STALE,
    ALERT_TRIGGERED,
)


@dataclass(frozen=True, slots=True)
class Event:
    topic: str
    payload: dict[str, Any]
    source: str
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"topic": self.topic, "payload": self.payload, "source": self.source, "ts": self.ts}
