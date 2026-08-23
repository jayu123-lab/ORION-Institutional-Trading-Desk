"""Candle aggregation from stored quotes (DERIVED provenance).

The desk stores every ingested quote; this module rolls them into H1 OHLC
candles so regime/brain/cross-asset engines have bar data. Candles built here
are tagged provider='derived-quotes', status='DERIVED' — never presented as
exchange-native bars.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.schema import Table as SATable

from core.memory.models import Candle, Quote

_CANDLE_TABLE = cast(SATable, Candle.__table__)

TIMEFRAME_SECONDS = {"M15": 900, "H1": 3600, "H4": 14400}


def _bucket(ts: datetime, seconds: int) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp((epoch // seconds) * seconds, tz=UTC)


def aggregate_quotes_to_candles(
    session: Session,
    *,
    timeframe: str = "H1",
    symbols: list[str] | None = None,
    since: datetime | None = None,
) -> int:
    """Roll quotes into OHLC buckets. Idempotent upsert per (symbol,bucket).
    Returns number of candle rows written."""
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"unsupported timeframe {timeframe}")
    step = TIMEFRAME_SECONDS[timeframe]

    q = select(Quote.symbol, Quote.price, Quote.volume, Quote.ts_received).order_by(
        Quote.symbol, Quote.ts_received
    )
    if symbols:
        q = q.where(Quote.symbol.in_([s.upper() for s in symbols]))
    if since is not None:
        q = q.where(Quote.ts_received >= since)

    buckets: dict[tuple[str, datetime], list[float]] = {}
    volumes: dict[tuple[str, datetime], float] = {}
    for sym, price, volume, ts in session.execute(q):
        price = float(price)
        if price <= 0:
            continue
        key = (sym, _bucket(ts, step))
        b = buckets.get(key)
        if b is None:
            buckets[key] = [price, price, price, price]
        else:
            b[1] = max(b[1], price)
            b[2] = min(b[2], price)
            b[3] = price
        if volume is not None:
            volumes[key] = volumes.get(key, 0.0) + float(volume)

    written = 0
    for (sym, ts_open), (o, hi, lo, c) in sorted(buckets.items()):
        stmt = (
            sqlite_insert(_CANDLE_TABLE)
            .values(
                symbol=sym,
                timeframe=timeframe,
                provider="derived-quotes",
                open=o,
                high=hi,
                low=lo,
                close=c,
                volume=volumes.get((sym, ts_open)),
                ts_open=ts_open,
                status="DERIVED",
            )
            .on_conflict_do_update(
                index_elements=["symbol", "timeframe", "ts_open", "provider"],
                set_={"high": hi, "low": lo, "close": c},
            )
        )
        session.execute(stmt)
        written += 1
    session.commit()
    return written


def backfill_all_timeframes(session: Session, *, since: datetime | None = None) -> dict[str, int]:
    return {
        tf: aggregate_quotes_to_candles(session, timeframe=tf, since=since)
        for tf in ("M15", "H1", "H4")
    }
