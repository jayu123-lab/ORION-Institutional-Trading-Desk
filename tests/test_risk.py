from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.market_data.base import DataQuality, DataStatus, Quote
from core.risk.engine import PortfolioState, Proposal, RiskEngine, RiskLimits
from core.risk.metrics import risk_of_ruin, trade_metrics
from core.risk.sizing import position_size, reward_risk


def _quote(status: DataStatus = DataStatus.LIVE) -> Quote:
    return Quote(
        symbol="XAUUSD",
        price=2350.0,
        bid=2349.8,
        ask=2350.2,
        ts_source=datetime.now(UTC),
        quality=DataQuality(provider="test", status=status),
    )


def _portfolio(**overrides) -> PortfolioState:
    base = dict(
        equity=100_000.0,
        balance=100_000.0,
        drawdown_pct=0.0,
        daily_risk_used_pct=0.0,
        weekly_risk_used_pct=0.0,
        total_notional=0.0,
    )
    base.update(overrides)
    return PortfolioState(**base)


def test_position_size_basic():
    res = position_size(10_000, 1.0, entry=2000, stop=1990)
    assert res.risk_amount == 100
    assert res.stop_distance == 10
    assert res.qty == 10


def test_position_size_rejects_degenerate():
    with pytest.raises(ValueError):
        position_size(10_000, 1.0, 2000, 2000)
    with pytest.raises(ValueError):
        position_size(0, 1.0, 2000, 1990)


def test_reward_risk():
    assert reward_risk(entry=100, stop=95, target=110) == 2.0


def test_engine_approves_sound_trade():
    engine = RiskEngine()
    # 20$ stop on 100k equity & 1% risk → 50 oz ≈ 117k notional (117% < 150% cap)
    proposal = Proposal("XAUUSD", "LONG", 2350, 2330, 2390)
    decision = engine.evaluate(proposal, _portfolio(), quote=_quote())
    assert decision.decision == "APPROVED", decision.reasons
    assert decision.suggested_qty and decision.suggested_qty > 0


def test_engine_rejects_stale_data():
    engine = RiskEngine()
    proposal = Proposal("XAUUSD", "LONG", 2350, 2345, 2362)
    decision = engine.evaluate(proposal, _portfolio(), quote=_quote(DataStatus.STALE))
    assert decision.decision == "REJECTED"
    assert any("STALE" in r for r in decision.reasons)


def test_engine_rejects_bad_rr():
    engine = RiskEngine(RiskLimits(min_reward_risk=2.0))
    proposal = Proposal("XAUUSD", "LONG", 2350, 2345, 2354)  # R:R < 1
    decision = engine.evaluate(proposal, _portfolio(), quote=_quote())
    assert decision.decision == "REJECTED"


def test_engine_reduce_size_on_daily_cap():
    engine = RiskEngine()  # max_daily 3%, per-trade 1%
    proposal = Proposal("XAUUSD", "LONG", 2350, 2345, 2362)
    portfolio = _portfolio(daily_risk_used_pct=2.7)  # only 0.3% room of 1% needed
    decision = engine.evaluate(proposal, portfolio, quote=_quote())
    assert decision.decision == "REDUCE_SIZE"
    assert decision.suggested_qty is not None


def test_engine_waits_for_event():
    engine = RiskEngine()
    proposal = Proposal("XAUUSD", "LONG", 2350, 2330, 2390)
    decision = engine.evaluate(
        proposal, _portfolio(), quote=_quote(), has_high_impact_event_pending=True
    )
    assert decision.decision == "WAIT"
    assert decision.conditions


def test_engine_rejects_drawdown_breach():
    engine = RiskEngine(RiskLimits(max_drawdown_pct=10))
    proposal = Proposal("XAUUSD", "LONG", 2350, 2345, 2362)
    decision = engine.evaluate(proposal, _portfolio(drawdown_pct=12), quote=_quote())
    assert decision.decision == "REJECTED"


def test_trade_metrics_expectancy_and_dd():
    m = trade_metrics([1.0, -1.0, 2.0, -1.0, 3.0])
    assert m.n_trades == 5
    assert m.win_rate == 60.0
    assert m.expectancy_r == pytest.approx(0.8, rel=1e-3)
    # cumulative: 1, 0, 2, 1, 4 → worst dip below running peak is -1R
    assert m.max_drawdown_r == pytest.approx(-1.0)


def test_risk_of_ruin_zero_edge():
    assert risk_of_ruin(win_prob=30, avg_win_r=1, avg_loss_r=2) == 1.0
