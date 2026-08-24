"""ORION voice — optional OpenAI TTS upgrade for the browser voice announcer.

The Command Center's voice alerts (`apps/web/lib/voice.ts`) work out of the
box with zero setup, using the browser's own free SpeechSynthesis engine.
This module adds an OPTIONAL, higher-quality upgrade: once the user configures
an OpenAI API key in Settings > Voz IA, `/api/v1/voice/speak` synthesizes the
same alert text with OpenAI's TTS model instead. The frontend always falls
back to the free browser voice automatically if this is unset or a call
fails — the feature never breaks, this only makes it sound better once
configured, at the user's own OpenAI cost.

Per project rule (same as Faro): no secret is ever returned to the frontend,
only CONFIGURED/fingerprint state; the raw key is used exclusively here for
the outbound OpenAI call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from core.security import SecretType, get_secret_store

logger = logging.getLogger("orion.voice")

VOICE_SETTINGS_PATH = Path("config/voice_settings.json")
VOICE_SYNTH_TIMEOUT_S = 15.0
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

# Stable, well-documented OpenAI TTS voice presets. "onyx" (deep, measured) is
# ORION's default to fit an institutional trading-desk tone; user-selectable
# in Settings > Voz IA.
VOICE_PRESETS = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")
DEFAULT_VOICE_PRESET = "onyx"
DEFAULT_MODEL = "gpt-4o-mini-tts"

MAX_TEXT_LENGTH = 600  # ORION alerts are short one-liners — bounds latency/cost

SynthStatus = Literal["OK", "NOT_CONFIGURED", "FAILED"]


# --------------------------------------------------------------------- settings
@dataclass(frozen=True)
class VoiceSettings:
    """Non-secret voice settings — the OpenAI API key lives in the secret store."""

    voice_preset: str = DEFAULT_VOICE_PRESET
    model: str = DEFAULT_MODEL


def load_voice_settings() -> VoiceSettings:
    if not VOICE_SETTINGS_PATH.exists():
        return VoiceSettings()
    try:
        raw = json.loads(VOICE_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("voice_settings.json unreadable, using defaults: %s", exc)
        return VoiceSettings()
    preset = str(raw.get("voice_preset", DEFAULT_VOICE_PRESET))
    if preset not in VOICE_PRESETS:
        preset = DEFAULT_VOICE_PRESET
    return VoiceSettings(voice_preset=preset, model=str(raw.get("model", DEFAULT_MODEL)))


def save_voice_settings(patch: dict[str, Any]) -> VoiceSettings:
    current = load_voice_settings()
    preset = str(patch.get("voice_preset", current.voice_preset))
    if preset not in VOICE_PRESETS:
        preset = current.voice_preset
    merged = VoiceSettings(voice_preset=preset, model=str(patch.get("model", current.model)))
    VOICE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOICE_SETTINGS_PATH.write_text(
        json.dumps({"voice_preset": merged.voice_preset, "model": merged.model}, indent=2),
        encoding="utf-8",
    )
    return merged


# ----------------------------------------------------------------------- result
@dataclass(frozen=True)
class VoiceSynthResult:
    status: SynthStatus
    detail: str
    audio: bytes | None = None
    content_type: str = "audio/mpeg"


# ------------------------------------------------------------------------ client
class VoiceClient:
    """Synthesizes ORION alert text via OpenAI TTS using the securely stored
    API key. Never raises on a network/API failure — reports FAILED instead,
    so the caller (the /api/v1/voice/speak router) can return a clean error
    and the frontend can fall back to the browser voice without a glitch."""

    def __init__(self, settings: VoiceSettings | None = None) -> None:
        self.settings = settings or load_voice_settings()

    def synthesize(self, text: str) -> VoiceSynthResult:
        api_key = get_secret_store().get_raw_secret(SecretType.OPENAI_API_KEY)
        if not api_key:
            return VoiceSynthResult("NOT_CONFIGURED", "OpenAI API key not configured — using browser voice")

        clipped = text[:MAX_TEXT_LENGTH]
        try:
            import httpx

            resp = httpx.post(
                OPENAI_TTS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": self.settings.model,
                    "voice": self.settings.voice_preset,
                    "input": clipped,
                    "response_format": "mp3",
                },
                timeout=VOICE_SYNTH_TIMEOUT_S,
            )
            if resp.status_code < 300:
                return VoiceSynthResult("OK", "synthesized", audio=resp.content)
            return VoiceSynthResult("FAILED", f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:  # noqa: BLE001 — outbound network call, report don't crash
            logger.error("voice synth failed: %s", exc)
            return VoiceSynthResult("FAILED", str(exc)[:300])
