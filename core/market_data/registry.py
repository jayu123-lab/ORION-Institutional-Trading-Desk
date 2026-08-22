"""Provider registry: map provider name → instance; per-symbol resolution."""

from __future__ import annotations

from core.market_data.base import MarketDataProvider, ProviderUnavailable


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
    """Phase 1 default: simulated only until real feeds are configured."""
    from core.market_data.simulated import SimulatedDataProvider

    reg = ProviderRegistry()
    reg.register(SimulatedDataProvider())
    return reg
