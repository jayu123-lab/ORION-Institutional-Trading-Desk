"""P34 — WATCH MODE.

"Vigila XAUUSD y avísame si llega a zona y aparece reacción."

States: WATCHING -> ARMED -> CONFIRMED | INVALIDATED; CANCELLED anytime.
Surveillance ONLY — never creates, routes or executes orders.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import desc, select

from core.memory.models import Quote, WatchRequest

logger = logging.getLogger("orion.watch")

ARMED_PROXIMITY_ATR = 0.5     # within 0.5 ATR of the zone → ARMED


def create_watch(session_factory, symbol: str, note: str | None,
                 zone_low: float | None = None, zone_high: float | None = None,
                 created_by: str | None = "user") -> dict:
    with session_factory() as session:
        row = WatchRequest(symbol=symbol.upper(), note=(note or "")[:500],
                           zone_low=zone_low, zone_high=zone_high,
                           state="WATCHING", created_by=created_by)
        session.add(row)
        session.commit()
        return _to_dict(row)


def cancel_watch(session_factory, watch_id: int) -> dict | None:
    with session_factory() as session:
        row = session.get(WatchRequest, watch_id)
        if row is None or row.state == "CANCELLED":
            return None
        row.state = "CANCELLED"
        row.state_ts = datetime.now(UTC)
        session.commit()
        return _to_dict(row)


def list_watches(session_factory, active_only: bool = True) -> list[dict]:
    with session_factory() as session:
        q = select(WatchRequest).order_by(desc(WatchRequest.id)).limit(50)
        rows = session.execute(q).scalars().all()
    out = [_to_dict(r) for r in rows]
    if active_only:
        out = [w for w in out if w["state"] not in ("CANCELLED", "INVALIDATED")]
    return out


def evaluate_watches(session_factory, atr_fallback_pct: float = 0.004) -> list[dict]:
    """Advance every active watch against the LATEST stored quote.

    WATCHING -> ARMED when price enters the zone band.
    ARMED   -> CONFIRMED when a bar closes back through the band edge
               (reaction evidence). Honest limits: confirmation here is
               mechanical (close back inside), NOT full structural read.
    """
    results: list[dict] = []
    with session_factory() as session:
        rows = session.execute(
            select(WatchRequest).where(WatchRequest.state.in_(("WATCHING", "ARMED")))
            .order_by(desc(WatchRequest.id)).limit(50)
        ).scalars().all()
        for row in rows:
            quote = session.execute(
                select(Quote).where(Quote.symbol == row.symbol)
                .order_by(desc(Quote.id)).limit(1)
            ).scalars().first()
            if quote is None or quote.price is None:
                continue
            price = float(quote.price)

            lo, hi = row.zone_low, row.zone_high
            if lo is None or hi is None:
                # derive a provisional band around current price when the
                # caller did not supply one (± fallback % of price)
                band = price * atr_fallback_pct
                lo, hi = price - band, price + band
                row.zone_low, row.zone_high = lo, hi

            if row.state == "WATCHING" and lo <= price <= hi:
                row.state = "ARMED"
                row.state_ts = datetime.now(UTC)
            elif row.state == "ARMED" and (price > hi or price < lo):
                # mechanical reaction evidence: armed inside the zone, then
                # price pushed away from it (either direction)
                row.state = "CONFIRMED"
                row.state_ts = datetime.now(UTC)
            session.commit()
            results.append(_to_dict(row))
    return results


def _to_dict(r: WatchRequest) -> dict:
    return {
        "id": r.id, "symbol": r.symbol, "note": r.note,
        "zone": [r.zone_low, r.zone_high], "state": r.state,
        "state_ts": r.state_ts.isoformat() if r.state_ts else None,
        "created_by": r.created_by,
        "ts": r.ts.isoformat() if r.ts else None,
        "execution": "NONE — watch mode never executes orders",
    }
