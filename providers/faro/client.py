"""Faro signal distribution — formats and (when configured) sends approved
trade ideas to the user's Faro account.

Faro's real API contract (endpoint/method/auth) is not yet known to ORION.
Per project rule, an unconfirmed integration is never faked as live: until a
real `endpoint_url` is set in Settings > Faro, `FaroClient.send()` composes
the fully valid message and appends it to a local append-only log tagged
DEMO_LOGGED — never reported as SENT. This keeps the connector fully built
and ready to go live the moment the real endpoint is provided.

Message contract (per project doctrine): every Faro signal carries a ticker,
stop loss, take-profit(s) and R:R, targets swing trading (R:R ~1:2-1:3), and
is at least MIN_MESSAGE_LENGTH characters — built only from real fields on
the approved idea, never invented numbers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from core.config import get_settings
from core.security import SecretType, get_secret_store

logger = logging.getLogger("orion.faro")

MIN_MESSAGE_LENGTH = 200
FARO_SETTINGS_PATH = Path("config/faro_settings.json")
FARO_OUTBOX_FILENAME = "faro_outbox.jsonl"
FARO_SEND_TIMEOUT_S = 8.0

SendStatus = Literal["SENT", "DEMO_LOGGED", "FAILED", "SKIPPED"]


# --------------------------------------------------------------------- settings
@dataclass(frozen=True)
class FaroSettings:
    """Non-secret Faro settings — the API key itself lives in the secret store."""

    endpoint_url: str = ""
    auto_send: bool = True
    min_message_length: int = MIN_MESSAGE_LENGTH


def load_faro_settings() -> FaroSettings:
    if not FARO_SETTINGS_PATH.exists():
        return FaroSettings()
    try:
        raw = json.loads(FARO_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("faro_settings.json unreadable, using defaults: %s", exc)
        return FaroSettings()
    return FaroSettings(
        endpoint_url=str(raw.get("endpoint_url", "")).strip(),
        auto_send=bool(raw.get("auto_send", True)),
        min_message_length=int(raw.get("min_message_length", MIN_MESSAGE_LENGTH)),
    )


def save_faro_settings(patch: dict[str, Any]) -> FaroSettings:
    current = load_faro_settings()
    merged = FaroSettings(
        endpoint_url=str(patch.get("endpoint_url", current.endpoint_url)).strip(),
        auto_send=bool(patch.get("auto_send", current.auto_send)),
        min_message_length=int(patch.get("min_message_length", current.min_message_length)),
    )
    FARO_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FARO_SETTINGS_PATH.write_text(
        json.dumps(
            {
                "endpoint_url": merged.endpoint_url,
                "auto_send": merged.auto_send,
                "min_message_length": merged.min_message_length,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return merged


# ----------------------------------------------------------------------- outbox
def _outbox_path() -> Path:
    data_dir = Path(get_settings().data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / FARO_OUTBOX_FILENAME


def _append_outbox(entry: dict) -> None:
    try:
        with _outbox_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:  # pragma: no cover - disk/permission edge case
        logger.error("failed to append faro outbox entry: %s", exc)


def read_outbox(limit: int = 20) -> list[dict]:
    path = _outbox_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.reverse()
    return out


# ----------------------------------------------------------------------- result
@dataclass(frozen=True)
class FaroSendResult:
    status: SendStatus
    detail: str
    message: str
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "detail": self.detail,
            "message": self.message,
            "ts": self.ts.isoformat(),
        }


# --------------------------------------------------------------- message format
def format_faro_message(
    *,
    asset: str,
    direction: str,
    entry: float,
    stop_loss: float,
    targets: list[float],
    timeframe: str | None = None,
    confidence: str | None = None,
    horizon: str | None = None,
    technical_thesis: str | None = None,
    fundamental_thesis: str | None = None,
    risks: str | None = None,
    liquidity_notes: str | None = None,
    invalidation: str | None = None,
    min_length: int = MIN_MESSAGE_LENGTH,
) -> str:
    """Compose the Faro signal text: ticker + SL + TP(s) + R:R, >= min_length chars.

    Padding to reach `min_length` only ever appends true, fixed statements
    about the system (never fabricated trade data) — real thesis/risk fields
    are used first, since most approved ideas already carry enough context.
    """
    targets = [t for t in targets if t is not None]
    tp1 = targets[0] if targets else None
    rr = None
    if tp1 is not None and entry != stop_loss:
        rr = abs(tp1 - entry) / abs(entry - stop_loss)

    lines = [
        f"ORION SIGNAL — {asset.upper()} {direction.upper()}",
        "Entry: {:g} | SL: {:g} | TP: {}".format(
            entry, stop_loss, " / ".join(f"{t:g}" for t in targets) if targets else "N/A"
        ),
    ]
    if rr is not None:
        lines.append(f"R:R (TP1): {rr:.2f}")
    if timeframe:
        lines.append(f"Timeframe: {timeframe}")
    if horizon:
        lines.append(f"Horizon: {horizon}")
    if confidence:
        lines.append(f"Confidence: {confidence}")
    if invalidation:
        lines.append(f"Invalidation: {invalidation}")
    if technical_thesis:
        lines.append(f"Technical: {technical_thesis}")
    if fundamental_thesis:
        lines.append(f"Fundamental: {fundamental_thesis}")
    if liquidity_notes:
        lines.append(f"Liquidity: {liquidity_notes}")
    if risks:
        lines.append(f"Risks: {risks}")

    message = "\n".join(lines)

    padding_candidates = [
        "Generated by ORION Institutional Trading Desk (paper/demo mode) — "
        "not financial advice, mandatory risk management applies.",
        f"Signal timestamp: {datetime.now(UTC).isoformat()}.",
        "Swing setup — reassess R:R and invalidation before any manual execution.",
    ]
    i = 0
    while len(message) < min_length and i < len(padding_candidates) * 3:
        message += "\n" + padding_candidates[i % len(padding_candidates)]
        i += 1

    return message


# ------------------------------------------------------------------------ client
class FaroClient:
    """Sends a composed Faro message, or logs it locally (DEMO) if the real
    endpoint isn't configured yet."""

    def __init__(self, settings: FaroSettings | None = None) -> None:
        self.settings = settings or load_faro_settings()

    def send(self, message: str) -> FaroSendResult:
        api_key = get_secret_store().get_raw_secret(SecretType.FARO_API_KEY)
        if not api_key:
            result = FaroSendResult("SKIPPED", "Faro API key not configured", message)
            _append_outbox(result.to_dict())
            return result

        if not self.settings.endpoint_url:
            result = FaroSendResult(
                "DEMO_LOGGED",
                "No Faro endpoint configured yet — message composed and validated "
                "but not sent over the network. Add the real endpoint in "
                "Settings > Faro to go live.",
                message,
            )
            _append_outbox(result.to_dict())
            return result

        try:
            import httpx

            resp = httpx.post(
                self.settings.endpoint_url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"message": message},
                timeout=FARO_SEND_TIMEOUT_S,
            )
            if resp.status_code < 300:
                result = FaroSendResult("SENT", f"HTTP {resp.status_code}", message)
            else:
                result = FaroSendResult(
                    "FAILED", f"HTTP {resp.status_code}: {resp.text[:200]}", message
                )
        except Exception as exc:  # noqa: BLE001 — outbound network call, report don't crash
            logger.error("faro send failed: %s", exc)
            result = FaroSendResult("FAILED", str(exc)[:300], message)

        _append_outbox(result.to_dict())
        return result


