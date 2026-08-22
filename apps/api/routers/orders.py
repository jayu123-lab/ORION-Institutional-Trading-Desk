"""Orders lifecycle: APPROVED idea → ticket → HUMAN confirm → paper fill."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from apps.api.routers.ideas import latest_quote_row, to_domain_quote
from core.execution.models import (
    Fill,
    OrderRequest,
    OrderSide,
    OrderState,
    OrderType,
    can_transition,
)
from core.execution.paper import PaperTradingEngine
from core.memory.audit import audit
from core.memory.models import Execution, Order, Position, utcnow

router = APIRouter(prefix="/api/v1/trades", tags=["orders"])


class OrderIn(BaseModel):
    trade_idea_id: int
    order_type: OrderType = OrderType.LIMIT
    qty: float | None = None


class ConfirmIn(BaseModel):
    confirmed_by: str = "human-operator"


@router.get("/orders")
def list_orders(session: Session = Depends(get_db)) -> list[dict]:
    rows = session.execute(select(Order).order_by(desc(Order.created_at)).limit(50)).scalars().all()
    return [
        {
            "id": r.id,
            "client_order_id": r.client_order_id,
            "asset": r.asset,
            "side": r.side,
            "type": r.order_type,
            "qty": r.qty,
            "state": r.state,
            "mode": r.mode,
        }
        for r in rows
    ]


@router.post("/orders", status_code=201)
def create_order(body: OrderIn, session: Session = Depends(get_db)) -> dict:
    idea = session.get(idea_model(), body.trade_idea_id)
    if idea is None:
        raise HTTPException(404, "idea not found")
    if not idea.state.startswith("APPROVED"):
        raise HTTPException(409, f"idea state '{idea.state}' is not APPROVED: risk gate required")

    from core.memory.models import RiskDecision

    decision = session.execute(
        select(RiskDecision)
        .where(RiskDecision.trade_idea_id == idea.id)
        .order_by(desc(RiskDecision.ts))
        .limit(1)
    ).scalar_one_or_none()
    qty = body.qty or (decision.suggested_size if decision else None)
    if qty is None or qty <= 0:
        raise HTTPException(400, "no size available: run risk review first")

    side = OrderSide.BUY if idea.direction == "LONG" else OrderSide.SELL
    order = Order(
        client_order_id=f"ORION-{utcnow().strftime('%Y%m%d%H%M%S%f')}-{idea.id}",
        trade_idea_id=idea.id,
        asset=idea.asset,
        side=side.value,
        order_type=body.order_type.value,
        qty=qty,
        limit_price=idea.entry,
        sl_price=idea.stop_loss,
        tp1=idea.tp1,
        mode="PAPER",
        state=OrderState.AWAITING_HUMAN_CONFIRMATION.value,
    )
    session.add(order)
    audit(
        session,
        actor="execution-trader",
        action="order_created",
        entity="orders",
        entity_id=order.client_order_id,
        detail={"requires_human_confirmation": True},
    )
    session.commit()
    return {
        "client_order_id": order.client_order_id,
        "state": order.state,
        "mode": order.mode,
        "note": "AWAITING_HUMAN_CONFIRMATION — POST /confirm to submit in PAPER",
    }


def idea_model():  # local import avoids circular module import at load time
    from core.memory.models import TradeIdea

    return TradeIdea


@router.post("/orders/{client_order_id}/confirm")
async def confirm_order(
    client_order_id: str, body: ConfirmIn, session: Session = Depends(get_db)
) -> dict:
    order = session.execute(
        select(Order).where(Order.client_order_id == client_order_id)
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(404, "order not found")
    if order.mode != "PAPER":
        raise HTTPException(403, "live orders are disabled in Phase 1")

    current = OrderState(order.state)
    target = OrderState.SUBMITTED
    if not can_transition(current, target):
        raise HTTPException(409, f"illegal transition {current}->{target}")

    quote_row = latest_quote_row(session, order.asset)
    if quote_row is None:
        raise HTTPException(409, "CANNOT PRICE ORDER - NO DATA AVAILABLE")

    request = OrderRequest(
        client_order_id=order.client_order_id,
        asset=order.asset,
        side=OrderSide(order.side),
        order_type=OrderType(order.order_type),
        qty=order.qty,
        limit_price=order.limit_price,
    )
    try:
        fill: Fill = PaperTradingEngine().simulate_fill(request, to_domain_quote(quote_row))
    except ValueError as exc:
        order.state = OrderState.SUBMITTED.value  # working order without fill yet
        session.commit()
        return {
            "client_order_id": order.client_order_id,
            "state": order.state,
            "fill": None,
            "note": str(exc),
        }

    order.human_confirmed_by = body.confirmed_by
    order.human_confirmed_at = utcnow()
    order.state = (
        OrderState.FILLED.value if fill.qty >= order.qty else OrderState.PARTIAL_FILL.value
    )

    session.add(
        Execution(
            order_id=order.id,
            fill_qty=fill.qty,
            fill_price=fill.price,
            commission=fill.commission,
            slippage_bps=fill.slippage_bps,
            venue="PAPER",
        )
    )
    session.add(
        Position(
            asset=order.asset,
            side=order.side,
            qty=fill.qty,
            avg_price=fill.price,
            sl_price=order.sl_price,
            tp_price=order.tp1,
            mode="PAPER",
            status="OPEN",
        )
    )
    audit(
        session,
        actor=f"human:{body.confirmed_by}",
        action="order_confirmed_and_filled",
        entity="orders",
        entity_id=order.client_order_id,
        detail={"fill_price": fill.price, "qty": fill.qty},
    )
    session.commit()
    return {
        "client_order_id": order.client_order_id,
        "state": order.state,
        "fill": fill.model_dump(mode="json"),
    }


@router.get("/positions")
def list_positions(session: Session = Depends(get_db)) -> list[dict]:
    rows = session.execute(select(Position).where(Position.status == "OPEN")).scalars().all()
    return [
        {
            "id": r.id,
            "asset": r.asset,
            "side": r.side,
            "qty": r.qty,
            "avg_price": r.avg_price,
            "sl_price": r.sl_price,
            "tp_price": r.tp_price,
            "opened_at": str(r.opened_at),
            "mode": r.mode,
        }
        for r in rows
    ]
