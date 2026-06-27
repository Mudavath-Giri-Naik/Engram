"""Assemble an Incident draft from a captured session.

Takes the raw command/output pairs plus engineer-provided metadata (symptom,
root cause, fix, outcome) and produces a validated Incident. The signature and
embedding_text are left blank here and filled by the ingest pipeline, so a draft
is always ingestable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from engram.capture.netmiko_session import CommandResult
from engram.capture.parsers import parse
from engram.domain.enums import Layer, Outcome, Protocol, Scope, Severity
from engram.domain.models import (
    Context,
    Incident,
    InvestigationStep,
    OutcomeRecord,
    Resolution,
    Symptom,
)


def build_incident(
    *,
    network_id: str,
    device_type: str,
    title: str,
    symptom_description: str,
    results: list[CommandResult],
    protocols: list[Protocol] | None = None,
    affected_layer: Layer = Layer.UNKNOWN,
    scope: Scope = Scope.DEVICE,
    severity: Severity = Severity.SEV3,
    devices: list[str] | None = None,
    topology_hash: str | None = None,
    root_cause: str = "",
    fix_description: str = "",
    commands_applied: list[str] | None = None,
    outcome_status: Outcome = Outcome.UNKNOWN,
    verification_method: str = "",
    verified: bool = False,
    mttr_seconds: int | None = None,
    handled_by: str = "",
    tags: list[str] | None = None,
) -> Incident:
    steps: list[InvestigationStep] = []
    seen_devices: list[str] = list(devices or [])
    for r in results:
        parsed = parse(device_type, r.command, r.raw_output)
        steps.append(
            InvestigationStep(
                device=r.device,
                command=r.command,
                raw_output=r.raw_output,
                parsed_output=parsed,
                timestamp=datetime.now(timezone.utc),
            )
        )
        if r.device not in seen_devices:
            seen_devices.append(r.device)

    return Incident(
        network_id=network_id,
        title=title or symptom_description[:80],
        handled_by=handled_by,
        tags=tags or [],
        symptom=Symptom(
            description=symptom_description,
            affected_layer=affected_layer,
            protocols=protocols or [],
            scope=scope,
            severity=severity,
        ),
        context=Context(devices=seen_devices, topology_hash=topology_hash),
        investigation=steps,
        resolution=Resolution(
            root_cause=root_cause,
            fix_description=fix_description,
            commands_applied=commands_applied or [],
        ),
        outcome=OutcomeRecord(
            status=outcome_status,
            verification_method=verification_method,
            verified=verified,
            mttr_seconds=mttr_seconds,
        ),
    )


def parse_transcript(text: str) -> tuple[str, list[CommandResult]]:
    """Parse a saved capture transcript into (device, results).

    Transcript format (simple, human-writable):

        # device: R3
        $ show ip bgp summary
        <raw output line 1>
        <raw output line 2>
        $ show ip bgp neighbors 10.0.13.1
        <raw output...>

    Lines beginning with '# device:' set the current device. Lines beginning
    with '$ ' start a new command; everything until the next '$ ' or '# device:'
    is that command's raw output.
    """
    device = "unknown"
    results: list[CommandResult] = []
    cur_cmd: str | None = None
    cur_lines: list[str] = []

    def flush() -> None:
        nonlocal cur_cmd, cur_lines
        if cur_cmd is not None:
            results.append(
                CommandResult(device=device, command=cur_cmd, raw_output="\n".join(cur_lines).strip("\n"))
            )
        cur_cmd, cur_lines = None, []

    for line in text.splitlines():
        if line.strip().lower().startswith("# device:"):
            flush()
            device = line.split(":", 1)[1].strip()
        elif line.startswith("$ "):
            flush()
            cur_cmd = line[2:].strip()
        else:
            if cur_cmd is not None:
                cur_lines.append(line)
    flush()
    return device, results
