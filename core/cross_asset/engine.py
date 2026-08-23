"""CrossAssetEngine — relations, divergences and regime detection (PRIORITY 4).

Deterministic analysis over stored candle series. Pairs have an EXPECTED
long-run correlation sign derived from macro mechanics (not from the data
being analysed):

    GOLD/DXY  negative   (USD strength weighs on metal)
    SPX/VIX   negative   (hedging demand rises when equities fall)
    GOLD/SILVER positive (metals complex)
    BTC/ETH   positive   (crypto beta)
    OIL/COPPER positive  (growth complex)

Relation verdicts:
- NORMAL RELATIONSHIP : correlation consistent with expected sign and history
- DIVERGENCE          : moderate breakdown (sign flip or |Δρ| > 0.35)
- REGIME CHANGE       : structural break (|Δρ| > 0.60 vs baseline)
- ABNORMAL RELATIONSHIP: current ρ contradicts the expected macro sign
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.market_brain.engines import momentum_score, pearson


class RelationState(StrEnum):
    NORMAL_RELATIONSHIP = "NORMAL RELATIONSHIP"
    DIVERGENCE = "DIVERGENCE"
    REGIME_CHANGE = "REGIME CHANGE"
    ABNORMAL_RELATIONSHIP = "ABNORMAL RELATIONSHIP"
    INSUFFICIENT_DATA = "INSUFFICIENT DATA"


# pair -> expected correlation sign (+1 / -1)
EXPECTED_SIGN: dict[str, int] = {
    "GOLD_DXY": -1,
    "SPX_VIX": -1,
    "GOLD_SILVER": +1,
    "BTC_ETH": +1,
    "OIL_COPPER": +1,
}

PAIR_SYMBOLS: dict[str, tuple[str, str]] = {
    "GOLD_DXY": ("XAUUSD", "DXY"),
    "SPX_VIX": ("SPX", "VIX"),
    "GOLD_SILVER": ("XAUUSD", "XAGUSD"),
    "BTC_ETH": ("BTCUSD", "ETHUSD"),
    "OIL_COPPER": ("CL", "HG"),
}


@dataclass(frozen=True)
class CrossAssetReading:
    pair: str
    correlation_now: float | None
    correlation_baseline: float | None
    state: str  # RelationState value
    detail: str

    @property
    def is_anomaly(self) -> bool:
        return self.state in (
            RelationState.DIVERGENCE.value,
            RelationState.REGIME_CHANGE.value,
            RelationState.ABNORMAL_RELATIONSHIP.value,
        )


@dataclass(frozen=True)
class RiskRegimeReading:
    risk_mode: str  # RISK_ON | RISK_OFF | NEUTRAL
    score: float  # -1..1
    detail: str


def _split_history(closes: list[float], baseline_frac: float = 0.5) -> tuple[list[float], list[float]]:
    """Split into baseline window (older half) and recent window (newer half)."""
    cut = max(10, int(len(closes) * baseline_frac))
    return closes[:cut], closes[cut:]


def classify_relation(
    rho_now: float | None,
    rho_baseline: float | None,
    expected_sign: int,
) -> tuple[RelationState, str]:
    if rho_now is None or rho_baseline is None:
        return RelationState.INSUFFICIENT_DATA, "insufficient overlapping history"
    delta = abs(rho_now - rho_baseline)
    if delta > 0.60:
        return (
            RelationState.REGIME_CHANGE,
            f"correlation moved {delta:+.2f} vs baseline {rho_baseline:+.2f}",
        )
    sign_now = 0 if abs(rho_now) < 0.15 else (1 if rho_now > 0 else -1)
    if expected_sign != 0 and sign_now != 0 and sign_now != expected_sign:
        return (
            RelationState.ABNORMAL_RELATIONSHIP,
            f"ρ={rho_now:+.2f} contradicts expected sign {expected_sign:+d}",
        )
    sign_baseline = 1 if rho_baseline > 0 else -1
    if delta > 0.35 or (
        abs(rho_baseline) > 0.30 and sign_now != 0 and sign_now != sign_baseline
    ):
        return RelationState.DIVERGENCE, f"ρ shifted {rho_baseline:+.2f} → {rho_now:+.2f}"
    return RelationState.NORMAL_RELATIONSHIP, f"ρ={rho_now:+.2f} within normal band"


class CrossAssetEngine:
    def __init__(self, min_history: int = 40) -> None:
        self.min_history = min_history

    def analyze_pair(
        self, pair: str, closes_a: list[float], closes_b: list[float]
    ) -> CrossAssetReading:
        expected = EXPECTED_SIGN.get(pair, 0)
        n = min(len(closes_a), len(closes_b))
        if n < self.min_history:
            return CrossAssetReading(pair, None, None, RelationState.INSUFFICIENT_DATA.value,
                                     f"need >= {self.min_history} bars, got {n}")
        base_a, rec_a = _split_history(closes_a[-n:])
        base_b, rec_b = _split_history(closes_b[-n:])
        rho_base = pearson(base_a, base_b)
        rho_now = pearson(rec_a, rec_b)
        state, detail = classify_relation(rho_now, rho_base, expected)
        # momentum divergence note for positively-expected pairs moving opposite
        if state == RelationState.NORMAL_RELATIONSHIP and expected > 0:
            ma = momentum_score(closes_a)
            mb = momentum_score(closes_b)
            if ma is not None and mb is not None and ma * mb < -0.04:
                detail += f" | momentum divergence {ma:+.2f}/{mb:+.2f}"
        return CrossAssetReading(pair, rho_now, rho_base, state.value, detail)

    def scan(self, closes_by_symbol: dict[str, list[float]]) -> list[CrossAssetReading]:
        readings: list[CrossAssetReading] = []
        for pair, (sym_a, sym_b) in PAIR_SYMBOLS.items():
            a = closes_by_symbol.get(sym_a)
            b = closes_by_symbol.get(sym_b)
            if not a or not b:
                continue
            readings.append(self.analyze_pair(pair, a, b))
        return readings

    def risk_regime(
        self,
        spx_momentum: float | None,
        vix_level: float | None,
        btc_momentum: float | None = None,
    ) -> RiskRegimeReading:
        terms: list[float] = []
        notes: list[str] = []
        if spx_momentum is not None:
            terms.append(spx_momentum)
            notes.append(f"SPX mom {spx_momentum:+.2f}")
        if vix_level is not None:
            t = max(-1.0, min(1.0, (16.0 - vix_level) / 14.0))
            terms.append(t)
            notes.append(f"VIX {vix_level:.1f}")
        if btc_momentum is not None:
            terms.append(btc_momentum)
            notes.append(f"BTC mom {btc_momentum:+.2f}")
        if not terms:
            return RiskRegimeReading("NEUTRAL", 0.0, "no inputs")
        score = sum(terms) / len(terms)
        mode = "RISK_ON" if score > 0.15 else "RISK_OFF" if score < -0.15 else "NEUTRAL"
        return RiskRegimeReading(mode, round(score, 3), ", ".join(notes))
