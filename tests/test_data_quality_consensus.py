from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.market_data.base import DataStatus, is_stale
from core.market_data.simulated import SimulatedDataProvider
from core.orchestration.confidence import (
    ConfidenceEngine,
    Outcome,
    Prediction,
)
from core.orchestration.consensus import ConsensusInput, compute_consensus


def test_stale_detection():
    now = datetime.now(UTC)
    assert not is_stale(now - timedelta(seconds=30), staleness_sec=120, now=now)
    assert is_stale(now - timedelta(seconds=600), staleness_sec=120, now=now)


async def test_simulated_provider_is_marked_simulated():
    provider = SimulatedDataProvider()
    quote = await provider.get_quote("XAUUSD")
    assert quote.quality.status == DataStatus.SIMULATED
    candles = await provider.get_candles("XAUUSD", "H1", limit=5)
    assert len(candles) == 5
    assert all(c.quality.status == DataStatus.SIMULATED for c in candles)


def test_consensus_weighted_not_majority():
    # 2 light LONGs vs 1 heavy SHORT: weights must dominate the vote count
    inputs = [
        ConsensusInput("news", "news", "LONG", 50),
        ConsensusInput("quant", "quant", "LONG", 50),
        ConsensusInput("liquidity", "liquidity", "SHORT", 100),
    ]
    result = compute_consensus(inputs)
    assert result.score < 0  # liquidity (20%) outweighs news+quant combined (25%? no...)
    # note: news .10*0.5 + quant .15*.5 = +0.125 vs liquidity .20*1 = -0.20 → net short


def test_consensus_surfaces_dissent():
    inputs = [
        ConsensusInput("macro", "macro", "LONG", 90),
        ConsensusInput("liquidity", "liquidity", "SHORT", 80),
    ]
    result = compute_consensus(inputs)
    assert result.has_dissent
    assert any(agent == "liquidity" and stance == "SHORT" for agent, stance in result.dissent)


def test_consensus_labels():
    strong_buy = compute_consensus([ConsensusInput("macro", "macro", "LONG", 100)])
    assert strong_buy.label == "STRONG BUY BIAS"
    neutral = compute_consensus(
        [
            ConsensusInput("a", "news", "LONG", 40),
            ConsensusInput("b", "quant", "WAIT", 100),
        ]
    )
    assert neutral.label in ("NEUTRAL",)


def test_confidence_calibration():
    engine = ConfidenceEngine()
    engine.register(Prediction("X>1", 70.0, datetime.now(UTC)))
    engine.register(Prediction("Y>1", 70.0, datetime.now(UTC)))
    engine.register(Prediction("Z>1", 30.0, datetime.now(UTC)))
    engine.resolve("X>1", Outcome(True, datetime.now(UTC)))
    engine.resolve("Y>1", Outcome(False, datetime.now(UTC)))
    engine.resolve("Z>1", Outcome(True, datetime.now(UTC)))
    report = engine.calibration()
    assert report is not None
    assert report.n_predictions == 3
    assert abs(report.hit_rate - 66.7) < 0.1
