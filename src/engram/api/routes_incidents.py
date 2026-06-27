"""Incident endpoints — all tenant-scoped via the resolved network_id."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from engram.api.deps import current_network_id, embedder, incident_repo, vector_store
from engram.domain.enums import Layer, Outcome, Protocol
from engram.domain.models import Incident, OutcomeRecord
from engram.embedding.embedder import Embedder
from engram.ingest.pipeline import ingest_incident
from engram.storage.incident_repo import IncidentRepo
from engram.storage.vector_store import VectorStore

router = APIRouter(tags=["incidents"])


class IncidentCreateResponse(BaseModel):
    id: str


@router.post("/incidents", response_model=IncidentCreateResponse, status_code=201)
def create_incident(
    incident: Incident,
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
    vs: VectorStore = Depends(vector_store),
    emb: Embedder = Depends(embedder),
) -> IncidentCreateResponse:
    # Force the tenant from auth — never trust network_id in the body.
    incident.network_id = network_id
    stored = ingest_incident(incident, repo=repo, vector_store=vs, embedder=emb)
    return IncidentCreateResponse(id=str(stored.id))


@router.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(
    incident_id: str,
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
) -> Incident:
    inc = repo.get(network_id, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc


@router.get("/incidents", response_model=list[Incident])
def list_incidents(
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
    protocol: Protocol | None = None,
    layer: Layer | None = None,
    outcome: Outcome | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Incident]:
    return repo.list_incidents(
        network_id,
        protocol=protocol.value if protocol else None,
        layer=layer.value if layer else None,
        outcome=outcome,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )


@router.patch("/incidents/{incident_id}/outcome", response_model=Incident)
def update_outcome(
    incident_id: str,
    outcome: OutcomeRecord,
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
    vs: VectorStore = Depends(vector_store),
    emb: Embedder = Depends(embedder),
) -> Incident:
    """Record the verified outcome of a fix.

    This is how a FAILED fix becomes first-class memory: an engineer marks the
    prior fix FAILED here, and future retrievals will surface the warning.
    """
    inc = repo.update_outcome(network_id, incident_id, outcome)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    # Keep the Qdrant payload's outcome_status in sync for retrieval flags.
    vs.upsert(inc, emb.embed_document(inc.embedding_text))
    return inc


@router.get("/stats")
def stats(
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
) -> dict:
    return repo.stats(network_id)
