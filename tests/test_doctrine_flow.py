"""Focused coverage for the implemented ORION doctrine flow components."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from core.desk.journal import evaluate_journal_outcome, record_decision
from core.desk.router import IntentRouter
from core.desk.watch import create_watch, evaluate_watches, list_watches
from core.doctrine.doctrine import ORIONTradingDoctrine
from core.doctrine.flow import DEALER_FIELDS, VOLUME_FLOW_FIELDS, dealer_block, volume_flow_block
from core.doctrine.liquidity import build_liquidity_map, detect_sweeps
from core.doctrine.range26 import orion_range_zone
from core.doctrine.scores import (
    classify_bias,
    compute_bias_score,
    compute_trade_quality,
    extension_score,
    freshness_score,
    risk_state_score,
    rr_score,
)
from core.doctrine.session_engine import compute_session_map
from core.memory.database import get_session_factory, init_db
from core.memory.models import Candle, Quote
from core.sessions import desk_clock
from core.translation.service import catalogs_payload, translate_text, ui_string


def candle(ts: datetime, high: float, low: float, close: float | None = None,
           open_: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        ts_open=ts, high=high, low=low, close=close if close is not None else (high + low) / 2,
        open=open_ if open_ is not None else (high + low) / 2,
    )


def test_doctrine_gates_stop_in_sequence_and_trade_only_after_confirmation():
    doctrine = ORIONTradingDoctrine()

    assert doctrine.evaluate("LONG", reaction=True, confirmation=True, rr=2.5,
                             risk_ok=False).status == "NO_TRADE"
    assert doctrine.evaluate("LONG", reaction=True, confirmation=True, rr=2.5,
                             has_level=False).status == "WAIT"
    assert doctrine.evaluate("LONG", reaction=None, confirmation=True, rr=2.5).status == "WAIT"
    assert doctrine.evaluate("LONG", reaction=False, confirmation=True, rr=2.5).status == "NO_TRADE"
    assert doctrine.evaluate("LONG", reaction=True, confirmation=None, rr=2.5).status == "WAIT"
    assert doctrine.evaluate("LONG", reaction=True, confirmation=False, rr=2.5).status == "WAIT"
    assert doctrine.evaluate("LONG", reaction=True, confirmation=True, rr=2.5,
                             extension_atr=2.1).status == "WAIT"
    assert doctrine.evaluate("LONG", reaction=True, confirmation=True, rr=None).status == "WAIT"
    assert doctrine.evaluate("LONG", reaction=True, confirmation=True, rr=1.9).status == "REJECT"
    decision = doctrine.evaluate("LONG", reaction=True, confirmation=True, rr=2.0)
    assert decision.status == "TRADE"
    assert decision.checks["RISK"] == "PASS"
    assert doctrine.evaluate("NEUTRAL", reaction=True, confirmation=True, rr=2.0).status == "WAIT"


def test_doctrine_rr_and_extension_helpers():
    assert ORIONTradingDoctrine.rr_of(100, 98, 106) == 3.0
    assert ORIONTradingDoctrine.rr_of(100, 100, 106) is None
    assert ORIONTradingDoctrine.extension_in_atr(106, 100, 2) == 3.0
    assert ORIONTradingDoctrine.extension_in_atr(106, 100, 0) is None


def test_flow_blocks_are_explicitly_unavailable():
    volume = volume_flow_block()
    dealer = dealer_block()
    assert set(volume) == set(VOLUME_FLOW_FIELDS)
    assert set(dealer) == set(DEALER_FIELDS)
    assert all(item["provenance"] == "NOT_AVAILABLE" for item in volume.values())
    assert all(item["value"] is None for item in dealer.values())


def test_scores_renormalize_missing_data_and_keep_bias_separate_from_quality():
    bias = compute_bias_score({"macro": {"value": 80}, "regime": {"value": 60}})
    assert bias.total == 71
    assert bias.band == "STRONG_BULLISH"
    assert "cross_asset" in bias.missing_inputs
    assert sum(bias.weights_used.values()) == pytest.approx(1.0)

    quality = compute_trade_quality({"reaction": {"score": 100}, "rr": {"score": 100}})
    assert quality.total == 100
    assert quality.band is None
    assert "location" in quality.missing_inputs
    assert classify_bias(45) == "BEARISH"
    assert rr_score(2) == 40
    assert extension_score(0.5) == 90
    assert freshness_score("STALE") == 25
    assert risk_state_score("RED_LIGHT") == 0


def test_session_map_derives_current_and_previous_reference_levels():
    now = datetime(2025, 1, 15, 18, tzinfo=UTC)
    candles = [
        candle(now - timedelta(days=1, hours=7), 110, 90, 100, 95),  # previous day
        candle(datetime(2025, 1, 6, 12, tzinfo=UTC), 130, 80, 100, 90),  # previous week
        candle(datetime(2025, 1, 15, 2, tzinfo=UTC), 105, 95, 100, 98),
        candle(datetime(2025, 1, 15, 9, tzinfo=UTC), 115, 100, 110, 105),
        candle(datetime(2025, 1, 15, 14, tzinfo=UTC), 120, 105, 115, 110),
    ]
    result = compute_session_map(candles, now=now)
    assert result.candle_count == len(candles)
    assert result.get("ASIA_HIGH") == 105
    assert result.get("LONDON_HIGH") == 120
    assert result.get("PDH") == 110
    assert result.get("PWH") == 130
    assert result.get("DAILY_OPEN") == 98
    assert result.get("NY_OPEN") == 110
    assert result.to_dict()["timeframe"] == "H1"


def test_liquidity_map_and_sweep_detection():
    base = datetime(2025, 1, 1, tzinfo=UTC)
    bars = [
        candle(base + timedelta(hours=i), high, low, close)
        for i, (high, low, close) in enumerate(
            [(101, 99, 100), (102, 98, 100), (110, 99, 108), (103, 97, 100),
             (104, 98, 102), (109, 99, 107), (105, 100, 103)]
        )
    ]
    lq = build_liquidity_map(bars, last_price=103, session_levels={"PDH": 110}, atr=2)
    assert any(pool.kind in {"SWING_HIGH", "RANGE_HIGH", "PDH"} for pool in lq.buy_side)
    assert lq.nearest(103, "BUY_SIDE") is not None

    sweep_bar = candle(base + timedelta(hours=7), 111, 101, 109)
    events = detect_sweeps(bars + [sweep_bar], lq)
    assert any(event.kind == "SWEEP_HIGH" and event.level == 110 for event in events)
    assert "NOT an entry" in events[0].note


def test_range26_requires_significance_and_reports_confluence():
    base = datetime(2025, 1, 1, tzinfo=UTC)
    bars = [candle(base + timedelta(hours=i), 130 if i == 2 else 110,
                   80 if i == 3 else 100) for i in range(5)]
    zone = orion_range_zone(bars, atr=10, liquidity_levels=[110.7692307])
    assert zone is not None
    assert zone.zone_price == pytest.approx(110.7692307)
    assert zone.confluences and "liquidity pool" in zone.confluences[0]
    assert orion_range_zone(bars, atr=20) is None


def test_translation_preserves_symbols_and_falls_back_for_unknown_text():
    translated = translate_text("Liquidity Sweep on XAUUSD at 2300", "es", "en")
    assert "barrido de liquidez" in translated.text
    assert "XAUUSD" in translated.text and "2300" in translated.text
    assert translated.translated is False  # ES is the canonical/default output
    original = "An unrelated sentence"
    assert translate_text(original, "fr").text == original
    assert ui_string("command_center", "en") == "COMMAND CENTER"
    payload = catalogs_payload()
    assert payload["default_language"] == "es"
    assert {item["code"] for item in payload["languages"]} >= {"es", "en"}


def test_routing_watch_and_session_clock():
    router = IntentRouter()
    watch_route = router.route("Vigila oro y avísame si llega a zona")
    assert watch_route.intent == "WATCH" and watch_route.asset == "XAUUSD"
    assert watch_route.required_agents == ["market-data-engineer", "risk-manager", "audit-agent"]
    assert router.route("revisa el riesgo de BTC").intent == "RISK"
    clock = desk_clock(datetime(2025, 1, 15, 14, tzinfo=UTC))
    assert {"LONDON", "NEW_YORK", "COMEX"} <= set(clock.active_sessions)
    assert clock.next_event_name == "NYSE_OPEN"


@pytest.fixture()
def session_factory(tmp_path):
    engine = init_db(create_engine(
        f"sqlite:///{tmp_path / 'doctrine.db'}", future=True,
        connect_args={"check_same_thread": False},
    ))
    return get_session_factory(engine)


def test_watch_transitions_without_execution(session_factory):
    with session_factory() as session:
        session.add(Quote(symbol="XAUUSD", provider="test", price=100,
                          ts_source=datetime.now(UTC), status="LIVE"))
        session.commit()
    watch = create_watch(session_factory, "xauusd", "wait for reaction", 99, 101)
    assert watch["state"] == "WATCHING"
    assert evaluate_watches(session_factory)[0]["state"] == "ARMED"
    with session_factory() as session:
        session.add(Quote(symbol="XAUUSD", provider="test", price=103,
                          ts_source=datetime.now(UTC), status="LIVE"))
        session.commit()
    confirmed = evaluate_watches(session_factory)[0]
    assert confirmed["state"] == "CONFIRMED"
    assert confirmed["execution"].startswith("NONE")
    assert len(list_watches(session_factory)) == 1


def test_journal_records_and_evaluates_real_candles(session_factory):
    now = datetime(2025, 1, 1, tzinfo=UTC)
    with session_factory() as session:
        session.add(Quote(symbol="XAUUSD", provider="test", price=110,
                          ts_source=now, status="LIVE"))
        for i in range(6):
            session.add(Candle(symbol="XAUUSD", timeframe="H1", provider="test",
                               open=100 + i, high=110 + i, low=99 + i, close=109 + i,
                               volume=1, ts_open=now + timedelta(hours=i)))
        session.commit()
    journal_id = record_decision(session_factory, symbol="xauusd", session_name="LONDON",
                                 bias="LONG", bias_score=70, trade_quality=80,
                                 decision="TRADE", reference_price=100)
    outcome = evaluate_journal_outcome(session_factory, journal_id, horizon_bars=24)
    assert outcome is not None
    assert outcome["outcome_status"] == "EVALUATED"
    assert outcome["correct_bias"] is True
    assert outcome["mfe"] > 0
