"""Offline tests for the Coinbase Exchange adapter (public spot ticker/candles)."""

import pytest

from providers.crypto.coinbase import (
    DESK_TO_PRODUCT,
    CoinbaseExchangeProvider,
    parse_candles_payload,
    parse_ticker,
)

TICKER = {
    "trade_id": 123456,
    "price": "76663.06",
    "size": "0.012",
    "bid": "76662.99",
    "ask": "76672.0",
    "volume": "11234.56",
    "time": "2026-08-23T10:06:28.952333Z",
}


def test_parse_ticker_full_payload():
    q = parse_ticker("BTCUSD", TICKER, "coinbase", 120)
    assert q.symbol == "BTCUSD"
    assert q.price == 76663.06
    assert q.bid == 76662.99
    assert q.ask == 76672.0
    assert q.volume == 11234.56
    assert q.ts_source.tzinfo is not None
    assert q.quality.provider == "coinbase"
    assert q.quality.quality == "A"  # latency 120ms < 800
    assert q.quality.status.value == "LIVE"


def test_parse_ticker_quality_b_on_high_latency():
    q = parse_ticker("ETHUSD", TICKER, "coinbase", 1500)
    assert q.quality.quality == "B"


def test_parse_ticker_rejects_missing_fields():
    with pytest.raises(ValueError):
        parse_ticker("BTCUSD", {}, "coinbase", 10)
    with pytest.raises(ValueError):
        parse_ticker("BTCUSD", {"price": "1.0"}, "coinbase", 10)  # no time


def test_parse_candles_newest_first_input_becomes_oldest_first():
    payload = [
        [1787500000, 100.0, 110.0, 101.0, 108.0, 12.5],
        [1787496400, 98.0, 105.0, 99.0, 100.5, 8.1],
    ]
    candles = parse_candles_payload(payload, "H1", limit=200)
    assert len(candles) == 2
    assert candles[0].ts_open < candles[1].ts_open  # oldest→newest
    first, second = candles
    assert (first.open, first.high, first.low, first.close) == (99.0, 105.0, 98.0, 100.5)
    assert second.close == 108.0


def test_parse_candles_skips_malformed_rows():
    payload = [
        [1787500000, 100.0, 110.0, 101.0, 108.0, 12.5],
        ["bad", "row"],
        [None, None, None, None, None, None],
    ]
    candles = parse_candles_payload(payload, "M1", limit=200)
    assert len(candles) == 1


def test_provider_mapping_and_supported():
    p = CoinbaseExchangeProvider()
    assert p.name == "coinbase"
    for desk in ("BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD"):
        assert desk in p.supported
        assert DESK_TO_PRODUCT[desk].endswith("-USD")
    assert p.supported.isdisjoint({"XAUUSD", "SPX"})  # never claims non-crypto symbols
