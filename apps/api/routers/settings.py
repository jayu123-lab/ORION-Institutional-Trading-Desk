"""ORION Settings — connections and credentials.

Two kinds of endpoints live here:

- Legacy generic endpoints (`/status`, `/configure`, `/remove`) kept for
  backward compatibility, bugs fixed in place.
- Namespaced per-provider endpoints (`/connections/<provider>/...`) used by
  the Settings page, one block per provider (Polymarket, Faro, ...).

No endpoint here ever returns a raw secret value — only CONFIGURED/fingerprint
state, per core.security's design.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from core.config import get_settings
from core.security import SecretType, get_secret_store
from providers.faro.client import (
    FaroClient,
    format_faro_message,
    load_faro_settings,
    read_outbox,
    save_faro_settings,
)

logger = logging.getLogger("orion.settings")
router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _check_localhost(request: Request) -> None:
    """Restrict secret-mutating ops to a local client only.

    ORION is a single-user local desk; this is a light guard against the
    dashboard ever being reachable from a non-loopback origin, not a
    substitute for the OS/network boundary.
    """
    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost", None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Localhost only")


# --------------------------------------------------------------- legacy (fixed)
@router.get("/status", status_code=status.HTTP_200_OK)
async def settings_status() -> dict[str, str | bool]:
    """Return the current ORION settings status.

    Superseded by `/connections/<provider>/status` for real per-provider
    detail; kept for backward compatibility with any existing caller. The
    previous version referenced two Settings fields that never existed
    (`orion_credentials_configured/_authenticated`) and would raise
    AttributeError on every call — fixed here to report real secret-store
    state instead of crashing.
    """
    s = get_settings()
    store = get_secret_store()
    configured = store.retrieve_secret(SecretType.GAMMA_API_KEY).success or store.retrieve_secret(
        SecretType.CLOB_TOKEN
    ).success
    return {
        "configured": configured,
        "authenticated": configured,
        "live_trading": "DISABLED" if not s.orion_live_mode else "ENABLED",
        "market_ws": "CONNECTED" if s.orion_polymarket_ws_embedded else "DISCONNECTED",
    }


class ConfigureIn(BaseModel):
    secret_type: str | None = None
    value: str = ""


@router.post("/configure", status_code=status.HTTP_200_OK)
async def settings_configure(payload: ConfigureIn, request: Request) -> dict[str, str]:
    """Generic secret configure (legacy path, bug fixed: no more NameError
    when secret_type is empty)."""
    _check_localhost(request)
    if not payload.secret_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="secret_type required")

    secret_store = get_secret_store()
    result = secret_store.store_secret(payload.secret_type, payload.value)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)

    return {
        "status": "CONFIGURED",
        "fingerprint": result.value or "",
        "secret_type": payload.secret_type,
        "message": "Credentials stored securely",
    }


@router.post("/remove", status_code=status.HTTP_200_OK)
async def settings_remove() -> dict[str, str | bool]:
    """Remove Polymarket credentials (legacy path)."""
    s = get_settings()
    s.orion_live_mode = False
    return {
        "status": "REMOVED",
        "message": "Polymarket credentials cleared",
        "live_trading_disabled": True,
    }


# ------------------------------------------------------------ Polymarket block
@router.get("/connections/polymarket/status")
async def polymarket_status() -> dict:
    s = get_settings()
    store = get_secret_store()
    gamma = store.retrieve_secret(SecretType.GAMMA_API_KEY)
    clob = store.retrieve_secret(SecretType.CLOB_TOKEN)
    return {
        "polymarket": {
            "connection": "CONNECTED" if gamma.success or clob.success else "NOT_CONFIGURED",
            "authentication": "AUTHENTICATED" if clob.success else "NOT_CONFIGURED",
            "mode": "LIVE" if s.orion_live_mode else "SHADOW",
            "live_trading": "ENABLED" if s.orion_live_mode else "DISABLED",
            "market_ws": "CONNECTED" if s.orion_polymarket_ws_embedded else "DISCONNECTED",
            "cob": "HEALTHY" if clob.success else "PENDING",
            "gamma": "HEALTHY" if gamma.success else "PENDING",
        }
    }


class PolymarketConfigureIn(BaseModel):
    gamma_api_key: str | None = None
    clob_token: str | None = None


@router.post("/connections/polymarket/configure")
async def polymarket_configure(payload: PolymarketConfigureIn, request: Request) -> dict:
    _check_localhost(request)
    store = get_secret_store()
    fingerprint = None
    if payload.gamma_api_key:
        res = store.store_secret(SecretType.GAMMA_API_KEY, payload.gamma_api_key)
        if not res.success:
            raise HTTPException(status_code=400, detail=res.error)
        fingerprint = res.value
    if payload.clob_token:
        res = store.store_secret(SecretType.CLOB_TOKEN, payload.clob_token)
        if not res.success:
            raise HTTPException(status_code=400, detail=res.error)
        fingerprint = res.value
    return {"status": "CONFIGURED", "fingerprint": fingerprint}


# ----------------------------------------------------------------- Faro block
@router.get("/connections/faro/status")
async def faro_status() -> dict:
    store = get_secret_store()
    key_result = store.retrieve_secret(SecretType.FARO_API_KEY)
    settings = load_faro_settings()
    history = read_outbox(limit=1)
    return {
        "faro": {
            "configured": key_result.success,
            "fingerprint": key_result.value if key_result.success else None,
            "endpoint_configured": bool(settings.endpoint_url),
            "endpoint_url": settings.endpoint_url,
            "auto_send": settings.auto_send,
            "min_message_length": settings.min_message_length,
            "last_signal": history[0] if history else None,
        }
    }


class FaroConfigureIn(BaseModel):
    api_key: str | None = None
    endpoint_url: str | None = None
    auto_send: bool | None = None


@router.post("/connections/faro/configure")
async def faro_configure(payload: FaroConfigureIn, request: Request) -> dict:
    _check_localhost(request)
    fingerprint = None
    if payload.api_key:
        res = get_secret_store().store_secret(SecretType.FARO_API_KEY, payload.api_key)
        if not res.success:
            raise HTTPException(status_code=400, detail=res.error)
        fingerprint = res.value

    patch: dict = {}
    if payload.endpoint_url is not None:
        patch["endpoint_url"] = payload.endpoint_url
    if payload.auto_send is not None:
        patch["auto_send"] = payload.auto_send
    settings = save_faro_settings(patch) if patch else load_faro_settings()

    return {
        "status": "CONFIGURED",
        "fingerprint": fingerprint,
        "endpoint_configured": bool(settings.endpoint_url),
        "auto_send": settings.auto_send,
    }


@router.post("/connections/faro/remove")
async def faro_remove(request: Request) -> dict:
    _check_localhost(request)
    res = get_secret_store().clear_secret(SecretType.FARO_API_KEY)
    return {"status": "REMOVED" if res.success else "ERROR", "message": res.error or "Faro API key cleared"}


@router.get("/connections/faro/history")
async def faro_history(limit: int = 20) -> dict:
    return {"history": read_outbox(limit=limit)}


class FaroTestIn(BaseModel):
    asset: str = "XAUUSD"
    direction: str = "LONG"
    entry: float = 2400.0
    stop_loss: float = 2380.0
    tp1: float = 2440.0
    tp2: float | None = 2460.0


@router.post("/connections/faro/test")
async def faro_test(payload: FaroTestIn, request: Request) -> dict:
    """Compose + attempt-send a clearly-labeled TEST message, without needing
    a real approved trade idea. Useful to validate the connector end to end."""
    _check_localhost(request)
    targets = [t for t in (payload.tp1, payload.tp2) if t is not None]
    message = format_faro_message(
        asset=payload.asset,
        direction=payload.direction,
        entry=payload.entry,
        stop_loss=payload.stop_loss,
        targets=targets,
        timeframe="H4",
        confidence="MODERATE",
        horizon="days",
        technical_thesis="TEST message generated from Settings > Faro to validate the connector end to end.",
        risks="This is a test signal, not a real trade idea.",
    )
    result = FaroClient().send(message)
    return result.to_dict()
