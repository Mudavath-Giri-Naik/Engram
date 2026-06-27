"""Server-side capture from a Cisco DevNet Always-On sandbox (real IOS XE over SSH).

Used by POST /v1/capture/devnet so the web dashboard can pull live Cisco data with
one click. Credentials default to the public Always-On IOS XE sandbox and can be
overridden via env (DEVNET_HOST/USER/PASSWORD) or the request body.
"""

from __future__ import annotations

import os

from engram.capture.builder import build_incident
from engram.capture.netmiko_session import CommandResult
from engram.domain.enums import Layer, Outcome, Protocol, Scope, Severity
from engram.domain.models import Incident

DEVNET_DEFAULTS = {
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


def run_devnet_capture(
    *,
    network_id: str,
    host: str | None = None,
    user: str | None = None,
    password: str | None = None,
    device_type: str | None = None,
    commands: list[str] | None = None,
    protocols: list[Protocol] | None = None,
) -> Incident:
    """SSH into the Cisco device, run real show commands, return an Incident draft."""
    from netmiko import ConnectHandler

    host = host or DEVNET_DEFAULTS["host"]
    user = user or DEVNET_DEFAULTS["user"]
    password = password or DEVNET_DEFAULTS["password"]
    device_type = device_type or DEVNET_DEFAULTS["device_type"]
    commands = commands or DEFAULT_COMMANDS

    conn = ConnectHandler(
        device_type=device_type, host=host, username=user, password=password,
        fast_cli=False, conn_timeout=45,
    )
    try:
        hostname = conn.find_prompt().strip("#> ") or host
        results = [
            CommandResult(device=hostname, command=c, raw_output=conn.send_command(c, read_timeout=60))
            for c in commands
        ]
    finally:
        conn.disconnect()

    return build_incident(
        network_id=network_id,
        device_type=device_type,
        title=f"Live snapshot — {hostname} (Cisco IOS XE)",
        symptom_description=(
            f"Live device state captured over SSH from real Cisco IOS XE router {hostname} "
            "via the DevNet sandbox."
        ),
        results=results,
        protocols=protocols or [Protocol.BGP],
        affected_layer=Layer.L3,
        scope=Scope.DEVICE,
        severity=Severity.SEV3,
        devices=[hostname],
        topology_hash="cisco-devnet",
        outcome_status=Outcome.UNKNOWN,
        handled_by="devnet-live",
        tags=["cisco", "ios-xe", "devnet", "live"],
    )
