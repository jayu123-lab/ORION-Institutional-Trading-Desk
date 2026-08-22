"""Polymarket read-only adapter.

Official docs (verified 2026-08-23):
- Gamma API (public, no auth): https://gamma-api.polymarket.com
  GET /markets?closed=false&limit=N&order=volumeNum&ascending=false, /events, /markets?slug=
- CLOB API: https://clob.polymarket.com  (public reads; trading requires L2 auth — out of scope)
- WS market channel: wss://ws-subscriptions-clob.polymarket.com/ws/market
  subscribe: {"assets_ids": [...], "type": "market"}

Known gotcha handled here: Gamma returns outcomePrices/outcomes/clobTokenIds as
JSON-encoded STRINGS that must be parsed before indexing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

from core.config import get_settings

logger = logging.getLogger("orion.polymarket")


class PolymarketError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketSummary:
    id: str
    question: str
    slug: str
    yes_price: float | None
    no_price: float | None
    spread: float | None
    volume: float | None
    liquidity: float | None
    end_date: str | None
    token_ids: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "slug": self.slug,
            "yes_price": self.yes_price,
            "no_price": self.no_price,
            "spread": self.spread,
            "volume": self.volume,
            "liquidity": self.liquidity,
            "end_date": self.end_date,
            "token_ids": self.token_ids,
        }


def _parse_jsonish(value: object) -> list:
    """Gamma sometimes returns JSON-encoded strings for array fields."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _to_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


class PolymarketAdapter:
    name = "polymarket"

    def __init__(self, timeout: float = 15.0) -> None:
        s = get_settings()
        self.gamma_url = s.polymarket_gamma_base_url.rstrip("/")
        self.clob_url = s.polymarket_clob_base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------- Gamma API
    async def list_markets(
        self,
        closed: bool = False,
        limit: int = 20,
        order: str = "volumeNum",
        ascending: bool = False,
    ) -> list[MarketSummary]:
        params = {
            "closed": str(closed).lower(),
            "limit": limit,
            "order": order,
            "ascending": str(ascending).lower(),
        }
        resp = await self._request(f"{self.gamma_url}/markets", params)
        return [self._summarize(m) for m in resp if isinstance(m, dict)]

    async def search_events(self, query: str, limit: int = 10) -> list[dict]:
        try:
            search = await self._request(
                f"{self.gamma_url}/public-search", {"q": query, "limit_per_type": limit}
            )
        except PolymarketError:
            return []
        events = search.get("events", []) if isinstance(search, dict) else []
        return [e for e in events if isinstance(e, dict)]

    async def get_market_by_slug(self, slug: str) -> MarketSummary | None:
        markets = await self._request(f"{self.gamma_url}/markets", {"slug": slug})
        for m in markets:
            if isinstance(m, dict) and m.get("slug") == slug:
                return self._summarize(m)
        return None

    # -------------------------------------------------------------- CLOB API
    async def get_order_book(self, token_id: str) -> dict:
        data = await self._request(f"{self.clob_url}/book", {"token_id": token_id})
        return data if isinstance(data, dict) else {}

    async def get_midpoint(self, token_id: str) -> float | None:
        data = await self._request(f"{self.clob_url}/midpoint", {"token_id": token_id})
        return _to_float(data.get("mid")) if isinstance(data, dict) else None

    async def get_last_trade_price(self, token_id: str) -> float | None:
        data = await self._request(f"{self.clob_url}/last-trade-price", {"token_id": token_id})
        return _to_float(data.get("price")) if isinstance(data, dict) else None

    # ---------------------------------------------------------------- internals
    async def _request(self, url: str, params: dict) -> list | dict:
        params = {k: v for k, v in params.items() if v is not None}
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.warning("polymarket request failed %s: %s", url, exc)
            raise PolymarketError(str(exc)) from exc

    def _summarize(self, m: dict) -> MarketSummary:
        prices = [_to_float(p) for p in _parse_jsonish(m.get("outcomePrices"))]
        tokens = [str(t) for t in _parse_jsonish(m.get("clobTokenIds"))]
        yes = next((p for p in prices if p is not None), None)
        no = next((p for p in reversed(prices) if p is not None), None)
        spread = None
        if yes is not None and no is not None and yes + no != 0:
            pass  # real spread needs the book; keep None rather than fake it
        return MarketSummary(
            id=str(m.get("id", "")),
            question=str(m.get("question", "")),
            slug=str(m.get("slug", "")),
            yes_price=yes,
            no_price=no,
            spread=spread,
            volume=_to_float(m.get("volumeNum")),
            liquidity=_to_float(m.get("liquidityNum")),
            end_date=m.get("endDate"),
            token_ids=tokens,
        )
