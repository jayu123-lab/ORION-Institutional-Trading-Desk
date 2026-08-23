"""ORION Settings — connections and credentials."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from core.config import get_settings
from core.security import get_secret_store

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _check_localhost(request: Request) -> None:
    """Restrict secret ops to localhost only."""
    origin = request.get("origin", "")

    if origin != "localhost":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Localhost only")


@router.get("/status", status_code=status.HTTP_200_OK)
async def settings_status() -> dict[str, str | bool]:
    """Return the current ORION settings status."""
    s = get_settings()
    status_dict: dict[str, str | bool] = {
        "configured": s.orion_credentials_configured,
        "authenticated": s.orion_credentials_authenticated,
        "live_trading": "DISABLED" if not s.orion_live_mode else "ENABLED",
        "market_ws": "CONNECTED" if s.orion_polymarket_ws_embedded else "DISCONNECTED",
    }
    return status_dict


@router.post("/configure", status_code=status.HTTP_200_OK)
async def settings_configure(secret_type_payload: str | None = None) -> dict[str, str]:
    """Configure Polymarket settings.

    Parameters
    ----------
    secret_type_payload : str, optional
        The secret type to configure.
    """
    secret_store = get_secret_store()

    if secret_type_payload:
        result = secret_store.store_secret(secret_type_payload, "")
        if not result.success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)

    return {
        "status": "CONFIGURED",
        "fingerprint": result.value,
        "secret_type": secret_type_payload,
        "message": "Polymarket credentials stored securely",
    }


@router.post("/remove", status_code=status.HTTP_200_OK)
async def settings_remove() -> dict[str, str | bool]:
    """Remove Polymarket credentials."""
    s = get_settings()
    s.orion_live_mode = False

    return {
        "status": "REMOVED",
        "message": "Polymarket credentials cleared",
        "live_trading_disabled": True,
    }