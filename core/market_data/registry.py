"""Provider registry: map provider name → instance; per-symbol resolution.

Resolution order for a symbol:
1. explicit routing registered via :meth:`route_symbol`;
2. first registered provider whose ``supported`` set contains the symbol;
3. nothing else — if no provider supports the symbol,
   :class:`ProviderUnavailable` is raised (never silently mis-routed).

Providers without a ``supported`` attribute are never symbol-matched; they can
only be selected through explicit routing or as the no-symbol default.
"""

from __future__ import annotations

import logging

from core.market_data.base import MarketDataProvider, ProviderUnavailable

logger = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, MarketDataProvider] = {}
        self._symbol_map: dict[str, str] = {}  # SYMBOL -> provider name (explicit routing)

    def register(self, provider: MarketDataProvider) -> None:
        self._providers[provider.name] = provider

    def route_symbol(self, symbol: str, provider: str) -> None:
        self._symbol_map[symbol.upper()] = provider

    def resolve(self, symbol: str | None = None) -> MarketDataProvider:
        if not self._providers:
            raise ProviderUnavailable("no providers registered")
        if symbol is None:
            # no-symbol callers (legacy/monitor sweeps): first registered wins
            return next(iter(self._providers.values()))
        sym = symbol.upper()
        if sym in self._symbol_map:
            name = self._symbol_map[sym]
            provider = self._providers.get(name)
            if provider is None:
                raise ProviderUnavailable(f"routed provider '{name}' not registered")
            return provider
        for provider in self._providers.values():
            supported = getattr(provider, "supported", None)
            if supported is not None and sym in supported:
                return provider
        raise ProviderUnavailable(f"no registered provider supports '{sym}'")

    @property
    def names(self) -> list[str]:
        return list(self._providers)


def build_default_registry() -> ProviderRegistry:
    """Default desk registry.

    Yahoo covers indices/commodities/stocks/FX/rates (unofficial public API);
    Coinbase Exchange covers crypto spot majors (public read-only ticker);
    simulated remains as opt-in fallback for development only.
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
    if get_settings().orion_coinbase_enabled:
        try:
            from providers.crypto import CoinbaseExchangeProvider

            reg.register(CoinbaseExchangeProvider())
        except ImportError:  # pragma: no cover - package always present in repo
            logger.warning("coinbase provider unavailable")
    if get_settings().orion_simulated_enabled:
        reg.register(SimulatedDataProvider())
    return reg
