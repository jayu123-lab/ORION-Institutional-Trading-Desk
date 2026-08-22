"""ORION API entrypoint.

Run: uvicorn apps.api.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.events.bus import get_event_bus
from core.logging import setup_logging
from core.memory.database import init_db
from core.memory.models import Asset
from providers.tradingview.webhook import router as tv_router

from .routers import chat, desk, ideas, market, orders, system


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(get_settings().log_level)
    init_db()
    _seed_assets()
    bus = get_event_bus()
    bus.start()
    yield
    await bus.stop()


def _seed_assets() -> None:
    """Ensure watchlist assets exist (idempotent)."""
    from apps.api.routers.market import _watchlist
    from core.memory.database import get_session_factory

    with get_session_factory()() as session:
        existing = {a.symbol for a in session.query(Asset).all()}
        for sym in _watchlist():
            if sym in existing:
                continue
            session.add(Asset(symbol=sym, asset_class=_class_of(sym)))
        session.commit()


def _class_of(symbol: str) -> str:
    metals = {"XAUUSD", "XAGUSD", "MGC", "GC"}
    crypto = {"BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD", "XLM", "HBAR"}
    rates = {"US10Y", "US02Y"}
    fx = {"EURUSD", "GBPUSD", "DXY"}
    if symbol in metals:
        return "metal"
    if symbol in crypto:
        return "crypto"
    if symbol in rates:
        return "rate"
    if symbol in fx:
        return "fx"
    return "index"


app = FastAPI(
    title="ORION Institutional Trading Desk",
    version="0.1.0",
    description=(
        "Multi-agent institutional desk simulation. "
        "PAPER MODE only; live execution disabled by design."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router_module in (system, market, chat, desk, ideas, orders):
    app.include_router(router_module.router)
app.include_router(tv_router)


@app.websocket("/ws/events")
async def ws_events(websocket) -> None:  # noqa: ANN001 - starlette type
    """Broadcast bus events to dashboard clients."""
    from starlette.websockets import WebSocket, WebSocketDisconnect

    assert isinstance(websocket, WebSocket)
    await websocket.accept()

    queue: asyncio.Queue = asyncio.Queue()
    bus = get_event_bus()

    async def forward(event) -> None:  # noqa: ANN001
        await queue.put(event.to_dict())

    bus.subscribe("*", forward)
    try:
        while True:
            data = await queue.get()
            await websocket.send_json(data)
    except WebSocketDisconnect:
        return
