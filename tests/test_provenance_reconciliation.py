"""Tests for core.provenance and core.market_data.reconciliation."""

from datetime import UTC, datetime, timedelta

import pytest

from core.events.bus import InMemoryEventBus
from core.events.types import DATA_STALE, FEED_DIVERGENCE
from core.market_data.base import DataQuality, DataStatus, Quote
from core.market_data.reconciliation import (
    FeedReading,
    FeedTier,
    MarketDataReconciliationEngine,
    ReconciliationState,
    publish_reconciliation,
)
from core.provenance import (
    ProvenanceType,
    VerificationState,
    can_present_as_verified,
    presentation_label,
    provenance_for_source_kind,
)


def _quote(
    price: float,
    *,
    provider: str = "test",
    age_sec: float = 0.0,
    latency_ms: int | None = 50,
    bid_ask_pct: float | None = None,
) -> Quote:
    now = datetime.now(UTC)
    q = Quote(
        symbol="XAUUSD",
        price=price,
        ts_source=now - timedelta(seconds=age_sec),
        quality=DataQuality(
            provider=provider,
            latency_ms=latency_ms,
            quality="A",
            status=DataStatus.LIVE,
        ),
    )
    if bid_ask_pct is not None:
        half = price * bid_ask_pct / 2
        q.bid = round(price - half, 4)
        q.ask = round(price + half, 4)
    return q


def _reading(tier: FeedTier, provider: str, quote: Quote) -> FeedReading:
    return FeedReading(tier=tier, provider=provider, quote=quote)


# ---------------------------------------------------------------- provenance


class TestProvenance:
    def test_verified_is_presentable(self):
        assert can_present_as_verified(ProvenanceType.VERIFIED) is True

    def test_derived_never_presentable_as_verified(self):
        for p in (
            ProvenanceType.DERIVED,
            ProvenanceType.INFERRED,
            ProvenanceType.SIMULATED,
        ):
            assert can_present_as_verified(p) is False

    def test_presentation_label_flags_non_verified(self):
        assert presentation_label(ProvenanceType.VERIFIED) == "VERIFIED"
        assert "not verified" in presentation_label(ProvenanceType.INFERRED)

    def test_source_kind_mapping(self):
        assert provenance_for_source_kind("live_feed") == ProvenanceType.VERIFIED
        assert provenance_for_source_kind("derived_calc") == ProvenanceType.DERIVED
        assert provenance_for_source_kind("llm_interpretation") == ProvenanceType.INFERRED
        assert provenance_for_source_kind("simulated") == ProvenanceType.SIMULATED

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="unknown source kind"):
            provenance_for_source_kind("magic")

    def test_verification_states_complete(self):
        expected = {
            "VERIFIED",
            "PARTIALLY_VERIFIED",
            "UNVERIFIED",
            "CONFLICTING_DATA",
            "STALE_DATA",
            "INSUFFICIENT_EVIDENCE",
        }
        assert {s.value for s in VerificationState} == expected


# ----------------------------------------------------------- reconciliation


