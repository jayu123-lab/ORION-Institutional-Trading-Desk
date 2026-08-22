"""Trading session engine. Internal UTC; display Europe/Madrid.

Sessions (all-day boundaries in UTC approximations used by the desk):
ASIA 00:00-08:00 · LONDON 08:00-16:00 · NEW_YORK 13:30-20:00 (overlap w/ London)
LONDON_FIX 10:00 & 15:00 · COMEX pit 13:30-18:30 · NYSE_OPEN 14:30 · NYSE_CLOSE 21:00
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone

try:
    from zoneinfo import ZoneInfo

    MADRID: ZoneInfo | timezone = ZoneInfo("Europe/Madrid")
except ImportError:  # pragma: no cover - py312+ always has zoneinfo
    MADRID = UTC


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start_utc: time
    end_utc: time


SESSIONS: tuple[SessionWindow, ...] = (
    SessionWindow("ASIA", time(0, 0), time(8, 0)),
    SessionWindow("LONDON", time(8, 0), time(16, 0)),
    SessionWindow("NEW_YORK", time(13, 30), time(20, 0)),
    SessionWindow("COMEX", time(13, 30), time(18, 30)),
)


def _in_window(now: datetime, w: SessionWindow) -> bool:
    t = now.time()
    return w.start_utc <= t < w.end_utc


@dataclass(frozen=True)
class DeskClock:
    utc: datetime
    madrid: datetime
    active_sessions: tuple[str, ...]
    next_event_name: str | None
    next_event_utc: datetime | None


FIX_TIMES_UTC = (time(10, 0), time(15, 0))
NYSE_OPEN_UTC = time(14, 30)
NYSE_CLOSE_UTC = time(21, 0)


def desk_clock(now: datetime | None = None) -> DeskClock:
    """Compute current sessions and the next fixed event of the trading day."""
    now = now or datetime.now(UTC)
    active = tuple(w.name for w in SESSIONS if _in_window(now, w))

    candidates: list[tuple[str, datetime]] = []
    for label, t in (
        ("LONDON_FIX_AM", FIX_TIMES_UTC[0]),
        ("LONDON_FIX_PM", FIX_TIMES_UTC[1]),
        ("NYSE_OPEN", NYSE_OPEN_UTC),
        ("NYSE_CLOSE", NYSE_CLOSE_UTC),
        ("LONDON_OPEN", SESSIONS[1].start_utc),
    ):
        candidate = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        candidates.append((label, candidate))
    name, when = min(candidates, key=lambda x: x[1])

    madrid = now.astimezone(MADRID)
    return DeskClock(
        utc=now, madrid=madrid, active_sessions=active, next_event_name=name, next_event_utc=when
    )
