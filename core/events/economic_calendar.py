from datetime import datetime, timedelta
from typing import List, Optional
from enum import Enum
import logging
import httpx

logger = logging.getLogger(__name__)


class ImpactLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EconomicEvent:
    """Represents an economic event/indicator."""

    def __init__(
        self,
        name: str,
        country: str,
        datetime_utc: datetime,
        impact: ImpactLevel,
        forecast: Optional[str] = None,
        previous: Optional[str] = None,
        actual: Optional[str] = None,
    ):
        self.name = name
        self.country = country
        self.datetime_utc = datetime_utc
        self.impact = impact
        self.forecast = forecast
        self.previous = previous
        self.actual = actual

    def is_upcoming(self, minutes_ahead: int = 60) -> bool:
        """Check if event is within X minutes."""
        now = datetime.utcnow()
        time_until = (self.datetime_utc - now).total_seconds() / 60
        return 0 <= time_until <= minutes_ahead

    def is_high_impact(self) -> bool:
        """Check if event has high impact."""
        return self.impact == ImpactLevel.HIGH

    def __repr__(self):
        return f"EconomicEvent({self.country}|{self.name}|{self.datetime_utc}|{self.impact})"


class EconomicCalendar:
    """Manages economic calendar events from reliable free sources."""

    def __init__(self):
        self.events: List[EconomicEvent] = []
        self.loaded_date = None

    async def fetch_from_tradingeconomics(self) -> bool:
        """Fetch calendar from Trading Economics (free tier)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Trading Economics requires API key for full access
                # For free tier, we'll seed with known events
                logger.info("Trading Economics integration requires API key")
                return False
        except Exception as e:
            logger.error(f"Failed to fetch from Trading Economics: {e}")
            return False

    def seed_major_events(self, country: str = "US"):
        """Seed calendar with known major events for the week."""
        now = datetime.utcnow()
        self.events = []

        major_events = {
            "US": [
                {
                    "name": "FOMC Meeting",
                    "day": "Wed",
                    "time": "18:00",
                    "impact": ImpactLevel.HIGH,
                },
                {
                    "name": "Non-Farm Payroll",
                    "day": "Fri",
                    "time": "13:30",
                    "impact": ImpactLevel.HIGH,
                },
                {
                    "name": "CPI (Consumer Price Index)",
                    "day": "Wed",
                    "time": "13:30",
                    "impact": ImpactLevel.HIGH,
                },
                {
                    "name": "Jobless Claims",
                    "day": "Thu",
                    "time": "13:30",
                    "impact": ImpactLevel.MEDIUM,
                },
                {
                    "name": "Retail Sales",
                    "day": "Fri",
                    "time": "13:30",
                    "impact": ImpactLevel.MEDIUM,
                },
                {
                    "name": "PMI Manufacturing",
                    "day": "Fri",
                    "time": "14:45",
                    "impact": ImpactLevel.MEDIUM,
                },
            ],
            "EUR": [
                {
                    "name": "ECB Monetary Policy Decision",
                    "day": "Thu",
                    "time": "13:45",
                    "impact": ImpactLevel.HIGH,
                },
                {
                    "name": "Eurozone CPI",
                    "day": "Wed",
                    "time": "10:00",
                    "impact": ImpactLevel.HIGH,
                },
                {
                    "name": "German ZEW Sentiment",
                    "day": "Tue",
                    "time": "10:00",
                    "impact": ImpactLevel.MEDIUM,
                },
            ],
            "GBP": [
                {
                    "name": "Bank of England Rate Decision",
                    "day": "Thu",
                    "time": "12:00",
                    "impact": ImpactLevel.HIGH,
                },
                {
                    "name": "UK CPI",
                    "day": "Wed",
                    "time": "07:00",
                    "impact": ImpactLevel.HIGH,
                },
            ],
        }

        events_by_country = major_events.get(country, [])
        for event_data in events_by_country:
            # Calculate next occurrence of event
            event_dt = self._next_event_datetime(
                now, event_data["day"], event_data["time"]
            )
            event = EconomicEvent(
                name=event_data["name"],
                country=country,
                datetime_utc=event_dt,
                impact=event_data["impact"],
            )
            self.events.append(event)

        self.loaded_date = now
        logger.info(f"Seeded {len(self.events)} events for {country}")

    def _next_event_datetime(
        self, base: datetime, day_name: str, time_str: str
    ) -> datetime:
        """Calculate next occurrence of an event."""
        days_ahead = {
            "Mon": 0,
            "Tue": 1,
            "Wed": 2,
            "Thu": 3,
            "Fri": 4,
            "Sat": 5,
            "Sun": 6,
        }
        target_day = days_ahead.get(day_name, 0)
        current_day = base.weekday()
        days_delta = (target_day - current_day) % 7
        if days_delta == 0 and base.time() >= datetime.strptime(time_str, "%H:%M").time():
            days_delta = 7

        next_date = base + timedelta(days=days_delta)
        hour, minute = map(int, time_str.split(":"))
        return next_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def get_upcoming_events(self, minutes_ahead: int = 60) -> List[EconomicEvent]:
        """Get events within X minutes."""
        return [e for e in self.events if e.is_upcoming(minutes_ahead)]

    def get_high_impact_events(self) -> List[EconomicEvent]:
        """Get only high-impact events."""
        return [e for e in self.events if e.is_high_impact()]

    def get_events_by_country(self, country: str) -> List[EconomicEvent]:
        """Get events for a specific country."""
        return [e for e in self.events if e.country == country]

    def format_calendar(self) -> str:
        """Return formatted calendar for display."""
        if not self.events:
            return "No events loaded"

        lines = ["Economic Calendar (UTC):"]
        for event in sorted(self.events, key=lambda x: x.datetime_utc):
            impact_icon = "🔴" if event.impact == ImpactLevel.HIGH else (
                "🟠" if event.impact == ImpactLevel.MEDIUM else "🟡"
            )
            lines.append(
                f"{impact_icon} {event.datetime_utc.strftime('%Y-%m-%d %H:%M')} "
                f"| {event.country} | {event.name}"
            )
        return "\n".join(lines)
