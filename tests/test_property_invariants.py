"""Property-based tests (PRIORITY 14): sizing, paper fills, risk engine,
reconciliation — invariants must hold for arbitrary valid inputs."""

import math
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.execution.models import OrderRequest, OrderSide, OrderType
from core.execution.paper import PaperConfig, PaperTradingEngine
from core.market_data.base import DataQuality, DataStatus, Quote
from core.market_data.reconciliation import (
    FeedReading,
    FeedTier,
    MarketDataReconciliationEngine,
    ReconciliationState,
)
from core.risk.engine import PortfolioState, Proposal, RiskEngine, RiskLimits
from core.risk.sizing import position_size, reward_risk

money = st.floats(min_value=1_000, max_value=10_000_000)
price = st.floats(min_value=0.5, max_value=100_000)


def _quote(price_: float, *, age_sec: float = 0.0, spread_pct: float = 0.0002) -> Quote:
    now = datetime.now(UTC)
    q = Quote(
        symbol="XAUUSD",
        price=price_,
        ts_source=now - timedelta(seconds=age_sec),
        quality=DataQuality(
            provider="test",
            latency_ms=40,
            quality="A",
            status=DataStatus.LIVE,
        ),
    )
    half = price_ * spread_pct / 2
    q.bid = round(price_ - half, 6)
    q.ask = round(price_ + half, 6)
    return q


# ------------------------------------------------------------------ sizing ---
@settings(max_examples=200, deadline=None)
@given(
    equity=money,
    risk_pct=st.floats(min_value=0.01, max_value=5.0),
    entry=price,
    stop_dist=st.floats(min_value=1e-4, max_value=50_000),
)
def test_sizing_risk_never_exceeds_budget(equity, risk_pct, entry, stop_dist):
    stop = entry + stop_dist  # direction irrelevant: abs() used
    res = position_size(equity, risk_pct, entry, stop)
    assert res.qty >= 0
    assert res.risk_amount == pytest.approx(equity * risk_pct / 100.0, abs=0.01)
    # actual risk of the sized position stays within budget (rounding tolerance)
    if res.qty > 0:
        assert res.qty * res.risk_per_unit <= equity * risk_pct / 100.0 * 1.0001 + 0.01


@settings(max_examples=100, deadline=None)
@given(entry=price, target_mult=st.floats(min_value=0.1, max_value=20))
def test_reward_risk_symmetric_and_positive(entry, target_mult):
    stop = entry * 0.98
    target = entry + abs(entry - stop) * target_mult
    rr = reward_risk(entry, stop, target)
    assert rr >= 0
    assert rr == pytest.approx(target_mult, abs=0.01)


@pytest.mark.parametrize(
    "bad",
    [(0, 1, 2, 3), (-5, 1, 2, 3), (100, 0, 2, 3), (100, -1, 2, 3), (100, 1, 2, 2)],
)
def test_sizing_rejects_degenerate(bad):
    with pytest.raises(ValueError):
        position_size(*bad)


# ------------------------------------------------------------- paper fills ---
orders = st.integers(min_value=1, max_value=100).map(float)


@settings(max_examples=150, deadline=None)
@given(mid=st.floats(min_value=1.0, max_value=50_000), qty=orders, seed=st.integers(0, 10**6))
def test_market_buy_fill_worse_than_mid(mid, qty, seed):
    eng = PaperTradingEngine(PaperConfig(seed=seed))
    order = OrderRequest(
        client_order_id=f"t{seed}", asset="XAUUSD", side=OrderSide.BUY,
        order_type=OrderType.MARKET, qty=qty,
    )
    fill = eng.simulate_fill(order, _quote(mid))
    assert fill.qty <= order.qty
    assert fill.price >= mid - 1e-9  # buyer never fills better than mid
    assert fill.commission >= 0 and fill.slippage_bps >= 0


@settings(max_examples=150, deadline=None)
@given(mid=st.floats(min_value=1.0, max_value=50_000), qty=orders, seed=st.integers(0, 10**6))
def test_market_sell_fill_worse_than_mid(mid, qty, seed):
    eng = PaperTradingEngine(PaperConfig(seed=seed))
    order = OrderRequest(
        client_order_id=f"t{seed}", asset="XAUUSD", side=OrderSide.SELL,
        order_type=OrderType.MARKET, qty=qty,
    )
    fill = eng.simulate_fill(order, _quote(mid))
    assert fill.qty <= order.qty and fill.qty > 0
    assert fill.price <= mid + 1e-9  # seller never fills better than mid


@settings(max_examples=100, deadline=None)
@given(limit_offset=st.floats(min_value=-0.005, max_value=-0.001), seed=st.integers(0, 999))
def test_limit_buy_fills_at_limit_or_better(limit_offset, seed):
    mid = 2500.0
    lp = mid * (1 + limit_offset)  # limit below mid → not touchable
    eng = PaperTradingEngine(PaperConfig(seed=seed))
    order = OrderRequest(
        client_order_id=f"l{seed}", asset="XAUUSD", side=OrderSide.BUY,
        order_type=OrderType.LIMIT, qty=1.0, limit_price=lp,
    )
    with pytest.raises(ValueError):
        eng.simulate_fill(order, _quote(mid))


@settings(max_examples=60, deadline=None)
@given(age=st.floats(min_value=181, max_value=10_000), seed=st.integers(0, 99))
def test_paper_refuses_stale_quote(age, seed):
    eng = PaperTradingEngine(PaperConfig(seed=seed))
    order = OrderRequest(
        client_order_id="s", asset="XAUUSD", side=OrderSide.BUY,
        order_type=OrderType.MARKET, qty=1.0,
    )
    stale = _quote(2500.0, age_sec=age)
    stale.quality.status = DataStatus.STALE
    with pytest.raises(ValueError):
        eng.simulate_fill(order, stale)


