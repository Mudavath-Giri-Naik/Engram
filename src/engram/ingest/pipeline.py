"""Ingest pipeline: incident -> signature -> summary -> embed -> dual write.

Writes the structured incident to Postgres AND its vector to Qdrant, both
tenant-scoped. If the caller did not supply a signature or embedding_text, we
derive them here so ingestion is robust to partial drafts (e.g. from capture).
"""

from __future__ import annotations

from engram.domain.models import Incident
from engram.domain.signature import derive_signature
from engram.domain.summary import build_embedding_text
from engram.embedding.embedder import Embedder, get_embedder
from engram.storage.incident_repo import IncidentRepo
from engram.storage.vector_store import VectorStore


def enrich(inc: Incident, embedder: Embedder | None = None) -> Incident:
    """Fill in derived fields (signature, embedding_text, embedding_model)."""
    embedder = embedder or get_embedder()

    if not inc.symptom.signature:
        extra = " ".join(s.raw_output for s in inc.investigation[:6])
        inc.symptom.signature = derive_signature(
            inc.symptom.description, protocols=inc.symptom.protocols, extra_text=extra
        )
    if not inc.embedding_text:
        inc.embedding_text = build_embedding_text(inc)
    inc.embedding_model = embedder.model_name
    return inc


def ingest_incident(
    inc: Incident,
    *,
    repo: IncidentRepo,
    vector_store: VectorStore,
    embedder: Embedder | None = None,
) -> Incident:
    """Enrich, embed, and dual-write one incident. Returns the stored incident."""
    embedder = embedder or get_embedder()
    inc = enrich(inc, embedder)

    vector = embedder.embed_document(inc.embedding_text)

    # Postgres (source of truth) first, then Qdrant.
    repo.upsert(inc)
    vector_store.upsert(inc, vector)
    return inc
