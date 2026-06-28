"""Capture REAL output from the local FRR lab routers and store it as an Engram
incident — so it shows up in the dashboard. Uses `docker exec` (Docker Desktop),
no SSH/VPN.

    python scripts/capture_lab.py                    # healthy snapshot of r1
    python scripts/capture_lab.py --node engram-r2   # capture r2 instead
    python scripts/capture_lab.py --title "R1-R2 BGP neighbor down" \
        --symptom "BGP neighbor 172.20.0.12 stuck, AS mismatch" \
        --root-cause "remote-as typo 65999" --fix "set remote-as back to 65002" \
        --outcome RESOLVED
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import httpx

API_URL = os.environ.get("ENGRAM_API_URL", "http://localhost:8000")
KEY = os.environ.get("ENGRAM_API_KEY", "local-dev-key")

COMMANDS = [
    "show ip bgp summary",
    "show ip bgp",
    "show ip route",
    "show running-config",
]


def dexec(container: str, cmd: str) -> str:
    """Run a vtysh command inside an FRR container and return real output."""
    r = subprocess.run(
        ["docker", "exec", container, "vtysh", "-c", cmd],
        capture_output=True, text=True,
    )
    return (r.stdout or r.stderr).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", default="engram-r1", help="container name (engram-r1 / engram-r2)")
    ap.add_argument("--title", default="Live snapshot — FRR r1")
    ap.add_argument("--symptom", default="Live router state captured from the local FRR lab.")
    ap.add_argument("--protocols", default="BGP")
    ap.add_argument("--layer", default="L3")
    ap.add_argument("--root-cause", default="")
    ap.add_argument("--fix", default="")
    ap.add_argument("--outcome", default="UNKNOWN", help="RESOLVED|PARTIAL|FAILED|UNKNOWN")
    ap.add_argument("--api-url", default=API_URL)
    ap.add_argument("--api-key", default=KEY)
    a = ap.parse_args()

    # sanity: is the container running?
    check = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True)
    if a.node not in check.stdout:
        print(f"Container '{a.node}' is not running. Start the lab first:\n"
              f"  docker compose -f lab/docker-compose.yml up -d")
        sys.exit(1)

    steps = []
    print(f"Capturing from {a.node} ...\n")
    for c in COMMANDS:
        out = dexec(a.node, c)
        preview = "\n  ".join(out.splitlines()[:6])
        print(f"$ {c}\n  {preview}\n")
        steps.append({"device": a.node, "command": c, "raw_output": out})

    incident = {
        "network_id": "from-auth",
        "title": a.title,
        "handled_by": "lab-capture",
        "tags": ["frr", "lab", "bgp"],
        "symptom": {
            "description": a.symptom,
            "protocols": [p.strip().upper() for p in a.protocols.split(",") if p.strip()],
            "affected_layer": a.layer, "scope": "LINK", "severity": "SEV2",
        },
        "context": {"devices": [a.node], "topology_hash": "frr-lab"},
        "investigation": steps,
        "resolution": {"root_cause": a.root_cause, "fix_description": a.fix},
        "outcome": {"status": a.outcome, "verified": bool(a.fix)},
    }

    r = httpx.post(
        f"{a.api_url}/v1/incidents",
        headers={"X-API-Key": a.api_key, "Content-Type": "application/json"},
        json=incident, timeout=60, trust_env=False,
    )
    if r.status_code >= 300:
        print(f"API error {r.status_code}: {r.text}")
        sys.exit(1)
    print(f"Stored REAL incident -> id {r.json()['id']}")
    print("Open the dashboard Incidents tab to see the real captured router output.")


if __name__ == "__main__":
    main()
