"""i18n endpoints (P20-P23): catalogs, translate, health."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core.config import get_settings
from core.translation import (
    catalogs_payload,
    translate_text,
)
from core.translation import (
    health as translation_health,
)

router = APIRouter(prefix="/api/v1/i18n", tags=["i18n"])


class TranslateIn(BaseModel):
    text: str
    target_lang: str | None = None
    source_lang: str | None = None


@router.get("/catalogs")
def catalogs() -> dict:
    payload = catalogs_payload()
    payload["ui_language_default"] = get_settings().orion_ui_language
    return payload


@router.post("/translate")
def translate(body: TranslateIn) -> dict:
    result = translate_text(body.text, body.target_lang or
                            get_settings().orion_ui_language, body.source_lang)
    return result.to_dict()


@router.get("/health")
def i18n_health() -> dict:
    return translation_health()
