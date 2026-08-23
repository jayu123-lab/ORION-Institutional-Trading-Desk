"""RedisEventBus — cross-process event bus with controlled fallback.

Implements the same EventBusLike contract as InMemoryEventBus:
- subscribe(pattern, handler)  (fnmatch wildcards)
- await publish(event)

Transport: Redis pub/sub, one channel per exact topic + a wildcard channel
for pattern subscribers. Handlers run as awaited tasks inside the dispatch
loop, mirroring InMemoryEventBus semantics.

Fallback rule: construction NEVER raises. If Redis is unreachable the bus
degrades to InMemoryEventBus and logs a warning — a local desk keeps working.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging

from core.events.bus import EventBusLike, InMemoryEventBus
from core.events.types import Event

logger = logging.getLogger("orion.events.redis")

CHANNEL_PREFIX = "orion:events:"


class RedisEventBus(EventBusLike):
    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        self._subs: dict[str, list] = {}  # pattern -> handlers
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        """Connect, register the dispatch loop. Raises on unreachable Redis."""
        await self._redis.ping()
        self._task = asyncio.get_running_loop().create_task(self._listen(), name="redis-bus")

    async def close(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        try:
            await self._pubsub.close()
            await self._redis.close()
        except Exception:  # noqa: BLE001 - shutdown must be quiet
            pass

    def subscribe(self, pattern: str, handler) -> None:
        self._subs.setdefault(pattern, []).append(handler)
        # psubscribe is idempotent per pattern; fire-and-forget registration
        asyncio.get_running_loop().create_task(self._ensure_psubscribe(pattern))

    async def _ensure_psubscribe(self, pattern: str) -> None:
        try:
            await self._pubsub.psubscribe(pattern)
        except Exception:  # noqa: BLE001
            logger.exception("psubscribe failed for %s", pattern)

    async def publish(self, event: Event) -> None:
        payload = json.dumps(event.to_dict())
        await self._redis.publish(CHANNEL_PREFIX + event.topic, payload)

    def _match(self, topic: str) -> list:
        handlers = []
        for pattern, hs in self._subs.items():
            if fnmatch.fnmatchcase(topic, pattern):
                handlers.extend(hs)
        return handlers

    async def _listen(self) -> None:
        async for message in self._pubsub.listen():
            if self._stop.is_set() or message is None:
                break
            if message.get("type") != "pmessage":
                continue
            try:
                data = json.loads(message["data"])
                event = Event(topic=data["topic"], payload=data["payload"], source=data["source"], ts=data["ts"])
            except (json.JSONDecodeError, KeyError):
                logger.warning("dropping malformed event frame")
                continue
            for handler in self._match(event.topic):
                try:
                    await handler(event)
                except Exception:  # noqa: BLE001 - subscriber errors never kill the loop
                    logger.exception("subscriber error on %s", event.topic)


async def build_event_bus(redis_url: str = "") -> EventBusLike:
    """Factory with controlled fallback: Redis when configured AND reachable,
    otherwise InMemory with an explicit warning."""
    if not redis_url:
        return InMemoryEventBus()
    try:
        bus = RedisEventBus(redis_url)
        await bus.start()
        logger.info("RedisEventBus connected to %s", redis_url)
        return bus
    except Exception as exc:  # noqa: BLE001 - fallback must be guaranteed
        logger.warning(
            "Redis unreachable (%s) — falling back to InMemoryEventBus "
            "(single-process events only)",
            exc,
        )
        return InMemoryEventBus()
