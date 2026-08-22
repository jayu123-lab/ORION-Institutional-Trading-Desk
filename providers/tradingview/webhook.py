"""TradingView Webhook Receiver (spec §13).

Receives JSON alerts from TradingView alerts (webhook URL pointing at
POST /api/v1/hooks/tradingview). Authentication via shared secret header
'X-ORION-Secret' compared against TRADINGVIEW_WEBHOOK_SECRET.

Credentials NEVER travel in alert payloads; alerts are stored raw + parsed.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError

from core.config import get_settings
from core.events.bus import emit
from core.events.types import ALERT_TRIGGERED
from core.memory.database import get_session_factory
from core.memory.models import TradingViewAlert

logger = logging.getLogger("orion.tradingview")
router = APIRouter(prefix="/hooks", tags=["hooks"])


class TVAlertPayload(BaseModel):
    """Conceptual schema — extra fields are preserved in `raw`."""

    symbol: str | None = None
    price: float | None = None
    time: str | None = None
    timeframe: str | None = None
    indicator: str | None = None
    signal: str | None = None
    volume: float | None = None


def verify_secret(header_value: str | None) -> None:
    expected = get_settings().tradingview_webhook_secret
    if not expected:
        raise HTTPException(status_code=503, detail="webhook secret not configured")
    if not header_value or not hmac.compare_digest(header_value, expected):
        raise HTTPException(status_code=401, detail="invalid webhook secret")


@router.post("/tradingview", status_code=202)
async def tradingview_webhook(
    request: Request,
    x_orion_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    verify_secret(x_orion_secret)
    try:
        body: dict[str, Any] = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="body must be JSON") from exc

    try:
        parsed = TVAlertPayload.model_validate(body)
    except ValidationError:
        parsed = TVAlertPayload()  # store raw anyway; never lose an alert

    session_factory = get_session_factory()
    with session_factory() as session:
        row = TradingViewAlert(
            symbol=parsed.symbol or "UNKNOWN",
            price=parsed.price,
            timeframe=parsed.timeframe,
            indicator=parsed.indicator,
            signal=parsed.signal,
            volume=parsed.volume,
            raw=body,
        )
        session.add(row)
        session.commit()
        logger.info("tv alert stored id=%s symbol=%s", row.id, row.symbol)
        await emit(
            ALERT_TRIGGERED,
            {"source": "tradingview", "symbol": row.symbol, "signal": row.signal, "id": row.id},
            "tradingview-webhook",
        )
        return {"accepted": True, "alert_id": row.id}
