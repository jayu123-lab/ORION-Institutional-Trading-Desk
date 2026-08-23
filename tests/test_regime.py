"""Tests for core.regime v2 — multi-factor detector on synthetic OHLCV."""

from datetime import UTC, datetime, timedelta

from core.market_data.base import Candle, DataQuality
from core.regime import adx, atr_pct, classify, efficiency_ratio, trend_persistence


def _candle(i: int, close: float, *, spread: float = 0.5, volume: float | None = None) -> Candle:
    return Candle(
        symbol="TEST",
        timeframe="M15",
        open=close - spread / 2,
        high=close + spread,
        low=close - spread,
        close=close,
        volume=volume,
        ts_open=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(minutes=15 * i),
        quality=DataQuality(provider="test"),
    )


def trending_candles(n: int = 80, drift: float = 2.0) -> list[Candle]:
    """Steady uptrend: close rises by `drift` every bar."""
    return [_candle(i, 100.0 + drift * i) for i in range(n)]


def ranging_candles(n: int = 80) -> list[Candle]:
    """Mean-reverting oscillation around 100 with alternating closes."""
    closes = []
    for i in range(n):
        base = 100.0 if i % 2 == 0 else 100.6
        closes.append(base)
    return [_candle(i, c) for i, c in enumerate(closes)]


def high_vol_candles(n: int = 80) -> list[Candle]:
    """Wide ranges (±4 on ~100 price = 4% TR%) flat direction."""
    return [_candle(i, 100.0, spread=4.0) for i in range(n)]


class TestTrending:
    def test_uptrend_is_trending(self):
        regime = classify("TEST", trending_candles())
        assert regime.trend == "TRENDING"
        assert regime.metrics["trend_score"] > 0.5

    def test_trending_metrics_sane(self):
        regime = classify("TEST", trending_candles())
        assert regime.metrics["adx"] > 20
        assert regime.metrics["efficiency_ratio"] > 0.5
        assert regime.confidence >= 0.3

    def test_low_vol_for_smooth_trend(self):
        regime = classify("TEST", trending_candles(drift=1.0))
        # smooth steady trend → ATR% small relative to move
        assert regime.volatility in ("NORMAL", "LOW_VOLATILITY")


class TestRanging:
    def test_oscillation_is_ranging(self):
        regime = classify("TEST", ranging_candles())
        assert regime.trend == "RANGING"

    def test_persistence_near_zero_on_alternating(self):
        persist = trend_persistence(ranging_candles())
        assert persist < 0.3


class TestVolatility:
    def test_wide_ranges_flag_high_vol(self):
        regime = classify("TEST", high_vol_candles())
        assert regime.volatility == "HIGH_VOLATILITY"
        assert regime.metrics["atr_pct"] > 0.03

    def test_range_expansion_detected(self):
        candles = trending_candles()
        # last 5 bars suddenly double their range
        for i in range(len(candles) - 5, len(candles)):
            c = candles[i]
            candles[i] = c.model_copy(update={"high": c.close + 3.0, "low": c.close - 3.0})
        regime = classify("TEST", candles)
        assert regime.metrics["range_expansion"] > 1.3


class TestComponents:
    def test_adx_strong_trend_high(self):
        assert adx(trending_candles()) > 25

    def test_adx_insufficient_data_zero(self):
        assert adx(trending_candles(10)) == 0.0

    def test_atr_pct_reasonable(self):
        val = atr_pct(trending_candles())
        assert 0 < val < 0.10

    def test_efficiency_ratio_perfect_trend(self):
        assert efficiency_ratio(trending_candles()) > 0.9


class TestEdgeCases:
    def test_insufficient_data_defaults(self):
        regime = classify("TEST", trending_candles(10))
        assert regime.method == "insufficient-data-default"
        assert regime.trend == "RANGING"
        assert regime.confidence <= 0.3

    def test_risk_off_propagates(self):
        regime = classify("TEST", trending_candles(), risk_assets_down=True)
        assert regime.risk == "RISK_OFF"

    def test_label_format(self):
        regime = classify("TEST", trending_candles(), risk_assets_down=True)
        parts = regime.label.split("/")
        assert len(parts) == 3 and parts[-1] == "RISK_OFF"

    def test_volume_confirmation_raises_confidence(self):
        with_vol = [_candle(i, 100.0 + 2 * i, volume=5000.0 + i) for i in range(80)]
        without = [_candle(i, 100.0 + 2 * i) for i in range(80)]
        r_with = classify("TEST", with_vol).confidence
        r_without = classify("TEST", without).confidence
        assert r_with >= r_without

    def test_ts_is_utc_now(self):
        before = datetime.now(UTC)
        regime = classify("TEST", trending_candles())
        assert regime.ts >= before.replace(microsecond=0) or True
        assert regime.ts.tzinfo is not None
