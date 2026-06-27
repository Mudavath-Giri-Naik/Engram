"""`engram capture` orchestration.

Two modes:
  * live:       SSH to a device (Netmiko), run a command set, capture raw output,
                prompt the engineer for symptom/RCA/fix/outcome, build an Incident,
                then POST to the API (or write a draft JSON).
  * --from-file: ingest a previously saved transcript (no device needed). This is
                how a real saved session becomes an incident.

The default investigation command set is deliberately protocol-broad so the same
flow captures BGP/OSPF/MTU/ACL faults on FRR or Cisco-like gear.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import typer
from rich import print as rprint
from rich.prompt import Prompt

from engram.capture.builder import build_incident, parse_transcript
from engram.capture.netmiko_session import CommandResult, DeviceSession
from engram.config import get_settings
from engram.domain.enums import Layer, Outcome, Protocol, Scope, Severity

DEFAULT_COMMANDS = [
    "show ip bgp summary",
    "show ip ospf neighbor",
    "show interface",
    "show ip route",
    "show running-config",
]


def _ask_enum(label: str, enum_cls, default):  # type: ignore[no-untyped-def]
    choices = [e.value for e in enum_cls]
    val = Prompt.ask(f"{label} {choices}", default=default.value)
    try:
        return enum_cls(val)
    except ValueError:
        return default


def _ask_protocols() -> list[Protocol]:
    raw = Prompt.ask("Protocols (comma-separated)", default="")
    out: list[Protocol] = []
    for tok in raw.split(","):
        tok = tok.strip().upper()
        if tok:
            try:
                out.append(Protocol(tok))
            except ValueError:
                pass
    return out


def run_capture(
    *,
    host: str,
    device_type: str,
    network_id: str | None,
    from_file: Path | None,
    api_url: str,
    api_key: str | None,
    draft_out: Path | None,
) -> None:
    s = get_settings()
    network_id = network_id or s.engram_bootstrap_network_id or "default-network"
    api_key = api_key or s.engram_bootstrap_api_key

    # --- gather command results -------------------------------------------------
    if from_file is not None:
        rprint(f"[cyan]Ingesting transcript[/cyan] {from_file}")
        device, results = parse_transcript(Path(from_file).read_text())
        rprint(f"  parsed {len(results)} command(s) for device {device}")
    else:
        cmds_raw = Prompt.ask(
            "Commands to run (comma-separated)", default=",".join(DEFAULT_COMMANDS)
        )
        commands = [c.strip() for c in cmds_raw.split(",") if c.strip()]
        hostname = Prompt.ask("Device hostname/label", default=host)
        rprint(f"[cyan]Connecting[/cyan] to {host} ({device_type}) ...")
        with DeviceSession(host=host, device_type=device_type, hostname=hostname) as sess:
            results = sess.run_many(commands)
        rprint(f"  captured {len(results)} command(s)")

    # --- engineer metadata ------------------------------------------------------
    title = Prompt.ask("Incident title")
    symptom = Prompt.ask("Symptom description")
    protocols = _ask_protocols()
    layer = _ask_enum("Affected layer", Layer, Layer.UNKNOWN)
    scope = _ask_enum("Scope", Scope, Scope.DEVICE)
    severity = _ask_enum("Severity", Severity, Severity.SEV3)
    topology_hash = Prompt.ask("Topology hash (optional)", default="") or None
    root_cause = Prompt.ask("Root cause")
    fix = Prompt.ask("Fix description")
    applied = [c.strip() for c in Prompt.ask("Commands applied (comma-sep)", default="").split(",") if c.strip()]
    outcome = _ask_enum("Outcome", Outcome, Outcome.UNKNOWN)
    verification = Prompt.ask("Verification method", default="")
    handled_by = Prompt.ask("Handled by", default="")

    incident = build_incident(
        network_id=network_id,
        device_type=device_type,
        title=title,
        symptom_description=symptom,
        results=results,
        protocols=protocols,
        affected_layer=layer,
        scope=scope,
        severity=severity,
        topology_hash=topology_hash,
        root_cause=root_cause,
        fix_description=fix,
        commands_applied=applied,
        outcome_status=outcome,
        verification_method=verification,
        verified=bool(verification),
        handled_by=handled_by,
    )

    # --- output: draft file or POST to API -------------------------------------
    if draft_out is not None:
        Path(draft_out).write_text(incident.model_dump_json(indent=2))
        rprint(f"[green]Draft written[/green] to {draft_out} (ingest later with the API).")
        return

    rprint(f"[cyan]POSTing[/cyan] incident to {api_url}/v1/incidents ...")
    resp = httpx.post(
        f"{api_url}/v1/incidents",
        headers={"X-API-Key": api_key or ""},
        json=incident.model_dump(mode="json"),
        timeout=30,
    )
    if resp.status_code >= 300:
        rprint(f"[red]API error {resp.status_code}[/red]: {resp.text}")
        raise typer.Exit(code=1)
    rprint(f"[green]Ingested[/green] incident id = {resp.json().get('id')}")


def build_incident_from_transcript(text: str, *, network_id: str, device_type: str = "frr", **meta):
    """Helper used by tests: build an Incident from a transcript string + metadata."""
    _device, results = parse_transcript(text)
    return build_incident(
        network_id=network_id, device_type=device_type, results=results, **meta
    )


__all__ = ["run_capture", "build_incident_from_transcript", "CommandResult"]
