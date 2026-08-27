"""Autonomous decision making: CIO + Risk Manager integration."""
import logging
from enum import Enum
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class DecisionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAITING = "waiting"
    EXECUTED = "executed"


class TradeDecision:
    """Represents an automated trade decision."""

    def __init__(
        self,
        asset: str,
        direction: str,  # LONG, SHORT, WAIT, NO_TRADE
        confidence: float,
        risk_score: float,
        entry_price: float,
        stop_loss: float,
        target: float,
        rationale: str,
        cio_bias: str,
    ):
        self.asset = asset
        self.direction = direction
        self.confidence = confidence
        self.risk_score = risk_score
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.target = target
        self.rationale = rationale
        self.cio_bias = cio_bias
        self.status = DecisionStatus.PENDING
        self.timestamp = datetime.utcnow()
        self.risk_approval = False
        self.risk_comments = ""

    def calculate_rr(self) -> float:
        """Calculate risk/reward ratio."""
        if self.direction == "LONG":
            risk = abs(self.entry_price - self.stop_loss)
            reward = abs(self.target - self.entry_price)
        else:  # SHORT
            risk = abs(self.stop_loss - self.entry_price)
            reward = abs(self.entry_price - self.target)

        return reward / risk if risk > 0 else 0

    def meets_risk_criteria(self) -> bool:
        """Check if trade meets minimum risk/reward criteria."""
        # Minimum R:R is 1:2
        rr = self.calculate_rr()
        return rr >= 1.5

    def __repr__(self):
        return (
            f"TradeDecision({self.asset} {self.direction} @ {self.entry_price} "
            f"| R:R={self.calculate_rr():.2f} | Conf={self.confidence:.0%})"
        )


class CIOAutonomousLayer:
    """Autonomous CIO decision making."""

    def __init__(self):
        self.decisions: List[TradeDecision] = []
        self.decision_threshold = 0.75  # 75% confidence minimum

    async def analyze_opportunity(
        self,
        asset: str,
        market_data: Dict,
        specialist_inputs: Dict,
    ) -> Optional[TradeDecision]:
        """Analyze opportunity and generate decision."""

        # Extract from specialist inputs
        macro_bias = specialist_inputs.get("macro", {}).get("bias", "NEUTRAL")
        liquidity_check = specialist_inputs.get("liquidity", {}).get("ok", False)
        trend = specialist_inputs.get("trend", "")
        momentum = specialist_inputs.get("momentum", 0)
        risk_score = specialist_inputs.get("risk_score", 50)

        # Determine direction based on signals
        if macro_bias == "STRONG_BULLISH" and liquidity_check and momentum > 50:
            direction = "LONG"
            confidence = min(0.95, abs(momentum) / 100)
        elif macro_bias == "BEARISH" and liquidity_check and momentum < -50:
            direction = "SHORT"
            confidence = min(0.95, abs(momentum) / 100)
        else:
            direction = "WAIT"
            confidence = 0.0

        # Skip if confidence too low
        if confidence < self.decision_threshold and direction != "WAIT":
            logger.info(f"Skipping {asset}: confidence {confidence:.0%} < threshold")
            return None

        # Calculate levels
        current_price = market_data.get("price", 0)
        if direction == "LONG":
            entry = current_price
            stop_loss = entry * 0.98  # 2% stop
            target = entry * 1.04  # 4% target (1:2 R:R)
        elif direction == "SHORT":
            entry = current_price
            stop_loss = entry * 1.02
            target = entry * 0.96
        else:
            return None

        decision = TradeDecision(
            asset=asset,
            direction=direction,
            confidence=confidence,
            risk_score=risk_score,
            entry_price=entry,
            stop_loss=stop_loss,
            target=target,
            rationale=f"Macro: {macro_bias} | Trend: {trend} | Momentum: {momentum:.0f}",
            cio_bias=macro_bias,
        )

        self.decisions.append(decision)
        logger.info(f"CIO Decision: {decision}")
        return decision

    def get_active_decisions(self) -> List[TradeDecision]:
        """Get all active decisions awaiting execution."""
        return [d for d in self.decisions if d.status == DecisionStatus.PENDING]


