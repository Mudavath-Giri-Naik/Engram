"""The main AIOps integration endpoint: POST /v1/query.

Runs the HybridRetriever then the comparative reasoner and returns both the
retrieved past incidents (with scores + match explanations) and the LLM's
ReasoningResult. Reasoning failures (e.g. unconfigured LLM) surface as a clear
503 — we never fabricate a reasoning result.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from engram.api.deps import current_network_id, embedder, incident_repo, vector_store
from engram.domain.models import FaultQuery, ReasoningResult, RetrievedIncident
from engram.embedding.embedder import Embedder
from engram.reasoning.reasoner import ReasoningError, reason
from engram.retrieval.hybrid import HybridRetriever
from engram.storage.incident_repo import IncidentRepo
from engram.storage.vector_store import VectorStore

router = APIRouter(tags=["query"])


class QueryResponse(BaseModel):
    retrieved: list[RetrievedIncident]
    reasoning: ReasoningResult | None
    reasoning_error: str | None = None


@router.post("/query", response_model=QueryResponse)
def query(
    fault: FaultQuery,
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
    vs: VectorStore = Depends(vector_store),
    emb: Embedder = Depends(embedder),
    reason_enabled: bool = True,
) -> QueryResponse:
    # Tenant from auth wins over anything in the body.
    fault.network_id = network_id

    retriever = HybridRetriever(repo, vs, emb)
    retrieved = retriever.retrieve(fault, k=3)

    if not retrieved:
        return QueryResponse(
            retrieved=[],
            reasoning=None,
            reasoning_error="No prior incidents in memory for this network yet.",
        )

    if not reason_enabled:
        return QueryResponse(retrieved=retrieved, reasoning=None)

    try:
        result = reason(fault, retrieved)
        return QueryResponse(retrieved=retrieved, reasoning=result)
    except ReasoningError as e:
        # Surface clearly; retrieval still returned useful memory.
        return QueryResponse(retrieved=retrieved, reasoning=None, reasoning_error=str(e))
    except Exception as e:  # noqa: BLE001
        # Surface the real LLM/provider error (don't hide it behind a dead 503).
        # Retrieval results are still returned and useful.
        return QueryResponse(
            retrieved=retrieved,
            reasoning=None,
            reasoning_error=f"Reasoning failed: {type(e).__name__}: {e}",
        )
