"""Seed a few realistic incidents into a RUNNING Engram API, then run the demo query.

Usage (with `python -m engram.cli serve` running in another terminal):

    python scripts/seed_demo_api.py

It reads the API key from ENGRAM_BOOTSTRAP_API_KEY (or .env.local), defaulting to
"local-dev-key". Override host/key with env vars ENGRAM_API_URL / ENGRAM_API_KEY.
This posts real incidents over HTTP — nothing is inserted behind the API.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx

API_URL = os.environ.get("ENGRAM_API_URL", "http://localhost:8000")


def _api_key() -> str:
    key = os.environ.get("ENGRAM_API_KEY") or os.environ.get("ENGRAM_BOOTSTRAP_API_KEY")
    if not key:
        # fall back to .env.local if present
        env = os.path.join(os.path.dirname(__file__), "..", ".env.local")
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if line.strip().startswith("ENGRAM_BOOTSTRAP_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    return key or "local-dev-key"


KEY = _api_key()
H = {"X-API-Key": KEY}


def add(client: httpx.Client, **k) -> str:
    body = {
        "network_id": "from-auth",
        "title": k["title"],
        "symptom": {
            "description": k["desc"], "protocols": k["protocols"],
            "affected_layer": k["layer"], "scope": "LINK", "severity": k.get("sev", "SEV2"),
        },
        "context": {"devices": k["devices"], "topology_hash": k.get("topo", "topo-v1")},
        "resolution": {"root_cause": k["rc"], "fix_description": k["fix"]},
        "outcome": {"status": k["outcome"], "verified": True, "mttr_seconds": k.get("mttr", 900)},
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=k.get("days_ago", 0))).isoformat(),
    }
    r = client.post(f"{API_URL}/v1/incidents", headers=H, json=body, timeout=60)
    r.raise_for_status()
    return r.json()["id"]


def main() -> None:
    print(f"Seeding demo incidents into {API_URL}  (X-API-Key={KEY})")
    # trust_env=False so localhost calls never get routed through a system proxy.
    with httpx.Client(trust_env=False) as c:
        try:
            c.get(f"{API_URL}/health", timeout=10).raise_for_status()
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"API not reachable at {API_URL}. Is `engram serve` running? ({e})")

        i47 = add(c, title="#47 BGP neighbor down R2-R3",
                  desc="BGP neighbor 10.0.23.3 to R3 stuck Active, never establishes",
                  protocols=["BGP"], layer="L3", devices=["R2", "R3"],
                  rc="neighbor remote-as typo (65999)", fix="corrected remote-as to 65002", outcome="RESOLVED")
        add(c, title="MTU mismatch on R1-R2 OSPF link",
            desc="OSPF adjacency stuck ExStart, MTU mismatch detected on the link",
            protocols=["OSPF", "MTU"], layer="L3", devices=["R1", "R2"],
            rc="eth1 mtu 9000 vs 1500", fix="set mtu 1500 on both ends", outcome="RESOLVED")
        add(c, title="ACL silently dropping DB flow",
            desc="App cannot reach database; ping works but TCP 5432 dropped by access-list",
            protocols=["ACL"], layer="L4", devices=["R4"],
            rc="deny rule on EDGE-IN", fix="permit 5432 from app subnet", outcome="RESOLVED")
        fid = add(c, title="Old BGP fix that FAILED",
                  desc="BGP neighbor down; tried clearing the session, did not help",
                  protocols=["BGP"], layer="L3", devices=["R4"],
                  rc="(wrong) suspected transient flap", fix="clear ip bgp * (did NOT resolve)",
                  outcome="FAILED", topo="topo-OLD", days_ago=400)

        print(f"  seeded #47={i47[:8]}  + MTU + ACL + FAILED({fid[:8]})")

        print("\nRunning the demo query: a new fault that looks like #47 ...")
        q = {
            "network_id": "from-auth",
            "description": "Site B (R3) not learning Site A routes; BGP session to R2 looks up; AS-path filtering suspected",
            "protocols": ["BGP"], "affected_layer": "L3", "devices": ["R3", "R2"],
            "current_topology_hash": "topo-v1",
        }
        d = c.post(f"{API_URL}/v1/query?reason_enabled=false", headers=H, json=q, timeout=120).json()
        for i, r in enumerate(d["retrieved"], 1):
            inc = r["incident"]
            line = f"  [{i}] {inc['title']}  (final={r['final_score']:.3f})  {r['match_explanation']}"
            print(line)
            if r["outcome_flag"]:
                print(f"        FLAG: {r['outcome_flag']}")
    print("\nDone. Open the dashboard (New Fault page) to see this visually, or http://localhost:8000/docs")


if __name__ == "__main__":
    main()
