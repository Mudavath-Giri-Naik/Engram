"""Filter-then-rank: tenant isolation, structured-filter relaxation, FAILED/stale flags."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from engram.domain.enums import Layer, Outcome, Protocol, Scope, Severity
from engram.domain.models import Context, FaultQuery, Incident, OutcomeRecord, Resolution, Symptom
from engram.ingest.pipeline import ingest_incident
from engram.retrieval.hybrid import HybridRetriever
from engram.storage.incident_repo import IncidentRepo
from engram.storage.vector_store import VectorStore


def _mk(net, title, desc, protos, layer, devs, sig, outcome, topo="topo-v1", occurred=None):
    return Incident(
        network_id=net,
        title=title,
        occurred_at=occurred or datetime.now(timezone.utc),
        symptom=Symptom(description=desc, protocols=protos, affected_layer=layer, signature=sig,
                        severity=Severity.SEV2, scope=Scope.LINK),
        context=Context(devices=devs, topology_hash=topo),
        resolution=Resolution(root_cause="rc", fix_description="fix"),
        outcome=OutcomeRecord(status=outcome, verified=True),
    )


def _retriever(session_factory, qdrant, embedder):
    repo = IncidentRepo(session_factory())
    vs = VectorStore(client=qdrant, collection="test_incidents")

    def ingest(inc):
        return ingest_incident(inc, repo=repo, vector_store=vs, embedder=embedder)

    return HybridRetriever(repo, vs, embedder), ingest


def test_filter_then_rank_and_failed_stale_flags(session_factory, qdrant, embedder):
    ret, ingest = _retriever(session_factory, qdrant, embedder)
    now = datetime.now(timezone.utc)
    a1 = ingest(_mk("netA", "#47 BGP down R3", "BGP neighbor to upstream down on R3",
                    [Protocol.BGP], Layer.L3, ["R3", "R1"], "BGP_NEIGHBOR_DOWN", Outcome.RESOLVED))
    ingest(_mk("netA", "MTU mismatch", "OSPF stuck mtu mismatch handoff",
               [Protocol.OSPF, Protocol.MTU], Layer.L3, ["R2"], "MTU_MISMATCH", Outcome.RESOLVED))
    a3 = ingest(_mk("netA", "old failed BGP", "BGP neighbor down tried clear FAILED",
                    [Protocol.BGP], Layer.L3, ["R4"], "BGP_NEIGHBOR_DOWN", Outcome.FAILED,
                    topo="topo-OLD", occurred=now - timedelta(days=400)))

    q = FaultQuery(network_id="netA",
                   description="BGP session to upstream flapping on R3, as-path looks different",
                   protocols=[Protocol.BGP], affected_layer=Layer.L3, devices=["R3"],
                   current_topology_hash="topo-v1")
    res = ret.retrieve(q, k=3)
    assert res, "expected non-empty retrieval"
    # the fresh, device-overlapping BGP incident ranks first
    assert res[0].incident.id == a1.id
    # FAILED + stale incident carries the flags
    failed = [r for r in res if r.incident.id == a3.id]
    assert failed and "FAILED" in (failed[0].outcome_flag or "")
    assert failed[0].staleness["stale"] and failed[0].staleness["topology_changed"]


def test_tenant_isolation(session_factory, qdrant, embedder):
    ret, ingest = _retriever(session_factory, qdrant, embedder)
    ingest(_mk("netA", "A bgp", "BGP neighbor down netA", [Protocol.BGP], Layer.L3, ["R3"],
               "BGP_NEIGHBOR_DOWN", Outcome.RESOLVED))
    ingest(_mk("netB", "B bgp", "BGP neighbor down netB", [Protocol.BGP], Layer.L3, ["R9"],
               "BGP_NEIGHBOR_DOWN", Outcome.RESOLVED))
    res = ret.retrieve(FaultQuery(network_id="netB", description="bgp down", protocols=[Protocol.BGP]), k=5)
    assert res and all(r.incident.network_id == "netB" for r in res)


def test_structured_filter_relaxes_when_too_few(session_factory, qdrant, embedder):
    ret, ingest = _retriever(session_factory, qdrant, embedder)
    # only BGP incidents exist; a DNS-filtered query would match nothing structurally
    ingest(_mk("netA", "bgp1", "BGP neighbor down", [Protocol.BGP], Layer.L3, ["R3"],
               "BGP_NEIGHBOR_DOWN", Outcome.RESOLVED))
    ingest(_mk("netA", "bgp2", "BGP neighbor flap", [Protocol.BGP], Layer.L3, ["R2"],
               "BGP_NEIGHBOR_DOWN", Outcome.RESOLVED))
    q = FaultQuery(network_id="netA", description="dns resolution failing", protocols=[Protocol.DNS],
                   affected_layer=Layer.L7, signature="DNS_RESOLUTION_FAIL")
    res = ret.retrieve(q, k=3)
    # relaxation to tenant-only means we still get memory back, never empty
    assert len(res) > 0