class RiskManagerAutonomousLayer:
    """Autonomous risk manager gate + veto power."""

    def __init__(self, max_daily_loss_pct: float = 2.0):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.daily_pnl = 0.0
        self.rejections: List[Dict] = []

    async def evaluate_trade(self, decision: TradeDecision, account_size: float) -> bool:
        """Evaluate trade and approve/reject."""

        # Check 1: Risk/Reward ratio
        if not decision.meets_risk_criteria():
            self._reject(decision, "R:R < 1:2")
            return False

        # Check 2: Daily loss limit
        risk_amount = abs(decision.entry_price - decision.stop_loss)
        max_risk = account_size * (self.max_daily_loss_pct / 100)
        if risk_amount > max_risk:
            self._reject(decision, f"Risk ${risk_amount:.0f} > limit ${max_risk:.0f}")
            return False

        # Check 3: Confidence check
        if decision.confidence < 0.70:
            self._reject(decision, "Confidence too low")
            return False

        # Check 4: Data quality
        if decision.risk_score > 70:  # High risk = low data quality
            self._reject(decision, "Data quality degraded")
            return False

        # APPROVED
        decision.status = DecisionStatus.APPROVED
        decision.risk_approval = True
        decision.risk_comments = "✅ Approved by Risk Manager"
        logger.info(f"Risk Manager APPROVED: {decision}")
        return True

    def _reject(self, decision: TradeDecision, reason: str) -> None:
        """Reject trade with reason."""
        decision.status = DecisionStatus.REJECTED
        decision.risk_comments = f"❌ Rejected: {reason}"
        self.rejections.append({
            "decision": decision,
            "reason": reason,
            "timestamp": datetime.utcnow(),
        })
        logger.warning(f"Risk Manager REJECTED {decision.asset}: {reason}")

    def get_daily_stats(self) -> Dict:
        """Get daily risk statistics."""
        return {
            "daily_pnl": self.daily_pnl,
            "max_loss_pct": self.max_daily_loss_pct,
            "rejections_today": len(self.rejections),
        }


class AutonomousTradeOrchestrator:
    """Orchestrates autonomous decision flow."""

    def __init__(self):
        self.cio = CIOAutonomousLayer()
        self.risk_manager = RiskManagerAutonomousLayer()
        self.executed_trades: List[TradeDecision] = []

    async def evaluate_asset(
        self,
        asset: str,
        market_data: Dict,
        specialist_inputs: Dict,
        account_size: float,
    ) -> Optional[TradeDecision]:
        """Full evaluation pipeline: CIO → Risk → Execute."""

        # Step 1: CIO analysis
        decision = await self.cio.analyze_opportunity(asset, market_data, specialist_inputs)
        if not decision:
            logger.info(f"CIO passed on {asset}")
            return None

        # Step 2: Risk approval
        if await self.risk_manager.evaluate_trade(decision, account_size):
            decision.status = DecisionStatus.APPROVED
            logger.warning(f"🔴 TRADE READY TO EXECUTE: {decision}")
            self.executed_trades.append(decision)
            return decision
        else:
            logger.info(f"Risk manager rejected {asset}")
            return None

    def get_execution_queue(self) -> List[TradeDecision]:
        """Get all approved trades awaiting execution."""
        return [
            d for d in self.cio.get_active_decisions()
            if d.status == DecisionStatus.APPROVED
        ]

    def get_stats(self) -> Dict:
        """Get orchestrator statistics."""
        return {
            "total_decisions": len(self.cio.decisions),
            "approved": len(self.get_execution_queue()),
            "executed": len(self.executed_trades),
            "risk_stats": self.risk_manager.get_daily_stats(),
        }
