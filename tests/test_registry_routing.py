"""Registry symbol routing: explicit route > supported set > ProviderUnavailable."""

import pytest

from core.market_data.base import MarketDataProvider, ProviderUnavailable, Quote
from core.market_data.registry import ProviderRegistry
from core.market_data.simulated import SimulatedDataProvider


def _quote(symbol: str, provider_name: str) -> Quote:
    from datetime import UTC, datetime

    from core.market_data.base import DataQuality, DataStatus

    return Quote(
        symbol=symbol,
        price=1.0,
        ts_source=datetime.now(UTC),
        quality=DataQuality(provider=provider_name, status=DataStatus.LIVE),
    )


class _FakeProvider(MarketDataProvider):
    def __init__(self, name: str, supported: frozenset[str] | None) -> None:
        self.name = name
        self.supported = supported

    async def get_quote(self, symbol: str) -> Quote:
        return _quote(symbol, self.name)

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 200):  # noqa: ANN201
        return []


_YAHOO_LIKE = frozenset({"XAUUSD", "SPX", "DXY", "US10Y"})
_CRYPTO_LIKE = frozenset({"BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD"})


def test_explicit_route_beats_registration_order():
    reg = ProviderRegistry()
    yahoo = _FakeProvider("yahoo", _YAHOO_LIKE)
    other = _FakeProvider("coinbase", _CRYPTO_LIKE | {"XAUUSD"})  # also supports XAUUSD
    reg.register(yahoo)
    reg.register(other)
    reg.route_symbol("XAUUSD", "coinbase")
    assert reg.resolve("XAUUSD") is other


def test_resolve_by_supported_set():
    reg = ProviderRegistry()
    yahoo = _FakeProvider("yahoo", _YAHOO_LIKE)
    crypto = _FakeProvider("coinbase", _CRYPTO_LIKE)
    reg.register(yahoo)
    reg.register(crypto)
    # crypto symbols must NOT fall through to the first-registered provider
    assert reg.resolve("BTCUSD") is crypto
    assert reg.resolve("XRPUSD") is crypto
    assert reg.resolve("SPX") is yahoo
    assert reg.resolve("xauusd") is yahoo  # case-insensitive


def test_unsupported_symbol_raises():
    reg = ProviderRegistry()
    reg.register(_FakeProvider("yahoo", _YAHOO_LIKE))
    with pytest.raises(ProviderUnavailable):
        reg.resolve("BTCUSD")
    with pytest.raises(ProviderUnavailable):
        reg.resolve("NOPE")


def test_routed_provider_must_be_registered():
    reg = ProviderRegistry()
    reg.register(_FakeProvider("yahoo", _YAHOO_LIKE))
    reg.route_symbol("BTCUSD", "ghost")
    with pytest.raises(ProviderUnavailable):
        reg.resolve("BTCUSD")


def test_no_symbol_returns_first_registered_default():
    reg = ProviderRegistry()
    first = _FakeProvider("yahoo", _YAHOO_LIKE)
    second = _FakeProvider("simulated", None)
    reg.register(first)
    reg.register(second)
    assert reg.resolve() is first


def test_empty_registry_raises():
    with pytest.raises(ProviderUnavailable):
        ProviderRegistry().resolve("BTCUSD")


def test_simulated_only_when_registered_and_supporting():
    sim = SimulatedDataProvider()
    assert sim.supported is not None and "BTCUSD" in sim.supported
    reg = ProviderRegistry()
    reg.register(_FakeProvider("yahoo", _YAHOO_LIKE))  # simulated NOT registered
    with pytest.raises(ProviderUnavailable):
        reg.resolve("BTCUSD")
    reg.register(sim)
    assert reg.resolve("BTCUSD") is sim  # only after being registered (enabled)


def test_provider_without_supported_attr_never_symbol_matched():
    reg = ProviderRegistry()
    blind = _FakeProvider("blind", None)
    reg.register(blind)
    with pytest.raises(ProviderUnavailable):
        reg.resolve("ANYTHING")  # no supported attr → not a catch-all
