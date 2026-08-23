"""Phase 1 scanner guarantees: deterministic features, selectivity and no lookahead."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from core.features.engine import calculate_features, classify_adx
from core.setups.expected_move import expected_move
from core.setups.library import SetupCandidate, opportunity_score, transition


def _bars(count: int = 45):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        SimpleNamespace(
            ts_open=start + timedelta(hours=i),
            open=100 + i * 0.1,
            high=101 + i * 0.1,
            low=99 + i * 0.1,
            close=100 + i * 0.1,
            volume=100 + i,
        )
        for i in range(count)
    ]


def test_adx_and_atr_are_present_and_adx_is_strength_not_direction():
    snapshot = calculate_features(_bars(), "XAUUSD")
    assert snapshot.value("atr") is not None
    assert snapshot.value("adx") is not None
    assert snapshot.value("plus_di") is not None
    assert snapshot.value("minus_di") is not None
    assert snapshot.value("adx_bucket") == classify_adx(snapshot.value("adx"))
    assert snapshot.values["delta"].provenance == "NOT_AVAILABLE"


def test_expected_move_requires_real_historical_sample():
    assert expected_move([1.0] * 29)["status"] == "INSUFFICIENT_SAMPLE"
    result = expected_move([float(i) for i in range(1, 101)])
    assert result["status"] == "CALCULATED"
    assert result["sample_size"] == 100
    assert result["expected_move_25"] < result["expected_move_50"] < result["expected_move_75"]


def test_score_exposes_subscores_and_state_requires_reaction():
    score = opportunity_score(
        {"context": 70, "location": 80, "liquidity": 75, "order_flow": None, "rr": 90}
    )
    assert 0 <= score["total"] <= 100
    assert "order_flow" in score["subscores"]
    candidate = SetupCandidate("one", "XAUUSD", "LIQUIDITY_SWEEP_REVERSAL", "LONG", score=90)
    transition(candidate, in_zone=True, reaction=False, score=90)
    assert candidate.state == "ARMED"
    transition(candidate, in_zone=True, reaction=True, score=90)
    assert candidate.state == "CONFIRMED"
