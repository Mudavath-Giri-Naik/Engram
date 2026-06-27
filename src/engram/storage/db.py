"""SQLAlchemy engine + session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from engram.config import get_settings


def sqlalchemy_url() -> str:
    """Normalize the configured DATABASE_URL into a SQLAlchemy URL.

    Managed hosts (Render/Railway/Heroku) hand out `postgres://...` or
    `postgresql://...` URLs that default to the (uninstalled) psycopg2 driver.
    We pin the psycopg v3 driver so those URLs work unchanged.
    """
    url = get_settings().database_url
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = sqlalchemy_url()
    # For local SQLite dev, create the parent directory if missing (SQLite won't).
    if url.startswith("sqlite"):
        path_part = url.split("///", 1)[-1]
        if path_part and path_part != ":memory:":
            Path(path_part).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
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
    return _session_factory()()
