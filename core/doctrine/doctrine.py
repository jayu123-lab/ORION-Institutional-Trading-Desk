"""ORION Trading Doctrine (P1-P2, P13-P14).

Central source of truth shared by CIO and every specialist:
ORION does NOT operate by prediction. It operates by

    CONTEXT -> LIQUIDITY -> LEVEL -> REACTION -> CONFIRMATION
            -> RISK -> EXECUTION / WAIT

A level without reaction is NO TRADE. A bias is NOT an entry.
Never chase price. R:R below 2:1 is REJECTED.
"""

from __future__ import annotations

from dataclasses import dataclass, field

OPERATING_SEQUENCE: tuple[str, ...] = (
    "CONTEXT", "LIQUIDITY", "LEVEL", "REACTION", "CONFIRMATION",
    "RISK", "EXECUTION_OR_WAIT",
)

HIERARCHY: tuple[str, ...] = (
    "MACRO", "INTERMARKET", "POSITIONING", "MARKET_REGIME", "LIQUIDITY",
    "STRUCTURE", "KEY_LEVEL", "REACTION", "CONFIRMATION", "RISK",
    "TRADE_OR_WAIT",
)

MIN_RR = 2.0              # P14 — minimum acceptable reward:risk
MAX_CHASE_ATR = 2.0       # P13 — beyond this extension from zone: no chasing


@dataclass
class DoctrineDecision:
    """Outcome of applying the doctrine to one setup."""

    status: str                 # TRADE | WAIT | REJECT | NO_TRADE
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)  # check -> PASS/FAIL/SKIP

    def to_dict(self) -> dict:
        return {"status": self.status, "reasons": self.reasons, "checks": self.checks}


class ORIONTradingDoctrine:
    """Deterministic rule engine enforcing the operating sequence."""

    def __init__(self, min_rr: float = MIN_RR, max_chase_atr: float = MAX_CHASE_ATR):
        self.min_rr = min_rr
        self.max_chase_atr = max_chase_atr

    # ------------------------------------------------------------------ gate
    def evaluate(
        self,
        bias: str,
        *,
        reaction: bool | None,
        confirmation: bool | None,
        rr: float | None,
        extension_atr: float | None = None,
        risk_ok: bool = True,
        has_level: bool = True,
    ) -> DoctrineDecision:
        """Apply the sequence in order; first hard stop wins.

        bias alone never produces a trade — it is context only.
        """
        checks: dict[str, str] = {}
        reasons: list[str] = []

        if not risk_ok:
            return DoctrineDecision("NO_TRADE", ["risk veto active"], {"RISK": "FAIL"})
        checks["RISK"] = "PASS"

        if not has_level:
            checks["LEVEL"] = "FAIL"
            return DoctrineDecision(
                "WAIT", ["no verified key level — nothing to react to yet"], checks
            )
        checks["LEVEL"] = "PASS"

        if reaction is None:
            checks["REACTION"] = "SKIP"
            return DoctrineDecision(
                "WAIT", ["insufficient data to confirm reaction at level"], checks
            )
        if reaction is False:
            checks["REACTION"] = "FAIL"
            return DoctrineDecision(
                "NO_TRADE", ["level without reaction — doctrine says NO TRADE"], checks
            )
        checks["REACTION"] = "PASS"

        if confirmation is None:
            checks["CONFIRMATION"] = "SKIP"
            return DoctrineDecision(
                "WAIT", ["reaction present but unconfirmed — wait for structure shift"],
                checks,
            )
        if confirmation is False:
            checks["CONFIRMATION"] = "FAIL"
            return DoctrineDecision(
                "WAIT", ["no confirmation — bias is NOT an entry"], checks
            )
        checks["CONFIRMATION"] = "PASS"

        if extension_atr is not None and extension_atr > self.max_chase_atr:
            checks["NO_CHASE"] = "FAIL"
            return DoctrineDecision(
                "WAIT",
                [f"price {extension_atr:.1f} ATR from zone — WAIT FOR RETRACEMENT "
                 f"(never chase)"],
                checks,
            )
        checks["NO_CHASE"] = (
            "PASS" if extension_atr is None else f"PASS ({extension_atr:.1f} ATR)"
        )

        if rr is None:
            checks["RR"] = "SKIP"
            return DoctrineDecision(
                "WAIT", ["no measurable R:R — cannot size responsibly"], checks
            )
        if rr < self.min_rr:
            checks["RR"] = "FAIL"
            return DoctrineDecision(
                "REJECT", [f"R:R {rr:.2f} < {self.min_rr:.0f}:1 minimum — REJECT"], checks
            )
        checks["RR"] = f"PASS ({rr:.1f}:1)"

        if bias in ("LONG", "SHORT"):
            reasons.append(f"bias {bias} aligned with confirmed level reaction")
            return DoctrineDecision("TRADE", reasons, checks)
        return DoctrineDecision(
            "WAIT", [f"bias '{bias}' offers no directional edge even at a good level"],
            checks,
        )

    # --------------------------------------------------------------- helpers
    @staticmethod
    def rr_of(entry: float, stop: float, target: float) -> float | None:
        """Reward:risk of entry/stop/target. None when undefined."""
        risk = abs(entry - stop)
        if risk <= 0:
            return None
        return abs(target - entry) / risk

    @staticmethod
    def extension_in_atr(price: float, zone: float | None, atr: float | None) -> float | None:
        """Distance from the reaction zone expressed in ATRs."""
        if zone is None or atr is None or atr <= 0 or price is None:
            return None
        return abs(price - zone) / atr
