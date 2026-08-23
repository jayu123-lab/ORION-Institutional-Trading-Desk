"""Yahoo Finance market-data adapter â€” multi-asset coverage.

Covers indices, equity futures, commodities futures, single stocks, FX and
US Treasury yields through the public chart endpoint:

    GET https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}
        ?interval=1m&range=1d

Verified empirically on 2026-08-23 (GC=F 4680.6 COMEX, ^GSPC 7674.37 SNP,
AAPL 309.35 NasdaqGS, EURUSD=X 1.1678 CCY, ^TNX 4.738 Cboe Indices,
CL=F 87.06 / NG=F 2.811 NYM, ZW=F 699.25 USX-cents CBOT, ^NDX 29308.86).
This endpoint is UNOFFICIAL (no public SLA/ToS guarantee) â€” treat as
best-effort; failures degrade to DISCONNECTED, never fabricated data.

Symbol proxy note: spot gold/silver are not served by Yahoo; XAUUSD/XAGUSD
are proxied with the COMEX front-month future (GC=F / SI=F), a common desk
practice. The quote keeps provider="yahoo" so agents can see the source.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from urllib.parse import quote as url_quote

import httpx

from core.market_data.base import (
    Candle,
    DataQuality,
    DataStatus,
    MarketDataProvider,
    ProviderUnavailable,
    Quote,
)

logger = logging.getLogger("orion.yahoo")

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = "Mozilla/5.0 (orion-desk; local research tool)"
QUOTE_TTL_SEC = 60
REQUEST_TIMEOUT = 10.0
REQUEST_GAP_SEC = 0.35  # gentle pacing between upstream calls

# desk symbol -> yahoo chart symbol
DESK_TO_YAHOO: dict[str, str] = {
    # Indices
    "SPX": "^GSPC",
    "NDX": "^NDX",
    "NASDAQ": "^IXIC",
    "DJI": "^DJI",
    "DAX": "^GDAXI",
    "IBEX": "^IBEX",
    "FTSE": "^FTSE",
    "VIX": "^VIX",
    # Equity index futures
    "ES": "ES=F",
    "NQ": "NQ=F",
    # Metals (spot proxied by front-month future â€” see PROXY_SYMBOLS)
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "SI": "SI=F",
    "HG": "HG=F",
    # Metals futures (direct contracts, verified on Yahoo 2026-08-23, CMX)
    "GC": "GC=F",
    "MGC": "MGC=F",
    # Energy & agriculture
    "CL": "CL=F",
    "BZ": "BZ=F",
    "NG": "NG=F",
    "ZW": "ZW=F",
    "ZC": "ZC=F",
    "KC": "KC=F",
    # FX & DXY
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "DXY": "DX-Y.NYB",
    # Rates (yields)
    "US10Y": "^TNX",
    "US13W": "^IRX",
    # Single stocks (megacap core)
}
STOCKS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "JPM", "KO"]
for _s in STOCKS:
    DESK_TO_YAHOO[_s] = _s

# Desk symbols served through a DIFFERENT instrument than their name implies.
# The dashboard MUST surface this so a futures print is never shown as exact
# spot XAUUSD. Verified proxies (front-month COMEX future):
PROXY_SYMBOLS: dict[str, str] = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
}

TIMEFRAME_MAP = {  # timeframe -> (interval, range)
    "M1": ("1m", "1d"),
    "M5": ("5m", "5d"),
    "M15": ("15m", "5d"),
    "H1": ("60m", "1mo"),
    "D1": ("1d", "1y"),
}


def yahoo_symbol_of(desk_symbol: str) -> str | None:
    return DESK_TO_YAHOO.get(desk_symbol.upper())


def parse_chart_payload(payload: dict, provider: str, latency_ms: int | None) -> Quote:
    """Pure parser: yahoo chart result -> Quote. Raises ValueError if unusable."""
    result = ((payload or {}).get("chart") or {}).get("result") or []
    if not result:
        raise ValueError("empty chart result")
    meta = result[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    ts_epoch = meta.get("regularMarketTime")
    if price is None or ts_epoch is None:
        raise ValueError("missing regularMarketPrice/regularMarketTime")
    volume = None
    try:
        series = (((result[0].get("indicators") or {}).get("quote") or [{}])[0])
        vols = series.get("volume") or []
        tail = [v for v in vols[-30:] if isinstance(v, (int, float))]
        volume = float(sum(tail) / len(tail)) if tail else None  # avg of last bars
    except (IndexError, TypeError):
        volume = None
    quality_a = latency_ms is not None and latency_ms < 800
    return Quote(
        symbol=str(meta.get("symbol", "")),
        price=float(price),
        bid=None,
        ask=None,
        volume=volume,
        ts_source=datetime.fromtimestamp(int(ts_epoch), tz=UTC),
        quality=DataQuality(
            provider=provider,
            latency_ms=latency_ms,
            quality="A" if quality_a else "B",
            status=DataStatus.LIVE,
        ),
    )


def parse_candles_payload(payload: dict, timeframe: str, limit: int) -> list[Candle]:
    """Pure parser: yahoo chart result -> candles oldestâ†’newest."""
    result = ((payload or {}).get("chart") or {}).get("result") or []
    if not result:
        raise ValueError("empty chart result")
    r0 = result[0]
    stamps = r0.get("timestamp") or []
    series = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    opens, highs, lows, closes, volumes = (
        series.get("open") or [],
        series.get("high") or [],
        series.get("low") or [],
        series.get("close") or [],
        series.get("volume") or [],
    )
    out: list[Candle] = []
    for i, ts in enumerate(stamps):

        def val(key_arr: list, idx: int) -> float | None:
            try:
                v = key_arr[idx]
                return float(v) if isinstance(v, (int, float)) else None
            except IndexError:
                return None

        o, h, low_v, c = val(opens, i), val(highs, i), val(lows, i), val(closes, i)
        if o is None or h is None or low_v is None or c is None:
            continue  # skip incomplete bars, never fabricate
        v = val(volumes, i)
        out.append(
            Candle(
                symbol=str(r0.get("meta", {}).get("symbol", "")),
                timeframe=timeframe,
                open=o,
                high=h,
                low=low_v,
                close=c,
                volume=v,
                ts_open=datetime.fromtimestamp(int(ts), tz=UTC),
                quality=DataQuality(provider="yahoo", status=DataStatus.LIVE),
            )
        )
    return out[-limit:]


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo"

    def __init__(self, base_url: str | None = None) -> None:
        self.supported = frozenset(DESK_TO_YAHOO)
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, tuple[float, Quote]] = {}
        self._last_request_ts = 0.0
        self._url = (base_url or CHART_URL).rstrip("/")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
            )
        return self._client

    async def _paced_get(self, url: str, params: dict) -> dict:
        gap = time.monotonic() - self._last_request_ts
        if gap < REQUEST_GAP_SEC:
            await asyncio.sleep(REQUEST_GAP_SEC - gap)
        client = await self._get_client()
        t0 = time.monotonic()
        resp = await client.get(url, params=params)
        self._last_request_ts = time.monotonic()
        resp.raise_for_status()
        payload = resp.json()
        payload["_latency_ms"] = int((time.monotonic() - t0) * 1000)
        return payload

    async def get_quote(self, symbol: str) -> Quote:
        desk_sym = symbol.upper()
        ysym = DESK_TO_YAHOO.get(desk_sym)
        if ysym is None:
            raise ProviderUnavailable(f"yahoo: no mapping for '{desk_sym}'")
        cached = self._cache.get(desk_sym)
        now = time.monotonic()
        if cached is not None and now - cached[0] < QUOTE_TTL_SEC:
            return cached[1]
        payload = await self._paced_get(
            self._url.format(symbol=url_quote(ysym, safe="")),
            {"interval": "1m", "range": "1d"},
        )
        latency = payload.pop("_latency_ms", None)
        quote = parse_chart_payload(payload, self.name, latency)
        quote.symbol = desk_sym  # normalize back to desk symbol
        self._cache[desk_sym] = (now, quote)
        return quote

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        desk_sym = symbol.upper()
        ysym = DESK_TO_YAHOO.get(desk_sym)
        if ysym is None:
            raise ProviderUnavailable(f"yahoo: no mapping for '{desk_sym}'")
        interval_range = TIMEFRAME_MAP.get(timeframe.upper())
        if interval_range is None:
            raise ProviderUnavailable(f"yahoo: unsupported timeframe '{timeframe}'")
        interval, rng = interval_range
        payload = await self._paced_get(
            self._url.format(symbol=url_quote(ysym, safe="")),
            {"interval": interval, "range": rng},
        )
        payload.pop("_latency_ms", None)
        return parse_candles_payload(payload, timeframe.upper(), limit)

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
