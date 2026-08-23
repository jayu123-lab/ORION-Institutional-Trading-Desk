"""Agents + news + macro read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from core.memory.models import Analysis, MacroEvent, NewsItem

router = APIRouter(prefix="/api/v1", tags=["desk"])


@router.post("/desk/{asset}/convene")
async def convene_desk(asset: str, session: Session = Depends(get_db)) -> dict:
    """Convene the full desk for one asset (spec PRIORITY 7).

    Runs the deterministic debate engine: MarketState -> 7 analyst opinions
    -> weighted consensus (dissent preserved) -> risk constraints ->
    audit verification stamps -> CIO synthesis. Persists Analysis+Opinions.
    """
    from core.debate.engine import DeskDebateEngine
    from core.memory.database import get_session_factory

    engine = DeskDebateEngine(get_session_factory())
    debate = await engine.convene(asset)
    return debate.model_dump(mode="json")


@router.get("/desk/{asset}/debates")
def latest_debates(asset: str, limit: int = 5, session: Session = Depends(get_db)) -> list[dict]:
    rows = (
        session.execute(
            select(Analysis)
            .where(Analysis.kind == "debate", Analysis.asset == asset.upper())
            .order_by(desc(Analysis.ts))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "ts": r.ts.isoformat() if r.ts else None,
            "stance": r.stance,
            "confidence": r.confidence,
            "summary": r.output_summary[:400],
            "full": r.full_output,
        }
        for r in rows
    ]


@router.get("/agents")
def agents_status() -> list[dict]:
    """Registry roster + honest dynamic status (never fabricated)."""
    from apps.api.routers.cio import get_registry

    return get_registry().to_list()


@router.get("/news")
def news(limit: int = 30, session: Session = Depends(get_db)) -> list[dict]:
    rows = (
        session.execute(select(NewsItem).order_by(desc(NewsItem.published_at)).limit(limit))
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "title": r.title,
            "source": r.source,
            "relevance": r.relevance,
            "published_at": str(r.published_at),
            "assets": r.assets or [],
        }
        for r in rows
    ]


@router.get("/macro")
def macro_events(limit: int = 30, session: Session = Depends(get_db)) -> list[dict]:
    rows = (
        session.execute(select(MacroEvent).order_by(desc(MacroEvent.scheduled_at)).limit(limit))
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "event": r.event_name,
            "region": r.region,
            "scheduled_at": str(r.scheduled_at),
            "actual": r.actual,
            "consensus": r.consensus,
            "previous": r.previous,
            "importance": r.importance,
        }
        for r in rows
    ]
