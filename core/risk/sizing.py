"""Position sizing: fixed fractional risk on stop distance."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SizingResult:
    qty: float
    risk_amount: float
    stop_distance: float
    risk_per_unit: float
    notional: float | None  # requires entry price


def position_size(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
    contract_value: float = 1.0,
    min_qty: float = 0.0,
) -> SizingResult:
    """
    contract_value: value per 1 unit of qty in account currency (1 for crypto/FX,
    point-value for futures). Raises ValueError on nonsensical inputs.
    """
    if equity <= 0 or risk_pct <= 0:
        raise ValueError("equity and risk_pct must be positive")
    if entry <= 0 or stop <= 0:
        raise ValueError("entry/stop must be positive")
    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        raise ValueError("entry equals stop: undefined risk")

    risk_amount = equity * risk_pct / 100.0
    risk_per_unit = stop_distance * contract_value
    qty = max(min_qty, round(risk_amount / risk_per_unit, 8))
    return SizingResult(
        qty=qty,
        risk_amount=round(risk_amount, 2),
        stop_distance=round(stop_distance, 6),
        risk_per_unit=round(risk_per_unit, 6),
        notional=round(qty * entry * contract_value, 2),
    )


def reward_risk(entry: float, stop: float, target: float) -> float:
    """R multiple of a target vs stop distance."""
    risk = abs(entry - stop)
    if risk == 0:
        raise ValueError("undefined R:R (entry==stop)")
    return round(abs(target - entry) / risk, 3)
