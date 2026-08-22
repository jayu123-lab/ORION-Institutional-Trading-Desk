from __future__ import annotations

import pytest

from core.events.bus import get_event_bus
from core.events.types import Event


@pytest.fixture()
def fresh_bus():
    from core.events import bus as bus_mod

    old = bus_mod._bus
    bus_mod._bus = None
    yield get_event_bus()
    bus_mod._bus = old


async def test_publish_subscribe_exact_topic(fresh_bus):
    seen: list[Event] = []

    async def handler(ev: Event) -> None:
        seen.append(ev)

    fresh_bus.subscribe("PRICE_UPDATE", handler)
    await fresh_bus.publish(Event("PRICE_UPDATE", {"symbol": "XAUUSD"}, "test"))
    await fresh_bus._dispatch(fresh_bus.published[-1])
    assert len(seen) == 1
    assert seen[0].payload["symbol"] == "XAUUSD"


async def test_wildcard_subscription(fresh_bus):
    seen: list[str] = []

    async def handler(ev: Event) -> None:
        seen.append(ev.topic)

    fresh_bus.subscribe("*", handler)
    await fresh_bus.publish(Event("NEWS_EVENT", {}, "t"))
    await fresh_bus.publish(Event("RISK_LIMIT", {}, "t"))
    await fresh_bus._dispatch(fresh_bus.published[-2])
    await fresh_bus._dispatch(fresh_bus.published[-1])
    assert sorted(seen) == ["NEWS_EVENT", "RISK_LIMIT"]


async def test_handler_error_does_not_break_bus(fresh_bus):
    calls = {"ok": 0}

    async def bad(ev: Event) -> None:
        raise RuntimeError("boom")

    async def good(ev: Event) -> None:
        calls["ok"] += 1

    fresh_bus.subscribe("*", bad)
    fresh_bus.subscribe("*", good)
    ev = Event("ALERT_TRIGGERED", {}, "t")
    await fresh_bus.publish(ev)
    await fresh_bus._dispatch(ev)
    assert calls["ok"] == 1
