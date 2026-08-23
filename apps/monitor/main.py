"""orion-monitor — persistent background service (spec §15).

Runs while the PC is on: heartbeat, quote refresh from registered providers,
feed health tracking, alert writing, DB snapshots. Independent of the chat.

Run: python -m apps.monitor.main
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from core.config import get_settings
from core.events.bus import get_event_bus
from core.events.types import FEED_DISCONNECTED
from core.logging import setup_logging
from core.market_data.base import MarketDataProvider, is_stale
from core.market_data.registry import build_default_registry
from core.memory.database import get_session_factory, init_db
from core.memory.models import Alert, Quote, RiskSnapshot, Source, utcnow

logger = logging.getLogger("orion.monitor")


class FeedHealth:
    """Tracks per-provider connection state with exponential backoff."""

    def __init__(self) -> None:
        self.connected: dict[str, bool] = {}
        self.failures: dict[str, int] = {}

    def record_success(self, provider: str) -> None:
        was_down = not self.connected.get(provider, False)
        self.connected[provider] = True
        self.failures[provider] = 0
        if was_down:
            logger.info("feed %s CONNECTED", provider)

    def record_failure(self, provider: str) -> None:
        self.connected[provider] = False
        self.failures[provider] = self.failures.get(provider, 0) + 1

    def backoff_seconds(self, provider: str) -> int:
        return min(300, 2 ** min(self.failures.get(provider, 0), 8))


class OrionMonitor:
    def __init__(self, symbols: list[str], providers: list[MarketDataProvider]) -> None:
        self.symbols = symbols
        self.providers = providers
        self.health = FeedHealth()
        self.session_factory = get_session_factory()
        self.bus = get_event_bus()
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ loops
    async def run_forever(self) -> None:
        settings = get_settings()
        logger.info(
            "orion-monitor started: symbols=%s providers=%s",
            len(self.symbols),
            [p.name for p in self.providers],
        )
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - monitor must survive any tick failure
                logger.exception("tick failed")
            await asyncio.sleep(settings.monitor_heartbeat_seconds)

    async def tick(self) -> None:
        for provider in self.providers:
            supported = getattr(provider, "supported", None)
            for symbol in self.symbols:
                if supported is not None and symbol.upper() not in supported:
                    continue  # provider does not cover this symbol (no silent fallback)
                try:
                    quote = await provider.get_quote(symbol)
                except Exception as exc:  # noqa: BLE001
                    self.health.record_failure(provider.name)
                    logger.warning("quote fail %s/%s: %s", provider.name, symbol, exc)
                    await self.bus.publish(
                        type(self)._event(
                            FEED_DISCONNECTED,
                            {"provider": provider.name, "symbol": symbol},
                        )
                    )
                    continue

                self.health.record_success(provider.name)
                await self._store_quote(provider.name, quote)

                if is_stale(quote.ts_source, get_settings().monitor_quote_staleness_sec):
                    await self._alert(
                        f"DATA STALE {symbol} ({provider.name})",
                        rule_name="data-stale",
                        severity="WARN",
                        payload={"symbol": symbol, "provider": provider.name},
                    )

        self._upsert_sources()
        self._write_risk_snapshot()

    # -------------------------------------------------------------- storage
    async def _store_quote(self, provider_name: str, quote) -> None:
        with self.session_factory() as session:
            session.add(
                Quote(
                    symbol=quote.symbol,
                    provider=provider_name,
                    price=quote.price,
                    bid=quote.bid,
                    ask=quote.ask,
                    volume=quote.volume,
                    ts_source=quote.ts_source,
                    latency_ms=quote.quality.latency_ms,
                    quality=quote.quality.quality,
                    status=quote.quality.status.value,
                )
            )
            session.commit()

    def _upsert_sources(self) -> None:
        with self.session_factory() as session:
            for provider in self.providers:
                src = session.query(Source).filter(Source.name == provider.name).one_or_none()
                status = "CONNECTED" if self.health.connected.get(provider.name) else "DISCONNECTED"
                if src is None:
                    session.add(Source(name=provider.name, kind="PROVIDER", status=status))
                else:
                    src.status = status
                    src.updated_at = utcnow()
            session.commit()

    def _write_risk_snapshot(self) -> None:
        """Paper account snapshot: equity constant in Phase 1; exposure from open positions."""
        from sqlalchemy import select

        from core.memory.models import Position

        with self.session_factory() as session:
            positions = (
                session.execute(select(Position).where(Position.status == "OPEN")).scalars().all()
            )
            equity = get_settings().orion_starting_equity
            total_notional = sum(abs(p.qty * p.avg_price) for p in positions)
            session.add(
                RiskSnapshot(
                    equity=equity,
                    balance=equity,
                    drawdown_pct=0.0,
                    daily_risk_used=0.0,
                    weekly_risk_used=0.0,
                    exposure_total=round(total_notional, 2),
                    verdict="GREEN_LIGHT" if total_notional / max(equity, 1) < 3 else "CAUTION",
                )
            )
            session.commit()

    async def _alert(self, message: str, rule_name: str, severity: str, payload: dict) -> None:
        with self.session_factory() as session:
            recent = session.execute(
                select(Alert)
                .where(Alert.rule_name == rule_name)
                .order_by(Alert.ts.desc())  # type: ignore[attr-defined]
                .limit(1)
            ).scalar_one_or_none()
            if recent is not None and datetime.now(UTC) - recent.ts.replace(tzinfo=UTC) < timedelta(
                minutes=10
            ):
                return  # dedupe window
            session.add(
                Alert(
                    rule_name=rule_name,
                    rule_kind="HEALTH",
                    payload=payload,
                    message=message,
                    severity=severity,
                )
            )
            session.commit()
        await self.bus.publish(type(self)._event("ALERT_TRIGGERED", {"message": message}))

    @staticmethod
    def _event(topic: str, payload: dict):
        from core.events.types import Event

        return Event(topic=topic, payload=payload, source="orion-monitor")


async def main_async() -> None:
    setup_logging(get_settings().log_level)
    init_db()
    registry = build_default_registry()
    monitor = OrionMonitor(symbols=_symbols(), providers=list(_providers_for(registry)))
    bus_task = asyncio.create_task(monitor.bus.run())
    try:
        await monitor.run_forever()
    finally:
        bus_task.cancel()


def _symbols() -> list[str]:
    from apps.api.routers.market import _watchlist

    return _watchlist()


def _providers_for(registry):  # noqa: ANN001
    """Real feeds via registry (yahoo/RTDS); simulated only as dev fallback.

    Symbols without a real mapping are skipped (never simulated silently).
    """
    providers: list = []
    for sym in _symbols():
        try:
            provider = registry.resolve(sym)
        except Exception as exc:  # noqa: BLE001 - unresolvable symbol must not kill monitor
            logger.debug("no provider for %s: %s", sym, exc)
            continue
        if provider.name == "simulated" and not get_settings().orion_simulated_enabled:
            continue
        if provider not in providers:
            providers.append(provider)
    if not providers:
        from core.market_data.simulated import SimulatedDataProvider

        sim = SimulatedDataProvider()
        registry.register(sim)
        providers = [sim]
    return providers


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("orion-monitor stopped by user")


if __name__ == "__main__":
    main()
