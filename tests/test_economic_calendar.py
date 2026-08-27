"""Tests for economic calendar."""
import pytest
from datetime import datetime, timedelta
from core.events.economic_calendar import (
    EconomicEvent,
    EconomicCalendar,
    ImpactLevel,
)


def test_economic_event_creation():
    """Test creating an economic event."""
    event = EconomicEvent(
        name="Non-Farm Payroll",
        country="US",
        datetime_utc=datetime.utcnow() + timedelta(hours=1),
        impact=ImpactLevel.HIGH,
    )
    
    assert event.name == "Non-Farm Payroll"
    assert event.country == "US"
    assert event.is_high_impact()


def test_event_upcoming_check():
    """Test upcoming event detection."""
    future = datetime.utcnow() + timedelta(minutes=30)
    event = EconomicEvent(
        name="Test Event",
        country="US",
        datetime_utc=future,
        impact=ImpactLevel.MEDIUM,
    )
    
    assert event.is_upcoming(minutes_ahead=60)
    assert not event.is_upcoming(minutes_ahead=10)


def test_calendar_seed():
    """Test seeding calendar with events."""
    calendar = EconomicCalendar()
    calendar.seed_major_events("US")
    
    assert len(calendar.events) > 0
    assert all(e.country == "US" for e in calendar.events)


def test_calendar_filters():
    """Test calendar filtering methods."""
    calendar = EconomicCalendar()
    calendar.seed_major_events("US")
    calendar.seed_major_events("EUR")
    
    us_events = calendar.get_events_by_country("US")
    assert all(e.country == "US" for e in us_events)
    
    high_impact = calendar.get_high_impact_events()
    assert all(e.is_high_impact() for e in high_impact)


def test_calendar_format():
    """Test calendar formatting."""
    calendar = EconomicCalendar()
    calendar.seed_major_events("US")
    
    formatted = calendar.format_calendar()
    assert "Economic Calendar" in formatted
    assert "US" in formatted
