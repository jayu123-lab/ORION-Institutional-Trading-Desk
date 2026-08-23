"""Embedded live-data ingestion for local dashboard use.

Keeps the dashboard populated even when the standalone monitor process is not
running. Disable with ORION_EMBEDDED_DATA=false when using apps.monitor.main.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from apps.api.routers.market import _watchlist
from core.config import get_settings
from core.events.bus import get_event_bus
from core.events.types import Event
from core.market_data.base import ProviderUnavailable
from core.market_data.registry import build_default_registry
from core.memory.database import get_session_factory
from core.memory.models import Quote

logger = logging.getLogger("orion.api.background")

PRIORITY_SYMBOLS = [
    "XAUUSD", "DXY", "US10Y", "VIX", "SPX", "NDX", "NQ",
    "BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD", "EURUSD", "GBPUSD",
]


class EmbeddedDataService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.registry = build_default_registry()
        self.session_factory = get_session_factory()
        self.bus = get_event_bus()
        configured = _watchlist()
        self.symbols = PRIORITY_SYMBOLS + [s for s in configured if s not in PRIORITY_SYMBOLS]
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        logger.info(
            "EMBEDDED DATA SERVICE STARTED (%s symbols, providers=%s)",
            len(self.symbols),
            self.registry.names,
        )
        await self.refresh_quotes()
        await self.refresh_news()
        quote_interval = max(15, int(self.settings.orion_embedded_quote_interval_sec))
        news_interval = max(120, int(self.settings.orion_embedded_news_interval_sec))
        next_news = asyncio.get_running_loop().time() + news_interval
        while not self._stop.is_set():
            logger.debug("next quote cycle in %ss", quote_interval)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=quote_interval)
                break
            except TimeoutError:
                pass
            await self.refresh_quotes()
            now = asyncio.get_running_loop().time()
            if now >= next_news:
                await self.refresh_news()
                next_news = now + news_interval

    async def refresh_quotes(self) -> None:
        stored = failed = skipped = 0
        for symbol in self.symbols:
            if self._stop.is_set():
                return
            try:
                provider = self.registry.resolve(symbol)
            except ProviderUnavailable as exc:
                logger.debug("quote routing failed %s: %s", symbol, exc)
                skipped += 1
                continue
            try:
                quote = await provider.get_quote(symbol)
            except ProviderUnavailable as exc:
                logger.debug("quote unavailable %s via %s: %s", symbol, provider.name, exc)
                skipped += 1
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("QUOTE FAILED %s via %s: %s", symbol, provider.name, exc)
                failed += 1
                continue
            await self._store_quote(provider.name, symbol, quote)
            stored += 1
        logger.info("QUOTES CYCLE DONE stored=%d failed=%d unroutable=%d", stored, failed, skipped)

    async def _store_quote(self, provider_name: str, symbol: str, quote) -> None:  # noqa: ANN001
        with self.session_factory() as session:
            session.add(Quote(
                symbol=symbol.upper(), provider=provider_name, price=quote.price,
                bid=quote.bid, ask=quote.ask, volume=quote.volume,
                ts_source=quote.ts_source, latency_ms=quote.quality.latency_ms,
                quality=quote.quality.quality, status=quote.quality.status.value,
            ))
            session.commit()
        await self.bus.publish(Event(
            topic="PRICE_UPDATE", source=f"embedded:{provider_name}",
            payload={
                "symbol": symbol.upper(), "price": quote.price,
                "provider": provider_name, "status": quote.quality.status.value,
                "ts": datetime.now(UTC).isoformat(),
            },
        ))

    async def refresh_news(self) -> None:
        try:
            from providers.news.rss import ingest_news

            inserted = await ingest_news()
            if inserted:
                logger.info("NEWS CYCLE: %s new headlines", inserted)
            else:
                logger.info("NEWS CYCLE: no new headlines")
        except Exception as exc:  # noqa: BLE001
            logger.warning("news cycle failed: %s", exc)
