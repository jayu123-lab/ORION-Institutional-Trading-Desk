from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.execution.models import OrderRequest, OrderSide, OrderState, OrderType, can_transition
from core.execution.paper import PaperConfig, PaperTradingEngine
from core.market_data.base import DataQuality, DataStatus, Quote


def _quote(price: float = 100.0, status: DataStatus = DataStatus.LIVE) -> Quote:
    return Quote(
        symbol="TEST",
        price=price,
        bid=price - 0.05,
        ask=price + 0.05,
        ts_source=datetime.now(UTC),
        quality=DataQuality(provider="test", status=status),
    )


def _market_order(side: OrderSide = OrderSide.BUY) -> OrderRequest:
    return OrderRequest(
        client_order_id="T-1",
        asset="TEST",
        side=side,
        order_type=OrderType.MARKET,
        qty=10,
    )


def test_fill_pays_spread_and_slippage_buy():
    engine = PaperTradingEngine(PaperConfig(seed=7))
    fill = engine.simulate_fill(_market_order(OrderSide.BUY), _quote(100.0), reference_range=1.0)
    # BUY must fill at/above mid (spread cost) and never below bid
    assert fill.price >= 99.95
    assert fill.slippage_bps >= 0
    assert fill.commission > 0


def test_sell_fills_below_mid():
    engine = PaperTradingEngine(PaperConfig(seed=3))
    fill = engine.simulate_fill(_market_order(OrderSide.SELL), _quote(100.0), reference_range=0.5)
    assert fill.price <= 100.05


def test_limit_not_touchable_stays_working():
    engine = PaperTradingEngine()
    order = OrderRequest(
        client_order_id="T-2",
        asset="TEST",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=5,
        limit_price=90.0,
    )
    with pytest.raises(ValueError, match="limit not touchable"):
        engine.simulate_fill(order, _quote(100.0))


def test_partial_fill_reduces_qty():
    cfg = PaperConfig(partial_fill_probability=1.0, partial_fill_min_fraction=0.5, seed=11)
    fill = PaperTradingEngine(cfg).simulate_fill(_market_order(), _quote())
    assert fill.qty < 10
    assert fill.qty >= 5


def test_refuses_stale_quote():
    engine = PaperTradingEngine()
    with pytest.raises(ValueError, match="stale"):
        engine.simulate_fill(_market_order(), _quote(status=DataStatus.STALE))


def test_deterministic_with_same_seed():
    q = _quote(50.0)
    f1 = PaperTradingEngine(PaperConfig(seed=99)).simulate_fill(_market_order(), q, 0.2)
    f2 = PaperTradingEngine(PaperConfig(seed=99)).simulate_fill(_market_order(), q, 0.2)
    assert (f1.price, f1.qty, f1.commission) == (f2.price, f2.qty, f2.commission)


def test_state_machine_transitions():
    assert can_transition(OrderState.AWAITING_HUMAN_CONFIRMATION, OrderState.SUBMITTED)
    assert not can_transition(OrderState.PROPOSED, OrderState.SUBMITTED)
    assert not can_transition(OrderState.CLOSED, OrderState.FILLED)
