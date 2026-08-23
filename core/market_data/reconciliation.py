"""MarketDataReconciliationEngine — cross-feed price validation.

Receives quotes for the same symbol from feeds with declared tiers
(PRIMARY/SECONDARY/TERTIARY/FALLBACK) and computes:

- percentage deviation vs the PRIMARY feed
- spread deviation (quoted bid/ask width, in bps)
- timestamp deviation between feeds and vs now
- latency deviation across feeds

Verdicts:
- CONSISTENT  → all checks within thresholds
- DEGRADED    → usable but reduced confidence (single feed, soft ts drift)
- DIVERGENT   → material price disagreement → trading must be blocked
- STALE       → primary feed too old

Pure computation; optional bus publishing of FEED_DIVERGENCE / DATA_STALE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from core.market_data.base import Quote, is_stale

if TYPE_CHECKING:
    from core.events.bus import EventBusLike


class FeedTier(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    TERTIARY = "TERTIARY"
    FALLBACK = "FALLBACK"


class ReconciliationState(StrEnum):
    CONSISTENT = "CONSISTENT"
    DEGRADED = "DEGRADED"
    DIVERGENT = "DIVERGENT"
    STALE = "STALE"


@dataclass(frozen=True)
class FeedReading:
    tier: FeedTier
    provider: str
    quote: Quote


@dataclass(frozen=True)
class ReconciliationReport:
    symbol: str
    state: ReconciliationState
    reference_price: float | None  # primary feed price
    feeds: tuple[FeedReading, ...]
    max_pct_deviation: float  # vs primary, fraction (0.0012 = 0.12%)
    max_spread_bps: float
    max_ts_deviation_sec: float  # between feeds
    max_age_sec: float  # oldest feed age vs now
    latency_spread_ms: int | None
    reason: str
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_payload(self) -> dict:
        return {
            "symbol": self.symbol,
            "state": self.state.value,
            "reference_price": self.reference_price,
            "max_pct_deviation": round(self.max_pct_deviation, 6),
            "max_spread_bps": round(self.max_spread_bps, 2),
            "max_ts_deviation_sec": round(self.max_ts_deviation_sec, 3),
            "max_age_sec": round(self.max_age_sec, 3),
            "latency_spread_ms": self.latency_spread_ms,
            "reason": self.reason,
            "providers": [f"{r.tier.value}:{r.provider}" for r in self.feeds],
            "ts": self.ts.isoformat(),
        }


def _age_sec(q: Quote, now: datetime) -> float:
    ts = q.ts_source if q.ts_source.tzinfo else q.ts_source.replace(tzinfo=UTC)
    return max(0.0, (now - ts).total_seconds())


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _spread_bps(q: Quote) -> float | None:
    if q.bid is None or q.ask is None or q.price <= 0:
        return None
    return abs(q.ask - q.bid) / q.price * 10_000


class MarketDataReconciliationEngine:
    """Stateless comparator — instantiate once and call reconcile() per symbol."""

    def __init__(
        self,
        *,
        max_pct_deviation: float = 0.003,  # 0.30% divergence threshold
        max_feed_ts_deviation_sec: float = 60.0,
        stale_after_sec: float = 180.0,
        warn_spread_bps: float = 15.0,
    ) -> None:
        self.max_pct_deviation = max_pct_deviation
        self.max_feed_ts_deviation_sec = max_feed_ts_deviation_sec
        self.stale_after_sec = stale_after_sec
        self.warn_spread_bps = warn_spread_bps

    def reconcile(
        self,
        symbol: str,
        readings: list[FeedReading],
        now: datetime | None = None,
    ) -> ReconciliationReport:
        if not readings:
            return ReconciliationReport(
                symbol=symbol.upper(),
                state=ReconciliationState.STALE,
                reference_price=None,
                feeds=(),
                max_pct_deviation=0.0,
                max_spread_bps=0.0,
                max_ts_deviation_sec=0.0,
                max_age_sec=float("inf"),
                latency_spread_ms=None,
                reason="no feeds available",
            )
        now = now or datetime.now(UTC)
        ordered = sorted(readings, key=lambda r: 0 if r.tier == FeedTier.PRIMARY else 1)
        primary = ordered[0]
        ref_price = primary.quote.price
        ages = [_age_sec(r.quote, now) for r in ordered]
        max_age = max(ages)

        # pairwise deviations vs primary
        pct_devs: list[float] = []
        ts_devs: list[float] = []
        for r in ordered[1:]:
            if ref_price:
                pct_devs.append(abs(r.quote.price - ref_price) / ref_price)
            t_ref = _aware(primary.quote.ts_source)
            t_r = _aware(r.quote.ts_source)
            ts_devs.append(abs((t_r - t_ref).total_seconds()))
        spreads = [b for b in (_spread_bps(r.quote) for r in ordered) if b is not None]
        latencies = [
            r.quote.quality.latency_ms
            for r in ordered
            if r.quote.quality.latency_ms is not None
        ]
        latency_spread = (max(latencies) - min(latencies)) if len(latencies) >= 2 else None

        max_pct = max(pct_devs, default=0.0)
        max_ts = max(ts_devs, default=0.0)
        max_spread = max(spreads, default=0.0)

        state, reason = self._verdict(
            n_feeds=len(ordered),
            primary_is_stale=is_stale(primary.quote.ts_source, int(self.stale_after_sec), now),
            any_stale=any(
                is_stale(r.quote.ts_source, int(self.stale_after_sec), now) for r in ordered
            ),
            max_pct=max_pct,
            max_ts=max_ts,
            max_spread=max_spread,
        )

        return ReconciliationReport(
            symbol=symbol.upper(),
            state=state,
            reference_price=ref_price,
            feeds=tuple(ordered),
            max_pct_deviation=max_pct,
            max_spread_bps=max_spread,
            max_ts_deviation_sec=max_ts,
            max_age_sec=max_age,
            latency_spread_ms=latency_spread,
            reason=reason,
            ts=now,
        )

    def _verdict(
        self,
        *,
        n_feeds: int,
        primary_is_stale: bool,
        any_stale: bool,
        max_pct: float,
        max_ts: float,
        max_spread: float,
    ) -> tuple[ReconciliationState, str]:
        if n_feeds == 0 or primary_is_stale:
            return ReconciliationState.STALE, (
                "primary feed stale" if n_feeds else "no feeds"
            )
        if max_pct > self.max_pct_deviation:
            return ReconciliationState.DIVERGENT, (
                f"price deviation {max_pct:.4%} exceeds "
                f"{self.max_pct_deviation:.4%} across feeds"
            )
        if any_stale:
            return ReconciliationState.DEGRADED, "secondary/tertiary feed stale"
        if n_feeds < 2:
            return ReconciliationState.DEGRADED, "single feed — no cross validation possible"
        if max_ts > self.max_feed_ts_deviation_sec:
            return (
                ReconciliationState.DEGRADED,
                f"feed timestamps differ by {max_ts:.0f}s",
            )
        if max_spread > self.warn_spread_bps:
            return ReconciliationState.DEGRADED, f"wide quoted spread {max_spread:.1f}bps"
        return ReconciliationState.CONSISTENT, "all cross-feed checks within thresholds"


async def publish_reconciliation(bus: EventBusLike, report: ReconciliationReport) -> None:
    """Emit FEED_DIVERGENCE / DATA_STALE events for bad states."""
    from core.events.types import DATA_STALE, FEED_DIVERGENCE, Event

    if report.state == ReconciliationState.DIVERGENT:
        payload = report.to_payload()
        payload["trading_blocked"] = True
        await bus.publish(
            Event(topic=FEED_DIVERGENCE, payload=payload, source="reconciliation")
        )
    elif report.state == ReconciliationState.STALE:
        await bus.publish(
            Event(topic=DATA_STALE, payload=report.to_payload(), source="reconciliation")
        )
