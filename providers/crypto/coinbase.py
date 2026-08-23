"""Coinbase Exchange market-data adapter — crypto spot majors, read-only.

Public, unauthenticated REST endpoints (official docs:
https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproductticker
and ..._getproductcandles; verified live 2026-08-23):

    GET https://api.exchange.coinbase.com/products/{product_id}/ticker
    GET https://api.exchange.coinbase.com/products/{product_id}/candles

`price` is the last executed trade on Coinbase Exchange (not a mid/rate we
compute); bid/ask are the top-of-book levels. Failures degrade to
ProviderUnavailable — never fabricated data.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import httpx

from core.market_data.base import (
    Candle,
    DataQuality,
    DataStatus,
    MarketDataProvider,
    ProviderUnavailable,
    Quote,
)

logger = logging.getLogger("orion.coinbase")

TICKER_URL = "https://api.exchange.coinbase.com/products/{product_id}/ticker"
CANDLES_URL = "https://api.exchange.coinbase.com/products/{product_id}/candles"
USER_AGENT = "Mozilla/5.0 (orion-desk; local research tool)"
REQUEST_TIMEOUT = 10.0
QUOTE_TTL_SEC = 20  # exchange rate-limits: 10 public req/s per IP; stay polite

# desk symbol -> Coinbase product id
DESK_TO_PRODUCT: dict[str, str] = {
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "XRPUSD": "XRP-USD",
    "SOLUSD": "SOL-USD",
}

TIMEFRAME_GRANULARITY_SEC = {  # desk timeframe -> candle granularity (seconds)
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "D1": 86400,
}


def _to_float(value) -> float | None:  # noqa: ANN001
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_ticker(desk_symbol: str, payload: dict, provider: str, latency_ms: int | None) -> Quote:
    """Pure parser: coinbase ticker JSON -> Quote. Raises ValueError if unusable."""
    price = _to_float(payload.get("price"))
    ts_raw = payload.get("time")
    if price is None or not ts_raw:
        raise ValueError("missing price/time in ticker payload")
    # e.g. '2026-08-23T10:06:28.952333Z'
    ts_source = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
    quality_a = latency_ms is not None and latency_ms < 800
    return Quote(
        symbol=desk_symbol,
        price=price,
        bid=_to_float(payload.get("bid")),
        ask=_to_float(payload.get("ask")),
        volume=_to_float(payload.get("volume")),  # 24h volume in base currency
        ts_source=ts_source,
        quality=DataQuality(
            provider=provider,
            latency_ms=latency_ms,
            quality="A" if quality_a else "B",
            status=DataStatus.LIVE,
        ),
    )


def parse_candles_payload(payload: list, timeframe: str, limit: int) -> list[Candle]:
    """Pure parser: coinbase candles array -> candles oldest→newest.

    Each row is [time_epoch_sec, low, high, open, close, volume], newest first.
    """
    out: list[Candle] = []
    for row in payload or []:
        try:
            ts_epoch, low, high, open_, close, volume = (float(v) for v in row)
        except (TypeError, ValueError):
            continue  # skip malformed rows, never fabricate
        out.append(
            Candle(
                symbol="",  # filled by caller with the DESK symbol
                timeframe=timeframe,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                ts_open=datetime.fromtimestamp(int(ts_epoch), tz=UTC),
                quality=DataQuality(provider="coinbase", status=DataStatus.LIVE),
            )
        )
    out.reverse()  # API returns newest-first → oldest→newest
    return out[-limit:]


class CoinbaseExchangeProvider(MarketDataProvider):
    name = "coinbase"

    def __init__(self) -> None:
        self.supported = frozenset(DESK_TO_PRODUCT)
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, tuple[float, Quote]] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}
            )
        return self._client

    async def get_quote(self, symbol: str) -> Quote:
        desk_sym = symbol.upper()
        product = DESK_TO_PRODUCT.get(desk_sym)
        if product is None:
            raise ProviderUnavailable(f"coinbase: no mapping for '{desk_sym}'")
        cached = self._cache.get(desk_sym)
        now = time.monotonic()
        if cached is not None and now - cached[0] < QUOTE_TTL_SEC:
            return cached[1]
        client = await self._get_client()
        t0 = time.monotonic()
        resp = await client.get(TICKER_URL.format(product_id=product))
        latency = int((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        quote = parse_ticker(desk_sym, resp.json(), self.name, latency)
        self._cache[desk_sym] = (now, quote)
        return quote

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        desk_sym = symbol.upper()
        product = DESK_TO_PRODUCT.get(desk_sym)
        if product is None:
            raise ProviderUnavailable(f"coinbase: no mapping for '{desk_sym}'")
        granularity = TIMEFRAME_GRANULARITY_SEC.get(timeframe.upper())
        if granularity is None:
            raise ProviderUnavailable(f"coinbase: unsupported timeframe '{timeframe}'")
        client = await self._get_client()
        resp = await client.get(
            CANDLES_URL.format(product_id=product),
            params={"granularity": granularity},
        )
        resp.raise_for_status()
        candles = parse_candles_payload(resp.json(), timeframe.upper(), limit)
        for c in candles:
            c.symbol = desk_sym
        return candles

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
