"""Structured + final scoring math."""

from __future__ import annotations

from engram.config import get_settings
from engram.domain.enums import Layer, Protocol, Scope, Severity
from engram.domain.models import Context, FaultQuery, Incident, Symptom
from engram.retrieval.scoring import final_score, severity_proximity, structured_score


def _inc(**kw) -> Incident:
    sym = Symptom(
        description=kw.get("desc", "x"),
        protocols=kw.get("protocols", []),
        affected_layer=kw.get("layer", Layer.UNKNOWN),
        signature=kw.get("signature", ""),
        severity=kw.get("severity", Severity.SEV3),
        scope=Scope.LINK,
    )
    return Incident(network_id="n", symptom=sym, context=Context(devices=kw.get("devices", [])))


def test_full_structured_match_beats_partial():
    q = FaultQuery(
        network_id="n",
        description="bgp down on r3",
        protocols=[Protocol.BGP],
        affected_layer=Layer.L3,
        signature="BGP_NEIGHBOR_DOWN",
        devices=["R3"],
    )
    strong = _inc(protocols=[Protocol.BGP], layer=Layer.L3, signature="BGP_NEIGHBOR_DOWN", devices=["R3", "R1"])
    weak = _inc(protocols=[Protocol.OSPF], layer=Layer.L2, signature="OSPF_ADJ_DOWN", devices=["R9"])
    s_strong, bd = structured_score(q, strong)
    s_weak, _ = structured_score(q, weak)
    assert s_strong > s_weak
    assert bd["signature_match"] is True
    assert "BGP" in bd["protocol_overlap"]
    assert "r3" in bd["device_overlap"]


def test_severity_proximity_monotonic():
    assert severity_proximity(Severity.SEV1, Severity.SEV1) == 1.0
    assert severity_proximity(Severity.SEV1, Severity.SEV2) > severity_proximity(Severity.SEV1, Severity.SEV4)


def test_final_score_uses_config_weights():
    s = get_settings()
    fs = final_score(1.0, 0.0)
    assert abs(fs - s.retrieval_w_vector) < 1e-9
    fs2 = final_score(0.0, 1.0)
    assert abs(fs2 - s.retrieval_w_structured) < 1e-9


def test_structured_score_bounded():
    q = FaultQuery(network_id="n", description="x", protocols=[Protocol.BGP], affected_layer=Layer.L3,
                   signature="BGP_NEIGHBOR_DOWN", devices=["R3"], severity=Severity.SEV2)
    inc = _inc(protocols=[Protocol.BGP], layer=Layer.L3, signature="BGP_NEIGHBOR_DOWN",
               devices=["R3"], severity=Severity.SEV2)
    score, _ = structured_score(q, inc)
    assert 0.0 <= score <= 1.0
