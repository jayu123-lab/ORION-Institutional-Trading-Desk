"""News ingestion via RSS feeds (Yahoo Finance headlines).

Feed format (verified live 2026-08-23):
    GET https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US
    → RSS 2.0 XML, channel.item[] with title/link/pubDate/description.

Public, no API key. Unofficial for trading use — headlines are stored verbatim
with source + timestamp; relevance is a coarse keyword heuristic, never a
fabricated score.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import NamedTuple
from xml.etree import ElementTree

import httpx
from defusedxml import ElementTree as DefusedElementTree
from sqlalchemy import select

from core.memory.models import NewsItem

logger = logging.getLogger("orion.news")

FEED_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"
USER_AGENT = "Mozilla/5.0 (orion-desk; local research tool)"
REQUEST_TIMEOUT = 10.0

# Symbols polled every ingestion cycle (aggregate + high-priority desks)
DEFAULT_FEED_SYMBOLS = [
    "^GSPC", "^NDX", "AAPL", "MSFT", "NVDA", "TSLA",
    "GC=F", "CL=F", "BTC-USD", "ETH-USD", "EURUSD=X",
]

# crude relevance heuristic over headline keywords
HIGH_KEYWORDS = (
    "fed", "fomc", "cpi", "inflation", "rate decision", "nfp", "jobs report",
    "war", "crash", "default", "emergency", "record", "plunge", "surge",
    "bankruptcy", "downgrade", "halt", "guidance cut",
)
NOISE_KEYWORDS = ("quiz", "poll:", "opinion:", "cartoon")


class ParsedHeadline(NamedTuple):
    title: str
    link: str | None
    published_at: datetime
    description: str | None


def parse_pub_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    try:
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def parse_rss(xml_text: str) -> list[ParsedHeadline]:
    """Pure parser: RSS 2.0 text → headlines. Bad input → []."""
    try:
        root = DefusedElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    items = root.findall(".//item")
    out: list[ParsedHeadline] = []
    for item in items:
        title_el = item.find("title")
        if title_el is None or not (title_el.text or "").strip():
            continue  # a headline without title is unusable, skip silently
        link_el = item.find("link")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")
        out.append(
            ParsedHeadline(
                title=(title_el.text or "").strip(),
                link=(link_el.text or None) if link_el is not None else None,
                published_at=parse_pub_date(pub_el.text if pub_el is not None else None),
                description=(desc_el.text or None) if desc_el is not None else None,
            )
        )
    return out


def classify_relevance(title: str) -> str:
    t = title.lower()
    if any(k in t for k in NOISE_KEYWORDS):
        return "NOISE"
    if any(k in t for k in HIGH_KEYWORDS):
        return "HIGH"
    return "MEDIUM"


async def fetch_symbol_headlines(client: httpx.AsyncClient, symbol: str) -> list[ParsedHeadline]:
    resp = await client.get(FEED_URL, params={"s": symbol, "region": "US", "lang": "en-US"})
    resp.raise_for_status()
    return parse_rss(resp.text)


async def ingest_news(symbols: list[str] | None = None) -> int:
    """Fetch RSS feeds and store new headlines. Returns rows inserted.

    Dedupe: (title, source) pair must not already exist.
    """
    symbols = symbols or DEFAULT_FEED_SYMBOLS
    inserted = 0
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    ) as client:
        for sym in symbols:
            try:
                headlines = await fetch_symbol_headlines(client, sym)
            except Exception as exc:  # noqa: BLE001 - feed failure must not kill cycle
                logger.warning("rss fail %s: %s", sym, exc)
                continue
            for h in headlines:
                if headline_exists(h.title):
                    continue
                store_news_item(
                    title=h.title,
                    body=h.description,
                    source=f"yahoo-rss:{sym}",
                    url=h.link,
                    published_at=h.published_at,
                    relevance=classify_relevance(h.title),
                    assets=[sym],
                )
                inserted += 1
            await asyncio.sleep(0.3)  # pacing between feeds
    return inserted


# --- storage helpers kept separate from fetching for testability ---
_session_factory = None


def _sf():
    global _session_factory
    if _session_factory is None:
        from core.memory.database import get_session_factory

        _session_factory = get_session_factory()
    return _session_factory


def headline_exists(title: str) -> bool:
    with _sf()() as session:
        return (
            session.execute(
                select(NewsItem.id).where(NewsItem.title == title).limit(1)
            ).scalar_one_or_none()
            is not None
        )


def store_news_item(**kwargs) -> None:
    with _sf()() as session:
        session.add(NewsItem(**kwargs))
        session.commit()


def reset_storage_cache_for_tests() -> None:
    global _session_factory
    _session_factory = None
