"""Market data endpoints: watchlist quotes, sessions clock, regime."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from core.config import get_settings
from core.memory.models import Candle, Quote

router = APIRouter(prefix="/api/v1/market", tags=["market"])

DEFAULT_WATCHLIST = [
    "XAUUSD",
    "XAGUSD",
    "SI",
    "HG",
    "SPX",
    "NDX",
    "NASDAQ",
    "DJI",
    "DAX",
    "IBEX",
    "FTSE",
    "VIX",
    "ES",
    "NQ",
    "CL",
    "BZ",
    "NG",
    "ZW",
    "ZC",
    "KC",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AMD",
    "NFLX",
    "JPM",
    "KO",
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "XRPUSD",
    "DXY",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "US10Y",
    "US13W",
]

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _watchlist() -> list[str]:
    path = _REPO_ROOT / "config" / "watchlist.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return list(DEFAULT_WATCHLIST)
        if isinstance(data, dict):  # {"symbols": [...], "_comment": ...}
            data = data.get("symbols", [])
        if isinstance(data, list) and data:
            return [str(s).upper() for s in data]
    return list(DEFAULT_WATCHLIST)


@router.get("/watchlist")
def watchlist() -> dict:
    return {"symbols": _watchlist(), "configurable": "config/watchlist.json"}


@router.get("/quotes")
def quotes(session: Session = Depends(get_db)) -> list[dict]:
    from providers.yahoo.adapter import PROXY_SYMBOLS

    s = get_settings()
    stale_after = timedelta(seconds=s.monitor_quote_staleness_sec)
    now = datetime.now(UTC)

    out: list[dict] = []
    for sym in _watchlist():
        q = session.execute(
            select(Quote).where(Quote.symbol == sym).order_by(desc(Quote.ts_received)).limit(1)
        ).scalar_one_or_none()
        if q is None:
            out.append({"symbol": sym, "status": "NO_DATA"})
            continue
        ts = q.ts_received if q.ts_received.tzinfo else q.ts_received.replace(tzinfo=UTC)
        status = q.status
        if q.status == "LIVE" and now - ts > stale_after:
            status = "STALE"
        # Honest labeling: XAUUSD/XAGUSD prints are COMEX front-month futures,
        # not exact spot. The dashboard must show the proxy instrument.
        proxy_of = PROXY_SYMBOLS.get(sym) if q.provider == "yahoo" else None
        out.append(
            {
                "symbol": sym,
                "price": q.price,
                "bid": q.bid,
                "ask": q.ask,
                "provider": q.provider,
                "proxy_of": proxy_of,
                "status": status,
                "ts": str(q.ts_received),
            }
        )
    return out


class QuoteIn(BaseModel):
    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    provider: str = "manual"
    status: str = "LIVE"  # callers MUST not send SIMULATED data as LIVE


@router.post("/quotes", status_code=201)
def push_quote(item: QuoteIn, session: Session = Depends(get_db)) -> dict:
    """Ingest endpoint used by the monitor and adapters."""
    from core.memory.models import utcnow

    row = Quote(
        symbol=item.symbol.upper(),
        provider=item.provider,
        price=item.price,
        bid=item.bid,
        ask=item.ask,
        volume=item.volume,
        ts_source=utcnow(),
        latency_ms=None,
        quality="B",
        status=item.status,
    )
    session.add(row)
    session.commit()
    return {"id": row.id, "symbol": row.symbol, "stored": True}


@router.get("/candles/{symbol}")
def candles(
    symbol: str, timeframe: str = "H1", limit: int = 200, session: Session = Depends(get_db)
) -> list[dict]:
    rows = (
        session.execute(
            select(Candle)
            .where(Candle.symbol == symbol.upper(), Candle.timeframe == timeframe)
            .order_by(desc(Candle.ts_open))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "o": r.open,
            "h": r.high,
            "l": r.low,
            "c": r.close,
            "volume": r.volume,
            "ts_open": str(r.ts_open),
            "status": r.status,
        }
        for r in reversed(rows)
    ]


@router.get("/sessions")
def sessions_clock() -> dict:
    from core.sessions import desk_clock

    c = desk_clock()
    return {
        "utc": c.utc.isoformat(),
        "madrid": c.madrid.isoformat(),
        "active_sessions": list(c.active_sessions),
        "next_event": {
            "name": c.next_event_name,
            "at_utc": c.next_event_utc.isoformat() if c.next_event_utc else None,
        },
    }
