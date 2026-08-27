import pytest
from core.execution.position_manager import Position, PositionManager


class TestPosition:
    """Test individual position."""

    def test_position_creation(self):
        """Test creating a position."""
        pos = Position(symbol="BTC", quantity=1.0, average_entry_price=50000.0)

        assert pos.symbol == "BTC"
        assert pos.quantity == 1.0
        assert pos.average_entry_price == 50000.0
        assert pos.is_open
        assert pos.is_long
        assert not pos.is_short

    def test_position_values(self):
        """Test position value calculations."""
        pos = Position(symbol="BTC", quantity=2.0, average_entry_price=50000.0, current_price=55000.0)

        assert pos.notional_value == 100000.0  # 2 * 50000
        assert pos.current_value == 110000.0  # 2 * 55000
        assert pos.unrealized_pnl == 10000.0  # 110000 - 100000
        assert pos.unrealized_pnl_pct == 10.0  # 10000 / 100000 * 100

    def test_short_position(self):
        """Test short position calculations."""
        pos = Position(symbol="BTC", quantity=-1.0, average_entry_price=50000.0, current_price=45000.0)

        assert pos.is_short
        assert not pos.is_long
        assert pos.notional_value == -50000.0
        assert pos.current_value == -45000.0
        assert pos.unrealized_pnl == 5000.0  # -45000 - (-50000)

    def test_closed_position(self):
        """Test closed position."""
        pos = Position(symbol="BTC")

        assert not pos.is_open
        assert pos.quantity == 0.0

    def test_update_price(self):
        """Test updating position price."""
        pos = Position(symbol="BTC", quantity=1.0, average_entry_price=50000.0)

        pos.update_price(55000.0)
        assert pos.current_price == 55000.0
        assert pos.unrealized_pnl == 5000.0

    def test_position_to_dict(self):
        """Test position serialization."""
        pos = Position(symbol="BTC", quantity=1.0, average_entry_price=50000.0, current_price=55000.0)

        data = pos.to_dict()

        assert data["symbol"] == "BTC"
        assert data["quantity"] == 1.0
        assert data["is_long"]
        assert data["average_entry_price"] == 50000.0
        assert data["unrealized_pnl"] == 5000.0


