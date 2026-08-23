"""Tests for the debate engine and audit verifier (P7 + P1)."""

import os
from datetime import UTC, datetime, timedelta

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from core.audit.verifier import AuditVerifier  # noqa: E402
from core.debate.engine import DeskDebateEngine  # noqa: E402
from core.memory.database import get_session_factory, init_db  # noqa: E402
from core.memory.models import Candle as DBCandle  # noqa: E402
from core.memory.models import Quote as DBQuote  # noqa: E402
from core.provenance import VerificationState  # noqa: E402


def _seed_db(session_factory) -> None:
    now = datetime.now(UTC)
    with session_factory() as s:
        # candles: XAUUSD uptrend; DXY flat-down; VIX low; SPX up
        def series(symbol: str, base: float, drift: float, n: int = 60):
            for i in range(n - 1, -1, -1):  # oldest first by ts
                c = base + drift * (n - i)
                s.add(
                    DBCandle(
                        symbol=symbol,
                        timeframe="H1",
                        provider="test",
                        open=c - 0.5,
                        high=c + 1.0,
                        low=c - 1.0,
                        close=c,
                        volume=1000.0,
                        ts_open=now - timedelta(hours=i),
                    )
                )

        series("XAUUSD", 4600.0, 1.5)
        series("DXY", 99.0, -0.02)
        series("VIX", 14.0, 0.01)
        series("SPX", 7500.0, 3.0)

        s.add(
            DBQuote(
                symbol="XAUUSD",
                provider="testfeed",
                price=4690.0,
                bid=4689.8,
                ask=4690.2,
                ts_source=now,
                status="LIVE",
            )
        )
        s.commit()


@pytest.fixture()
def session_factory():
    init_db()
    sf = get_session_factory()
    _seed_db(sf)
    yield sf


class TestAuditVerifier:
    def test_check_source_verified(self, session_factory):
        av = AuditVerifier(session_factory)
        res = av.check_source(
            {
                "symbol": "XAUUSD",
                "provider": "testfeed",
                "ts": datetime.now(UTC).isoformat(),
                "price": 4690.0,
            }
        )
        assert res.state == VerificationState.VERIFIED

    def test_check_source_stale(self, session_factory):
        av = AuditVerifier(session_factory)
        old = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
        res = av.check_source({"symbol": "XAUUSD", "ts": old})
        assert res.state == VerificationState.STALE_DATA

    def test_check_source_conflicting_price(self, session_factory):
        av = AuditVerifier(session_factory)
        res = av.check_source(
            {"symbol": "XAUUSD", "ts": datetime.now(UTC).isoformat(), "price": 5000.0}
        )
        assert res.state == VerificationState.CONFLICTING_DATA

    def test_check_source_future_ts(self, session_factory):
        av = AuditVerifier(session_factory)
        future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        assert (
            av.check_source({"symbol": "XAUUSD", "ts": future}).state
            == VerificationState.CONFLICTING_DATA
        )

    def test_opinion_numbers_without_sources_unverified(self, session_factory):
        av = AuditVerifier(session_factory)
        state = av.audit_opinion(
            {
                "agent": "x",
                "arguments": ["price moved 4% today"],
                "data_sources": [],
            }
        )
        assert state == VerificationState.UNVERIFIED.value

    def test_numeric_coherence(self, session_factory):
        av = AuditVerifier(session_factory)
        assert av.numeric_coherence(0.05, 100.0, 105.0) is True
        assert av.numeric_coherence(0.05, 100.0, 130.0) is False


class TestDeskDebate:
    @pytest.mark.asyncio
    async def test_convene_returns_full_debate(self, session_factory):
        engine = DeskDebateEngine(session_factory)
        debate = await engine.convene("XAUUSD")
        agents = [o.agent for o in debate.opinions]
        for expected in (
            "orion-macro",
            "orion-quant",
            "orion-liquidity",
            "orion-positioning",
            "orion-news",
            "orion-crossasset",
            "orion-metals",
        ):
            assert expected in agents, f"missing {expected}"
        for op in debate.opinions:
            op.validate_bias()
            assert op.arguments, f"{op.agent} has no arguments"
            assert op.invalidation, f"{op.agent} missing invalidation"

    @pytest.mark.asyncio
    async def test_positioning_honest_not_available(self, session_factory):
        engine = DeskDebateEngine(session_factory)
        debate = await engine.convene("XAUUSD")
        pos = next(o for o in debate.opinions if o.agent == "orion-positioning")
        assert any("NOT AVAILABLE" in a for a in pos.arguments)
        assert pos.bias == "WAIT"

    @pytest.mark.asyncio
    async def test_audit_stamps_every_opinion(self, session_factory):
        engine = DeskDebateEngine(session_factory)
        debate = await engine.convene("XAUUSD")
        for op in debate.opinions:
            assert op.verification_state in {s.value for s in VerificationState}

    @pytest.mark.asyncio
    async def test_consensus_present_with_weights(self, session_factory):
        engine = DeskDebateEngine(session_factory)
        debate = await engine.convene("XAUUSD")
        assert debate.consensus["n_inputs"] >= 6
        assert debate.consensus["weights_used"]
        assert debate.consensus["internal_tag_only"] is True

    @pytest.mark.asyncio
    async def test_cio_synthesis_mentions_conditions_and_dissent(self, session_factory):
        engine = DeskDebateEngine(session_factory)
        debate = await engine.convene("XAUUSD")
        syn = debate.cio_synthesis
        assert syn.provenance == "INFERRED"  # synthesis is never VERIFIED
        assert syn.key_conditions
        assert "none" in syn.dissent_summary.lower() or ":" in syn.dissent_summary

    @pytest.mark.asyncio
    async def test_debate_persisted(self, session_factory):
        from sqlalchemy import select

        from core.memory.models import AgentOpinion as DBAgentOpinion
        from core.memory.models import Analysis

        engine = DeskDebateEngine(session_factory)
        await engine.convene("XAUUSD")
        with session_factory() as s:
            rows = s.execute(select(Analysis).where(Analysis.kind == "debate")).scalars().all()
            assert len(rows) >= 1  # factory is a process-wide singleton: rows accumulate
            ops = (
                s.execute(select(DBAgentOpinion).where(DBAgentOpinion.debate_id.is_not(None)))
                .scalars()
                .all()
            )
            assert len(ops) >= 6

    @pytest.mark.asyncio
    async def test_crypto_scope_skips_metals_voice(self, session_factory):
        engine = DeskDebateEngine(session_factory)
        debate = await engine.convene("BTCUSD")
        assert "orion-metals" not in [o.agent for o in debate.opinions]
