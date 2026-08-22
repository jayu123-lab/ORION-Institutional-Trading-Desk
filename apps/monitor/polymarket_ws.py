"""Polymarket RTDS WebSocket monitor — real-time crypto reference prices.

Connects to wss://ws-live-data.polymarket.com and subscribes to the
`crypto_prices` topic (Binance feed: btcusdt/ethusdt/solusdt/xrpusdt).

Protocol verified against official docs (docs.polymarket.com, "Real-Time Data")
and validated against the live endpoint:
- application-level heartbeat: send text frame `PING` every 5 seconds;
- subscription frame: {"action": "subscribe", "subscriptions": [
    {"topic": "crypto_prices", "type": "*", "filters": ""}]};
  NOTE: empirically the documented server-side comma-separated `filters`
  (e.g. "btcusdt,ethusdt") yields NO events; subscribing unfiltered and
  filtering client-side (parse_rtds_message drops unknown symbols) works;
- update message shape:
    {"topic": "crypto_prices", "type": "update", "timestamp": <epoch_ms>,
     "payload": {"symbol": "btcusdt", "timestamp": <epoch_ms>, "value": <num>}}
  the first frame after connecting is an empty string (harmless, ignored).

Run: python -m apps.monitor.polymarket_ws
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from core.config import get_settings
from core.events.bus import get_event_bus
from core.events.types import FEED_CONNECTED, FEED_DISCONNECTED, PRICE_UPDATE
from core.logging import setup_logging
from core.memory.database import get_session_factory, init_db
from core.memory.models import Quote, Source

logger = logging.getLogger("orion.polymarket_ws")

RTDS_URL = "wss://ws-live-data.polymarket.com"

# Binance symbol -> desk symbol (watchlist names)
RTDS_SYMBOL_MAP = {
    "btcusdt": "BTCUSD",
    "ethusdt": "ETHUSD",
    "solusdt": "SOLUSD",
    "xrpusdt": "XRPUSD",
}

PROVIDER_NAME = "polymarket-rtds"
HEARTBEAT_SEC = 5  # docs: PING every 5 seconds
RECONNECT_MIN_SEC = 1.0
RECONNECT_MAX_SEC = 60.0


@dataclass(frozen=True)
class ParsedTick:
    symbol: str  # desk symbol (BTCUSD...)
    price: float
    ts_source: datetime
    rtt_ms: int | None = None


def parse_rtds_message(raw: str | bytes, now: datetime | None = None) -> list[ParsedTick]:
    """Pure parser for RTDS frames → desk ticks. Never raises; bad input → []."""
    try:
        msg = json.loads(raw if isinstance(raw, str) else raw.decode())
    except (ValueError, UnicodeDecodeError):
        return []

    ticks: list[ParsedTick] = []
    entries = msg if isinstance(msg, list) else [msg]
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("topic") != "crypto_prices":
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        binance_sym = str(payload.get("symbol", "")).lower()
        desk_sym = RTDS_SYMBOL_MAP.get(binance_sym)
        if desk_sym is None:
            continue
        value = payload.get("full_accuracy_value", payload.get("value"))
        try:
            price = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        ts_ms = payload.get("timestamp") or entry.get("timestamp")
        ts_source = (
            datetime.fromtimestamp(int(ts_ms) / 1000, tz=UTC)
            if isinstance(ts_ms, (int, float)) and ts_ms > 0
            else (now or datetime.now(UTC))
        )
        rtt = None
        received_at = entry.get("timestamp")
        if isinstance(received_at, (int, float)) and isinstance(ts_ms, (int, float)):
            rtt = max(0, int(received_at - ts_ms))
        ticks.append(ParsedTick(symbol=desk_sym, price=price, ts_source=ts_source, rtt_ms=rtt))
    return ticks


class PolymarketWSMonitor:
    """Persistent RTDS listener writing LIVE quotes into the desk DB."""

    def __init__(self, session_factory=None, bus=None) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.bus = bus or get_event_bus()
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        import websockets

        backoff = RECONNECT_MIN_SEC
        logger.info(
            "polymarket-ws connecting to %s symbols=%s", RTDS_URL, sorted(RTDS_SYMBOL_MAP.values())
        )
        while not self._stop.is_set():
            try:
                async with websockets.connect(RTDS_URL) as ws:
                    # unfiltered: server-side `filters` proved unreliable (see docstring);
                    # parse_rtds_message drops symbols outside RTDS_SYMBOL_MAP
                    await ws.send(
                        json.dumps(
                            {
                                "action": "subscribe",
                                "subscriptions": [
                                    {"topic": "crypto_prices", "type": "*", "filters": ""}
                                ],
                            }
                        )
                    )
                    self._mark_source("CONNECTED")
                    await self.bus.publish(self._event(FEED_CONNECTED, {"source": PROVIDER_NAME}))
                    backoff = RECONNECT_MIN_SEC
                    heartbeat = asyncio.create_task(self._heartbeat(ws))
                    try:
                        async for raw in ws:
                            if self._stop.is_set():
                                break
                            for tick in parse_rtds_message(raw):
                                await self._store_tick(tick)
                    finally:
                        heartbeat.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep reconnecting forever
                logger.warning("ws disconnected: %s — retry in %.0fs", exc, backoff)
            self._mark_source("DISCONNECTED")
            await self.bus.publish(self._event(FEED_DISCONNECTED, {"source": PROVIDER_NAME}))
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_SEC)

    @staticmethod
    async def _heartbeat(ws) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SEC)
            await ws.send("PING")

    # ---------------------------------------------------------------- storage
    async def _store_tick(self, tick: ParsedTick) -> None:
        with self.session_factory() as session:
            session.add(
                Quote(
                    symbol=tick.symbol,
                    provider=PROVIDER_NAME,
                    price=tick.price,
                    bid=None,
                    ask=None,
                    volume=None,
                    ts_source=tick.ts_source,
                    latency_ms=tick.rtt_ms,
                    quality="A" if (tick.rtt_ms or 0) < 1500 else "B",
                    status="LIVE",
                )
            )
            session.commit()
        await self.bus.publish(
            self._event(PRICE_UPDATE, {"symbol": tick.symbol, "price": tick.price})
        )

    def _mark_source(self, status: str) -> None:
        with self.session_factory() as session:
            src = session.query(Source).filter(Source.name == PROVIDER_NAME).one_or_none()
            if src is None:
                session.add(Source(name=PROVIDER_NAME, kind="WS", status=status, base_url=RTDS_URL))
            else:
                src.status = status
            session.commit()

    @staticmethod
    def _event(topic: str, payload: dict):
        from core.events.types import Event

        return Event(topic=topic, payload=payload, source=PROVIDER_NAME)


async def main_async() -> None:
    setup_logging(get_settings().log_level)
    init_db()
    monitor = PolymarketWSMonitor()
    bus_task = asyncio.create_task(monitor.bus.run())
    try:
        await monitor.run_forever()
    finally:
        bus_task.cancel()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("polymarket-ws stopped by user")


if __name__ == "__main__":
    main()
