"""Session Engine (P5) — derives institutional reference levels from REAL
stored H1 candles.

Levels produced (each tagged DERIVED with source and timestamp):
  Asia High/Low, London High/Low, Previous Day High/Low,
  Previous Week High/Low, Daily Open, Weekly Open, London Open, NY Open.

When candles do not cover a window the level is listed in `missing`
instead of being invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta

SESSION_WINDOWS: dict[str, tuple[time, time]] = {
    "ASIA": (time(0, 0), time(8, 0)),
    "LONDON": (time(8, 0), time(16, 0)),
    "NEW_YORK": (time(13, 30), time(20, 0)),
}


@dataclass
class SessionLevel:
    name: str
    value: float | None
    provenance: str = "DERIVED"
    source: str = "db:candles"
    ts: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "provenance": self.provenance if self.value is not None else "NOT_AVAILABLE",
            "source": self.source,
            "ts": self.ts,
        }


@dataclass
class SessionMap:
    levels: list[SessionLevel] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    computed_at: str = ""
    candle_count: int = 0
    timeframe: str = "H1"

    def to_dict(self) -> dict:
        return {
            "levels": [lv.to_dict() for lv in self.levels],
            "missing": self.missing,
            "computed_at": self.computed_at,
            "candle_count": self.candle_count,
            "timeframe": self.timeframe,
        }

    def get(self, name: str) -> float | None:
        for lv in self.levels:
            if lv.name == name:
                return lv.value
        return None


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def compute_session_map(
    candles: list,  # ORM Candle rows with ts_open/high/low/(close), ascending
    now: datetime | None = None,
    timeframe: str = "H1",
) -> SessionMap:
    """Derive session/previous-period levels from stored bars.

    candles must be ascending by ts_open. Only windows fully covered by the
    data produce values; everything else lands in `missing`.
    """
    now = _as_utc(now or datetime.now(UTC))
    out = SessionMap(computed_at=now.isoformat(), timeframe=timeframe)
    if not candles:
        out.missing.extend([
            "ASIA_HIGH", "ASIA_LOW", "LONDON_HIGH", "LONDON_LOW",
            "PDH", "PDL", "PWH", "PWL", "DAILY_OPEN", "WEEKLY_OPEN",
            "LONDON_OPEN", "NY_OPEN",
        ])
        return out

    def hi_lo(rows: list) -> tuple[float, float]:
        return max(r.high for r in rows), min(r.low for r in rows)

    def add(name: str, value: float | None, ts_ref: datetime | None) -> None:
        out.levels.append(SessionLevel(
            name=name, value=value,
            ts=ts_ref.isoformat() if ts_ref else now.isoformat(),
        ))
        if value is None:
            out.missing.append(name)

    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    prev_day0 = today0 - timedelta(days=1)

    # --- current-day windows (Asia / London so far today)
    asia = [c for c in candles if today0 <= _as_utc(c.ts_open) < today0 + timedelta(hours=8)]
    london = [c for c in candles
              if today0 + timedelta(hours=8) <= _as_utc(c.ts_open) < today0 + timedelta(hours=16)]

    ah = al = lh = ll = None
    a_ts = l_ts = None
    if asia:
        ah, al = hi_lo(asia)
        a_ts = asia[-1].ts_open
    else:
        out.missing += ["ASIA_HIGH", "ASIA_LOW"]
    if london:
        lh, ll = hi_lo(london)
        l_ts = london[-1].ts_open
    else:
        out.missing += ["LONDON_HIGH", "LONDON_LOW"]
    add("ASIA_HIGH", ah, a_ts)
    add("ASIA_LOW", al, a_ts)
    add("LONDON_HIGH", lh, l_ts)
    add("LONDON_LOW", ll, l_ts)

    # --- previous day / previous week
    prev_day = [c for c in candles if prev_day0 <= _as_utc(c.ts_open) < today0]
    pdh = pdl = None
    pd_ts = prev_day[-1].ts_open if prev_day else None
    if prev_day:
        pdh, pdl = hi_lo(prev_day)
    else:
        out.missing += ["PDH", "PDL"]
    add("PDH", pdh, pd_ts)
    add("PDL", pdl, pd_ts)

    iso_week0 = (today0 - timedelta(days=now.isoweekday() - 1))
    prev_week0 = iso_week0 - timedelta(days=7)
    prev_week = [c for c in candles
                 if prev_week0 <= _as_utc(c.ts_open) < prev_week0 + timedelta(days=7)]
    pwh = pwl = None
    pw_ts = prev_week[-1].ts_open if prev_week else None
    if prev_week:
        pwh, pwl = hi_lo(prev_week)
    else:
        out.missing += ["PWH", "PWL"]
    add("PWH", pwh, pw_ts)
    add("PWL", pwl, pw_ts)

    # --- opens
    today_rows = [c for c in candles if _as_utc(c.ts_open) >= today0]
    week_rows = [c for c in candles if _as_utc(c.ts_open) >= iso_week0]
    d_ts = today_rows[0].ts_open if today_rows else None
    w_ts = week_rows[0].ts_open if week_rows else None
    add("DAILY_OPEN", today_rows[0].open if today_rows else None, d_ts)
    add("WEEKLY_OPEN",
        week_rows[0].open if week_rows else None, w_ts)

    london_open_row = next(
        (c for c in today_rows if _as_utc(c.ts_open).time() >= SESSION_WINDOWS["LONDON"][0]),
        None,
    )
    ny_open_row = next(
        (c for c in today_rows
         if _as_utc(c.ts_open).time() >= SESSION_WINDOWS["NEW_YORK"][0]),
        None,
    )
    add("LONDON_OPEN", london_open_row.open if london_open_row else None,
        london_open_row.ts_open if london_open_row else None)
    add("NY_OPEN", ny_open_row.open if ny_open_row else None,
        ny_open_row.ts_open if ny_open_row else None)

    out.candle_count = len(candles)
    return out
