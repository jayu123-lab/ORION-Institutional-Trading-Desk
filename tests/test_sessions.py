from __future__ import annotations

from datetime import UTC, datetime

from core.sessions import desk_clock


def test_utc_and_madrid_representation():
    c = desk_clock(datetime(2026, 8, 20, 12, 0, tzinfo=UTC))  # 14:00 Madrid
    assert c.utc.hour == 12
    assert c.madrid.hour == 14


def test_active_sessions_london_ny_overlap():
    c = desk_clock(datetime(2026, 8, 20, 15, 0, tzinfo=UTC))
    assert "LONDON" in c.active_sessions
    assert "NEW_YORK" in c.active_sessions


def test_asia_session_early_morning():
    c = desk_clock(datetime(2026, 8, 20, 3, 0, tzinfo=UTC))
    assert "ASIA" in c.active_sessions
    assert "LONDON" not in c.active_sessions


def test_next_event_is_future():
    c = desk_clock()
    assert c.next_event_name is not None
    assert c.next_event_utc > c.utc or c.next_event_utc == c.utc
