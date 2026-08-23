"""Audit / Verification core (spec PRIORITY 1).

Independent of any analyst consensus. Its ONLY job is to find problems:

- feed staleness and timestamp sanity
- cross-feed price discrepancies (via reconciliation engine)
- unsupported claims (numeric assertions without cited sources)
- numeric coherence (recompute derived numbers)

Verdicts use VerificationState. The auditor never votes on direction and is
excluded from consensus weighting by design.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from core.market_data.reconciliation import (
    FeedReading,
    FeedTier,
    MarketDataReconciliationEngine,
    ReconciliationState,
)
from core.provenance import VerificationState


class DataSourceRef(dict):
    """Expected shape: {"symbol": str, "provider": str, "ts": iso-str}."""

    pass


class SourceCheckResult:
    __slots__ = ("source", "state", "detail")

    def __init__(self, source: dict, state: VerificationState, detail: str) -> None:
        self.source = source
        self.state = state
        self.detail = detail


class DebateAuditReport:
    __slots__ = ("opinion_states", "source_checks", "discrepancies", "overall", "notes")

    def __init__(self) -> None:
        self.opinion_states: dict[str, str] = {}
        self.source_checks: list[SourceCheckResult] = []
        self.discrepancies: list[str] = []
        self.notes: list[str] = []

    @property
    def overall_state(self) -> VerificationState:
        if self.discrepancies:
            return VerificationState.CONFLICTING_DATA
        states = [VerificationState(s) for s in self.opinion_states.values()]
        if not states:
            return VerificationState.INSUFFICIENT_EVIDENCE
        order = [
            VerificationState.CONFLICTING_DATA,
            VerificationState.STALE_DATA,
            VerificationState.UNVERIFIED,
            VerificationState.INSUFFICIENT_EVIDENCE,
            VerificationState.PARTIALLY_VERIFIED,
            VerificationState.VERIFIED,
        ]
        return min(states, key=order.index)


class AuditVerifier:
    """Stateless verification helpers + DB-backed source checking."""

    #: seconds after which a cited quote is considered stale for audit purposes
    STALE_AFTER_SEC = 300

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.source_checks: list[SourceCheckResult] = []
        self.discrepancies: list[str] = []

    # ------------------------------------------------------------- sources
    def check_source(
        self,
        source: dict[str, Any],
        now: datetime | None = None,
    ) -> SourceCheckResult:
        """Validate one cited data source against the DB."""
        now = now or datetime.now(UTC)
        symbol = str(source.get("symbol") or "").upper()
        ts_raw = source.get("ts")
        if not symbol or not ts_raw:
            return SourceCheckResult(
                source, VerificationState.INSUFFICIENT_EVIDENCE, "missing symbol/ts"
            )

        try:
            ts = datetime.fromisoformat(str(ts_raw))
        except ValueError:
            return SourceCheckResult(
                source, VerificationState.UNVERIFIED, "unparseable timestamp"
            )
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if ts > now:
            return SourceCheckResult(
                source, VerificationState.CONFLICTING_DATA, "timestamp in the future"
            )

        age = (now - ts).total_seconds()
        if age > self.STALE_AFTER_SEC * 12:  # citations older than 1h are stale evidence
            return SourceCheckResult(
                source, VerificationState.STALE_DATA, f"age {age:.0f}s"
            )

        row = self._latest_db_quote(symbol)
        if row is None:
            return SourceCheckResult(
                source, VerificationState.UNVERIFIED, f"no stored quote for {symbol}"
            )

        db_price = float(row.price)
        claimed = source.get("price")
        if claimed is not None:
            dev = abs(db_price - float(claimed)) / max(db_price, 1e-9)
            if dev > 0.01:  # >1% off stored data → conflicting
                return SourceCheckResult(
                    source,
                    VerificationState.CONFLICTING_DATA,
                    f"cited price deviates {dev:.2%} from stored {db_price}",
                )
        return SourceCheckResult(source, VerificationState.VERIFIED, f"age {age:.0f}s, coherent")
    def cross_feed_check(self, symbol: str, now: datetime | None = None) -> list[str]:
        """Detect discrepancies between providers currently storing this symbol."""
        now = now or datetime.now(UTC)
        readings: list[FeedReading] = []
        tiers = [FeedTier.PRIMARY, FeedTier.SECONDARY, FeedTier.TERTIARY]
        with self.session_factory() as session:
            from core.memory.models import Quote as DBQuote

            rows = (
                session.execute(
                    select(DBQuote)
                    .where(DBQuote.symbol == symbol.upper())
                    .order_by(DBQuote.id.desc())
                    .limit(30)
                )
                .scalars()
                .all()
            )
        seen_providers: set[str] = set()
        for r in rows:
            if r.provider in seen_providers:
                continue
            seen_providers.add(r.provider)
            tier = tiers[min(len(readings), len(tiers) - 1)]
            readings.append(
                FeedReading(
                    tier=tier,
                    provider=r.provider,
                    quote=_row_to_quote(r),
                )
            )
        if len(readings) < 2:
            return []
        report = MarketDataReconciliationEngine().reconcile(symbol, readings, now)
        if report.state == ReconciliationState.DIVERGENT:
            return [report.reason]
        return []

    # -------------------------------------------------------------- debate
    def audit_opinion(self, opinion: dict[str, Any], now: datetime | None = None) -> str:
        """Verify one debate opinion: sources exist/fresh/coherent; numbers cited."""
        now = now or datetime.now(UTC)
        args_text = " ".join(opinion.get("arguments") or [])
        has_numbers = any(ch.isdigit() for ch in args_text)
        sources = opinion.get("data_sources") or []
        if not sources:
            if has_numbers:
                return VerificationState.UNVERIFIED.value  # numbers without provenance
            return VerificationState.INSUFFICIENT_EVIDENCE.value

        states: list[VerificationState] = []
        for s in sources:
            res = self.check_source(s, now)
            self.source_checks.append(res)
            states.append(res.state)
            if res.state == VerificationState.CONFLICTING_DATA:
                self.discrepancies.append(f"{opinion.get('agent')}: {res.detail}")
        verified = sum(1 for s in states if s == VerificationState.VERIFIED)
        if verified == len(states):
            return VerificationState.VERIFIED.value
        if verified > 0:
            return VerificationState.PARTIALLY_VERIFIED.value
        return states[0].value

    def numeric_coherence(self, claimed_pct: float, base: float, target: float) -> bool:
        """Recompute a percentage claim within 0.05 tolerance."""
        if base == 0:
            return False
        actual = abs(target - base) / abs(base)
        return abs(actual - claimed_pct) <= 0.05

    # ------------------------------------------------------------------ io
    def _latest_db_quote(self, symbol: str):
        from core.memory.models import Quote as DBQuote

        with self.session_factory() as session:
            return (
                session.execute(
                    select(DBQuote)
                    .where(DBQuote.symbol == symbol.upper())
                    .order_by(DBQuote.id.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )


def _row_to_quote(row) -> Any:
    from core.market_data.base import DataQuality, DataStatus, Quote

    dq = DataQuality(provider=row.provider, status=DataStatus.LIVE, quality="UNKNOWN")
    return Quote(symbol=row.symbol, price=row.price, ts_source=row.ts_source, quality=dq)
