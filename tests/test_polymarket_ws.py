"""Tests for the Polymarket RTDS WS monitor parser (no network)."""

from datetime import UTC, datetime

from apps.monitor.polymarket_ws import ParsedTick, parse_rtds_message

NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)


def test_parse_crypto_price_update():
    raw = (
        '{"topic":"crypto_prices","type":"update","timestamp":1785000000000,'
        '"payload":{"symbol":"btcusdt","timestamp":1784999999500,"value":67234.5}}'
    )
    ticks = parse_rtds_message(raw)
    assert len(ticks) == 1
    t = ticks[0]
    assert isinstance(t, ParsedTick)
    assert t.symbol == "BTCUSD"
    assert t.price == 67234.5
    assert t.ts_source == datetime.fromtimestamp(1784999999.5, tz=UTC)
    assert t.rtt_ms == 500


def test_parse_full_accuracy_value_preferred():
    raw = (
        '{"topic":"crypto_prices","type":"update","timestamp":1000,'
        '"payload":{"symbol":"xrpusdt","timestamp":900,'
        '"value":2.0,"full_accuracy_value":"2.12345"}}'
    )
    ticks = parse_rtds_message(raw, now=NOW)
    assert ticks[0].symbol == "XRPUSD"
    assert ticks[0].price == 2.12345


def test_ignores_other_topics_and_bad_json():
    assert parse_rtds_message('{"topic":"comments","type":"update"}') == []
    assert parse_rtds_message("not json at all") == []
    assert parse_rtds_message("[1,2,3]") == []
    assert parse_rtds_message(b"\xff\xfe") == []


def test_unknown_symbol_dropped():
    raw = (
        '{"topic":"crypto_prices","type":"update","timestamp":10,'
        '"payload":{"symbol":"dogeusdt","timestamp":5,"value":1}}'
    )
    assert parse_rtds_message(raw) == []


def test_missing_or_invalid_price_dropped():
    raw = '{"topic":"crypto_prices","type":"update","payload":{"symbol":"btcusdt"}}'
    assert parse_rtds_message(raw) == []
    raw = (
        '{"topic":"crypto_prices","type":"update","timestamp":10,'
        '"payload":{"symbol":"ethusdt","timestamp":5,"value":"NaN-ish"}}'
    )
    assert parse_rtds_message(raw) == []


def test_list_frame_and_fallback_ts():
    raw = (
        '[{"topic":"crypto_prices","type":"update","payload":{"symbol":"solusdt","value":150.25}}]'
    )
    ticks = parse_rtds_message(raw, now=NOW)
    assert len(ticks) == 1
    assert ticks[0].symbol == "SOLUSD"
    assert ticks[0].price == 150.25
    assert ticks[0].ts_source == NOW  # fallback to now when no ts present
