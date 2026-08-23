"""Simulated data provider — ALWAYS tagged DataStatus.SIMULATED.

Used for paper-trading demos and tests. Its output must never be displayed
or stored without the SIMULATED status attached.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from core.market_data.base import (
    Candle,
    DataQuality,
    DataStatus,
    MarketDataProvider,
    ProviderUnavailable,
    Quote,
)
from core.provenance import ProvenanceType

_BASE_PRICES: dict[str, float] = {
    "XAUUSD": 2350.0,
    "BTCUSD": 65000.0,
    "ETHUSD": 3400.0,
    "XRPUSD": 0.62,
    "SOLUSD": 150.0,
}


class SimulatedDataProvider(MarketDataProvider):
    """Deterministic sine-wave walk around a base price (seeded by symbol+time)."""

    name = "simulated"
    supported = frozenset(_BASE_PRICES)

    def _price_at(self, symbol: str, ts: datetime) -> float:
        base = _BASE_PRICES.get(symbol.upper())
        if base is None:
            raise ProviderUnavailable(f"no simulated config for {symbol}")
        phase = ts.timestamp() / 3600.0
        wave = math.sin(phase * 2 * math.pi / 6.0) + 0.4 * math.sin(phase * 2 * math.pi / 17.0)
        return round(base * (1 + 0.01 * wave), 6)

    async def get_quote(self, symbol: str) -> Quote:
        now = datetime.now(UTC)
        price = self._price_at(symbol, now)
        spread = price * 0.0002
        return Quote(
            symbol=symbol.upper(),
            price=price,
            bid=round(price - spread / 2, 6),
            ask=round(price + spread / 2, 6),
            volume=None,
            ts_source=now,
            quality=DataQuality(
                provider=self.name,
                status=DataStatus.SIMULATED,
                quality="C",
                provenance=ProvenanceType.SIMULATED,
            ),
        )

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        step_min = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}.get(timeframe)
        if step_min is None:
            raise ProviderUnavailable(f"unsupported timeframe {timeframe}")
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        out: list[Candle] = []
        for i in range(limit, 0, -1):
            ts_open = now - timedelta(minutes=step_min * i)
            o = self._price_at(symbol, ts_open)
            c = self._price_at(symbol, ts_open + timedelta(minutes=step_min))
            hi = max(o, c) * 1.001
            lo = min(o, c) * 0.999
            out.append(
                Candle(
                    symbol=symbol.upper(),
                    timeframe=timeframe,
                    open=o,
                    high=round(hi, 6),
                    low=round(lo, 6),
                    close=c,
                    volume=None,
                    ts_open=ts_open,
                    quality=DataQuality(
                        provider=self.name,
                        status=DataStatus.SIMULATED,
                        quality="C",
                        provenance=ProvenanceType.SIMULATED,
                    ),
                )
            )
        return out
