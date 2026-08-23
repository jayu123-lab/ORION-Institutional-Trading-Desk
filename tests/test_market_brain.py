"""Tests for core.market_brain — deterministic engines + composition."""

import math

import pytest

from core.market_brain.brain import MarketBrain
from core.market_brain.engines import (
    data_quality_score,
    liquidity_score,
    macro_score,
    momentum_score,
    pearson,
    range_contraction_metric,
    relative_volume_metric,
    returns,
    risk_score,
    roc,
    rolling_correlation,
    zscore,
)
from core.market_brain.state import RegimeLabel, RiskMode, VolatilityState


def _series(n: int, fn) -> list[float]:
    return [fn(i) for i in range(n)]


class TestSeriesMath:
    def test_returns_log(self):
        r = returns([100.0, 110.0])
        assert len(r) == 1 and abs(r[0] - math.log(1.1)) < 1e-9

    def test_roc_insufficient_none(self):
        assert roc([100.0] * 5, 10) is None

    def test_zscore_standardizes_last_value(self):
        vals = [1.0, 2.0, 3.0, 4.0, 100.0]
        z = zscore(vals)
        assert z is not None and z > 1.5

    def test_pearson_perfect_correlation(self):
        a = [float(i) for i in range(20)]
        b = [2.0 * i + 1.0 for i in range(20)]
        assert pearson(a, b) == pytest.approx(1.0)

    def test_pearson_inverse(self):
        a = [float(i) for i in range(20)]
        b = [float(-i) for i in range(20)]
        assert pearson(a, b) == pytest.approx(-1.0)

    def test_pearson_degenerate_none(self):
        assert pearson([1.0, 1.0, 1.0], [2.0, 3.0, 4.0]) is None

    def test_rolling_correlation_shape_and_values(self):
        a = _series(60, lambda i: float(i))
        b = _series(60, lambda i: float(i) ** 2)
        roll = rolling_correlation(a, b, window=20)
        assert len(roll) == 60
        tail = [v for v in roll[-10:] if v is not None]
        assert all(v > 0.99 for v in tail)


class TestScores:
    def test_momentum_uptrend_positive(self):
        closes = _series(80, lambda i: 100 * (1 + 0.002) ** i)
        m = momentum_score(closes)
        assert m is not None and m > 0.3

    def test_momentum_downtrend_negative(self):
        closes = _series(80, lambda i: 100 * (1 - 0.002) ** i)
        assert momentum_score(closes) < -0.3

    def test_momentum_flat_near_zero(self):
        closes = [100.0 if i % 2 == 0 else 100.05 for i in range(80)]
        assert abs(momentum_score(closes)) < 0.25

    def test_momentum_needs_data(self):
        assert momentum_score([100.0] * 5) is None

    def test_liquidity_all_inputs_missing_none(self):
        assert (
            liquidity_score(spread_bps=None, relative_volume=None, range_contraction=None)
            is None
        )

    def test_liquidity_tight_spread_good(self):
        s = liquidity_score(spread_bps=1.5, relative_volume=None, range_contraction=None)
        assert s is not None and s > 0.9

    def test_liquidity_wide_spread_bad(self):
        s = liquidity_score(spread_bps=60.0, relative_volume=0.2, range_contraction=1.5)
        assert s is not None and s < 0.3

    def test_macro_stress_when_vix_high(self):
        v, detail = macro_score(
            dxy_roc=None, us10y_change=None, vix_level=32.0, spx_momentum=-0.5
        )
        assert v is not None and v < -0.6
        assert "vix_contribution" in detail

    def test_macro_positive_calm_regime(self):
        v, _ = macro_score(dxy_roc=-0.01, us10y_change=-0.02, vix_level=12.0, spx_momentum=0.6)
        assert v is not None and v > 0.3

    def test_macro_no_inputs_honest_none(self):
        v, detail = macro_score(
            dxy_roc=None, us10y_change=None, vix_level=None, spx_momentum=None
        )
        assert v is None and "no macro inputs" in str(detail)

    def test_risk_score_high_vol_penalized(self):
        v, _ = risk_score(
            volatility_state="HIGH", drawdown_pct=-0.10, macro_stress=-0.8, feed_degraded=True
        )
        assert v <= -0.7

    def test_risk_score_calm_positive(self):
        v, _ = risk_score(
            volatility_state="LOW", drawdown_pct=-0.01, macro_stress=0.6, feed_degraded=False
        )
        assert v > 0.2

    def test_data_quality_fraction(self):
        assert data_quality_score([1, 1, None]) == pytest.approx(2 / 3, abs=1e-3)
        assert data_quality_score([]) == 0.0


