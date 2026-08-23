"""Offline tests for the Yahoo Finance adapter (real captured fixture)."""

import json
from pathlib import Path

import pytest

from providers.yahoo.adapter import (
    DESK_TO_YAHOO,
    YahooFinanceProvider,
    parse_candles_payload,
    parse_chart_payload,
)

FIXTURE = Path(__file__).parent / "fixtures" / "yahoo_gc_f.json"


@pytest.fixture()
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_quote_from_real_fixture(payload):
    quote = parse_chart_payload(payload, "yahoo", 120)
    assert quote.symbol == "GC=F"
    assert quote.price > 0
    assert quote.ts_source.tzinfo is not None
    assert quote.quality.provider == "yahoo"
    assert quote.quality.quality == "A"  # latency 120ms < 800
    assert quote.volume is None or quote.volume > 0


def test_parse_quality_b_on_high_latency(payload):
    quote = parse_chart_payload(payload, "yahoo", 1500)
    assert quote.quality.quality == "B"


def test_parse_rejects_empty_and_missing():
    with pytest.raises(ValueError):
        parse_chart_payload({}, "yahoo", 10)
    with pytest.raises(ValueError):
        parse_chart_payload({"chart": {"result": []}}, "yahoo", 10)
    with pytest.raises(ValueError):
        # meta without price/time must not fabricate
        parse_chart_payload({"chart": {"result": [{"meta": {}}]}}, "yahoo", 10)


def test_parse_candles_skips_null_bars(payload):
    candles = parse_candles_payload(payload, "M1", limit=100)
    assert len(candles) >= 1
    for c in candles:
        assert c.low <= c.high
        assert c.open is not None
        assert c.close is not None


def test_symbol_map_covers_all_asset_classes():
    classes = {
        "indices": ["SPX", "NDX", "NASDAQ", "DJI", "DAX", "IBEX", "FTSE", "VIX"],
        "futures": ["ES", "NQ", "CL", "BZ", "NG", "ZW", "ZC", "KC", "HG", "SI"],
        "metals_proxied": ["XAUUSD", "XAGUSD"],
        "fx_dxy": ["EURUSD", "GBPUSD", "USDJPY", "DXY"],
        "rates": ["US10Y", "US13W"],
        "stocks": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"],
    }
    for group, syms in classes.items():
        for s in syms:
            assert s in DESK_TO_YAHOO, f"{group}: missing {s}"


def test_provider_rejects_unmapped_symbol():
    provider = YahooFinanceProvider()
    import asyncio

    async def run() -> None:
        try:
            await provider.get_quote("NOEXISTO")
            raise AssertionError("should raise")
        except Exception as exc:  # noqa: BLE001
            assert type(exc).__name__ in ("ProviderUnavailable",)

    asyncio.run(run())
