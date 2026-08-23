"""Health + SYSTEM STATUS endpoints (spec §40)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from core.config import get_settings
from core.memory.models import Analysis, Candle, NewsItem, Quote, Source

router = APIRouter(prefix="/api/v1", tags=["system"])

STARTED_AT = datetime.now(UTC)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "orion-api", "version": "0.1.0"}


def _age_sec(last: datetime | None, now: datetime) -> float | None:
    if last is None:
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return max(0.0, (now - last).total_seconds())


def _classify(age: float | None, healthy: float, degraded: float, stale: float) -> str:
    """HEALTHY / DEGRADED / STALE / FAILED from evidence age."""
    if age is None:
        return "FAILED"
    if age <= healthy:
        return "HEALTHY"
    if age <= degraded:
        return "DEGRADED"
    if age <= stale:
        return "STALE"
    return "FAILED"


def _service_states(session: Session, now: datetime) -> list[dict]:
    s = get_settings()
    feed_healthy = float(s.monitor_quote_staleness_sec)

    def feed_state(provider: str) -> tuple[str, float | None]:
        last = session.execute(
            select(Quote.ts_received)
            .where(Quote.provider == provider)
            .order_by(desc(Quote.ts_received))
            .limit(1)
        ).scalar_one_or_none()
        age = _age_sec(last, now)
        return _classify(age, feed_healthy, feed_healthy * 5, feed_healthy * 30), age

    out: list[dict] = []

    st, age = feed_state("yahoo")
    out.append(
        {
            "service": "monitor.yahoo_poller",
            "state": st,
            "detail": f"last quote {age:.0f}s ago" if age is not None else "no quotes ingested",
        }
    )

    if s.orion_polymarket_ws_embedded:
        st, age = feed_state("polymarket-rtds")
        out.append(
            {
                "service": "monitor.polymarket_rtds",
                "state": st,
                "detail": f"last tick {age:.0f}s ago" if age is not None else "no ticks ingested",
            }
        )
    else:
        # Intentionally disabled in configuration — report that, not a failure.
        out.append(
            {
                "service": "monitor.polymarket_rtds",
                "state": "DISABLED",
                "detail": "embedded RTDS monitor disabled (ORION_POLYMARKET_WS_EMBEDDED=false)",
            }
        )

    st, age = feed_state("coinbase")
    out.append(
        {
            "service": "data.coinbase",
            "state": st,
            "detail": f"last ticker {age:.0f}s ago" if age is not None else "no tickers ingested",
        }
    )

    # Embedded data service = ingestion activity from ANY provider. This reflects
    # the lifespan task that populates the dashboard when the monitor is not running.
    last_any = session.execute(select(func.max(Quote.ts_received))).scalar_one_or_none()
    age = _age_sec(last_any, now)
    out.append(
        {
            "service": "api.embedded_data",
            "state": _classify(age, 180, 600, 1800),
            "detail": (
                f"ingesting, last row {age:.0f}s ago" if age is not None else "no quotes stored"
            ),
        }
    )

    cftc_source = session.execute(
        select(Source).where(Source.name == "cftc-scheduled")
    ).scalar_one_or_none()
    out.append(
        {
            "service": "data.cftc",
            "state": cftc_source.status if cftc_source else "NOT_CONFIGURED",
            "detail": cftc_source.notes if cftc_source else "weekly scheduler has not completed",
        }
    )

    last_news = session.execute(select(func.max(NewsItem.published_at))).scalar_one_or_none()
    age = _age_sec(last_news, now)
    out.append(
        {
            "service": "news.rss_cycle",
            "state": _classify(age, 6 * 3600, 24 * 3600, 72 * 3600),
            "detail": (
                f"latest headline {age / 3600:.1f}h old" if age is not None else "no headlines"
            ),
        }
    )

    last_candle = session.execute(
        select(func.max(Candle.ts_open)).where(Candle.timeframe == "H1")
    ).scalar_one_or_none()
    age = _age_sec(last_candle, now)
    out.append(
        {
            "service": "monitor.candle_rollup",
            "state": _classify(age, 2 * 3600, 6 * 3600, 24 * 3600),
            "detail": f"latest H1 bar {age / 3600:.1f}h old" if age is not None else "no candles",
        }
    )

    last_debate = session.execute(
        select(func.max(Analysis.ts)).where(Analysis.kind == "debate")
    ).scalar_one_or_none()
    age = _age_sec(last_debate, now)
    out.append(
        {
            "service": "desk.debates",
            "state": "HEALTHY" if age is not None and age <= 24 * 3600 else "IDLE",
            "detail": (
                f"last debate {age / 3600:.1f}h ago" if age is not None else "never convened"
            ),
        }
    )
    return out


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
    services = _service_states(session, datetime.now(UTC))

    worst = {svc["state"] for svc in services}
    if "FAILED" in worst:
        overall = "DEGRADED" if n_quotes else "DISCONNECTED"
    elif feeds and all(f["status"] != "CONNECTED" for f in feeds):
        overall = "DEGRADED"
    else:
        overall = "OPERATIONAL"

    from core.events.bus import get_event_bus

    return {
        "database": {"status": "CONNECTED", "engine": session.bind.dialect.name},  # type: ignore[union-attr]
        "overall": overall,
        "feeds": feeds,
        "services": services,
        "event_bus": type(get_event_bus()).__name__,
        "uptime_seconds": int((datetime.now(UTC) - STARTED_AT).total_seconds()),
        "live_mode": get_settings().orion_live_mode,
        "ts": datetime.now(UTC).isoformat(),
    }
