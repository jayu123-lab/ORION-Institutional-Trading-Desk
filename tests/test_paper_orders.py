import pytest
from core.execution.paper_orders import (
    PaperOrder,
    OrderStatus,
    OrderSide,
    OrderType,
    OrderExecution,
    PaperOrderBook,
)


class TestOrderExecution:
    """Test order execution tracking."""

    def test_execution_creation(self):
        """Test creating an execution."""
        execution = OrderExecution(quantity=1.0, price=100.0, commission=1.0, slippage=0.5)

        assert execution.quantity == 1.0
        assert execution.price == 100.0
        assert execution.commission == 1.0
        assert execution.slippage == 0.5

    def test_execution_costs(self):
        """Test execution cost calculations."""
        execution = OrderExecution(quantity=10.0, price=100.0, commission=5.0, slippage=0.1)

        assert execution.total_value == 1000.0  # 10 * 100
        assert execution.total_cost == 1006.0  # 1000 + 5 + (10 * 0.1)


class TestPaperOrder:
    """Test paper orders."""

    def test_order_creation(self):
        """Test creating an order."""
        order = PaperOrder(
            symbol="BTC",
            side=OrderSide.BUY,
            quantity=1.0,
            order_type=OrderType.LIMIT,
            limit_price=50000.0,
        )

        assert order.symbol == "BTC"
        assert order.side == OrderSide.BUY
        assert order.quantity == 1.0
        assert order.status == OrderStatus.PENDING
        assert order.limit_price == 50000.0

    def test_filled_quantity(self):
        """Test tracking filled quantity."""
        order = PaperOrder(symbol="BTC", side=OrderSide.BUY, quantity=10.0)

        assert order.filled_quantity == 0.0
        assert order.remaining_quantity == 10.0

        order.add_execution(5.0, 50000.0)
        assert order.filled_quantity == 5.0
        assert order.remaining_quantity == 5.0
        assert order.status == OrderStatus.PARTIALLY_FILLED

        order.add_execution(5.0, 50000.0)
        assert order.filled_quantity == 10.0
        assert order.remaining_quantity == 0.0
        assert order.status == OrderStatus.FILLED

    def test_average_fill_price(self):
        """Test weighted average fill price."""
        order = PaperOrder(symbol="BTC", side=OrderSide.BUY, quantity=10.0)

        order.add_execution(3.0, 100.0)
        order.add_execution(7.0, 110.0)

        # (3*100 + 7*110) / 10 = (300 + 770) / 10 = 107
        assert order.average_fill_price == 107.0

    def test_total_commissions_and_slippage(self):
        """Test aggregated costs."""
        order = PaperOrder(symbol="BTC", side=OrderSide.BUY, quantity=10.0)

        # slippage is total slippage for that execution, not per-unit
        order.add_execution(5.0, 100.0, commission=2.0, slippage=0.5)
        order.add_execution(5.0, 101.0, commission=2.0, slippage=0.5)

        assert order.total_commission == 4.0
        assert order.total_slippage == 1.0

    def test_is_complete(self):
        """Test completion status."""
        order = PaperOrder(symbol="BTC", side=OrderSide.BUY, quantity=10.0)

        assert not order.is_complete
        order.status = OrderStatus.FILLED
        assert order.is_complete

        order2 = PaperOrder(symbol="ETH", side=OrderSide.SELL, quantity=5.0)
        order2.status = OrderStatus.CANCELLED
        assert order2.is_complete

    def test_order_to_dict(self):
        """Test order serialization."""
        order = PaperOrder(
            symbol="BTC",
            side=OrderSide.BUY,
            quantity=1.0,
            limit_price=50000.0,
            reference_id="ref_123",
        )
        order.add_execution(0.5, 50000.0, commission=10.0)

        data = order.to_dict()

        assert data["symbol"] == "BTC"
        assert data["side"] == "BUY"
        assert data["quantity"] == 1.0
        assert data["limit_price"] == 50000.0
        assert data["filled_quantity"] == 0.5
        assert data["total_commission"] == 10.0
        assert data["reference_id"] == "ref_123"


class TestPaperOrderBook:
    """Test order book management."""

    def test_create_order(self):
        """Test creating orders in book."""
        book = PaperOrderBook()

        order = book.create_order("BTC", OrderSide.BUY, 1.0)

        assert order.symbol == "BTC"
        assert order.side == OrderSide.BUY
        assert order.quantity == 1.0
        assert book.get_order(order.order_id) == order

    def test_get_active_orders(self):
        """Test retrieving active orders."""
        book = PaperOrderBook()

        btc_order = book.create_order("BTC", OrderSide.BUY, 1.0)
        eth_order = book.create_order("ETH", OrderSide.SELL, 10.0)

        active = book.get_active_orders()
        assert len(active) == 2
        assert btc_order in active
        assert eth_order in active

        btc_only = book.get_active_orders("BTC")
        assert len(btc_only) == 1
        assert btc_only[0].symbol == "BTC"

    def test_cancel_order(self):
        """Test cancelling orders."""
        book = PaperOrderBook()

        order = book.create_order("BTC", OrderSide.BUY, 1.0)
        order_id = order.order_id

        assert book.cancel_order(order_id)
        assert order.status == OrderStatus.CANCELLED
        assert book.get_order(order_id) is None  # Moved to history
        assert len(book.get_order_history()) == 1

    def test_cannot_cancel_filled_order(self):
        """Test that filled orders cannot be cancelled."""
        book = PaperOrderBook()

        order = book.create_order("BTC", OrderSide.BUY, 1.0)
        order.status = OrderStatus.FILLED

        assert not book.cancel_order(order.order_id)

    def test_order_history(self):
        """Test order history tracking."""
        book = PaperOrderBook()

        order1 = book.create_order("BTC", OrderSide.BUY, 1.0)
        order2 = book.create_order("ETH", OrderSide.SELL, 10.0)

        book.cancel_order(order1.order_id)
        order2.status = OrderStatus.FILLED
        book.close_order(order2.order_id)

        history = book.get_order_history()
        assert len(history) == 2

        btc_history = book.get_order_history("BTC")
        assert len(btc_history) == 1
        assert btc_history[0].symbol == "BTC"

    def test_all_orders(self):
        """Test getting all orders."""
        book = PaperOrderBook()

        active = book.create_order("BTC", OrderSide.BUY, 1.0)
        completed = book.create_order("ETH", OrderSide.SELL, 10.0)

        book.cancel_order(completed.order_id)

        all_orders = book.get_all_orders()
        assert len(all_orders) == 2
        assert active in all_orders
        assert completed in all_orders

    def test_close_order(self):
        """Test closing completed orders."""
        book = PaperOrderBook()

        order = book.create_order("BTC", OrderSide.BUY, 1.0)
        order.status = OrderStatus.FILLED

        assert book.close_order(order.order_id)
        assert book.get_order(order.order_id) is None
        assert order in book.get_order_history()

    def test_cannot_close_incomplete_order(self):
        """Test that incomplete orders cannot be closed."""
        book = PaperOrderBook()

        order = book.create_order("BTC", OrderSide.BUY, 1.0)
        assert not book.close_order(order.order_id)
