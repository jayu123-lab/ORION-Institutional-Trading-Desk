"""Order domain model and the exact lifecycle states from the spec (§11)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OrderState(StrEnum):
    PROPOSED = "PROPOSED"
    RISK_REVIEW = "RISK_REVIEW"
    APPROVED = "APPROVED"
    AWAITING_HUMAN_CONFIRMATION = "AWAITING_HUMAN_CONFIRMATION"
    SUBMITTED = "SUBMITTED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    STOPPED = "STOPPED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


# Allowed transitions — anything else is a bug, not a silent state jump.
TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.PROPOSED: {OrderState.RISK_REVIEW, OrderState.CANCELLED, OrderState.REJECTED},
    OrderState.RISK_REVIEW: {OrderState.APPROVED, OrderState.REJECTED},
    OrderState.APPROVED: {OrderState.AWAITING_HUMAN_CONFIRMATION, OrderState.REJECTED},
    OrderState.AWAITING_HUMAN_CONFIRMATION: {OrderState.SUBMITTED, OrderState.CANCELLED},
    OrderState.SUBMITTED: {
        OrderState.PARTIAL_FILL,
        OrderState.FILLED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
    },
    OrderState.PARTIAL_FILL: {
        OrderState.PARTIAL_FILL,
        OrderState.FILLED,
        OrderState.STOPPED,
        OrderState.CANCELLED,
    },
    OrderState.FILLED: {OrderState.STOPPED, OrderState.CLOSED},
    OrderState.STOPPED: {OrderState.CLOSED},
    OrderState.CLOSED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
}


def can_transition(current: OrderState, target: OrderState) -> bool:
    return target in TRANSITIONS[current]


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderRequest(BaseModel):
    client_order_id: str
    asset: str
    side: OrderSide
    order_type: OrderType
    qty: float = Field(gt=0)
    limit_price: float | None = None
    stop_price: float | None = None
    sl_price: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None
    trade_idea_id: int | None = None


class Fill(BaseModel):
    qty: float
    price: float
    commission: float = 0.0
    slippage_bps: float = 0.0
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
