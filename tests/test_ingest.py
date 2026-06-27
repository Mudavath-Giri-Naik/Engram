"""incident -> summary -> embed -> store round-trips (Postgres-shape + real Qdrant)."""

from __future__ import annotations

from engram.domain.enums import Layer, Outcome, Protocol, Scope, Severity
from engram.domain.models import Context, Incident, InvestigationStep, OutcomeRecord, Resolution, Symptom
from engram.ingest.pipeline import ingest_incident
from engram.storage.incident_repo import IncidentRepo
from engram.storage.vector_store import VectorStore
from tests.conftest import fixture_text


def _bgp_incident() -> Incident:
    raw = fixture_text("bgp_neighbor_down_show_ip_bgp_summary.txt")
    return Incident(
        network_id="netA",
        title="R1 BGP down",
        symptom=Symptom(
            description="BGP neighbor 10.0.13.1 to R1 stuck Active",
            protocols=[Protocol.BGP],
            affected_layer=Layer.L3,
            scope=Scope.LINK,
            severity=Severity.SEV2,
        ),
        context=Context(devices=["R3", "R1"], topology_hash="topo-v1"),
        investigation=[InvestigationStep(device="R3", command="show ip bgp summary", raw_output=raw)],
        resolution=Resolution(root_cause="typo", fix_description="fix neighbor addr"),
        outcome=OutcomeRecord(status=Outcome.RESOLVED, mttr_seconds=900, verified=True),
    )


def test_ingest_roundtrip(session_factory, qdrant, embedder):
    repo = IncidentRepo(session_factory())
    vs = VectorStore(client=qdrant, collection="test_incidents")
    inc = ingest_incident(_bgp_incident(), repo=repo, vector_store=vs, embedder=embedder)

    # signature + embedding_text auto-derived
    assert inc.symptom.signature == "BGP_NEIGHBOR_DOWN"
    assert inc.embedding_text and inc.embedding_model == embedder.model_name

    # Postgres side
    got = repo.get("netA", str(inc.id))
    assert got is not None and got.title == "R1 BGP down"
    assert got.investigation[0].raw_output  # real captured output retained

    # Qdrant side: searchable, tenant scoped
    vec = embedder.embed_query("bgp neighbor down on R1")
    hits = vs.search(network_id="netA", vector=vec, limit=5, protocols=["BGP"], layer="L3")
    assert hits and hits[0][0] == str(inc.id)


def test_ingest_tenant_isolation_in_vectorstore(session_factory, qdrant, embedder):
    repo = IncidentRepo(session_factory())
    vs = VectorStore(client=qdrant, collection="test_incidents")
    ingest_incident(_bgp_incident(), repo=repo, vector_store=vs, embedder=embedder)
    # another tenant searching must see nothing
    hits = vs.search(network_id="other", vector=embedder.embed_query("bgp"), limit=5)
    assert hits == []
