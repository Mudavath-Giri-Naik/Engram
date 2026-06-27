"""Capture REAL output from a Cisco DevNet Always-On sandbox and ingest it as an
Engram incident. This is real Cisco IOS XE data over SSH — nothing simulated.

    python scripts/capture_devnet.py

Defaults target the public Always-On IOS XE sandbox. Credentials rotate over time
— if login fails, grab the current host/user/password from your free DevNet
account at https://developer.cisco.com/site/sandbox/ (Networking -> "IOS XE on
Cat8kv Always On") and pass them as flags or env vars:

    python scripts/capture_devnet.py --host <h> --user <u> --password <p>

Env vars also work: DEVNET_HOST, DEVNET_USER, DEVNET_PASSWORD,
ENGRAM_API_URL, ENGRAM_API_KEY.
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

# Well-known public Always-On IOS XE sandbox (verify current creds on DevNet).
DEFAULTS = {
    "host": os.environ.get("DEVNET_HOST", "sandbox-iosxe-latest-1.cisco.com"),
    "user": os.environ.get("DEVNET_USER", "admin"),
    "password": os.environ.get("DEVNET_PASSWORD", "C1sco12345"),
    "device_type": "cisco_xe",
}
DEFAULT_COMMANDS = [
    "show version",
    "show ip interface brief",
    "show ip route",
    "show running-config | section router bgp",
]


def capture(host, user, password, device_type, commands):
    from netmiko import ConnectHandler

    print(f"Connecting to {host} ({device_type}) over SSH ...")
    conn = ConnectHandler(
        device_type=device_type, host=host, username=user, password=password,
        fast_cli=False, conn_timeout=40,
    )
    hostname = conn.find_prompt().strip("#> ") or host
    print(f"Connected. Device prompt: {hostname}\n")
    steps = []
    for cmd in commands:
        print(f"  $ {cmd}")
        out = conn.send_command(cmd, read_timeout=60)
        print("  " + "\n  ".join(out.splitlines()[:6]) + ("\n  ..." if out.count("\n") > 6 else "") + "\n")
        steps.append({"device": hostname, "command": cmd, "raw_output": out})
    conn.disconnect()
    return hostname, steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=DEFAULTS["host"])
    ap.add_argument("--user", default=DEFAULTS["user"])
    ap.add_argument("--password", default=DEFAULTS["password"])
    ap.add_argument("--device-type", default=DEFAULTS["device_type"])
    ap.add_argument("--api-url", default=os.environ.get("ENGRAM_API_URL", "http://localhost:8000"))
    ap.add_argument("--api-key", default=os.environ.get("ENGRAM_API_KEY", "local-dev-key"))
    ap.add_argument("--title", default="Cisco IOS XE — interface/routing snapshot (DevNet)")
    ap.add_argument("--symptom", default="Captured live device state from a real Cisco IOS XE router for the incident record.")
    ap.add_argument("--protocols", default="BGP", help="comma-separated, e.g. BGP,OSPF")
    ap.add_argument("--layer", default="L3")
    ap.add_argument("--root-cause", default="")
    ap.add_argument("--fix", default="")
    ap.add_argument("--outcome", default="UNKNOWN", help="RESOLVED|PARTIAL|FAILED|UNKNOWN")
    args = ap.parse_args()

    try:
        hostname, steps = capture(args.host, args.user, args.password, args.device_type, DEFAULT_COMMANDS)
    except Exception as e:  # noqa: BLE001
        print(f"\nSSH capture failed: {e}\n"
              "-> Check the current sandbox host/credentials on developer.cisco.com "
              "(they rotate), and that outbound SSH/port 22 is allowed.")
        sys.exit(1)

    incident = {
        "network_id": "from-auth",
        "title": args.title,
        "handled_by": "devnet-capture",
        "tags": ["cisco", "ios-xe", "devnet"],
        "symptom": {
            "description": args.symptom,
            "protocols": [p.strip().upper() for p in args.protocols.split(",") if p.strip()],
            "affected_layer": args.layer, "scope": "DEVICE", "severity": "SEV3",
        },
        "context": {"devices": [hostname], "topology_hash": "cisco-devnet"},
        "investigation": steps,
        "resolution": {"root_cause": args.root_cause, "fix_description": args.fix},
        "outcome": {"status": args.outcome, "verified": False},
    }

    print(f"Ingesting incident into Engram at {args.api_url} ...")
    r = httpx.post(f"{args.api_url}/v1/incidents",
                   headers={"X-API-Key": args.api_key, "Content-Type": "application/json"},
                   json=incident, timeout=60, trust_env=False)
    if r.status_code >= 300:
        print(f"API error {r.status_code}: {r.text}")
        sys.exit(1)
    print(f"Ingested REAL Cisco incident -> id {r.json()['id']}")
    print("Open the dashboard Incidents page to see the real captured CLI output.")


if __name__ == "__main__":
    main()
