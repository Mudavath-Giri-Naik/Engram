"""API: auth (401 on bad key), tenant scoping, /v1/incidents and /v1/query."""

from __future__ import annotations

from tests.conftest import TEST_API_KEY, fixture_text

H = {"X-API-Key": TEST_API_KEY}


def _incident_body() -> dict:
    return {
        "network_id": "SHOULD_BE_OVERRIDDEN_BY_AUTH",
        "title": "#47 BGP down",
        "symptom": {
            "description": "BGP neighbor 10.0.13.1 to R1 stuck Active",
            "protocols": ["BGP"],
            "affected_layer": "L3",
            "scope": "LINK",
            "severity": "SEV2",
        },
        "context": {"devices": ["R3", "R1"], "topology_hash": "topo-v1"},
        "investigation": [
            {"device": "R3", "command": "show ip bgp summary",
             "raw_output": fixture_text("bgp_neighbor_down_show_ip_bgp_summary.txt")}
        ],
        "resolution": {"root_cause": "remote-as typo", "fix_description": "corrected remote-as"},
        "outcome": {"status": "RESOLVED", "verified": True, "mttr_seconds": 900},
    }


def test_auth_required(client):
    assert client.post("/v1/incidents", json={}).status_code == 401
    assert client.get("/v1/incidents", headers={"X-API-Key": "nope"}).status_code == 401


def test_create_get_list_and_tenant_forced(client):
    r = client.post("/v1/incidents", headers=H, json=_incident_body())
    assert r.status_code == 201
    iid = r.json()["id"]

    g = client.get(f"/v1/incidents/{iid}", headers=H)
    assert g.status_code == 200
    body = g.json()
    # tenant comes from the API key, never the request body
    assert body["network_id"] == "test-net"
    # signature auto-derived from real captured output
    assert body["symptom"]["signature"] == "BGP_NEIGHBOR_DOWN"

    assert len(client.get("/v1/incidents?protocol=BGP", headers=H).json()) == 1
    assert len(client.get("/v1/incidents?layer=L1", headers=H).json()) == 0


def test_patch_outcome_failed_is_first_class(client):
    iid = client.post("/v1/incidents", headers=H, json=_incident_body()).json()["id"]
    p = client.patch(f"/v1/incidents/{iid}/outcome", headers=H,
                     json={"status": "FAILED", "verification_method": "ping", "verified": True})
    assert p.status_code == 200 and p.json()["outcome"]["status"] == "FAILED"
    stats = client.get("/v1/stats", headers=H).json()
    assert stats["failed_fixes_remembered"] == 1


def test_query_retrieves_and_flags_failed(client):
    iid = client.post("/v1/incidents", headers=H, json=_incident_body()).json()["id"]
    client.patch(f"/v1/incidents/{iid}/outcome", headers=H,
                 json={"status": "FAILED", "verification_method": "ping", "verified": True})
    q = {
        "network_id": "ignored",
        "description": "BGP session flapping on R3, as-path looks different",
        "protocols": ["BGP"], "affected_layer": "L3", "devices": ["R3"],
        "current_topology_hash": "topo-v1",
    }
    data = client.post("/v1/query?reason_enabled=false", headers=H, json=q).json()
    assert data["retrieved"] and data["retrieved"][0]["incident"]["id"] == iid
    assert "FAILED" in (data["retrieved"][0]["outcome_flag"] or "")


def test_query_reasoning_unconfigured_surfaces_error_not_fake(client):
    client.post("/v1/incidents", headers=H, json=_incident_body())
    q = {"network_id": "ignored", "description": "bgp flap on R3", "protocols": ["BGP"],
         "affected_layer": "L3", "devices": ["R3"]}
    data = client.post("/v1/query", headers=H, json=q).json()
    # placeholder LLM key -> reasoning is None + a clear error, never fabricated
    assert data["reasoning"] is None
    assert "not configured" in (data["reasoning_error"] or "")
