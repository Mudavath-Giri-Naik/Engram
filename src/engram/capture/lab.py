"""Local FRR lab control — drives the two real routers via `docker exec`.

Powers the dashboard's Capture / Break / Fix buttons. Runs on the API host
(Docker Desktop), no SSH/VPN. All output is real `vtysh` output from FRR.
"""

from __future__ import annotations

import subprocess

from engram.capture.builder import build_incident
from engram.capture.netmiko_session import CommandResult
from engram.domain.enums import Layer, Outcome, Protocol, Scope, Severity
from engram.domain.models import Incident

NODES = {"r1": "engram-r1", "r2": "engram-r2"}
COMMANDS = ["show ip bgp summary", "show ip bgp", "show ip route", "show running-config"]
PEER = "172.20.0.12"
DOWN_STATES = ("Active", "Idle", "Connect", "OpenSent", "OpenConfirm")


class LabError(RuntimeError):
    pass


def _run(args: list[str], what: str) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=25)
    except FileNotFoundError as e:
        raise LabError("Docker not found on the API host. Is Docker Desktop running?") from e
    except subprocess.TimeoutExpired as e:
        raise LabError(f"Timed out: {what}.") from e
    if r.returncode != 0 and "No such container" in (r.stderr or ""):
        raise LabError(
            "Lab routers aren't running. Start them: docker compose -f lab/docker-compose.yml up -d"
        )
    return r


def _vtysh(container: str, cmd: str) -> str:
    r = _run(["docker", "exec", container, "vtysh", "-c", cmd], f"{cmd} on {container}")
    return (r.stdout or r.stderr).strip()


def _config(container: str, lines: list[str]) -> None:
    args = ["docker", "exec", container, "vtysh", "-c", "configure terminal"]
    for c in lines:
        args += ["-c", c]
    _run(args, f"configure {container}")


def status() -> dict:
    out = _vtysh("engram-r1", "show ip bgp summary")
    up = False
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0] == PEER:
            up = not any(s in line for s in DOWN_STATES)
            break
    return {"bgp_up": up, "peer": PEER}


def break_bgp() -> None:
    """Inject a real fault: wrong neighbor AS (a common typo)."""
    _config("engram-r1", ["router bgp 65001", f"neighbor {PEER} remote-as 65999"])
    _vtysh("engram-r1", "clear ip bgp *")


def heal_bgp() -> None:
    """Fix it: correct the neighbor AS back to 65002."""
    _config("engram-r1", ["router bgp 65001", f"neighbor {PEER} remote-as 65002"])
    _vtysh("engram-r1", "clear ip bgp *")


def capture(network_id: str, node: str = "r1") -> Incident:
    """Capture real router state into an Incident, auto-titled by current health."""
    container = NODES.get(node, node)
    results = [
        CommandResult(device=container, command=c, raw_output=_vtysh(container, c))
        for c in COMMANDS
    ]
    up = status()["bgp_up"]
    if up:
        title = f"{container} — healthy snapshot (BGP up)"
        symptom = f"Live snapshot of {container}: eBGP session to {PEER} established."
        outcome = Outcome.RESOLVED
    else:
        title = f"BGP neighbor {PEER} down on {container}"
        symptom = (
            f"BGP neighbor {PEER} is not established (stuck Active/Idle) — captured live "
            f"from {container}."
        )
        outcome = Outcome.UNKNOWN
    return build_incident(
        network_id=network_id, device_type="frr", title=title, symptom_description=symptom,
        results=results, protocols=[Protocol.BGP], affected_layer=Layer.L3, scope=Scope.LINK,
        severity=Severity.SEV2, devices=[container, "engram-r2"], topology_hash="frr-lab",
        outcome_status=outcome, handled_by="lab", tags=["frr", "lab", "bgp", "live"],
    )
