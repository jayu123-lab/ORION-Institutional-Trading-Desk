"""Paper trading order management and execution."""

import logging
from datetime import datetime
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from uuid import uuid4

logger = logging.getLogger(__name__)


class OrderStatus(str, Enum):
    """Order lifecycle states."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderSide(str, Enum):
    """Order direction."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order execution type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


@dataclass
class OrderExecution:
    """Single fill/partial execution of an order."""

    execution_id: str = field(default_factory=lambda: f"exec_{uuid4().hex[:8]}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    quantity: float = 0.0
    price: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0

    @property
    def total_value(self) -> float:
        """Total execution value before fees."""
        return self.quantity * self.price

    @property
    def total_cost(self) -> float:
        """Total cost including commission and slippage."""
        slippage_cost = self.quantity * self.slippage
        return self.total_value + self.commission + slippage_cost


@dataclass
class PaperOrder:
    """Paper trading order."""

    order_id: str = field(default_factory=lambda: f"ord_{uuid4().hex[:12]}")
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: float = 0.0
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    executions: list[OrderExecution] = field(default_factory=list)
    reference_id: Optional[str] = None

    @property
    def filled_quantity(self) -> float:
        """Total quantity filled."""
        return sum(e.quantity for e in self.executions)

    @property
    def remaining_quantity(self) -> float:
        """Quantity still awaiting fill."""
        return self.quantity - self.filled_quantity

    @property
    def is_complete(self) -> bool:
        """Order is fully filled or cancelled."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        )

    @property
    def average_fill_price(self) -> float:
        """Weighted average price of fills."""
        if not self.executions:
            return 0.0
        total_value = sum(e.total_value for e in self.executions)
        total_qty = self.filled_quantity
        return total_value / total_qty if total_qty > 0 else 0.0

    @property
    def total_commission(self) -> float:
        """Sum of all execution commissions."""
        return sum(e.commission for e in self.executions)

    @property
    def total_slippage(self) -> float:
        """Sum of all execution slippages."""
        return sum(e.slippage for e in self.executions)

    def add_execution(
        self,
        quantity: float,
        price: float,
        commission: float = 0.0,
        slippage: float = 0.0,
    ) -> OrderExecution:
        """Add a fill to the order."""
        execution = OrderExecution(
            quantity=quantity,
            price=price,
            commission=commission,
            slippage=slippage,
        )
        self.executions.append(execution)

        # Update status
        if self.filled_quantity >= self.quantity:
            self.status = OrderStatus.FILLED
            self.filled_at = datetime.utcnow()
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIALLY_FILLED

        return execution

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "status": self.status.value,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "average_fill_price": self.average_fill_price,
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "executions": len(self.executions),
            "reference_id": self.reference_id,
        }


class PaperOrderBook:
    """Manages paper trading orders."""

    def __init__(self):
        self.orders: dict[str, PaperOrder] = {}
        self.order_history: list[PaperOrder] = []

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reference_id: Optional[str] = None,
    ) -> PaperOrder:
        """Create a new order."""
        order = PaperOrder(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            reference_id=reference_id,
        )
        self.orders[order.order_id] = order
        logger.info(f"Created order: {order.order_id} {side.value} {quantity} {symbol}")
        return order

    def get_order(self, order_id: str) -> Optional[PaperOrder]:
        """Retrieve order by ID."""
        return self.orders.get(order_id)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        order = self.orders.get(order_id)
        if not order:
            return False
        if order.is_complete:
            return False
        order.status = OrderStatus.CANCELLED
        self.order_history.append(order)
        del self.orders[order_id]
        logger.info(f"Cancelled order: {order_id}")
        return True

    def get_active_orders(self, symbol: Optional[str] = None) -> list[PaperOrder]:
        """Get active orders, optionally filtered by symbol."""
        orders = list(self.orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def get_order_history(self, symbol: Optional[str] = None) -> list[PaperOrder]:
        """Get completed orders."""
        history = self.order_history.copy()
        if symbol:
            history = [o for o in history if o.symbol == symbol]
        return history

    def get_all_orders(self) -> list[PaperOrder]:
        """Get all orders (active and completed)."""
        return list(self.orders.values()) + self.order_history

    def close_order(self, order_id: str) -> bool:
        """Move order to history."""
        order = self.orders.get(order_id)
        if not order:
            return False
        if not order.is_complete:
            return False
        self.order_history.append(order)
        del self.orders[order_id]
        return True
