"""Position tracking and management."""

import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Individual position in a symbol."""

    symbol: str
    quantity: float = 0.0
    average_entry_price: float = 0.0
    current_price: float = 0.0
    opened_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_open(self) -> bool:
        """Check if position is open."""
        return self.quantity != 0.0

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0.0

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0.0

    @property
    def notional_value(self) -> float:
        """Total value at entry price."""
        return self.quantity * self.average_entry_price

    @property
    def current_value(self) -> float:
        """Total value at current price."""
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss."""
        return self.current_value - self.notional_value

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as percentage."""
        if self.notional_value == 0.0:
            return 0.0
        return (self.unrealized_pnl / abs(self.notional_value)) * 100.0

    def update_price(self, price: float) -> None:
        """Update current market price."""
        self.current_price = price
        self.last_updated = datetime.utcnow()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "is_long": self.is_long,
            "is_short": self.is_short,
            "average_entry_price": self.average_entry_price,
            "current_price": self.current_price,
            "notional_value": self.notional_value,
            "current_value": self.current_value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "opened_at": self.opened_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }


class PositionManager:
    """Manages open positions across all symbols."""

    def __init__(self, initial_cash: float = 100000.0):
        self.positions: dict[str, Position] = {}
        self.initial_cash = initial_cash
        self.realized_pnl = 0.0
        self.cash_balance = initial_cash
        self.total_commission_paid = 0.0

    def add_position(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        commission: float = 0.0,
    ) -> Position:
        """Add or update a position."""
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)

        pos = self.positions[symbol]
        old_quantity = pos.quantity
        old_value = pos.notional_value

        # Calculate new average entry price
        new_quantity = old_quantity + quantity
        if new_quantity == 0.0:
            pos.quantity = 0.0
            pos.average_entry_price = 0.0
        else:
            new_value = old_value + (quantity * entry_price)
            pos.quantity = new_quantity
            pos.average_entry_price = new_value / new_quantity

        # Update cash and commission tracking
        cost = quantity * entry_price + commission
        self.cash_balance -= cost
        self.total_commission_paid += commission

        pos.update_price(entry_price)
        logger.info(
            f"Updated position {symbol}: qty={pos.quantity}, "
            f"entry={pos.average_entry_price:.2f}, cash={self.cash_balance:.2f}"
        )

        return pos

    def close_position(self, symbol: str, exit_price: float, commission: float = 0.0):
        """Close a position."""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        if not pos.is_open:
            return None

        # Realize profit/loss
        exit_value = pos.quantity * exit_price
        realized = exit_value - pos.notional_value - commission
        self.realized_pnl += realized

        # Update cash
        self.cash_balance += exit_value - commission
        self.total_commission_paid += commission

        logger.info(
            f"Closed position {symbol}: realized_pnl={realized:.2f}, cash={self.cash_balance:.2f}"
        )

        # Clear position
        pos.quantity = 0.0
        pos.average_entry_price = 0.0

        return realized

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol."""
        return self.positions.get(symbol)

    def get_open_positions(self) -> list[Position]:
        """Get all open positions."""
        return [p for p in self.positions.values() if p.is_open]

    def get_all_positions(self) -> list[Position]:
        """Get all positions (open and closed)."""
        return list(self.positions.values())

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update market prices for positions."""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_price(price)

    @property
    def total_unrealized_pnl(self) -> float:
        """Sum of all unrealized P&L."""
        return sum(p.unrealized_pnl for p in self.get_open_positions())

    @property
    def total_notional_value(self) -> float:
        """Sum of all notional values."""
        return sum(p.notional_value for p in self.get_open_positions())

    @property
    def total_current_value(self) -> float:
        """Sum of all current values."""
        return sum(p.current_value for p in self.get_open_positions())

    @property
    def portfolio_value(self) -> float:
        """Total portfolio value (cash + positions)."""
        return self.cash_balance + self.total_current_value

    @property
    def portfolio_return_pct(self) -> float:
        """Total portfolio return as percentage."""
        if self.initial_cash == 0.0:
            return 0.0
        return ((self.portfolio_value - self.initial_cash) / self.initial_cash) * 100.0

    @property
    def risk_exposure_pct(self) -> float:
        """Percentage of portfolio in positions (notional)."""
        if self.portfolio_value == 0.0:
            return 0.0
        return (abs(self.total_notional_value) / self.portfolio_value) * 100.0

    def get_summary(self) -> dict:
        """Get portfolio summary."""
        return {
            "initial_cash": self.initial_cash,
            "cash_balance": self.cash_balance,
            "total_notional_value": self.total_notional_value,
            "total_current_value": self.total_current_value,
            "total_unrealized_pnl": self.total_unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "total_commission_paid": self.total_commission_paid,
            "portfolio_value": self.portfolio_value,
            "portfolio_return_pct": self.portfolio_return_pct,
            "risk_exposure_pct": self.risk_exposure_pct,
            "open_positions_count": len(self.get_open_positions()),
            "all_positions_count": len(self.get_all_positions()),
        }

    def get_positions_dict(self) -> dict[str, dict]:
        """Get all positions as dictionary."""
        return {p.symbol: p.to_dict() for p in self.get_all_positions()}
