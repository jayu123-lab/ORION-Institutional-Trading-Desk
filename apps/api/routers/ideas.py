"""Trading ideas + risk review gate (IDEA → RISK)."""

from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from core.config import get_settings
from core.market_data.base import DataQuality, DataStatus, Quote
from core.memory.audit import audit
from core.memory.models import Position, RiskDecision, TradeIdea, utcnow
from core.memory.models import Quote as QuoteRow
from core.risk.engine import PortfolioState, Proposal, RiskEngine, RiskLimits

router = APIRouter(prefix="/api/v1/trades", tags=["trades"])


class IdeaIn(BaseModel):
    proposed_by: str = "analyst"
    asset: str
    direction: str = Field(pattern="^(LONG|SHORT|FLAT)$")
    timeframe: str | None = None
    entry: float | None = None
    invalidation: float | None = None
    stop_loss: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None
    probability: float | None = Field(default=None, ge=0, le=100)
    confidence: str | None = Field(default=None, pattern="^(LOW|MODERATE|HIGH|VERY HIGH)$")
    horizon: str | None = None
    technical_thesis: str | None = None
    fundamental_thesis: str | None = None
    catalysts: str | None = None
    risks: str | None = None
    liquidity_notes: str | None = None
    activation_conditions: str | None = None
    cancel_conditions: str | None = None
    data_source: str | None = None
    price_used: float | None = None


def portfolio_state(session: Session) -> PortfolioState:
    equity = get_settings().orion_starting_equity
    positions = session.execute(select(Position).where(Position.status == "OPEN")).scalars().all()
    by_asset: dict[str, float] = {}
    total_notional = 0.0
    for p in positions:
        notion = abs(p.qty * p.avg_price)
        by_asset[p.asset] = by_asset.get(p.asset, 0.0) + notion
        total_notional += notion
    return PortfolioState(
        equity=equity,
        balance=equity,
        drawdown_pct=0.0,
        daily_risk_used_pct=0.0,
        weekly_risk_used_pct=0.0,
        total_notional=round(total_notional, 2),
        notional_by_asset={k: round(v, 2) for k, v in by_asset.items()},
        open_trades_today=len(positions),
    )


def latest_quote_row(session: Session, symbol: str) -> QuoteRow | None:
    return session.execute(
        select(QuoteRow)
        .where(QuoteRow.symbol == symbol.upper())
        .order_by(desc(QuoteRow.ts_received))
        .limit(1)
    ).scalar_one_or_none()


def to_domain_quote(row: QuoteRow) -> Quote:
    ts = row.ts_source if row.ts_source.tzinfo else row.ts_source.replace(tzinfo=UTC)
    return Quote(
        symbol=row.symbol,
        price=row.price,
        bid=row.bid,
        ask=row.ask,
        volume=row.volume,
        ts_source=ts,
        quality=DataQuality(provider=row.provider, status=DataStatus(row.status)),
    )


@router.get("/ideas")
def list_ideas(session: Session = Depends(get_db)) -> list[dict]:
    rows = session.execute(select(TradeIdea).order_by(desc(TradeIdea.ts)).limit(50)).scalars().all()
    return [
        {
            "id": r.id,
            "asset": r.asset,
            "direction": r.direction,
            "state": r.state,
            "entry": r.entry,
            "stop_loss": r.stop_loss,
            "tp1": r.tp1,
            "probability": r.probability,
            "confidence": r.confidence,
            "ts": str(r.ts),
        }
        for r in rows
    ]


@router.post("/ideas", status_code=201)
def create_idea(idea: IdeaIn, session: Session = Depends(get_db)) -> dict:
    row = TradeIdea(**idea.model_dump(), state="PROPOSED", ts=utcnow())
    session.add(row)
    session.flush()
    audit(
        session,
        actor="api",
        action="trade_idea_created",
        entity="trade_ideas",
        entity_id=row.id,
        detail={"asset": row.asset, "direction": row.direction},
    )
    session.commit()
    return {"id": row.id, "state": row.state}


@router.post("/ideas/{idea_id}/risk-review")
def risk_review(idea_id: int, session: Session = Depends(get_db)) -> dict:
    idea = session.get(TradeIdea, idea_id)
    if idea is None:
        raise HTTPException(404, "idea not found")

    engine = RiskEngine(RiskLimits())
    proposal = Proposal(
        asset=idea.asset,
        direction=idea.direction,
        entry=idea.entry or 0.0,
        stop_loss=idea.stop_loss or 0.0,
        target1=idea.tp1 or 0.0,
    )
    quote_row = latest_quote_row(session, idea.asset)
    quote = to_domain_quote(quote_row) if quote_row else None

    decision = engine.evaluate(proposal, portfolio_state(session), quote)

    session.add(
        RiskDecision(
            trade_idea_id=idea.id,
            decision=decision.decision,
            reasons=decision.reasons,
            conditions=decision.conditions,
            suggested_size=decision.suggested_qty,
            ts=utcnow(),
        )
    )
    idea.state = decision.decision if decision.decision != "REDUCE_SIZE" else "APPROVED_REDUCED"
    audit(
        session,
        actor="risk-engine",
        action="risk_decision",
        entity="trade_ideas",
        entity_id=idea.id,
        detail={"decision": decision.decision, "reasons": decision.reasons},
    )
    session.commit()

    # Faro publish: only on a full, unreduced APPROVED — never on
    # REDUCE_SIZE/WAIT/REJECTED, keeping the human-approval spirit of the
    # IDEA -> CIO -> RISK -> EXECUTION flow for anything sent outward.
    faro_result = None
    if decision.decision == "APPROVED":
        from providers.faro.client import maybe_send_faro_signal

        try:
            sent = maybe_send_faro_signal(idea, decision.decision)
            if sent is not None:
                faro_result = sent.to_dict()
                audit(
                    session,
                    actor="faro-publisher",
                    action="faro_signal",
                    entity="trade_ideas",
                    entity_id=idea.id,
                    detail={"status": sent.status, "detail": sent.detail},
                )
                session.commit()
        except Exception as exc:  # noqa: BLE001 — publishing must never break risk-review
            faro_result = {"status": "FAILED", "detail": str(exc)[:300]}

    return {
        "idea_id": idea.id,
        "decision": decision.decision,
        "reasons": decision.reasons,
        "conditions": decision.conditions,
        "suggested_qty": decision.suggested_qty,
        "computed_risk_pct": decision.computed_risk_pct,
        "faro": faro_result,
    }