class TestPositionManager:
    """Test position manager."""

    def test_initialization(self):
        """Test manager initialization."""
        manager = PositionManager(initial_cash=100000.0)

        assert manager.initial_cash == 100000.0
        assert manager.cash_balance == 100000.0
        assert manager.realized_pnl == 0.0
        assert manager.portfolio_value == 100000.0

    def test_add_position(self):
        """Test adding a position."""
        manager = PositionManager(initial_cash=100000.0)

        pos = manager.add_position("BTC", quantity=1.0, entry_price=50000.0)

        assert pos.symbol == "BTC"
        assert pos.quantity == 1.0
        assert pos.average_entry_price == 50000.0
        assert manager.cash_balance == 50000.0  # 100000 - 50000

    def test_add_position_with_commission(self):
        """Test adding position with commission."""
        manager = PositionManager(initial_cash=100000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0, commission=100.0)

        assert manager.cash_balance == 49900.0  # 100000 - 50000 - 100
        assert manager.total_commission_paid == 100.0

    def test_average_price_calculation(self):
        """Test average entry price with multiple fills."""
        manager = PositionManager(initial_cash=1000000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)
        manager.add_position("BTC", quantity=1.0, entry_price=55000.0)

        pos = manager.get_position("BTC")
        assert pos.quantity == 2.0
        assert pos.average_entry_price == 52500.0  # (50000 + 55000) / 2

    def test_close_position(self):
        """Test closing a position."""
        manager = PositionManager(initial_cash=100000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)
        assert manager.cash_balance == 50000.0

        realized = manager.close_position("BTC", exit_price=55000.0)

        assert realized == 5000.0  # Profit
        assert manager.cash_balance == 105000.0
        assert manager.realized_pnl == 5000.0

    def test_close_position_with_loss(self):
        """Test closing position at a loss."""
        manager = PositionManager(initial_cash=100000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)
        realized = manager.close_position("BTC", exit_price=45000.0)

        assert realized == -5000.0
        assert manager.cash_balance == 95000.0
        assert manager.realized_pnl == -5000.0

    def test_close_short_position(self):
        """Test closing a short position."""
        manager = PositionManager(initial_cash=100000.0)

        manager.add_position("BTC", quantity=-1.0, entry_price=50000.0)
        assert manager.cash_balance == 150000.0  # Received proceeds

        realized = manager.close_position("BTC", exit_price=45000.0)

        assert realized == 5000.0  # Profit from short
        assert manager.realized_pnl == 5000.0

    def test_get_open_positions(self):
        """Test retrieving open positions."""
        manager = PositionManager(initial_cash=1000000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)
        manager.add_position("ETH", quantity=10.0, entry_price=3000.0)

        open_pos = manager.get_open_positions()
        assert len(open_pos) == 2

    def test_total_unrealized_pnl(self):
        """Test total unrealized P&L."""
        manager = PositionManager(initial_cash=1000000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)
        manager.add_position("ETH", quantity=10.0, entry_price=3000.0)

        manager.positions["BTC"].update_price(55000.0)
        manager.positions["ETH"].update_price(3500.0)

        total_pnl = manager.total_unrealized_pnl
        assert total_pnl == 10000.0  # BTC: 5000, ETH: 5000

    def test_portfolio_value(self):
        """Test total portfolio value."""
        manager = PositionManager(initial_cash=100000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)
        assert manager.portfolio_value == 100000.0  # Cash 50000 + Position 50000

        manager.positions["BTC"].update_price(55000.0)
        assert manager.portfolio_value == 105000.0  # Cash 50000 + Position 55000

    def test_portfolio_return_pct(self):
        """Test portfolio return percentage."""
        manager = PositionManager(initial_cash=100000.0)

        manager.add_position("BTC", quantity=2.0, entry_price=50000.0)
        manager.positions["BTC"].update_price(60000.0)

        # Portfolio: 100000 + unrealized 20000 = 120000
        # Return: (120000 - 100000) / 100000 * 100 = 20%
        assert manager.portfolio_return_pct == 20.0

    def test_risk_exposure_pct(self):
        """Test risk exposure percentage."""
        manager = PositionManager(initial_cash=100000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)

        # Notional value: 50000
        # Portfolio value: 100000
        # Exposure: (50000 / 100000) * 100 = 50%
        assert manager.risk_exposure_pct == 50.0

    def test_update_prices(self):
        """Test updating multiple prices at once."""
        manager = PositionManager(initial_cash=1000000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)
        manager.add_position("ETH", quantity=10.0, entry_price=3000.0)

        prices = {"BTC": 55000.0, "ETH": 3500.0}
        manager.update_prices(prices)

        assert manager.positions["BTC"].current_price == 55000.0
        assert manager.positions["ETH"].current_price == 3500.0

    def test_get_summary(self):
        """Test portfolio summary."""
        manager = PositionManager(initial_cash=100000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)
        manager.positions["BTC"].update_price(55000.0)

        summary = manager.get_summary()

        assert summary["initial_cash"] == 100000.0
        assert summary["cash_balance"] == 50000.0
        assert summary["portfolio_value"] == 105000.0
        assert summary["total_unrealized_pnl"] == 5000.0

    def test_get_positions_dict(self):
        """Test positions serialization."""
        manager = PositionManager(initial_cash=100000.0)

        manager.add_position("BTC", quantity=1.0, entry_price=50000.0)
        positions_dict = manager.get_positions_dict()

        assert "BTC" in positions_dict
        assert positions_dict["BTC"]["quantity"] == 1.0