class TestCandleMetrics:
    class C:
        def __init__(
            self,
            opn: float,
            high: float,
            low: float,
            close: float,
            volume: float | None = None,
        ):
            self.open, self.high, self.low = opn, high, low
            self.close, self.volume = close, volume

    def test_relative_volume(self):
        candles = [self.C(1, 2, 0.5, 1.5, volume=100.0) for _ in range(21)]
        candles[-1].volume = 300.0
        rv = relative_volume_metric(candles)
        assert rv is not None and rv > 2.0

    def test_relative_volume_absent_none(self):
        candles = [self.C(1, 2, 0.5, 1.5) for _ in range(30)]
        assert relative_volume_metric(candles) is None

    def test_range_expansion_detected_on_wild_tail(self):
        calm = [self.C(100, 101, 99, 100) for _ in range(60)]
        wild = [self.C(100, 108, 92, 100) for _ in range(10)]
        ratio = range_contraction_metric(calm + wild)
        assert ratio is not None and ratio > 2.0


class FakeRow:
    """Mimics DB Candle/Quote rows by duck-typing."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class TestCompose:
    def _brain(self):
        import types

        return MarketBrain(session_factory=types.SimpleNamespace())

    def test_full_compose_with_data(self):
        brain = self._brain()
        closes = _series(80, lambda i: 100 * (1 + 0.001) ** i)
        candles = [
            FakeRow(open=c - 0.5, high=c + 1, low=c - 1, close=c, volume=1000.0 + i)
            for i, c in enumerate(closes)
        ]
        state = brain.compose(
            scope="TEST",
            scope_closes=closes,
            scope_candles=candles,
            spread_bps=2.0,
            macro_closes={
                "VIX": [13.0] * 30,
                "SPX": _series(60, lambda i: 5000 * (1 + 0.001) ** i),
            },
            benchmark_closes=_series(60, lambda i: 5000 * (1 + 0.001) ** i),
            quote_freshness=[5.0],
        )
        assert state.regime in (RegimeLabel.TRENDING, RegimeLabel.RANGING)
        assert state.momentum_score is not None and state.momentum_score > 0
        assert state.positioning_score is None  # never fabricated
        assert 0.0 <= state.data_quality <= 1.0
        names = {c.name for c in state.components}
        assert {"regime", "momentum", "liquidity", "positioning", "risk"} <= names
        pos = next(c for c in state.components if c.name == "positioning")
        assert pos.detail["availability"] == "NOT AVAILABLE"

    def test_risk_off_on_macro_stress(self):
        brain = self._brain()
        closes = _series(80, lambda i: 100 - 0.1 * i)
        candles = [FakeRow(open=c, high=c + 4, low=c - 4, close=c, volume=100.0) for c in closes]
        state = brain.compose(
            scope="TEST",
            scope_closes=closes,
            scope_candles=candles,
            spread_bps=40.0,
            macro_closes={"VIX": [35.0] * 30},
            benchmark_closes=[],
            quote_freshness=[None],  # stale quote → feed degraded
        )
        assert state.risk_mode == RiskMode.RISK_OFF
        assert state.volatility == VolatilityState.HIGH

    def test_insufficient_data_scope(self):
        brain = self._brain()
        state = brain.compose(
            scope="X",
            scope_closes=[100.0, 101.0],
            scope_candles=[],
            spread_bps=None,
            macro_closes={},
            benchmark_closes=[],
            quote_freshness=[None],
        )
        assert state.regime == RegimeLabel.INSUFFICIENT_DATA
        assert state.momentum_score is None
        assert state.data_quality < 0.3
