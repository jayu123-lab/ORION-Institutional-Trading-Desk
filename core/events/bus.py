"""Asynchronous in-process event bus.

Phase 1 uses a single-process bus (sufficient for api+monitor on one host).
Phase 2 will add RedisEventBus implementing the same EventBusLike interface.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from core.events.types import Event

logger = logging.getLogger("orion.events")

Handler = Callable[[Event], Awaitable[None]]


class EventBusLike:
    async def publish(self, event: Event) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def subscribe(self, pattern: str, handler: Handler) -> None:  # pragma: no cover
        raise NotImplementedError


class InMemoryEventBus(EventBusLike):
    """Pub/sub with wildcard patterns ('PRICE_*', '*'). Handlers run as tasks."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] | None = None
        self._loop_id: int | None = None
        self._task: asyncio.Task[None] | None = None
        self.published: list[Event] = []  # bounded ring below

    def _queue_for_current_loop(self) -> asyncio.Queue[Event]:
        """Recreate the queue if we are running on a different event loop
        (happens across TestClient instances / repeated asyncio.run calls)."""
        loop_id = id(asyncio.get_running_loop())
        if self._queue is None or self._loop_id != loop_id:
            self._queue = asyncio.Queue()
            self._loop_id = loop_id
        return self._queue

    def subscribe(self, pattern: str, handler: Handler) -> None:
        self._subs[pattern].append(handler)

    async def publish(self, event: Event) -> None:
        self.published.append(event)
        if len(self.published) > 1000:
            del self.published[:500]
        await self._queue_for_current_loop().put(event)
        logger.debug("published %s from %s", event.topic, event.source)

    async def _dispatch(self, event: Event) -> None:
        for pattern, handlers in list(self._subs.items()):
            if not fnmatch.fnmatchcase(event.topic, pattern):
                continue
            for handler in handlers:
                try:
                    await handler(event)
                except Exception:  # noqa: BLE001 - one bad subscriber must not kill the bus
                    logger.exception("subscriber error on %s", event.topic)

    async def run(self) -> None:
        queue = self._queue_for_current_loop()
        while True:
            event = await queue.get()
            await self._dispatch(event)
            queue.task_done()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self.run(), name="event-bus")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


_bus: InMemoryEventBus | None = None


def get_event_bus() -> InMemoryEventBus:
    global _bus
    if _bus is None:
        _bus = InMemoryEventBus()
    return _bus


async def emit(topic: str, payload: dict[str, Any], source: str) -> Event:
    bus = get_event_bus()
    ev = Event(topic=topic, payload=payload, source=source)
    await bus.publish(ev)
    return ev
