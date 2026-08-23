"""Tests for quote→candle aggregation (DERIVED provenance)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from core.memory.candles import aggregate_quotes_to_candles
from core.memory.models import Candle, Quote


@pytest.fixture()
def session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from core.memory.models import Base

    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = Session(engine)
    yield s
    s.close()


def _seed_quotes(session, symbol: str, base_price: float, hours: int):
    t0 = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)
    for h in range(hours):
        ticks = ((10, base_price + h), (30, base_price + h + 0.5), (50, base_price + h - 0.25))
        for minute, price in ticks:
            session.add(
                Quote(
                    symbol=symbol,
                    provider="test",
                    price=price,
                    ts_source=t0 + timedelta(hours=h, minutes=minute),
                    ts_received=t0 + timedelta(hours=h, minutes=minute),
                )
            )
    session.commit()


def test_aggregates_hourly_ohlc(session):
    _seed_quotes(session, "XAUUSD", 2500.0, 3)
    n = aggregate_quotes_to_candles(session, timeframe="H1", symbols=["XAUUSD"])
    assert n == 3
    rows = (
        session.execute(select(Candle).where(Candle.symbol == "XAUUSD").order_by(Candle.ts_open))
        .scalars()
        .all()
    )
    first = rows[0]
    assert first.open == 2500.0
    assert first.high == pytest.approx(max(2500.0, 2500.5, 2499.75))
    assert first.low == pytest.approx(min(2500.0, 2500.5, 2499.75))
    # last quote of the hour closes the bar
    assert first.close == 2499.75
    assert first.provider == "derived-quotes"
    assert first.status == "DERIVED"


def test_idempotent_upsert_updates_extremes(session):
    _seed_quotes(session, "BTCUSD", 60000.0, 2)
    aggregate_quotes_to_candles(session, timeframe="H1", symbols=["BTCUSD"])
    # new higher tick arrives late in the same hour window → high/close update, no dup row
    session.add(
        Quote(
            symbol="BTCUSD",
            provider="test",
            price=61234.0,
            ts_source=datetime(2026, 8, 20, 1, 55, tzinfo=UTC),
            ts_received=datetime(2026, 8, 20, 1, 55, tzinfo=UTC),
        )
    )
    session.commit()
    n = aggregate_quotes_to_candles(session, timeframe="H1", symbols=["BTCUSD"])
    rows = session.execute(select(Candle).where(Candle.symbol == "BTCUSD")).scalars().all()
    assert len(rows) == 2
    assert n == 2
    second = next(r for r in rows if r.ts_open.hour == 1)
    assert second.high == 61234.0 and second.close == 61234.0


def test_skips_nonpositive_prices(session):
    session.add(
        Quote(symbol="ETHUSD", provider="t", price=0.0,
              ts_source=datetime(2026, 8, 20, tzinfo=UTC),
              ts_received=datetime(2026, 8, 20, tzinfo=UTC))
    )
    session.commit()
    assert aggregate_quotes_to_candles(session, timeframe="H1") == 0


def test_unsupported_timeframe_raises(session):
    with pytest.raises(ValueError):
        aggregate_quotes_to_candles(session, timeframe="D7")
