"""Lab control + AI-agent endpoints — drive the real FRR routers from the UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from engram.api.deps import current_network_id, embedder, incident_repo, vector_store
from engram.capture import lab
from engram.capture.lab import LabError
from engram.domain.models import FaultQuery
from engram.embedding.embedder import Embedder
from engram.ingest.pipeline import ingest_incident
from engram.reasoning.reasoner import ReasoningError, reason
from engram.retrieval.hybrid import HybridRetriever
from engram.storage.incident_repo import IncidentRepo
from engram.storage.vector_store import VectorStore

router = APIRouter(tags=["lab"])


class CmdOutput(BaseModel):
    command: str
    output: str


class LabResponse(BaseModel):
    ok: bool
    bgp_up: bool | None = None
    incident_id: str | None = None
    title: str | None = None
    device: str | None = None
    signature: str | None = None
    outputs: list[CmdOutput] = []
    error: str | None = None


def _err(e: Exception) -> str:
    return str(e) if isinstance(e, LabError) else f"{type(e).__name__}: {e}"


def _outputs(inc) -> list[CmdOutput]:
    return [CmdOutput(command=s.command, output=s.raw_output) for s in inc.investigation]


@router.get("/lab/status", response_model=LabResponse)
def lab_status(network_id: str = Depends(current_network_id)) -> LabResponse:
    try:
        return LabResponse(ok=True, bgp_up=lab.status()["bgp_up"])
    except Exception as e:  # noqa: BLE001
        return LabResponse(ok=False, error=_err(e))


@router.post("/lab/break", response_model=LabResponse)
def lab_break(network_id: str = Depends(current_network_id)) -> LabResponse:
    try:
        lab.break_bgp()
        return LabResponse(ok=True, bgp_up=False)
    except Exception as e:  # noqa: BLE001
        return LabResponse(ok=False, error=_err(e))


@router.post("/lab/heal", response_model=LabResponse)
def lab_heal(network_id: str = Depends(current_network_id)) -> LabResponse:
    try:
        lab.heal_bgp()
        return LabResponse(ok=True, bgp_up=True)
    except Exception as e:  # noqa: BLE001
        return LabResponse(ok=False, error=_err(e))


@router.post("/lab/capture", response_model=LabResponse)
def lab_capture(
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
    vs: VectorStore = Depends(vector_store),
    emb: Embedder = Depends(embedder),
) -> LabResponse:
    """Pull live router output and store it as an incident — returns the REAL output."""
    try:
        inc = lab.capture(network_id)
        ingest_incident(inc, repo=repo, vector_store=vs, embedder=emb)
        return LabResponse(
            ok=True, incident_id=str(inc.id), title=inc.title, device=inc.context.devices[0],
            signature=inc.symptom.signature, outputs=_outputs(inc),
            bgp_up=(inc.outcome.status.value == "RESOLVED"),
        )
    except Exception as e:  # noqa: BLE001
        return LabResponse(ok=False, error=_err(e))


class AgentResponse(BaseModel):
    ok: bool
    bgp_up: bool | None = None
    incident_id: str | None = None
    title: str | None = None
    device: str | None = None
    signature: str | None = None
    outputs: list[CmdOutput] = []
    retrieved: list[dict] = []
    reasoning: dict | None = None
    reasoning_error: str | None = None
    error: str | None = None


@router.post("/lab/investigate", response_model=AgentResponse)
def lab_investigate(
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
    vs: VectorStore = Depends(vector_store),
    emb: Embedder = Depends(embedder),
) -> AgentResponse:
    """AI agent: look at the live device, compare to past memory, explain + recommend.

    Captures the current real state, searches this network's memory for similar PAST
    incidents, runs the LLM to explain in plain words, then records the new incident.
    """
    try:
        inc = lab.capture(network_id)  # build from live output (not yet stored)
        query = FaultQuery(
            network_id=network_id,
            description=inc.symptom.description,
            protocols=inc.symptom.protocols,
            affected_layer=inc.symptom.affected_layer,
            scope=inc.symptom.scope,
            devices=inc.context.devices,
            current_topology_hash=inc.context.topology_hash,
        )
        # search PAST memory first (so the agent compares to history, not itself)
        retrieved = HybridRetriever(repo, vs, emb).retrieve(query, k=3)

        reasoning_dict = None
        rerr = None
        try:
            if retrieved:
                reasoning_dict = reason(query, retrieved).model_dump()
            else:
                rerr = "No prior incidents to compare against yet — capture a few first."
        except ReasoningError as e:
            rerr = str(e)
        except Exception as e:  # noqa: BLE001
            rerr = f"{type(e).__name__}: {e}"

        # now record the live capture into memory
        ingest_incident(inc, repo=repo, vector_store=vs, embedder=emb)

        return AgentResponse(
            ok=True, incident_id=str(inc.id), title=inc.title, device=inc.context.devices[0],
            signature=inc.symptom.signature, outputs=_outputs(inc),
            bgp_up=(inc.outcome.status.value == "RESOLVED"),
            retrieved=[r.model_dump(mode="json") for r in retrieved],
            reasoning=reasoning_dict, reasoning_error=rerr,
        )
    except Exception as e:  # noqa: BLE001
        return AgentResponse(ok=False, error=_err(e))
