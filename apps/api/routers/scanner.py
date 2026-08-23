"""Always-on scanner status and opportunity radar."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from core.memory.models import OpportunityCandidate
from core.scanner.service import scanner_status

router = APIRouter(prefix="/api/v1/scanner", tags=["scanner"])


@router.get("/status")
def status(session: Session = Depends(get_db)) -> dict:
    state = scanner_status()
    latest = session.execute(
        select(OpportunityCandidate).order_by(desc(OpportunityCandidate.ts)).limit(1)
    ).scalar_one_or_none()
    if latest is not None and latest.ts is not None:
        recent = latest.ts.replace(tzinfo=UTC) >= datetime.now(UTC) - timedelta(minutes=2)
        state.update(running=recent, last_scan=latest.ts.isoformat())
    return state


@router.get("/radar")
def radar(limit: int = 25, session: Session = Depends(get_db)) -> dict:
    rows = (
        session.execute(
            select(OpportunityCandidate)
            .order_by(desc(OpportunityCandidate.opportunity_score), desc(OpportunityCandidate.ts))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return {
        "opportunities": [
            {
                "setup_id": row.setup_id,
                "symbol": row.symbol,
                "setup": row.setup,
                "state": row.state,
                "opportunity": row.opportunity_score,
                "bias": row.bias_score,
                "trade_quality": row.trade_quality,
                "adx": row.features.get("adx"),
                "volume": row.features.get("volume"),
                "rr": row.subscores.get("rr"),
                "stat_edge": row.subscores.get("statistical_edge"),
                "last_update": row.ts.isoformat() if row.ts else None,
                "reason": row.reason,
            }
            for row in rows
        ]
    }
