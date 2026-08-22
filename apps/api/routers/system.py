"""Health + SYSTEM STATUS endpoints (spec §40)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from core.config import get_settings
from core.memory.models import Quote, Source

router = APIRouter(prefix="/api/v1", tags=["system"])

STARTED_AT = datetime.now(UTC)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "orion-api", "version": "0.1.0"}


def _feed_status(session: Session) -> list[dict]:
    s = get_settings()
    stale_after = timedelta(seconds=s.monitor_quote_staleness_sec)
    now = datetime.now(UTC)

    sources = session.execute(select(Source)).scalars().all()
    out: list[dict] = []
    for src in sources:
        last_quote = session.execute(
            select(Quote)
            .where(Quote.provider == src.name)
            .order_by(desc(Quote.ts_received))
            .limit(1)
        ).scalar_one_or_none()
        if last_quote is None:
            status = "DISCONNECTED"
        elif now - last_quote.ts_received.replace(tzinfo=UTC) > stale_after:
            status = "STALE"
        else:
            status = "CONNECTED"
        out.append(
            {
                "source": src.name,
                "kind": src.kind,
                "status": status,
                "last_update": str(last_quote.ts_received) if last_quote else None,
            }
        )
    return out


@router.get("/system/status")
def system_status(session: Session = Depends(get_db)) -> dict:
    n_quotes = session.execute(select(func.count()).select_from(Quote)).scalar() or 0
    feeds = _feed_status(session)
    overall = "CONNECTED"
    if not feeds or all(f["status"] != "CONNECTED" for f in feeds):
        overall = "DEGRADED" if n_quotes else "DISCONNECTED"

    return {
        "database": {"status": "CONNECTED", "engine": session.bind.dialect.name},  # type: ignore[union-attr]
        "overall": overall,
        "feeds": feeds,
        "uptime_seconds": int((datetime.now(UTC) - STARTED_AT).total_seconds()),
        "live_mode": get_settings().orion_live_mode,
        "ts": datetime.now(UTC).isoformat(),
    }
