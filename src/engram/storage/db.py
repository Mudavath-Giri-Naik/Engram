"""SQLAlchemy engine + session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from engram.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    s = get_settings()
    # For local SQLite dev, create the parent directory if it doesn't exist
    # (SQLite will not create missing folders and errors with "unable to open
    # database file"). No-op for server databases like Postgres.
    if s.database_url.startswith("sqlite"):
        from pathlib import Path

        path_part = s.database_url.split("///", 1)[-1]
        if path_part and path_part != ":memory:":
            Path(path_part).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    return create_engine(s.database_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context manager."""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    """FastAPI-friendly session (caller is responsible for closing)."""
    return _session_factory()()
