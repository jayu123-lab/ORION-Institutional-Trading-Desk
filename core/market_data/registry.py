"""Provider registry: map provider name → instance; per-symbol resolution."""

from __future__ import annotations

import logging

from core.market_data.base import MarketDataProvider, ProviderUnavailable

logger = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, MarketDataProvider] = {}
        self._symbol_map: dict[str, str] = {}  # SYMBOL -> provider name (optional routing)

    def register(self, provider: MarketDataProvider) -> None:
        self._providers[provider.name] = provider

    def route_symbol(self, symbol: str, provider: str) -> None:
        self._symbol_map[symbol.upper()] = provider

    def resolve(self, symbol: str | None = None) -> MarketDataProvider:
        if symbol and symbol.upper() in self._symbol_map:
            name = self._symbol_map[symbol.upper()]
            provider = self._providers.get(name)
            if provider is None:
                raise ProviderUnavailable(f"routed provider '{name}' not registered")
            return provider
        if not self._providers:
            raise ProviderUnavailable("no providers registered")
        # first registered acts as default
        return next(iter(self._providers.values()))

    @property
    def names(self) -> list[str]:
        return list(self._providers)


def build_default_registry() -> ProviderRegistry:
    """Default desk registry.

    Yahoo covers indices/commodities/stocks/FX/rates (unofficial public API);
    Polymarket RTDS handles crypto LIVE separately; simulated remains as
    opt-in fallback for development only.
    """
    from core.config import get_settings
    from core.market_data.simulated import SimulatedDataProvider

    reg = ProviderRegistry()
    if get_settings().orion_yahoo_enabled:
        try:
            from providers.yahoo import YahooFinanceProvider

            reg.register(YahooFinanceProvider())
        except ImportError:  # pragma: no cover - package always present in repo
            logger.warning("yahoo provider unavailable")
    if get_settings().orion_simulated_enabled:
        reg.register(SimulatedDataProvider())
    return reg
