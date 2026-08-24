"""Command Center endpoints (P17-P18, P34).

- GET /api/v1/command/ticker          — top ticker quotes (real stored)
- GET /api/v1/command/intelligence    — right-panel feed (news/risk/CIO/watch)
- GET /api/v1/command/watches         — watch-mode registry state
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from core.desk.watch import evaluate_watches, list_watches
from core.memory.database import get_session_factory
from core.memory.models import Alert, Analysis, NewsItem, OpportunityCandidate, Quote
from core.news import filter_relevant_news

router = APIRouter(prefix="/api/v1/command", tags=["command"])

TICKER_SYMBOLS = (
    "XAUUSD", "NQ", "EURUSD", "GBPUSD",  # priority watch: gold, Nasdaq, EUR, GBP
    "DXY", "US10Y", "VIX", "SPX", "BTCUSD", "XRPUSD",
)


def _latest_relative_volume(session: Session, sym: str) -> float | None:
    """Real relative-volume reading from the scanner's feature pipeline for
    this symbol, if one has run recently. Never fabricated — None when the
    scanner has not produced a candidate for this symbol yet."""
    row = session.execute(
        select(OpportunityCandidate)
        .where(OpportunityCandidate.symbol == sym)
        .order_by(desc(OpportunityCandidate.ts))
        .limit(1)
    ).scalar_one_or_none()
    if row is None or not row.features:
        return None
    rv = row.features.get("relative_volume")
    return float(rv) if isinstance(rv, (int, float)) else None


@router.get("/ticker")
def ticker(session: Session = Depends(get_db)) -> dict:
    now = datetime.now(UTC)
    out: list[dict] = []
    for sym in TICKER_SYMBOLS:
        row = (
            session.execute(
                select(Quote).where(Quote.symbol == sym).order_by(desc(Quote.id)).limit(1)
            )
            .scalars()
            .first()
        )
        if row is None:
            out.append({
                "symbol": sym, "price": None, "status": "NOT_AVAILABLE",
                "volume": None, "relative_volume": _latest_relative_volume(session, sym),
            })
            continue
        ts = (
            row.ts_received.replace(tzinfo=UTC)
            if row.ts_received.tzinfo is None
            else row.ts_received
        )
        age_s = max(0.0, (now - ts).total_seconds())
        status = row.status
        if status == "LIVE" and age_s > 300:
            status = "STALE"
        prev_close = session.execute(
            select(Quote.price)
            .where(Quote.symbol == sym, Quote.id < row.id)
            .order_by(desc(Quote.id))
            .limit(1)
        ).scalar_one_or_none()
        change_pct = (
            round((float(row.price) - float(prev_close)) / float(prev_close) * 100, 3)
            if isinstance(prev_close, (int, float)) and prev_close and row.price
            else None
        )
        out.append(
            {
                "symbol": sym,
                "price": row.price,
                "change_pct": change_pct,
                "status": status,
                "ts": ts.isoformat(),
                "provider": row.provider,
                "volume": row.volume,
                "relative_volume": _latest_relative_volume(session, sym),
            }
        )
    return {"ticker": out, "ts": now.isoformat()}


@router.get("/intelligence")
def intelligence(session: Session = Depends(get_db)) -> dict:
    """Right panel feed — every item REAL and provenance-labelled."""
    news = (
        session.execute(select(NewsItem).order_by(desc(NewsItem.published_at)).limit(50))
        .scalars()
        .all()
    )
    latest_cio = (
        session.execute(
            select(Analysis)
            .where(Analysis.kind.in_(("cio", "cio_brief")))
            .order_by(desc(Analysis.ts))
            .limit(1)
        )
        .scalars()
        .first()
    )
    latest_debate = (
        session.execute(
            select(Analysis).where(Analysis.kind == "debate").order_by(desc(Analysis.ts)).limit(1)
        )
        .scalars()
        .first()
    )
    risk_alerts = (
        session.execute(
            select(Alert).where(Alert.rule_kind == "SPIKE").order_by(desc(Alert.ts)).limit(3)
        )
        .scalars()
        .all()
    )

    relevant_news = filter_relevant_news(news, limit=5)
    return {
        "latest_news": relevant_news,
        "macro_flag": relevant_news[0] if relevant_news else None,
        "liquidity_event": _last_liquidity_event(latest_debate),
        "risk_warnings": [
            {"message": a.message, "severity": a.severity, "ts": a.ts.isoformat() if a.ts else None}
            for a in risk_alerts
        ],
        "cio_decision": {
            "asset": latest_cio.asset if latest_cio else None,
            "stance": latest_cio.stance if latest_cio else None,
            "summary": (latest_cio.output_summary or "")[:280] if latest_cio else None,
            "ts": latest_cio.ts.isoformat() if latest_cio and latest_cio.ts else None,
        },
        "ts": datetime.now(UTC).isoformat(),
    }


def _macro_flag(item: NewsItem | None) -> dict | None:
    if item is None:
        return None
    return {
        "title": item.title,
        "source": item.source,
        "relevance": item.relevance,
        "ts": item.published_at.isoformat() if item.published_at else None,
    }


def _last_liquidity_event(debate_row: Analysis | None) -> dict | None:
    if debate_row is None:
        return None
    summary = debate_row.full_output or ""
    marker = "LIQUIDITY:"
    idx = summary.find(marker)
    snippet = ""
    if idx >= 0:
        chunk = summary[idx + len(marker) : idx + 400]
        line = next((ln.strip(" -") for ln in chunk.splitlines() if ln.strip()), "")
        snippet = line[:220]
    return {
        "asset": debate_row.asset,
        "event": snippet or "no pools mapped yet",
        "provenance": "DERIVED",
        "ts": debate_row.ts.isoformat() if debate_row.ts else None,
    }


@router.get("/watches")
def watches(evaluate: bool = False, session: Session = Depends(get_db)) -> dict:
    factory = get_session_factory(cast(Engine, session.get_bind()))
    if evaluate:
        evaluate_watches(factory)
    return {"watches": list_watches(factory)}
