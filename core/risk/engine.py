"""RiskEngine: independent evaluation with VETO authority (spec §3).

The risk manager never approves just because others agree — it recomputes
sizing, checks limits/exposure/data quality and can return WAIT/REJECT.

Decision taxonomy:
- FATAL issues (stale data, degenerate levels, R:R below minimum, drawdown halt,
  invalid direction) -> REJECTED, never negotiable.
- CAP issues (daily/weekly risk, exposure caps) -> REDUCE_SIZE when a fitting
  fraction exists (>= 25% of intended risk), else REJECTED.
- Timing constraints (high-impact event) -> WAIT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from core.market_data.base import DataStatus, Quote
from core.risk.sizing import position_size

Decision = Literal["APPROVED", "REDUCE_SIZE", "WAIT", "REJECTED"]


@dataclass(frozen=True)
class RiskLimits:
    max_risk_per_trade_pct: float = 1.0  # % equity per trade
    max_daily_risk_pct: float = 3.0
    max_weekly_risk_pct: float = 6.0
    max_drawdown_pct: float = 10.0  # halt new risk beyond this DD
    max_total_exposure_pct: float = 300.0  # notional / equity
    max_single_asset_exposure_pct: float = 150.0
    max_correlated_group_exposure_pct: float = 250.0
    min_reward_risk: float = 1.0
    stale_data_rejects: bool = True


@dataclass(frozen=True)
class PortfolioState:
    equity: float
    balance: float
    drawdown_pct: float
    daily_risk_used_pct: float
    weekly_risk_used_pct: float
    total_notional: float
    notional_by_asset: dict[str, float] = field(default_factory=dict)
    open_trades_today: int = 0


@dataclass(frozen=True)
class Proposal:
    asset: str
    direction: str  # LONG|SHORT
    entry: float
    stop_loss: float
    target1: float
    contract_value: float = 1.0
    correlated_group: str | None = None  # e.g. "usd-metals", "majors"


@dataclass(frozen=True)
class RiskDecision:
    decision: Decision
    reasons: list[str]
    conditions: list[str]
    suggested_qty: float | None = None
    computed_risk_pct: float | None = None

    @property
    def approved(self) -> bool:
        return self.decision == "APPROVED"


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def evaluate(
        self,
        proposal: Proposal,
        portfolio: PortfolioState,
        quote: Quote | None = None,
        has_high_impact_event_pending: bool = False,
        correlated_group_notional: float = 0.0,
    ) -> RiskDecision:
        if portfolio.equity <= 0:
            return RiskDecision("REJECTED", ["no equity configured"], [])

        # --- data quality gate --------------------------------------------
        if quote is not None and self.limits.stale_data_rejects:
            if quote.quality.status in (DataStatus.STALE, DataStatus.DISCONNECTED):
                return RiskDecision(
                    "REJECTED",
                    [f"quote status {quote.quality.status} from {quote.quality.provider}"],
                    [],
                )

        entry, stop = proposal.entry, proposal.stop_loss
        if entry <= 0 or stop <= 0 or entry == stop:
            return RiskDecision("REJECTED", ["entry/stop missing or degenerate"], [])

        sizing = position_size(
            portfolio.equity,
            self.limits.max_risk_per_trade_pct,
            entry,
            stop,
            proposal.contract_value,
        )
        risk_pct = sizing.risk_amount / portfolio.equity * 100
        rr = abs(proposal.target1 - entry) / abs(entry - stop)

        # --- FATAL issues ---------------------------------------------------
        fatal: list[str] = []
        if rr < self.limits.min_reward_risk:
            fatal.append(f"R:R {rr:.2f} below minimum {self.limits.min_reward_risk}")
        if portfolio.drawdown_pct >= self.limits.max_drawdown_pct:
            fatal.append(f"drawdown {portfolio.drawdown_pct:.1f}% at/above halt threshold")
        if proposal.direction not in ("LONG", "SHORT"):
            fatal.append(f"invalid direction '{proposal.direction}'")
        if fatal:
            return RiskDecision("REJECTED", fatal, [])

        # --- CAP issues (reducible) -----------------------------------------
        caps: list[str] = []
        new_notional = sizing.notional or 0.0

        if portfolio.daily_risk_used_pct + risk_pct > self.limits.max_daily_risk_pct:
            caps.append(
                f"daily risk {portfolio.daily_risk_used_pct:.2f}%+{risk_pct:.2f}% exceeds cap"
            )
        if portfolio.weekly_risk_used_pct + risk_pct > self.limits.max_weekly_risk_pct:
            caps.append("weekly risk cap exceeded")

        total_exposure_pct = (portfolio.total_notional + new_notional) / portfolio.equity * 100
        if total_exposure_pct > self.limits.max_total_exposure_pct:
            caps.append(f"total exposure {total_exposure_pct:.0f}% above cap")

        single = new_notional + portfolio.notional_by_asset.get(proposal.asset, 0.0)
        if single / portfolio.equity * 100 > self.limits.max_single_asset_exposure_pct:
            caps.append(f"single-asset exposure on {proposal.asset} above cap")

        if proposal.correlated_group:
            group = (correlated_group_notional + new_notional) / portfolio.equity * 100
            if group > self.limits.max_correlated_group_exposure_pct:
                caps.append(f"correlated group '{proposal.correlated_group}' exposure {group:.0f}%")

        conditions: list[str] = []
        if has_high_impact_event_pending:
            conditions.append("high-impact event pending: consider WAIT until release")

        if caps:
            fit = self._fit_factor(portfolio, sizing.risk_amount)
            if fit >= 0.25:
                return RiskDecision(
                    "REDUCE_SIZE",
                    caps,
                    conditions,
                    suggested_qty=round(sizing.qty * fit, 8),
                    computed_risk_pct=round(risk_pct * fit, 3),
                )
            caps.insert(0, "even reduced size violates limits")
            return RiskDecision("REJECTED", caps, conditions)

        if conditions:
            return RiskDecision("WAIT", ["acceptable risk but timing constraints"], conditions)

        return RiskDecision(
            "APPROVED",
            [f"sizing {sizing.qty} @ risk {risk_pct:.2f}% equity; R:R {rr:.2f}"],
            conditions,
            suggested_qty=sizing.qty,
            computed_risk_pct=round(risk_pct, 3),
        )

    def _fit_factor(self, portfolio: PortfolioState, risk_amount: float) -> float:
        """Fraction of intended risk that fits the daily cap."""
        room = max(0.0, self.limits.max_daily_risk_pct - portfolio.daily_risk_used_pct)
        intended_pct = risk_amount / portfolio.equity * 100
        if intended_pct <= 0:
            return 0.0
        return min(1.0, room / intended_pct)

    def snapshot_verdict(self, portfolio: PortfolioState) -> str:
        if portfolio.drawdown_pct >= self.limits.max_drawdown_pct:
            return "RED_LIGHT"
        if portfolio.daily_risk_used_pct >= self.limits.max_daily_risk_pct * 0.6:
            return "CAUTION"
        return "GREEN_LIGHT"

    def now(self) -> datetime:
        return datetime.now(UTC)
