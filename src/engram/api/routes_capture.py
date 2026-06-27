"""Live-capture + identity endpoints used by the web dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from engram.api.deps import current_network_id, embedder, incident_repo, vector_store
from engram.capture.devnet import DEVNET_DEFAULTS, run_devnet_capture
from engram.domain.enums import Protocol
from engram.embedding.embedder import Embedder
from engram.ingest.pipeline import ingest_incident
from engram.storage.incident_repo import IncidentRepo
from engram.storage.vector_store import VectorStore

router = APIRouter(tags=["capture"])


@router.get("/whoami")
def whoami(network_id: str = Depends(current_network_id)) -> dict:
    """Return the tenant (network) the API key belongs to — shown in the dashboard."""
    return {"network_id": network_id}


class DevNetCaptureRequest(BaseModel):
    host: str | None = None
    user: str | None = None
    password: str | None = None
    protocols: list[str] = ["BGP"]


class CaptureResponse(BaseModel):
    ok: bool
    incident_id: str | None = None
    device: str | None = None
    commands: int = 0
    title: str | None = None
    error: str | None = None
    sandbox: str | None = None


@router.post("/capture/devnet", response_model=CaptureResponse)
def capture_devnet(
    req: DevNetCaptureRequest,
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
    vs: VectorStore = Depends(vector_store),
    emb: Embedder = Depends(embedder),
) -> CaptureResponse:
    """Pull REAL output from a Cisco DevNet IOS XE device and store it as an incident."""
    host = req.host or DEVNET_DEFAULTS["host"]
    try:
        protocols = [Protocol(p.upper()) for p in req.protocols if p.upper() in Protocol.__members__]
        inc = run_devnet_capture(
            network_id=network_id, host=req.host, user=req.user, password=req.password,
            protocols=protocols or [Protocol.BGP],
        )
        ingest_incident(inc, repo=repo, vector_store=vs, embedder=emb)
        return CaptureResponse(
            ok=True, incident_id=str(inc.id),
            device=inc.context.devices[0] if inc.context.devices else None,
            commands=len(inc.investigation), title=inc.title, sandbox=host,
        )
    except Exception as e:  # noqa: BLE001
        return CaptureResponse(ok=False, error=f"{type(e).__name__}: {e}", sandbox=host)
