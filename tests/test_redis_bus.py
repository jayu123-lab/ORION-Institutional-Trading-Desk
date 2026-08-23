"""Tests for RedisEventBus factory + fallback (PRIORITY 10).

Integration with a live server runs only when REDIS_URL_TEST is set and
reachable; otherwise the fallback contract is what's verified.
"""

import asyncio
import os

import pytest

from core.events.bus import InMemoryEventBus
from core.events.redis_bus import RedisEventBus, build_event_bus
from core.events.types import PRICE_UPDATE, Event


@pytest.mark.asyncio
async def test_empty_url_returns_inmemory():
    bus = await build_event_bus("")
    assert isinstance(bus, InMemoryEventBus)


@pytest.mark.asyncio
async def test_unreachable_redis_falls_back(monkeypatch):
    monkeypatch.setattr(
        "core.events.redis_bus.RedisEventBus.start",
        lambda self: _raise(),
    )
    bus = await build_event_bus("redis://127.0.0.1:1/0")
    assert isinstance(bus, InMemoryEventBus)


async def _raise():
    raise ConnectionError("no redis here")


@pytest.mark.skipif(not os.environ.get("REDIS_URL_TEST"), reason="no live Redis configured")
@pytest.mark.asyncio
async def test_live_pubsub_roundtrip():
    received: list[Event] = []
    ready = asyncio.Event()

    async def handler(event: Event) -> None:
        received.append(event)
        ready.set()

    bus = await build_event_bus(os.environ["REDIS_URL_TEST"])
    assert isinstance(bus, RedisEventBus)
    try:
        bus.subscribe(PRICE_UPDATE, handler)
        # give the psubscribe task a moment to register
        await asyncio.sleep(0.3)
        await bus.publish(Event(topic=PRICE_UPDATE, payload={"s": "XAUUSD"}, source="test"))
        await asyncio.wait_for(ready.wait(), timeout=5)
        assert received[0].payload["s"] == "XAUUSD"
    finally:
        if isinstance(bus, RedisEventBus):
            await bus.close()


def test_event_types_complete():
    from core.events import types as t

    required = {
        "PRICE_UPDATE", "NEWS_EVENT", "MACRO_EVENT", "REGIME_CHANGE",
        "FEED_DIVERGENCE", "SIGNAL_CREATED", "RISK_LIMIT", "TRADE_PROPOSED",
        "TRADE_APPROVED", "TRADE_REJECTED", "ORDER_UPDATE", "POSITION_UPDATE",
        "DATA_STALE",
    }
    assert required <= set(t.ALL_EVENTS)
