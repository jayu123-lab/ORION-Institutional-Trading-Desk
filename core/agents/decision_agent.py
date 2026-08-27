"""LLM Agent for autonomous trading decisions."""
import logging
from typing import Optional, Dict, List
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class DecisionAgentPrompt:
    """System prompts for decision-making agent."""

    @staticmethod
    def get_system_prompt() -> str:
        return """You are ORION's autonomous decision-making agent. Your role is to:

1. ANALYZE market data and specialist inputs
2. GENERATE trade decisions with clear reasoning
3. RESPECT risk parameters and R:R minimums
4. PROVIDE actionable recommendations

DECISION FRAMEWORK:
- You only recommend trades with R:R >= 1:2
- Confidence must be >= 75% for LONG/SHORT recommendations
- Default to WAIT if uncertain
- Always cite data sources and calculations
- Never override risk manager veto

OUTPUT FORMAT:
{
  "decision": "LONG|SHORT|WAIT",
  "confidence": 0.0-1.0,
  "rationale": "Clear reasoning",
  "entry": price,
  "stop_loss": price,
  "target": price,
  "risk_reward": ratio,
  "catalyst": "What triggered this decision",
  "risk_level": "LOW|MEDIUM|HIGH"
}

CONSTRAINTS:
- Only use data provided
- Show all calculations
- Flag data quality issues
- Consider volatility (VIX) impact
- Account for liquidity requirements"""

    @staticmethod
    def get_analysis_prompt(
        asset: str,
        market_data: Dict,
        specialist_inputs: Dict,
        account_size: float,
    ) -> str:
        return f"""Analyze this trading opportunity and provide a decision:

ASSET: {asset}

MARKET DATA:
{json.dumps(market_data, indent=2)}

SPECIALIST INPUTS:
{json.dumps(specialist_inputs, indent=2)}

ACCOUNT SIZE: ${account_size:,.0f}

Your task:
1. Evaluate macro bias from specialists
2. Check liquidity requirements
3. Calculate entry/stop/target levels
4. Verify R:R ratio >= 1:2
5. Assess risk/reward balance
6. Provide final recommendation

Generate JSON response with decision framework."""


class LLMDecisionAgent:
    """Autonomous LLM agent for trading decisions."""

    def __init__(self, model_name: str = "claude-opus"):
        self.model = model_name
        self.decision_history: List[Dict] = []
        self.system_prompt = DecisionAgentPrompt.get_system_prompt()

    async def analyze_and_decide(
        self,
        asset: str,
        market_data: Dict,
        specialist_inputs: Dict,
        account_size: float,
    ) -> Optional[Dict]:
        """
        Use LLM to analyze and generate trade decision.
        Note: In production, this would call Anthropic API.
        """
        try:
            analysis_prompt = DecisionAgentPrompt.get_analysis_prompt(
                asset, market_data, specialist_inputs, account_size
            )

            decision = await self._simulated_llm_analysis(
                asset, market_data, specialist_inputs, account_size
            )

            if decision:
                self.decision_history.append({
                    "asset": asset,
                    "decision": decision,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                logger.info(f"LLM Decision for {asset}: {decision['decision']}")
                return decision

            return None

        except Exception as e:
            logger.error(f"LLM decision error: {e}")
            return None

    async def _simulated_llm_analysis(
        self,
        asset: str,
        market_data: Dict,
        specialist_inputs: Dict,
        account_size: float,
    ) -> Optional[Dict]:
        """Simulated LLM analysis (placeholder for real API call)."""

        macro_bias = specialist_inputs.get("macro", {}).get("bias", "NEUTRAL")
        liquidity_ok = specialist_inputs.get("liquidity", {}).get("ok", False)
        momentum = specialist_inputs.get("momentum", 0)
        risk_score = specialist_inputs.get("risk_score", 50)

        current_price = market_data.get("price", 0)
        vix = market_data.get("vix", 20)

        if macro_bias == "STRONG_BULLISH" and liquidity_ok and momentum > 60:
            decision_type = "LONG"
            confidence = min(0.95, 0.70 + (momentum / 200))
        elif macro_bias == "BEARISH" and liquidity_ok and momentum < -60:
            decision_type = "SHORT"
            confidence = min(0.95, 0.70 + (abs(momentum) / 200))
        else:
            decision_type = "WAIT"
            confidence = 0.5

        if decision_type == "WAIT" or confidence < 0.75:
            return {
                "decision": "WAIT",
                "confidence": confidence,
                "rationale": "Insufficient conviction or unfavorable conditions",
                "risk_level": "N/A",
            }

        if decision_type == "LONG":
            entry = current_price
            stop_loss = entry * 0.98
            target = entry * (1.04 if vix < 20 else 1.03)
        else:
            entry = current_price
            stop_loss = entry * 1.02
            target = entry * (0.96 if vix < 20 else 0.97)

        risk = abs(entry - stop_loss)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0

        if risk_score > 70:
            risk_level = "HIGH"
        elif risk_score > 50:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "decision": decision_type,
            "confidence": round(confidence, 2),
            "rationale": f"Macro bias {macro_bias}, momentum {momentum:.0f}, VIX {vix:.1f}",
            "entry": round(entry, 2),
            "stop_loss": round(stop_loss, 2),
            "target": round(target, 2),
            "risk_reward": round(rr, 2),
            "catalyst": f"Specialist consensus: {macro_bias}",
            "risk_level": risk_level,
            "max_position_size": round(account_size * 0.02 / risk, 0) if risk > 0 else 0,
        }

    def get_decision_history(self, limit: int = 10) -> List[Dict]:
        """Get recent decisions."""
        return self.decision_history[-limit:]

    def get_performance_stats(self) -> Dict:
        """Get agent performance statistics."""
        total_decisions = len(self.decision_history)
        long_decisions = len([d for d in self.decision_history if d["decision"]["decision"] == "LONG"])
        short_decisions = len([d for d in self.decision_history if d["decision"]["decision"] == "SHORT"])
        wait_decisions = total_decisions - long_decisions - short_decisions

        avg_confidence = (
            sum(d["decision"].get("confidence", 0) for d in self.decision_history) / total_decisions
            if total_decisions > 0
            else 0
        )

        return {
            "total_decisions": total_decisions,
            "long": long_decisions,
            "short": short_decisions,
            "wait": wait_decisions,
            "avg_confidence": round(avg_confidence, 2),
            "model": self.model,
        }
