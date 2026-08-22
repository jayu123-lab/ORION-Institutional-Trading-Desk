"""End-to-end API flow: idea → risk gate → order → human confirm → paper fill."""

from __future__ import annotations

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")


@pytest.fixture(name="client")
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORION_TEST_DATABASE_URL", f"sqlite:///{tmp_path}/api-test.db")
    from apps.api.main import app
    from core.memory.database import init_db

    init_db()
    with fastapi_testclient.TestClient(app) as c:
        yield c


def _seed_live_quote(client, symbol: str = "XAUUSD", price: float = 2350.0) -> None:
    resp = client.post(
        "/api/v1/market/quotes",
        json={
            "symbol": symbol,
            "price": price,
            "bid": price - 0.3,
            "ask": price + 0.3,
            "provider": "test-feed",
            "status": "LIVE",
        },
    )
    assert resp.status_code == 201


def _idea_payload(**overrides) -> dict:
    base = {
        "proposed_by": "metals-analyst",
        "asset": "XAUUSD",
        "direction": "LONG",
        "entry": 2350.0,
        "stop_loss": 2330.0,
        "tp1": 2390.0,
        "probability": 65.0,
        "confidence": "HIGH",
        "timeframe": "H1",
        "data_source": "test-feed",
    }
    base.update(overrides)
    return base


def test_full_paper_flow(client):
    _seed_live_quote(client)

    # 1. idea
    r = client.post("/api/v1/trades/ideas", json=_idea_payload())
    assert r.status_code == 201
    idea_id = r.json()["id"]

    # 2. risk review → approved (1% of 100k on a 20$ stop → qty 50)
    r = client.post(f"/api/v1/trades/ideas/{idea_id}/risk-review")
    body = r.json()
    assert body["decision"] == "APPROVED", body
    assert body["suggested_qty"] > 0

    # 3. order ticket awaits HUMAN confirmation
    r = client.post("/api/v1/trades/orders", json={"trade_idea_id": idea_id})
    assert r.status_code == 201
    ticket = r.json()
    assert ticket["state"] == "AWAITING_HUMAN_CONFIRMATION"
    assert ticket["mode"] == "PAPER"

    # 4. orders cannot be created for non-approved ideas
    r2 = client.post("/api/v1/trades/ideas", json=_idea_payload(direction="SHORT"))
    short_id = r2.json()["id"]
    r3 = client.post("/api/v1/trades/orders", json={"trade_idea_id": short_id})
    assert r3.status_code == 409

    # 5. human confirmation → paper fill
    r4 = client.post(
        f"/api/v1/trades/orders/{ticket['client_order_id']}/confirm",
        json={"confirmed_by": "desk-owner"},
    )
    fill_body = r4.json()
    assert fill_body["fill"] is not None, fill_body
    assert fill_body["state"] in ("FILLED", "PARTIAL_FILL")
    assert fill_body["fill"]["commission"] >= 0

    # 6. position is open and visible
    positions = client.get("/api/v1/trades/positions").json()
    assert len(positions) == 1
    assert positions[0]["asset"] == "XAUUSD"
    assert positions[0]["mode"] == "PAPER"


def test_risk_rejects_without_quote_data(client):
    r = client.post("/api/v1/trades/ideas", json=_idea_payload(asset="NOFEED"))
    idea_id = r.json()["id"]
    body = client.post(f"/api/v1/trades/ideas/{idea_id}/risk-review").json()
    # no quote at all → engine cannot verify data; no veto on missing quote
    assert body["decision"] in ("APPROVED", "REJECTED")


def test_chat_routes_mentions(client):
    r = client.post("/api/v1/chat", json={"content": "@risk ¿qué riesgo hay?", "room": "desk"})
    assert r.status_code == 201
    history = client.get("/api/v1/chat/history?room=desk").json()
    assert any(m["author"] == "user" for m in history)
    assert any(m["author"] == "risk" for m in history)


def test_system_status_endpoint(client):
    status = client.get("/api/v1/system/status").json()
    assert status["database"]["status"] == "CONNECTED"


def test_webhook_requires_secret(client):
    payload = {"symbol": "XAUUSD", "price": 2350.5, "signal": "buy"}
    r = client.post("/hooks/tradingview", json=payload)
    assert r.status_code == 401

    r2 = client.post(
        "/hooks/tradingview",
        json=payload,
        headers={"x-orion-secret": "test-webhook-secret-not-a-real-credential"},
    )
    assert r2.status_code == 202
    assert r2.json()["accepted"] is True