class TestReconciliation:
    def setup_method(self) -> None:
        self.engine = MarketDataReconciliationEngine()

    def test_consistent_two_feeds(self):
        report = self.engine.reconcile(
            "XAUUSD",
            [
                _reading(FeedTier.PRIMARY, "rtds", _quote(4700.0)),
                _reading(FeedTier.SECONDARY, "yahoo", _quote(4700.9)),
            ],
        )
        assert report.state == ReconciliationState.CONSISTENT
        assert report.reference_price == 4700.0
        assert report.max_pct_deviation < 0.001

    def test_divergent_price_blocks(self):
        report = self.engine.reconcile(
            "BTCUSD",
            [
                _reading(FeedTier.PRIMARY, "rtds", _quote(77000.0)),
                _reading(FeedTier.SECONDARY, "other", _quote(77_000 * 1.01)),  # 1% off
            ],
        )
        assert report.state == ReconciliationState.DIVERGENT
        payload = report.to_payload()
        assert payload["state"] == "DIVERGENT"

    def test_stale_primary_feed(self):
        report = self.engine.reconcile(
            "XAUUSD",
            [_reading(FeedTier.PRIMARY, "slow", _quote(4700.0, age_sec=999))],
        )
        assert report.state == ReconciliationState.STALE

    def test_single_feed_is_degraded(self):
        report = self.engine.reconcile(
            "XAUUSD",
            [_reading(FeedTier.PRIMARY, "only", _quote(4700.0))],
        )
        assert report.state == ReconciliationState.DEGRADED
        assert "single feed" in report.reason

    def test_no_feeds_stale_with_reason(self):
        report = self.engine.reconcile("XAUUSD", [])
        assert report.state == ReconciliationState.STALE
        assert report.reference_price is None

    def test_timestamp_drift_degrades(self):
        engine = MarketDataReconciliationEngine(max_feed_ts_deviation_sec=10.0)
        report = engine.reconcile(
            "XAUUSD",
            [
                _reading(FeedTier.PRIMARY, "a", _quote(4700.0)),
                _reading(FeedTier.SECONDARY, "b", _quote(4700.1, age_sec=120)),
            ],
        )
        assert report.state == ReconciliationState.DEGRADED

    def test_wide_spread_degrades(self):
        engine = MarketDataReconciliationEngine(warn_spread_bps=5.0)
        report = engine.reconcile(
            "XAUUSD",
            [
                _reading(FeedTier.PRIMARY, "a", _quote(4700.0, bid_ask_pct=0.003)),
                _reading(FeedTier.SECONDARY, "b", _quote(4700.2)),
            ],
        )
        assert report.state == ReconciliationState.DEGRADED
        assert report.max_spread_bps > 5.0

    def test_secondary_stale_degrades_but_not_divergent(self):
        report = self.engine.reconcile(
            "XAUUSD",
            [
                _reading(FeedTier.PRIMARY, "a", _quote(4700.0)),
                _reading(FeedTier.SECONDARY, "b", _quote(4700.5, age_sec=500)),
            ],
        )
        # price close → not divergent; secondary stale → degraded
        assert report.state in (ReconciliationState.DEGRADED, ReconciliationState.STALE)

    def test_latency_spread_computed(self):
        report = self.engine.reconcile(
            "XAUUSD",
            [
                _reading(FeedTier.PRIMARY, "a", _quote(4700.0, latency_ms=40)),
                _reading(FeedTier.SECONDARY, "b", _quote(4700.1, latency_ms=310)),
            ],
        )
        assert report.latency_spread_ms == 270

    @pytest.mark.asyncio
    async def test_publish_emits_feed_divergence_event(self):
        bus = InMemoryEventBus()
        report = self.engine.reconcile(
            "BTCUSD",
            [
                _reading(FeedTier.PRIMARY, "a", _quote(77000.0)),
                _reading(FeedTier.SECONDARY, "b", _quote(78_500.0)),
            ],
        )
        await publish_reconciliation(bus, report)
        topics = [e.topic for e in bus.published]
        assert FEED_DIVERGENCE in topics
        ev = next(e for e in bus.published if e.topic == FEED_DIVERGENCE)
        assert ev.payload["trading_blocked"] is True

    @pytest.mark.asyncio
    async def test_publish_emits_data_stale_on_stale_state(self):
        bus = InMemoryEventBus()
        report = self.engine.reconcile(
            "XAUUSD", [_reading(FeedTier.PRIMARY, "a", _quote(4700.0, age_sec=900))]
        )
        await publish_reconciliation(bus, report)
        assert any(e.topic == DATA_STALE for e in bus.published)

    @pytest.mark.asyncio
    async def test_consistent_publishes_nothing(self):
        bus = InMemoryEventBus()
        report = self.engine.reconcile(
            "XAUUSD",
            [
                _reading(FeedTier.PRIMARY, "a", _quote(4700.0)),
                _reading(FeedTier.SECONDARY, "b", _quote(4700.5)),
            ],
        )
        await publish_reconciliation(bus, report)
        assert bus.published == []
