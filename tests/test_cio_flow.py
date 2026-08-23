"""CIO-led desk workflow: routing, context, specialists, risk/audit gates, chat API."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from apps.api.routers import cio as cio_router_module  # noqa: E402
from core.desk.cio import CIOOrchestrator  # noqa: E402
from core.desk.context import ContextBuilder  # noqa: E402
from core.desk.registry import AgentRegistry  # noqa: E402
from core.desk.router import IntentRouter  # noqa: E402
from core.memory.database import get_session_factory, init_db  # noqa: E402
from core.memory.models import Candle as DBCandle  # noqa: E402
from core.memory.models import Quote as DBQuote  # noqa: E402


def _make_engine(tmp_path):
    os.environ["ORION_TEST_DATABASE_URL"] = f"sqlite:///{tmp_path}/cio-test.db"
    return init_db()


def _seed_db(engine, *, stale_quote: bool = False, with_candles: bool = True) -> None:
    now = datetime.now(UTC)
    quote_ts = now - timedelta(minutes=30) if stale_quote else now
    with get_session_factory(engine)() as s:
        if with_candles:
            def series(symbol: str, base: float, drift: float, n: int = 60):
                for i in range(n - 1, -1, -1):
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
            series("US10Y", 4.5, 0.001)

        for sym, px in (("XAUUSD", 4690.0), ("DXY", 98.8), ("US10Y", 4.72)):
            s.add(
                DBQuote(
                    symbol=sym,
                    provider="testfeed",
                    price=px,
                    bid=px * 0.9999,
                    ask=px * 1.0001,
                    ts_source=quote_ts,
                    ts_received=quote_ts,
                    status="STALE" if stale_quote else "LIVE",
                )
            )
        s.commit()


@pytest.fixture()
def desk(tmp_path):
    engine = _make_engine(tmp_path)
    _seed_db(engine)
    AgentRegistry.reset()
    yield CIOOrchestrator(get_session_factory(engine), AgentRegistry)
    AgentRegistry.reset()


# ------------------------------------------------------------------- router
class TestIntentRouter:
    def test_default_market_analysis_gold(self):
        d = IntentRouter().route("Analiza XAUUSD")
        assert d.intent == "MARKET_ANALYSIS"
        assert d.asset == "XAUUSD"
        assert d.required_agents[0] == "metals-analyst"
        assert "risk-manager" in d.required_agents and "audit-agent" in d.required_agents

    def test_trade_plan_intent(self):
        d = IntentRouter().route("¿Comprarías oro ahora?")
        assert d.intent == "TRADE_PLAN"
        assert d.asset == "XAUUSD"

    def test_xrp_routes_crypto_pipeline(self):
        d = IntentRouter().route("Analiza XRP")
        assert d.asset == "XRPUSD"
        assert d.asset_class == "crypto"
        assert d.required_agents[0] == "crypto-analyst"

    def test_desk_debate_intent(self):
        d = IntentRouter().route("Convoca la mesa para XAUUSD")
        assert d.intent == "DESK_DEBATE"
        assert d.asset == "XAUUSD"

    def test_risk_intent(self):
        d = IntentRouter().route("revisa el riesgo de BTC")
        assert d.intent == "RISK"
        assert d.asset == "BTCUSD"


# ------------------------------------------------------------------ context
class TestContextBuilder:
    @pytest.mark.asyncio
    async def test_provenance_tags(self, tmp_path):
        engine = _make_engine(tmp_path)
        _seed_db(engine)
        ctx = await ContextBuilder(get_session_factory(engine)).build("XAUUSD")
        price = ctx["price"]
        assert price["provenance"] in ("VERIFIED", "DERIVED")
        assert price["source"] == "db:testfeed"
        assert isinstance(price["value"], float)
        ms = ctx["market_state"]
        assert {"regime", "volatility", "risk_mode", "data_quality"} <= set(ms)
        assert ctx["positioning_cftc"]["provenance"] in ("VERIFIED", "NOT_AVAILABLE")

    @pytest.mark.asyncio
    async def test_missing_symbol_is_honest(self, tmp_path):
        engine = _make_engine(tmp_path)
        _seed_db(engine)
        ctx = await ContextBuilder(get_session_factory(engine)).build("NOEXIST")
        assert ctx["price"]["provenance"] == "NOT_AVAILABLE"


# ----------------------------------------------------------------- pipeline
@pytest.mark.asyncio
async def test_gold_pipeline_runs_specialists(desk):
    out = await desk.handle("Analiza XAUUSD")
    agents_run = {a["agent"] for a in out["activity"]}
    assert {"metals-analyst", "macro-strategist", "quant-architect",
            "risk-manager", "audit-agent"} <= agents_run
    assert f"ORION CIO {'-' * 3} XAUUSD DESK READ".replace("---", "\u2014") in out["reply"]
    assert out["routing"]["asset"] == "XAUUSD"


@pytest.mark.asyncio
async def test_risk_veto_blocks_plan_on_stale_quote(tmp_path):
    engine = _make_engine(tmp_path)
    _seed_db(engine, stale_quote=True)
    AgentRegistry.reset()
    orch = CIOOrchestrator(get_session_factory(engine), AgentRegistry)
    out = await orch.handle("Comprar\u00edas oro ahora?")
    assert "NO TRADE" in out["reply"]
    AgentRegistry.reset()


@pytest.mark.asyncio
async def test_audit_reports_gaps_without_candles(tmp_path):
    engine = _make_engine(tmp_path)
    _seed_db(engine, with_candles=False)
    AgentRegistry.reset()
    orch = CIOOrchestrator(get_session_factory(engine), AgentRegistry)
    out = await orch.handle("Analiza XAUUSD")
    assert "candle history" in out["audit"]["gaps"]
    assert out["audit"]["verdict"] == "PASS_WITH_GAPS"
    conf_line = next(ln for ln in out["reply"].splitlines() if ln.startswith("CONFIDENCE:"))
    assert "LOW" in conf_line or "MODERATE" in conf_line
    AgentRegistry.reset()


@pytest.mark.asyncio
async def test_desk_debate_via_cio(desk):
    out = await desk.handle("Convoca la mesa para XAUUSD")
    assert "ORION DESK DEBATE \u2014 XAUUSD" in out["reply"]
    assert "CONSENSUS:" in out["reply"]
    assert any(a["agent"] == "desk" and a["status"] == "ok" for a in out["activity"])


@pytest.mark.asyncio
async def test_registry_records_real_runs(desk):
    spec_before = AgentRegistry.get("metals-analyst")
    assert spec_before is not None and spec_before.health == "NEVER_RUN"
    await desk.handle("Analiza XAUUSD")
    spec_after = AgentRegistry.get("metals-analyst")
    assert spec_after is not None
    assert spec_after.last_run is not None
    assert spec_after.health in ("HEALTHY", "STALE")
    cio_spec = AgentRegistry.get("orion-cio")
    assert cio_spec is not None
    assert cio_spec.last_run is not None


def test_registry_roster_shape():
    AgentRegistry.reset()
    roster = AgentRegistry.to_list()
    assert len(roster) == 15
    required_keys = {"agent_id", "name", "role", "status", "health"}
    assert all(required_keys <= set(a) for a in roster)
    ids = {a["agent_id"] for a in roster}
    assert {"orion-cio", "risk-manager", "metals-analyst", "crypto-analyst",
            "market-data-engineer", "audit-agent"} <= ids


# ---------------------------------------------------------------- chat API
@pytest.fixture(name="client")
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORION_TEST_DATABASE_URL", f"sqlite:///{tmp_path}/cio-api.db")
    monkeypatch.setenv("ORION_EMBEDDED_DATA", "false")
    from core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(cio_router_module, "_ORCHESTRATOR", None)
    monkeypatch.setattr(cio_router_module, "_REGISTRY", None)
    from apps.api.main import app

    init_db()
    with fastapi_testclient.TestClient(app) as c:
        yield c


def test_chat_without_mention_goes_through_cio(client):
    from core.memory.database import get_session_factory as gsf

    now = datetime.now(UTC)
    with gsf()() as s:
        s.add(DBQuote(symbol="XAUUSD", provider="testfeed", price=4690.0, bid=4689.0,
                      ask=4691.0, ts_source=now, ts_received=now, status="LIVE"))
        for i in range(20):
            c = 4600.0 + (20 - i)
            s.add(DBCandle(symbol="XAUUSD", timeframe="H1", provider="t",
                           open=c - 0.5, high=c + 1, low=c - 1, close=c,
                           volume=1.0, ts_open=now - timedelta(hours=i)))
        s.commit()

    r = client.post("/api/v1/chat", json={"content": "Analiza XAUUSD", "room": "desk"})
    assert r.status_code == 201
    body = r.json()
    cio_payload = body.get("cio")
    assert cio_payload is not None
    assert cio_payload["routing"]["asset"] == "XAUUSD"
    assert len(cio_payload["activity"]) >= 3

    hist = client.get("/api/v1/chat/history?room=desk").json()
    assert hist[-1]["author"] == "orion-cio"


def test_chat_with_unknown_mention_reports_system_error(client):
    r = client.post("/api/v1/chat", json={"content": "@fantasma hola", "room": "desk"})
    assert r.status_code == 201
    hist = client.get("/api/v1/chat/history?room=desk").json()
    assert hist[-1]["author"] == "system"
    assert "@fantasma" in hist[-1]["content"]


def test_cio_agents_endpoint_shape(client):
    r = client.get("/api/v1/agents")
    assert r.status_code == 200
    roster = r.json()
    assert len(roster) == 15
    first = roster[0]
    for key in ("agent_id", "name", "role", "status", "health"):
        assert key in first
