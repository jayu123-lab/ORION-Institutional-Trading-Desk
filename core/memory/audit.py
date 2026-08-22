"""Append-only audit helpers (spec §27). Never mutate or delete past records."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from core.memory.models import AuditLog

MODEL_VERSION = "0.1.0"


def audit(
    session: Session,
    actor: str,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=detail or {},
            model_version=MODEL_VERSION,
        )
    )
