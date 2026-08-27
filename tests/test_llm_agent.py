"""Tests for LLM decision agent."""
import pytest
from core.agents.decision_agent import LLMDecisionAgent, DecisionAgentPrompt


def test_decision_agent_prompt():
    """Test decision agent system prompt."""
    prompt = DecisionAgentPrompt.get_system_prompt()
    assert "R:R >= 1:2" in prompt
    assert "LONG|SHORT|WAIT" in prompt
    assert "Confidence" in prompt


def test_analysis_prompt_generation():
    """Test analysis prompt generation."""
    market_data = {"price": 450.0, "vix": 18.5}
    specialist_inputs = {
        "macro": {"bias": "BULLISH"},
        "momentum": 65,
    }

    prompt = DecisionAgentPrompt.get_analysis_prompt(
        asset="SPY",
        market_data=market_data,
        specialist_inputs=specialist_inputs,
        account_size=100000,
    )

    assert "SPY" in prompt
    assert "450" in prompt
    assert "100" in prompt  # Cuenta con formato


@pytest.mark.asyncio
async def test_llm_agent_initialization():
    """Test LLM agent initialization."""
    agent = LLMDecisionAgent(model_name="claude-opus")
    assert agent.model == "claude-opus"
    assert len(agent.decision_history) == 0


@pytest.mark.asyncio
async def test_simulated_analysis_long():
    """Test simulated LLM analysis for LONG signal."""
    agent = LLMDecisionAgent()
    market_data = {"price": 450.0, "vix": 15}
    specialist_inputs = {
        "macro": {"bias": "STRONG_BULLISH"},
        "liquidity": {"ok": True},
        "momentum": 75,
        "risk_score": 30,
    }

    decision = await agent._simulated_llm_analysis(
        asset="SPY",
        market_data=market_data,
        specialist_inputs=specialist_inputs,
        account_size=100000,
    )

    assert decision is not None
    assert decision["decision"] == "LONG"
    assert decision["confidence"] >= 0.75


@pytest.mark.asyncio
async def test_simulated_analysis_wait():
    """Test simulated LLM analysis for WAIT signal."""
    agent = LLMDecisionAgent()
    market_data = {"price": 450.0, "vix": 25}
    specialist_inputs = {
        "macro": {"bias": "NEUTRAL"},
        "liquidity": {"ok": False},
        "momentum": 20,
        "risk_score": 60,
    }

    decision = await agent._simulated_llm_analysis(
        asset="SPY",
        market_data=market_data,
        specialist_inputs=specialist_inputs,
        account_size=100000,
    )

    assert decision is not None
    assert decision["decision"] == "WAIT"


@pytest.mark.asyncio
async def test_decision_history():
    """Test decision history tracking."""
    agent = LLMDecisionAgent()
    market_data = {"price": 450.0, "vix": 15}
    specialist_inputs = {
        "macro": {"bias": "STRONG_BULLISH"},
        "liquidity": {"ok": True},
        "momentum": 75,
        "risk_score": 30,
    }

    await agent.analyze_and_decide(
        asset="SPY",
        market_data=market_data,
        specialist_inputs=specialist_inputs,
        account_size=100000,
    )

    await agent.analyze_and_decide(
        asset="QQQ",
        market_data=market_data,
        specialist_inputs=specialist_inputs,
        account_size=100000,
    )

    history = agent.get_decision_history()
    assert len(history) >= 2


@pytest.mark.asyncio
async def test_performance_stats():
    """Test performance statistics."""
    agent = LLMDecisionAgent()
    stats = agent.get_performance_stats()

    assert "total_decisions" in stats
    assert "long" in stats
    assert "short" in stats
    assert "wait" in stats
    assert "avg_confidence" in stats
    assert stats["model"] == "claude-opus"
