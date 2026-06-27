"""Shared test fixtures.

These build a fully real stack that needs no external services:
  - SQLite (in-memory) for the structured store, via the real ORM + repos.
  - Qdrant in LOCAL in-memory mode (QdrantClient(":memory:")) — real vector
    search, no Docker.
  - A real (deterministic, feature-hashing) embedder so torch isn't required.

Nothing here is a mock that returns canned data: every store performs real
reads/writes and real vector similarity. Only the heavyweight neural embedder
and the paid LLM are substituted (the embedder by a real hashing embedder; the
LLM is exercised separately via reasoner unit tests / overridden in API tests).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).parent))  # make _embed importable

from _embed import DIM, HashingEmbedder  # noqa: E402

from engram.storage.orm import Base, Tenant  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
TEST_API_KEY = "test-key-123"
TEST_NETWORK = "test-net"


@pytest.fixture
def engine():
    # StaticPool + a single shared connection so every session sees the SAME
    # in-memory database (default sqlite:// gives each connection its own DB).
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def qdrant():
    client = QdrantClient(":memory:")
    client.create_collection(
        "test_incidents", vectors_config=qm.VectorParams(size=DIM, distance=qm.Distance.COSINE)
    )
    return client


@pytest.fixture
def embedder():
    return HashingEmbedder()


@pytest.fixture
def seeded_tenant(session_factory):
    s = session_factory()
    s.add(Tenant(api_key=TEST_API_KEY, network_id=TEST_NETWORK, name="test",
                 created_at=datetime.now(timezone.utc)))
    s.commit()
    s.close()
    return TEST_API_KEY, TEST_NETWORK


@pytest.fixture
def client(session_factory, qdrant, embedder, seeded_tenant):
    """FastAPI TestClient with all external deps overridden to the real test stack."""
    from fastapi.testclient import TestClient

    from engram.api import deps
    from engram.main import create_app
    from engram.storage.incident_repo import IncidentRepo
    from engram.storage.vector_store import VectorStore

    app = create_app()
    vs = VectorStore(client=qdrant, collection="test_incidents")

    def _db_session():
        s = session_factory()
        try:
            yield s
            s.commit()
        finally:
            s.close()

    # Override only the leaf deps; the real incident_repo/current_network_id will
    # consume the overridden db_session, keeping one shared session per request.
    app.dependency_overrides[deps.db_session] = _db_session
    app.dependency_overrides[deps.vector_store] = lambda: vs
    app.dependency_overrides[deps.embedder] = lambda: embedder
    _ = IncidentRepo  # imported for type clarity / potential direct use
    return TestClient(app)


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()
