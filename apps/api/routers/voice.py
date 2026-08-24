"""ORION voice synthesis — runtime TTS action endpoint.

Distinct from `/api/v1/settings/connections/voice/*` (credential/preset CRUD,
in `settings.py`): this is the endpoint the Command Center calls every time
it wants to speak an alert out loud. Returns raw MP3 bytes on success; a
clear non-2xx status when OpenAI isn't configured or the call failed, so the
frontend can fall back to the browser's own free voice without a glitch.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from providers.voice.client import MAX_TEXT_LENGTH, VoiceClient

logger = logging.getLogger("orion.voice.router")
router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


class SpeakIn(BaseModel):
    text: str
    lang: str = "en"


@router.post("/speak")
async def speak(payload: SpeakIn) -> Response:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="text required")
    result = VoiceClient().synthesize(text[:MAX_TEXT_LENGTH])
    if result.status == "NOT_CONFIGURED":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result.detail)
    if result.status == "FAILED" or not result.audio:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.detail)
    return Response(content=result.audio, media_type=result.content_type)
