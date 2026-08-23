"""Pure deterministic calculators for the Market Brain.

No I/O, no LLM, no hidden state: functions in, numbers out. All provenance
of results is DERIVED unless the caller passes verified inputs (feeds).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

# ------------------------------------------------------------------- series


def returns(closes: list[float]) -> list[float]:
    if len(closes) < 2:
        return []
    return [
        math.log(b / a) for a, b in zip(closes, closes[1:], strict=False) if a > 0 and b > 0
    ]


def roc(closes: list[float], lookback: int) -> float | None:
    """Rate of change over `lookback` bars (log return). None if insufficient."""
    if len(closes) <= lookback:
        return None
    a, b = closes[-(lookback + 1)], closes[-1]
    return math.log(b / a) if a > 0 and b > 0 else None


def zscore(values: list[float]) -> float | None:
    """Z-score of the LAST element vs the series. None if variance is zero."""
    if len(values) < 3:
        return None
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    std = var**0.5
    if std == 0:
        return None
    return (values[-1] - mean) / std


def pearson(a: list[float], b: list[float]) -> float | None:
    """Pearson correlation over paired samples. None if degenerate."""
    n = min(len(a), len(b))
    if n < 3:
        return None
    x, y = a[-n:], b[-n:]
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y, strict=False))
    vx = sum((xi - mx) ** 2 for xi in x)
    vy = sum((yi - my) ** 2 for yi in y)
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def rolling_correlation(
    a: list[float],
    b: list[float],
    window: int,
    min_periods: int = 10,
) -> list[float | None]:
    """Rolling Pearson of returns; each entry ends at that index."""
    ra, rb = returns(a), returns(b)
    out: list[float | None] = [None] * (len(a))
    for i in range(min_periods, min(len(ra), len(rb)) + 1):
        w_a = ra[max(0, i - window) : i]
        w_b = rb[max(0, i - window) : i]
        out[i] = pearson(w_a, w_b)
    return out


def relative_strength(
    symbol_closes: list[float], benchmark_closes: list[float]
) -> dict[str, float | None]:
    """RS ratio now + its z-score over history (both same length ideally)."""
    n = min(len(symbol_closes), len(benchmark_closes))
    if n < 5:
        return {"rs": None, "rs_zscore": None}
    sym, ben = symbol_closes[-n:], benchmark_closes[-n:]
    ratios = [s / b for s, b in zip(sym, ben, strict=False) if b != 0]
    rs_now = ratios[-1] if ratios else None
    # z-score of RS computed on log-ratio changes to be stationary
    lr = returns(ratios)
    z = zscore(lr)
    return {"rs": rs_now, "rs_zscore": z}


# ------------------------------------------------------------------ scores


def momentum_score(closes: list[float], atr_pct_value: float | None = None) -> float | None:
    """Multi-horizon momentum ∈ [-1,1]: weighted ROC 10/20/50 normalized by vol.

    Normalization by realized std keeps cross-asset comparability.
    """
    r10 = roc(closes, 10)
    r20 = roc(closes, 20)
    r50 = roc(closes, 50)
    raw = [r for r in (r10, r20, r50) if r is not None]
    if not raw:
        return None
    rets = returns(closes[-60:])
    std = (
        (sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / max(len(rets) - 1, 1)) ** 0.5
        if len(rets) > 2
        else 0.0
    )
    norm = std if std > 1e-9 else (atr_pct_value or 0.01)
    weights = {10: 0.5, 20: 0.3, 50: 0.2}
    score = 0.0
    total_w = 0.0
    for lb, w in weights.items():
        r = roc(closes, lb)
        if r is not None:
            score += w * max(-3.0, min(3.0, r / (norm * math.sqrt(lb))))
            total_w += w
    if total_w == 0:
        return None
    return max(-1.0, min(1.0, score / total_w))


def liquidity_score(
    *,
    spread_bps: float | None,
    relative_volume: float | None,
    range_contraction: float | None,
) -> float | None:
    """Composite ∈ [0,1]. Missing inputs reduce confidence but not honesty:
    with no spread at all we still score from volume/range; all-None → None."""
    parts: list[tuple[float, float]] = []  # (value∈[0,1], weight)

    if spread_bps is not None and spread_bps >= 0:
        # 2bps → ~1.0 ; 50bps+ → ~0.0
        s = max(0.0, 1.0 - spread_bps / 50.0)
        parts.append((s, 0.5))
    if relative_volume is not None:
        parts.append((max(0.0, min(1.0, relative_volume)), 0.3))
    if range_contraction is not None:
        # contraction <1 → calmer book ≈ more liquid for execution
        rc = max(0.0, min(1.0, 2.0 - range_contraction))
        parts.append((rc, 0.2))

    if not parts:
        return None
    total_w = sum(w for _, w in parts)
    return sum(v * w for v, w in parts) / total_w


def macro_score(
    *,
    dxy_roc: float | None,
    us10y_change: float | None,
    vix_level: float | None,
    spx_momentum: float | None,
) -> tuple[float | None, dict[str, object]]:
    """Macro stress gauge ∈ [-1,1]; negative = risk-off pressure.

    Inputs (all optional, real feeds only):
    - DXY rising          → USD strength → pressure on risk assets (-)
    - US10Y sharp rise    → rates stress (-)
    - VIX elevated (>20)  → fear (-)
    - SPX momentum        → direct (+ trend, - slide)
    """
    terms: list[float] = []
    detail: dict[str, object] = {}

    if dxy_roc is not None:
        t = max(-1.0, min(1.0, -dxy_roc * 25))  # +4% move → -1.0
        terms.append(t)
        detail["dxy_contribution"] = round(t, 3)
    if us10y_change is not None:
        t = max(-1.0, min(1.0, -us10y_change * 400))  # +25bp → -1.0
        terms.append(t)
        detail["us10y_contribution"] = round(t, 3)
    if vix_level is not None:
        # VIX 12→+0.2 ; 20→-0.33 ; 30+→-1.0
        t = max(-1.0, min(1.0, (16.0 - vix_level) / 14.0))
        terms.append(t)
        detail["vix_contribution"] = round(t, 3)
    if spx_momentum is not None:
        terms.append(max(-1.0, min(1.0, spx_momentum)))
        detail["spx_contribution"] = round(spx_momentum, 3)

    if not terms:
        return None, {"reason": "no macro inputs available"}
    return sum(terms) / len(terms), detail


def risk_score(
    *,
    volatility_state: str,
    drawdown_pct: float | None,
    macro_stress: float | None,
    feed_degraded: bool,
) -> tuple[float, dict[str, object]]:
    """Execution risk gauge ∈ [-1,1]; negative = risky conditions."""
    base = 0.0
    detail: dict[str, object] = {}
    if volatility_state == "HIGH":
        base -= 0.35
    elif volatility_state == "LOW":
        base += 0.15
    if drawdown_pct is not None:
        dd = max(-1.0, min(1.0, drawdown_pct * 8))  # -12.5% DD → -1.0
        base += 0.4 * dd
        detail["drawdown_contribution"] = round(dd, 3)
    if macro_stress is not None:
        base += 0.4 * macro_stress
        detail["macro_contribution"] = round(macro_stress, 3)
    if feed_degraded:
        base -= 0.2
        detail["feed_penalty"] = -0.2
    return max(-1.0, min(1.0, base)), detail


def data_quality_score(freshness: list[float | None]) -> float:
    """Fraction of expected inputs that are fresh (non-None)."""
    if not freshness:
        return 0.0
    ok = sum(1 for f in freshness if f is not None and f >= 0)
    return round(ok / len(freshness), 3)


# ------------------------------------------------------- candle-level metrics
# Duck-typed: anything with .volume / .high / .low / .close works (DB rows,
# pydantic Candles). Returns None when the series is too short to judge.


def relative_volume_metric(candles: list, lookback: int = 20) -> float | None:
    vols = [c.volume for c in candles[-(lookback + 1) :] if c.volume]
    if len(vols) < 5:
        return None
    avg = sum(vols[:-1]) / (len(vols) - 1)
    return vols[-1] / avg if avg > 0 else None


def _true_range(prev, cur) -> float:
    return max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close))


def range_contraction_metric(candles: list, recent: int = 5, baseline: int = 50) -> float | None:
    """Avg TR(recent)/avg TR(baseline). <1 = contraction (calm book)."""
    if len(candles) < min(baseline + 1, 30):
        return None

    def avg_tr(window: list) -> float | None:
        trs = [_true_range(p, c) for p, c in zip(window, window[1:], strict=False)]
        return sum(trs) / len(trs) if trs else None

    base = avg_tr(candles[-baseline:])
    rec = avg_tr(candles[-recent:])
    if not base or not rec:
        return None
    return rec / base


def utcnow() -> datetime:
    return datetime.now(UTC)
