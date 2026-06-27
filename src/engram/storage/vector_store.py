"""Qdrant wrapper — vector store with tenant + structured pre-filtering.

The payload stored alongside each vector carries the structured fields used for
*filter-then-rank* retrieval: network_id (tenant), protocols, layer, signature,
devices, severity, outcome, topology_hash, occurred_at. The tenant filter is a
hard `must`; the structured filter is a soft, relaxable candidate filter applied
by the HybridRetriever.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from engram.config import get_settings
from engram.domain.models import Incident


@lru_cache(maxsize=1)
def get_qdrant() -> QdrantClient:
    """Qdrant client. QDRANT_URL selects the mode:
      - http(s)://host:port  -> remote server (production / docker compose)
      - ":memory:"           -> embedded in-memory (single process; not shared)
      - "local" or a path    -> embedded ON-DISK (no server, no Docker needed)
    On-disk embedded mode lets the whole stack run on a laptop with no Docker.
    (Embedded mode is opened by one process at a time.)
    """
    s = get_settings()
    url = (s.qdrant_url or "").strip()
    if url.startswith(("http://", "https://")):
        # check_compatibility=False silences the noisy client/server version warning.
        return QdrantClient(url=url, api_key=s.qdrant_api_key or None, check_compatibility=False)
    if url == ":memory:":
        return QdrantClient(location=":memory:")
    path = "./.engram/qdrant" if url in ("", "local") else url
    return QdrantClient(path=path)


def ensure_collection(dim: int | None = None, client: QdrantClient | None = None) -> None:
    """Create the collection if missing, with payload indexes for fast filtering."""
    s = get_settings()
    client = client or get_qdrant()
    dim = dim or s.embedding_dim
    if not client.collection_exists(s.qdrant_collection):
        client.create_collection(
            collection_name=s.qdrant_collection,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )
    for field in ("network_id", "protocols", "affected_layer", "signature", "devices", "outcome_status"):
        try:
            client.create_payload_index(
                s.qdrant_collection, field_name=field, field_schema=qm.PayloadSchemaType.KEYWORD
            )
        except Exception:
            pass  # already exists


def _payload(inc: Incident) -> dict[str, Any]:
    return {
        "network_id": inc.network_id,
        "protocols": [p.value for p in inc.symptom.protocols],
        "affected_layer": inc.symptom.affected_layer.value,
        "signature": inc.symptom.signature,
        "scope": inc.symptom.scope.value,
        "severity": inc.symptom.severity.value,
        "devices": inc.context.devices,
        "outcome_status": inc.outcome.status.value,
        "topology_hash": inc.context.topology_hash,
        "occurred_at": inc.occurred_at.isoformat(),
        "title": inc.title,
    }


class VectorStore:
    def __init__(self, client: QdrantClient | None = None, collection: str | None = None) -> None:
        self.s = get_settings()
        # Allow dependency injection (e.g. an in-memory QdrantClient(":memory:")
        # in tests). Defaults to the process-wide configured client.
        self.client = client or get_qdrant()
        self.collection = collection or self.s.qdrant_collection

    def upsert(self, inc: Incident, vector: list[float]) -> None:
        self.client.upsert(
            collection_name=self.collection,
            points=[qm.PointStruct(id=str(inc.id), vector=vector, payload=_payload(inc))],
        )

    def delete(self, incident_id: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=qm.PointIdsList(points=[incident_id]),
        )

    def search(
        self,
        *,
        network_id: str,
        vector: list[float],
        limit: int = 20,
        protocols: list[str] | None = None,
        layer: str | None = None,
        signature: str | None = None,
        structured: bool = True,
    ) -> list[tuple[str, float, dict]]:
        """Tenant-scoped vector search.

        `network_id` is always a hard `must`. When `structured=True` and any of
        protocols/layer/signature are supplied, they become a candidate filter
        (`should`, requiring >=1 match). The HybridRetriever relaxes to
        tenant-only when this yields too few candidates.
        """
        must: list[qm.Condition] = [
            qm.FieldCondition(key="network_id", match=qm.MatchValue(value=network_id))
        ]
        query_filter = qm.Filter(must=must)

        if structured:
            should: list[qm.Condition] = []
            for p in protocols or []:
                should.append(qm.FieldCondition(key="protocols", match=qm.MatchValue(value=p)))
            if layer:
                should.append(qm.FieldCondition(key="affected_layer", match=qm.MatchValue(value=layer)))
            if signature:
                should.append(qm.FieldCondition(key="signature", match=qm.MatchValue(value=signature)))
            if should:
                # must AND (>=1 should) — exactly the candidate semantics we want.
                query_filter = qm.Filter(must=must, should=should)

        res = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [(str(p.id), float(p.score), dict(p.payload or {})) for p in res.points]

    def count(self, network_id: str | None = None) -> int:
        flt = None
        if network_id:
            flt = qm.Filter(
                must=[qm.FieldCondition(key="network_id", match=qm.MatchValue(value=network_id))]
            )
        return self.client.count(self.collection, count_filter=flt).count