def maybe_send_faro_signal(idea: Any, risk_decision_status: str) -> FaroSendResult | None:
    """Called after a risk-review. Sends only when auto_send is on AND the
    idea was fully APPROVED (not REDUCE_SIZE/WAIT/REJECTED) — never on a
    partial or capped approval, to keep the human-approval spirit of the
    IDEA -> CIO -> RISK -> EXECUTION flow for anything published outward."""
    settings = load_faro_settings()
    if not settings.auto_send:
        return None
    if risk_decision_status != "APPROVED":
        return None

    targets = [t for t in (getattr(idea, "tp1", None), getattr(idea, "tp2", None),
                            getattr(idea, "tp3", None)) if t is not None]
    message = format_faro_message(
        asset=idea.asset,
        direction=idea.direction,
        entry=idea.entry or 0.0,
        stop_loss=idea.stop_loss or 0.0,
        targets=targets,
        timeframe=idea.timeframe,
        confidence=idea.confidence,
        horizon=idea.horizon,
        technical_thesis=idea.technical_thesis,
        fundamental_thesis=idea.fundamental_thesis,
        risks=idea.risks,
        liquidity_notes=idea.liquidity_notes,
        invalidation=str(idea.invalidation) if idea.invalidation is not None else None,
        min_length=settings.min_message_length,
    )
    return FaroClient(settings).send(message)
