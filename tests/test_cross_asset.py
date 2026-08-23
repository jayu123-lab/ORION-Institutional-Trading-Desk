"""Tests for core.cross_asset.engine (PRIORITY 4)."""


from core.cross_asset.engine import (
    CrossAssetEngine,
    RelationState,
    RiskRegimeReading,
)


def _correlated(
    n: int = 60, sign: float = 1.0, noise: float = 0.0
) -> tuple[list[float], list[float]]:
    a, b = [], []
    for i in range(n):
        x = float(i) + noise * ((i * 7919) % 13 - 6)
        y = sign * float(i) + noise * ((i * 104729) % 11 - 5)
        a.append(x)
        b.append(y)
    return a, b


class TestPairAnalysis:
    def test_positive_pair_normal(self):
        engine = CrossAssetEngine()
        a, b = _correlated(sign=+1.0)
        reading = engine.analyze_pair("BTC_ETH", a, b)
        assert reading.state == RelationState.NORMAL_RELATIONSHIP.value
        assert reading.correlation_now is not None and reading.correlation_now > 0.95

    def test_gold_dxy_positive_correlation_abnormal(self):
        """GOLD UP + DXY UP → positive ρ on a negative-expected pair → ABNORMAL."""
        engine = CrossAssetEngine()
        gold, dxy = _correlated(sign=+1.0)
        reading = engine.analyze_pair("GOLD_DXY", gold, dxy)
        assert reading.state == RelationState.ABNORMAL_RELATIONSHIP.value
        assert reading.is_anomaly

    def test_sign_flip_is_regime_change(self):
        engine = CrossAssetEngine()
        # baseline: strongly negative; recent: strongly positive
        base_a = [float(i) for i in range(40)]
        base_b = [float(-2 * i) for i in range(40)]
        rec_a = [float(i) for i in range(40)]
        rec_b = [float(2 * i) for i in range(40)]
        closes_a = base_a + rec_a
        closes_b = base_b + rec_b
        reading = engine.analyze_pair("GOLD_DXY", closes_a, closes_b)
        assert reading.state == RelationState.REGIME_CHANGE.value

    def test_moderate_shift_is_divergence(self):
        engine = CrossAssetEngine()
        base_a = [float(i) for i in range(40)]
        base_b = [0.8 * float(i) + 3.0 for i in range(40)]  # rho = +1 baseline
        # deterministic modular noise (no RNG): recent rho ~ 0.74 (delta 0.26)
        rec_a = [float(i) for i in range(40)]
        rec_b = [0.4 * i + ((i * 7919) % 51 - 25) / 25.0 * 8.0 for i in range(40)]
        reading = engine.analyze_pair("GOLD_SILVER", base_a + rec_a, base_b + rec_b)
        assert reading.state == RelationState.DIVERGENCE.value

    def test_insufficient_data(self):
        engine = CrossAssetEngine(min_history=50)
        a, b = _correlated(20)
        reading = engine.analyze_pair("SPX_VIX", a, b)
        assert reading.state == RelationState.INSUFFICIENT_DATA.value
        assert reading.correlation_now is None

    def test_scan_skips_missing_symbols(self):
        engine = CrossAssetEngine()
        a, b = _correlated()
        readings = engine.scan({"XAUUSD": a, "DXY": b})
        assert len(readings) == 1
        assert readings[0].pair == "GOLD_DXY"


class TestRiskRegime:
    def test_risk_off_when_vix_high_spx_down(self):
        engine = CrossAssetEngine()
        r: RiskRegimeReading = engine.risk_regime(spx_momentum=-0.6, vix_level=30.0)
        assert r.risk_mode == "RISK_OFF"
        assert r.score < -0.4

    def test_risk_on_calm_grinding_up(self):
        engine = CrossAssetEngine()
        r = engine.risk_regime(spx_momentum=0.5, vix_level=12.0, btc_momentum=0.4)
        assert r.risk_mode == "RISK_ON"

    def test_neutral_no_inputs(self):
        engine = CrossAssetEngine()
        r = engine.risk_regime(None, None)
        assert r.risk_mode == "NEUTRAL" and r.score == 0.0
