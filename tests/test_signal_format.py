"""Tests for core.signals.format — the orion-signal contract (P8)."""

import pytest
from pydantic import ValidationError

from core.signals.format import OrionSignal, validate_or_invalid, validate_signal


def _valid_signal(**overrides) -> OrionSignal:
    base = dict(
        asset="XAUUSD",
        price=4690.0,
        price_source="yahoo",
        data_quality=0.9,
        direction="LONG",
        entry_type="LIMIT",
        entry=4670.0,
        stop=4650.0,
        targets=[4720.0, 4760.0, 4810.0],
        risk_reward=2.5,
        confidence="MODERATE",
        market_regime="TRENDING/NORMAL/RISK_ON",
        technical_reason="break of swing high with efficiency ratio 0.42",
        fundamental_reason="N/A — no macro release in window",
        liquidity_reason="spread 3bps, London session overlap",
        positioning_reason="NOT AVAILABLE — no COT feed configured",
        news_risk="no HIGH relevance headlines on asset",
        invalidation="H1 close back below 4660 invalidates breakout thesis",
        no_trade_conditions=["FEED_DIVERGENT state", "VIX > 28"],
        sources=["quotes:XAUUSD@2026-08-23T00:00:00+00:00"],
    )
    base.update(overrides)
    return OrionSignal(**base)


class TestValidSignals:
    def test_valid_signal_passes(self):
        result = validate_signal(_valid_signal())
        assert result.is_valid, result.errors

    def test_short_signal_geometry(self):
        sig = _valid_signal(
            direction="SHORT",
            entry=4710.0,
            stop=4735.0,
            targets=[4660.0, 4620.0, 4570.0],
            risk_reward=2.0,
        )
        assert validate_signal(sig).is_valid

    def test_warnings_for_missing_positioning(self):
        result = validate_signal(_valid_signal())
        assert any("positioning" in w for w in result.warnings)


class TestInvalidSignals:
    def test_stop_wrong_side_long(self):
        result = validate_signal(_valid_signal(stop=4690.0))
        assert not result.is_valid
        assert any("stop" in e.lower() for e in result.errors)

    def test_target_wrong_side(self):
        result = validate_signal(_valid_signal(targets=[4600.0, 4760.0, 4810.0]))
        assert any("TP1" in e for e in result.errors)

    def test_claimed_rr_mismatch_rejected(self):
        result = validate_signal(_valid_signal(risk_reward=5.0))  # real TP1 RR is 2.5
        assert any("R:R" in e for e in result.errors)

    def test_low_data_quality_gate(self):
        result = validate_signal(_valid_signal(data_quality=0.3))
        assert not result.is_valid
        assert any("data_quality" in e for e in result.errors)

    def test_bad_direction_enum(self):
        result = validate_signal(_valid_signal(direction="UP"))
        assert any("direction" in e for e in result.errors)

    def test_empty_sources_rejected(self):
        with pytest.raises(ValidationError):
            _valid_signal(sources=[])  # schema-level gate: sources required


class TestRawDictPath:
    def test_validate_or_invalid_schema_violation(self):
        out = validate_or_invalid({"asset": "XAUUSD"})  # almost everything missing
        assert out["state"] == "SIGNAL_INVALID"
        assert out["missing_critical"], out

    def test_validate_or_invalid_coherence_error(self):
        good = _valid_signal().model_dump(mode="json")
        good["stop"] = 99999.0  # nonsense for a LONG
        out = validate_or_invalid(good)
        assert out["state"] == "SIGNAL_INVALID"
        assert any("stop" in e.lower() for e in out["errors"])

    def test_validate_or_invalid_round_trip_ok(self):
        payload = _valid_signal().model_dump(mode="json")
        out = validate_or_invalid(payload)
        assert out["state"] == "SIGNAL_VALID"

    def test_targets_minimum_three_enforced_by_pydantic(self):
        with pytest.raises(ValidationError):
            _valid_signal(targets=[4720.0])

    def test_flat_direction_skips_geometry_checks(self):
        sig = _valid_signal(direction="FLAT", entry=100.0, stop=90.0, risk_reward=0.0)
        result = validate_signal(sig)
        # FLAT carries no geometry; only other gates apply
        assert not any("stop must be" in e for e in result.errors)
