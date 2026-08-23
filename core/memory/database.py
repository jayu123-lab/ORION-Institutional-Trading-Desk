"""SQLAlchemy engine/session management. SQLite for dev, Postgres via DATABASE_URL."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings


def _ensure_sqlite_dir(url: str) -> None:
    if not url.startswith("sqlite"):
        return
    path = url.split("///", 1)[-1]
    parent = Path(path).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> Engine:
    url = os.environ.get("ORION_TEST_DATABASE_URL") or get_settings().database_url
    _ensure_sqlite_dir(url)
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        # WAL + busy timeout: the desk writes from several threads/tasks at once
        # (quote ingestion, debate persistence, CIO analyses) — without this,
        # concurrent commits raise "database is locked".
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        return engine
    return create_engine(url, **kwargs)


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    eng = engine or get_engine()
    return sessionmaker(bind=eng, expire_on_commit=False, future=True)


def init_db(engine: Engine | None = None) -> Engine:
    """Create all tables. Alembic owns migrations in production."""
    eng = engine or get_engine()
    from core.memory.models import Base  # local import to avoid cycle

    Base.metadata.create_all(eng)
    return eng
