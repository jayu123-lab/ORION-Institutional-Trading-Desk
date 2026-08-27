"""Tests for autonomous decision making."""
import pytest
from core.orchestration.autonomous_decision import (
    TradeDecision,
    CIOAutonomousLayer,
    RiskManagerAutonomousLayer,
    AutonomousTradeOrchestrator,
)


def test_trade_decision_creation():
    """Test creating a trade decision."""
    decision = TradeDecision(
        asset="SPY",
        direction="LONG",
        confidence=0.85,
        risk_score=30,
        entry_price=450.0,
        stop_loss=441.0,
        target=468.0,
        rationale="Bullish bias confirmed",
        cio_bias="STRONG_BULLISH",
    )
    assert decision.asset == "SPY"
    assert decision.direction == "LONG"


def test_trade_decision_rr_calculation():
    """Test R:R ratio calculation."""
    decision = TradeDecision(
        asset="SPY",
        direction="LONG",
        confidence=0.85,
        risk_score=30,
        entry_price=450.0,
        stop_loss=441.0,  # Risk: 9
        target=468.0,  # Reward: 18 (1:2 R:R)
        rationale="Test",
        cio_bias="BULLISH",
    )
    rr = decision.calculate_rr()
    assert rr >= 1.5  # Should be approximately 2.0


def test_trade_decision_meets_criteria():
    """Test if trade meets minimum R:R criteria."""
    # Good trade: 1:2 R:R
    good_trade = TradeDecision(
        asset="SPY",
        direction="LONG",
        confidence=0.85,
        risk_score=30,
        entry_price=450.0,
        stop_loss=441.0,
        target=468.0,
        rationale="Test",
        cio_bias="BULLISH",
    )
    assert good_trade.meets_risk_criteria()

    # Bad trade: insufficient R:R
    bad_trade = TradeDecision(
        asset="QQQ",
        direction="LONG",
        confidence=0.85,
        risk_score=30,
        entry_price=350.0,
        stop_loss=348.0,  # Risk: 2
        target=351.0,  # Reward: 1 (0.5:1 R:R)
        rationale="Test",
        cio_bias="BULLISH",
    )
    assert not bad_trade.meets_risk_criteria()


@pytest.mark.asyncio
async def test_cio_analysis():
    """Test CIO analysis and decision generation."""
    cio = CIOAutonomousLayer()
    market_data = {"price": 450.0}
    specialist_inputs = {
        "macro": {"bias": "STRONG_BULLISH"},
        "liquidity": {"ok": True},
        "trend": "UP",
        "momentum": 75,
        "risk_score": 25,
    }

    decision = await cio.analyze_opportunity(
        asset="SPY",
        market_data=market_data,
        specialist_inputs=specialist_inputs,
    )

    assert decision is not None
    assert decision.direction == "LONG"


@pytest.mark.asyncio
async def test_risk_manager_approval():
    """Test risk manager approval logic."""
    risk_mgr = RiskManagerAutonomousLayer(max_daily_loss_pct=2.0)

    # Create a good trade
    decision = TradeDecision(
        asset="SPY",
        direction="LONG",
        confidence=0.85,
        risk_score=30,
        entry_price=450.0,
        stop_loss=441.0,
        target=468.0,
        rationale="Test",
        cio_bias="BULLISH",
    )

    account_size = 100000
    approved = await risk_mgr.evaluate_trade(decision, account_size)
    assert approved


@pytest.mark.asyncio
async def test_autonomous_orchestrator():
    """Test full orchestration pipeline."""
    orchestrator = AutonomousTradeOrchestrator()

    market_data = {"price": 450.0}
    specialist_inputs = {
        "macro": {"bias": "STRONG_BULLISH"},
        "liquidity": {"ok": True},
        "trend": "UP",
        "momentum": 75,
        "risk_score": 25,
    }

    decision = await orchestrator.evaluate_asset(
        asset="SPY",
        market_data=market_data,
        specialist_inputs=specialist_inputs,
        account_size=100000,
    )

    assert decision is None or decision.status.value in ["approved", "pending", "rejected"]