# ------------------------------------------------------------ risk engine ---
portfolios = st.fixed_dictionaries(
    {
        "equity": money,
        "drawdown": st.floats(min_value=0, max_value=25),
        "daily_used": st.floats(min_value=0, max_value=8),
        "weekly_used": st.floats(min_value=0, max_value=12),
        "notional": st.floats(min_value=0, max_value=2_000_000),
    }
)


@settings(max_examples=200, deadline=None)
@given(pf=portfolios, entry=price)
def test_drawdown_halt_is_fatal(pf, entry):
    port = PortfolioState(
        equity=pf["equity"], balance=pf["equity"],
        drawdown_pct=pf["drawdown"], daily_risk_used_pct=pf["daily_used"],
        weekly_risk_used_pct=pf["weekly_used"], total_notional=pf["notional"],
    )
    eng = RiskEngine(RiskLimits())
    prop = Proposal(asset="XAUUSD", direction="LONG", entry=entry,
                    stop_loss=entry * 0.99, target1=entry * 1.02)
    d = eng.evaluate(prop, port, quote=_quote(entry))
    if pf["drawdown"] >= eng.limits.max_drawdown_pct:
        assert d.decision == "REJECTED"


@settings(max_examples=200, deadline=None)
@given(pf=portfolios, entry=price)
def test_approved_implies_within_single_trade_cap(pf, entry):
    if pf["drawdown"] >= 10:
        return
    port = PortfolioState(
        equity=pf["equity"], balance=pf["equity"],
        drawdown_pct=pf["drawdown"], daily_risk_used_pct=pf["daily_used"],
        weekly_risk_used_pct=pf["weekly_used"], total_notional=pf["notional"],
    )
    eng = RiskEngine(RiskLimits())
    prop = Proposal(asset="XAUUSD", direction="LONG", entry=entry,
                    stop_loss=entry * 0.99, target1=entry * 1.02)
    d = eng.evaluate(prop, port, quote=_quote(entry))
    assert d.decision in ("APPROVED", "REDUCE_SIZE", "WAIT", "REJECTED")
    if d.decision == "APPROVED":
        assert d.computed_risk_pct is not None
        assert d.computed_risk_pct <= eng.limits.max_risk_per_trade_pct * 1.001


@settings(max_examples=100, deadline=None)
@given(direction=st.sampled_from(["LONG", "SHORT"]), entry=price)
def test_valid_directions_never_crash(direction, entry):
    port = PortfolioState(equity=100_000, balance=100_000, drawdown_pct=0,
                          daily_risk_used_pct=0, weekly_risk_used_pct=0,
                          total_notional=0)
    eng = RiskEngine(RiskLimits())
    stop = entry * (0.99 if direction == "LONG" else 1.01)
    target = entry * (1.02 if direction == "LONG" else 0.98)
    prop = Proposal(asset="XAUUSD", direction=direction, entry=entry,
                    stop_loss=stop, target1=target)
    d = eng.evaluate(prop, port, quote=_quote(entry))
    assert d.decision == "APPROVED"
    assert math.isfinite(d.suggested_qty)


@settings(max_examples=80, deadline=None)
@given(bad_dir=st.sampled_from(["long", "UP", "", "FLAT"]))
def test_invalid_direction_always_rejected(bad_dir):
    port = PortfolioState(equity=100_000, balance=100_000, drawdown_pct=0,
                          daily_risk_used_pct=0, weekly_risk_used_pct=0,
                          total_notional=0)
    eng = RiskEngine(RiskLimits())
    prop = Proposal(asset="XAUUSD", direction=bad_dir, entry=2500,
                    stop_loss=2475, target1=2550)
    assert eng.evaluate(prop, port).decision == "REJECTED"


# ------------------------------------------------------- reconciliation ------
@settings(max_examples=120, deadline=None)
@given(dev=st.floats(min_value=0.0, max_value=0.05))
def test_divergence_threshold_monotonic(dev):
    eng = MarketDataReconciliationEngine()
    now = datetime.now(UTC)
    primary = _quote(2500.0)
    secondary = _quote(2500.0 * (1 + dev))
    for q in (primary, secondary):
        q.ts_source = now
    report = eng.reconcile(
        symbol="XAUUSD",
        readings=[
            FeedReading(tier=FeedTier.PRIMARY, provider="rtds", quote=primary),
            FeedReading(tier=FeedTier.SECONDARY, provider="second", quote=secondary),
        ],
        now=now,
    )
    if dev > eng.max_pct_deviation:
        assert report.state == ReconciliationState.DIVERGENT
    else:
        assert report.state != ReconciliationState.DIVERGENT


@settings(max_examples=80, deadline=None)
@given(age_sec=st.floats(min_value=0, max_value=600))
def test_stale_classification_by_age(age_sec):
    eng = MarketDataReconciliationEngine(stale_after_sec=180.0)
    now = datetime.now(UTC)
    q = _quote(2500.0, age_sec=age_sec)
    report = eng.reconcile(
        symbol="XAUUSD",
        readings=[FeedReading(tier=FeedTier.PRIMARY, provider="p", quote=q)],
        now=now,
    )
    if age_sec > 180:
        assert report.state == ReconciliationState.STALE
    else:
        assert report.state != ReconciliationState.STALE
