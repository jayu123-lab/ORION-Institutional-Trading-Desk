"""Real Claude API integration for trade decision analysis."""

import logging
import os
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class ClaudeDecisionAnalyzer:
    """Interfaces with Claude API for real-time trade decision analysis."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = "claude-opus-5"
        self.base_url = "https://api.anthropic.com"
        self.version = "2024-06-01"

    async def analyze_market_context(
        self,
        symbol: str,
        current_price: float,
        bid_ask: dict,
        recent_volume: dict,
        market_regime: str,
        macro_context: str,
        data_quality: str,
    ) -> dict:
        """Analyze market context using Claude."""
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set; skipping real Claude analysis")
            return {"status": "skipped", "reason": "API key not configured"}

        prompt = self._build_analysis_prompt(
            symbol, current_price, bid_ask, recent_volume, market_regime, macro_context, data_quality
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": self.version,
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 1000,
                        "system": self._get_system_prompt(),
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )

            if response.status_code == 200:
                result = response.json()
                analysis = result["content"][0]["text"]
                return {
                    "status": "success",
                    "symbol": symbol,
                    "analysis": analysis,
                    "model": self.model,
                }
            else:
                logger.error(f"Claude API error: {response.status_code} {response.text}")
                return {
                    "status": "error",
                    "reason": f"API returned {response.status_code}",
                }
        except Exception as e:
            logger.error(f"Failed to call Claude API: {e}")
            return {"status": "error", "reason": str(e)}

    async def generate_trade_decision(
        self,
        symbol: str,
        analysis_context: str,
        current_positions: dict,
        risk_limits: dict,
    ) -> dict:
        """Generate a trade decision recommendation using Claude."""
        if not self.api_key:
            return {"status": "skipped", "reason": "API key not configured"}

        prompt = self._build_decision_prompt(
            symbol, analysis_context, current_positions, risk_limits
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": self.version,
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 800,
                        "system": self._get_decision_system_prompt(),
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )

            if response.status_code == 200:
                result = response.json()
                decision = result["content"][0]["text"]
                return {
                    "status": "success",
                    "symbol": symbol,
                    "decision": decision,
                    "model": self.model,
                }
            else:
                logger.error(f"Claude API error: {response.status_code}")
                return {"status": "error", "reason": f"API returned {response.status_code}"}
        except Exception as e:
            logger.error(f"Failed to generate decision: {e}")
            return {"status": "error", "reason": str(e)}

    def _build_analysis_prompt(
        self,
        symbol: str,
        current_price: float,
        bid_ask: dict,
        recent_volume: dict,
        market_regime: str,
        macro_context: str,
        data_quality: str,
    ) -> str:
        """Build market analysis prompt for Claude."""
        return f"""
Analyze the following market context for {symbol} and provide institutional-grade insights:

CURRENT MARKET STATE:
- Symbol: {symbol}
- Current Price: ${current_price}
- Bid/Ask: {bid_ask}
- Recent Volume: {recent_volume}

MARKET REGIME: {market_regime}
MACRO CONTEXT: {macro_context}
DATA QUALITY: {data_quality}

Provide:
1. Key technical observations
2. Macro drivers affecting this asset
3. Risk factors to monitor
4. Potential support/resistance levels
5. Institutional positioning clues (if any)

Keep analysis focused, data-driven, and actionable.
"""

    def _build_decision_prompt(
        self,
        symbol: str,
        analysis_context: str,
        current_positions: dict,
        risk_limits: dict,
    ) -> str:
        """Build trade decision prompt for Claude."""
        return f"""
Based on the following analysis, recommend a trade decision for {symbol}:

ANALYSIS:
{analysis_context}

CURRENT POSITIONS:
{current_positions}

RISK LIMITS:
- Max daily loss: {risk_limits.get('max_daily_loss')}
- R:R requirement: {risk_limits.get('risk_reward_ratio')}
- Position limit: {risk_limits.get('position_limit')}

Recommend one of: LONG, SHORT, HOLD, REDUCE
Provide confidence level (0-100) and risk/reward ratio.
Include stop loss and take profit levels if taking position.
"""

    def _get_system_prompt(self) -> str:
        """System prompt for market analysis."""
        return """You are an institutional trading desk analyst. Provide accurate,
data-driven market analysis. Never make unfounded claims about future price movements.
Focus on probability, risk management, and verified data. Avoid retail trading advice."""

    def _get_decision_system_prompt(self) -> str:
        """System prompt for trade decisions."""
        return """You are a senior trader making position recommendations.
Prioritize risk management above all else. Every recommendation must have:
1. Clear entry logic
2. Stop loss level with risk amount
3. Take profit target with potential gain
4. Risk/reward ratio >= 1:2
5. Confidence level based on evidence

Never recommend a trade without proper risk parameters."""

    def is_configured(self) -> bool:
        """Check if Claude API is properly configured."""
        return bool(self.api_key)
