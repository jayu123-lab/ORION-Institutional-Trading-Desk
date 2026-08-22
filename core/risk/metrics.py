"""Portfolio metrics from closed R-multiple trades (spec §3 checklist)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TradeMetrics:
    n_trades: int
    win_rate: float | None  # 0..100
    profit_factor: float | None
    expectancy_r: float | None
    avg_win_r: float | None
    avg_loss_r: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown_r: float | None


def trade_metrics(r_multiples: list[float]) -> TradeMetrics:
    if not r_multiples:
        return TradeMetrics(0, None, None, None, None, None, None, None, None)

    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r <= 0]
    win_rate = len(wins) / len(r_multiples) * 100

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else math.inf

    mean = sum(r_multiples) / len(r_multiples)

    def _std(vals: list[float]) -> float:
        m = sum(vals) / len(vals)
        return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) if vals else 0.0

    std_all = _std(r_multiples)
    downside = [r for r in r_multiples if r < 0]
    std_down = _std(downside) or 0.0

    # running max drawdown in R
    equity, peak, dd = 0.0, 0.0, 0.0
    for r in r_multiples:
        equity += r
        peak = max(peak, equity)
        dd = min(dd, equity - peak)

    return TradeMetrics(
        n_trades=len(r_multiples),
        win_rate=round(win_rate, 1),
        profit_factor=round(profit_factor, 3),
        expectancy_r=round(mean, 4),
        avg_win_r=round((gross_win / len(wins)) if wins else 0.0, 3),
        avg_loss_r=round((-gross_loss / len(losses)) if losses else 0.0, 3),
        sharpe=round(mean / std_all * math.sqrt(len(r_multiples)), 3) if std_all > 0 else None,
        sortino=(round(mean / std_down * math.sqrt(len(r_multiples)), 3) if std_down > 0 else None),
        max_drawdown_r=round(dd, 3),
    )


def risk_of_ruin(
    win_prob: float, avg_win_r: float, avg_loss_r: float, ruin_fraction: float = 0.5
) -> float:
    """
    Approximate risk of hitting -ruin_fraction of equity before doubling,
    using the classic gambler's-ruin approximation on fixed-fraction bets.
    Returns probability 0..1. Educational estimate, not a guarantee.
    """
    p = win_prob / 100.0
    q = 1 - p
    edge = p * avg_win_r - q * abs(avg_loss_r)
    if edge <= 0:
        return 1.0
    units = max(2, int(round(ruin_fraction / max(abs(avg_loss_r), 1e-9))))
    ratio = (q * abs(avg_loss_r)) / (p * avg_win_r)
    try:
        return min(1.0, (ratio**units))
    except OverflowError:
        return 1.0
