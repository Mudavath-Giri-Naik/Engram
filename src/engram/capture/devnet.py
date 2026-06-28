"""Server-side capture from a Cisco DevNet sandbox (real IOS XE over SSH).

Used by POST /v1/capture/devnet so the web dashboard can pull live Cisco data with
one click. Connection details come from settings (.env.local: DEVNET_HOST /
DEVNET_USER / DEVNET_PASSWORD / DEVNET_PORT / DEVNET_DEVICE_TYPE) and can be
overridden per-request.

Note: reserved sandboxes use a private IP (e.g. 10.10.20.x) reachable only over
the Cisco DevNet VPN — the API host must be on that VPN.
"""

from __future__ import annotations

from engram.capture.builder import build_incident
from engram.capture.netmiko_session import CommandResult
from engram.config import get_settings
from engram.domain.enums import Layer, Outcome, Protocol, Scope, Severity
from engram.domain.models import Incident

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
    port: int | None = None,
    device_type: str | None = None,
    commands: list[str] | None = None,
    protocols: list[Protocol] | None = None,
) -> Incident:
    """SSH into the Cisco device, run real show commands, return an Incident draft."""
    from netmiko import ConnectHandler

    s = get_settings()
    host = host or s.devnet_host
    user = user or s.devnet_user
    password = password or s.devnet_password
    port = port or s.devnet_port
    device_type = device_type or s.devnet_device_type
    commands = commands or DEFAULT_COMMANDS

    conn = ConnectHandler(
        device_type=device_type, host=host, port=port, username=user, password=password,
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
