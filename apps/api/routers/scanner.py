"""Always-on scanner status and opportunity radar."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from core.config import get_settings
from core.memory.models import OpportunityCandidate, OpportunityTransition
from core.notifications import notify_windows
from core.scanner.service import ACTIVE_STATES, scanner_status

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
    latest_by_symbol: dict[str, OpportunityCandidate] = {}
    rows = (
        session.execute(select(OpportunityCandidate).order_by(desc(OpportunityCandidate.ts)))
        .scalars()
        .all()
    )
    for row in rows:
        latest_by_symbol.setdefault(row.symbol, row)
    state["watchlist"] = [
        {
            "symbol": symbol,
            "state": (
                "NO DATA"
                if symbol not in latest_by_symbol
                else "SETUP ACTIVE"
                if latest_by_symbol[symbol].setup != "NO_QUALIFIED_SETUP"
                else "WATCHING"
            ),
        }
        for symbol in state["symbols"]
    ]
    state["unique_active_setups"] = sum(
        row.setup != "NO_QUALIFIED_SETUP" and row.state in ACTIVE_STATES
        for row in latest_by_symbol.values()
    )
    return state


@router.get("/radar")
def radar(limit: int = 15, session: Session = Depends(get_db)) -> dict:
    rows = (
        session.execute(
            select(OpportunityCandidate)
            .where(
                OpportunityCandidate.state.in_(ACTIVE_STATES),
                OpportunityCandidate.setup != "NO_QUALIFIED_SETUP",
                func.length(OpportunityCandidate.setup_id) == 24,
            )
            .order_by(desc(OpportunityCandidate.opportunity_score), desc(OpportunityCandidate.ts))
            .limit(min(limit, 15))
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
                "direction": row.direction,
                "opportunity": row.opportunity_score,
                "bias": row.bias_score,
                "trade_quality": row.trade_quality,
                "adx": row.features.get("adx"),
                "adx_slope": row.features.get("adx_slope"),
                "plus_di": row.features.get("plus_di"),
                "minus_di": row.features.get("minus_di"),
                "volume": row.features.get("volume"),
                "relative_volume": row.features.get("relative_volume"),
                "rr": row.features.get("rr"),
                "stat_edge": row.features.get("statistical_edge"),
                "data_quality": row.features.get("data_quality"),
                "missing_inputs": row.features.get("missing_inputs", []),
                "last_update": row.ts.isoformat() if row.ts else None,
                "reason": row.reason,
            }
            for row in rows
        ]
    }


@router.get("/history")
def history(limit: int = 50, session: Session = Depends(get_db)) -> dict:
    rows = (
        session.execute(
            select(OpportunityTransition)
            .order_by(desc(OpportunityTransition.ts))
            .limit(min(limit, 100))
        )
        .scalars()
        .all()
    )
    return {
        "history": [
            {
                "setup_id": row.setup_id,
                "symbol": row.symbol,
                "setup": row.setup,
                "previous_state": row.previous_state,
                "state": row.new_state,
                "score": row.score,
                "reason": row.reason,
                "ts": row.ts.isoformat() if row.ts else None,
            }
            for row in rows
        ]
    }


@router.post("/notification-test")
def notification_test() -> dict:
    if not get_settings().orion_notification_test_mode:
        raise HTTPException(status_code=403, detail="NOTIFICATION_TEST_MODE is disabled")
    sent = notify_windows("ORION — TEST ALERT", "Synthetic notification test; no setup or order")
    return {"sent": sent, "label": "TEST ALERT", "statistics_contaminated": False}
