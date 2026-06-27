"""API dependencies: DB session + API-key auth that resolves the tenant.

Auth model: the client sends `X-API-Key`. We look it up in the `tenants` table
and inject the resolved `network_id` into the handler. Every handler is therefore
tenant-scoped by construction — a handler cannot act on a tenant the caller is
not authenticated for, because the network_id comes from the key, not the body.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from engram.embedding.embedder import Embedder, get_embedder
from engram.storage.db import get_session
from engram.storage.incident_repo import IncidentRepo
from engram.storage.tenant_repo import TenantRepo
from engram.storage.vector_store import VectorStore


def db_session() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_network_id(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: Session = Depends(db_session),
) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header"
        )
    network_id = TenantRepo(session).resolve(x_api_key)
    if not network_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown API key"
        )
    return network_id


def incident_repo(session: Session = Depends(db_session)) -> IncidentRepo:
    return IncidentRepo(session)


def vector_store() -> VectorStore:
    return VectorStore()


def embedder() -> Embedder:
    return get_embedder()
