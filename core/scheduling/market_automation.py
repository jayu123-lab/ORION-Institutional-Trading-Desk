"""Market automation tasks scheduled via SchedulerEngine."""
import logging
from typing import Optional

from core.scheduling.scheduler import SchedulerEngine
from core.events.economic_calendar import EconomicCalendar, ImpactLevel
from core.volume_monitor.volume_engine import VolumeMonitor

logger = logging.getLogger(__name__)


class MarketAutomation:
    """Coordinates scheduled market monitoring: calendar alerts, volume tracking."""

    def __init__(self, scheduler: SchedulerEngine):
        self.scheduler = scheduler
        self.calendar = EconomicCalendar()
        self.volume_monitor = VolumeMonitor()
        self.monitoring_symbols = ["SPY", "QQQ", "GLD", "bitcoin", "ethereum"]

    async def initialize(self):
        """Set up all scheduled tasks."""
        # Seed economic calendar with major events
        self.calendar.seed_major_events("US")
        self.calendar.seed_major_events("EUR")
        self.calendar.seed_major_events("GBP")

        # Schedule volume monitoring (every 5 minutes)
        for symbol in self.monitoring_symbols:
            self.scheduler.add_interval_job(
                self._monitor_volume,
                minutes=5,
                job_id=f"volume_{symbol}",
                kwargs={"symbol": symbol},
            )

        # Schedule calendar check (every hour)
        self.scheduler.add_cron_job(
            self._check_upcoming_events,
            "0 * * * *",  # Every hour
            "check_calendar",
        )

        # Schedule economic data refresh (daily at 00:00 UTC)
        self.scheduler.add_cron_job(
            self._refresh_calendar,
            "0 0 * * *",
            "refresh_calendar",
        )

        logger.info("Market automation initialized with scheduled tasks")
        await self.scheduler.start()

    async def _monitor_volume(self, symbol: str):
        """Fetch and monitor volume for a symbol."""
        try:
            if symbol.lower() in ["bitcoin", "ethereum"]:
                snapshot = await self.volume_monitor.fetch_crypto_volume(symbol.lower())
            else:
                snapshot = await self.volume_monitor.fetch_stock_volume(symbol)

            if snapshot:
                if self.volume_monitor.is_volume_spike(symbol):
                    logger.warning(
                        f"VOLUME SPIKE: {symbol} - {snapshot.volume:,.0f} "
                        f"(notional: ${snapshot.notional:,.0f})"
                    )
        except Exception as e:
            logger.error(f"Error monitoring volume for {symbol}: {e}")

    async def _check_upcoming_events(self):
        """Check for upcoming economic events (within 60 minutes)."""
        upcoming = self.calendar.get_upcoming_events(minutes_ahead=60)
        high_impact = [e for e in upcoming if e.is_high_impact()]

        if high_impact:
            logger.warning(f"HIGH IMPACT EVENTS INCOMING: {len(high_impact)}")
            for event in high_impact:
                logger.warning(
                    f"  ⏰ {event.name} ({event.country}) in "
                    f"{(event.datetime_utc - datetime.utcnow()).total_seconds() / 60:.0f} min"
                )

        if upcoming:
            logger.info(f"Upcoming events in next 60 min: {len(upcoming)}")

    async def _refresh_calendar(self):
        """Refresh economic calendar daily."""
        logger.info("Refreshing economic calendar")
        for country in ["US", "EUR", "GBP"]:
            self.calendar.seed_major_events(country)

    def get_status(self) -> dict:
        """Get status of all monitoring components."""
        return {
            "scheduler_running": self.scheduler.is_running(),
            "monitored_symbols": self.volume_monitor.get_monitored_symbols(),
            "economic_events": len(self.calendar.events),
            "upcoming_high_impact": len(self.calendar.get_high_impact_events()),
        }

    async def cleanup(self):
        """Clean up resources."""
        await self.scheduler.stop()
        logger.info("Market automation stopped")


# Import datetime for logging
from datetime import datetime
