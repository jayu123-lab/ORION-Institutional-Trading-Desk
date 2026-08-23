"""P15: per-service health classification (HEALTHY/DEGRADED/STALE/FAILED)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.routers.system import _classify, _service_states
from core.config import get_settings
from core.memory.models import Base, Candle, NewsItem, Quote


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = Session(engine)
    yield s
    s.close()


@pytest.fixture()
def rtds_enabled(monkeypatch):
    """Force the embedded RTDS monitor ON for feed-state assertions."""
    monkeypatch.setattr(get_settings(), "orion_polymarket_ws_embedded", True)


def test_classify_thresholds():
    assert _classify(None, 100, 500, 3000) == "FAILED"
    assert _classify(50, 100, 500, 3000) == "HEALTHY"
    assert _classify(400, 100, 500, 3000) == "DEGRADED"
    assert _classify(2000, 100, 500, 3000) == "STALE"
    assert _classify(9999, 100, 500, 3000) == "FAILED"


def test_empty_db_reports_failed_services(session):
    now = datetime.now(UTC)
    states = {s["service"]: s["state"] for s in _service_states(session, now)}
    assert states["monitor.yahoo_poller"] == "FAILED"
    assert states["news.rss_cycle"] == "FAILED"
    assert states["monitor.candle_rollup"] == "FAILED"


def test_rtds_disabled_reports_not_configured(session):
    """RTDS off in config → DISABLED, never a fake STALE/FAILED."""
    now = datetime.now(UTC)
    states = {s["service"]: s["state"] for s in _service_states(session, now)}
    assert states["monitor.polymarket_rtds"] == "DISABLED"


@pytest.mark.usefixtures("rtds_enabled")
def test_empty_db_reports_failed_services_with_rtds_on(session):
    now = datetime.now(UTC)
    states = {s["service"]: s["state"] for s in _service_states(session, now)}
    assert states["monitor.polymarket_rtds"] == "FAILED"  # enabled + no ticks = FAILED


@pytest.mark.usefixtures("rtds_enabled")
def test_fresh_quotes_are_healthy(session):
    now = datetime.now(UTC)
    for provider in ("yahoo", "polymarket-rtds"):
        session.add(
            Quote(symbol="XAUUSD", provider=provider, price=1.0, ts_source=now, ts_received=now)
        )
    session.commit()
    states = {s["service"]: s["state"] for s in _service_states(session, now)}
    assert states["monitor.yahoo_poller"] == "HEALTHY"
    assert states["monitor.polymarket_rtds"] == "HEALTHY"


def test_stale_and_fresh_news_candle_mix(session):
    now = datetime.now(UTC)
    session.add(NewsItem(title="t", source="s", published_at=now - timedelta(hours=10)))
    session.add(
        Candle(
            symbol="XAUUSD",
            timeframe="H1",
            provider="derived-quotes",
            open=1,
            high=1,
            low=1,
            close=1,
            ts_open=now - timedelta(hours=3),
        )
    )
    session.commit()
    report = {s["service"]: s for s in _service_states(session, now)}
    assert report["news.rss_cycle"]["state"] == "DEGRADED"  # 10h old: healthy≤6h, degraded≤24h
    assert report["monitor.candle_rollup"]["state"] == "DEGRADED"  # 3h old: healthy≤2h
