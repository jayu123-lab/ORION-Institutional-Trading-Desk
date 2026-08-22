"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from core.memory.database import get_session_factory


def get_db() -> Iterator[Session]:
    factory = get_session_factory()
    with factory() as session:
        yield session
