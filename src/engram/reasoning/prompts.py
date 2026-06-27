"""The comparative-reasoning prompt contract.

The model is given the new fault and the top-k retrieved past incidents (with
their structured fields, outcomes, and staleness already computed by Engram). It
must reason *comparatively* — grounding similarity in matched structured fields,
naming concrete differences, adapting the closest past fix, and refusing to claim
certainty. Output is strict JSON matching ReasoningResult.
"""

from __future__ import annotations

import json

from engram.domain.models import FaultQuery, RetrievedIncident

SYSTEM_PROMPT = """\
You are Engram's reasoning core. Engram is a NETWORK-SPECIFIC incident memory: it
stores how *this particular network* was actually troubleshot in the past. You
already have textbook networking knowledge; your job here is NOT to recite theory
but to reason COMPARATIVELY between a NEW fault and SPECIFIC PAST INCIDENTS from
this same network that Engram retrieved for you.

Rules:
- Ground every similarity_pct in the MATCHED STRUCTURED FIELDS you are given
  (protocol, layer, signature, device overlap, severity), not on prose vibes.
- Name concrete KEY DIFFERENCES (e.g. different AS-path, different device role,
  different topology).
- Derive recommended_hypothesis and recommended_fix from the CLOSEST past
  incident, ADAPTED for the differences. List the incident IDs you adapted from
  in adapted_from.
- If any retrieved incident has outcome FAILED, you MUST add a warning telling
  the engineer not to blindly repeat that fix.
- If any retrieved incident is marked stale (topology changed / too old), warn
  that its fix may no longer be valid.
- NEVER claim certainty. Always set requires_human_approval to true.
- Respond with STRICT JSON ONLY. No markdown, no code fences, no prose outside
  the JSON object.
"""

# The exact JSON shape we expect back (mirrors ReasoningResult).
OUTPUT_SCHEMA_HINT = {
    "comparisons": [
        {
            "incident_id": "<uuid>",
            "similarity_pct": 0,
            "rationale": "<why, citing matched structured fields>",
            "key_differences": ["<difference>"],
        }
    ],
    "recommended_hypothesis": "<most likely root cause for the NEW fault>",
    "recommended_fix": "<adapted fix>",
    "adapted_from": ["<incident_id>"],
    "warnings": ["<warning>"],
    "confidence": "low|medium|high",
    "requires_human_approval": True,
}


def _incident_brief(r: RetrievedIncident) -> dict:
    inc = r.incident
    return {
        "incident_id": str(inc.id),
        "title": inc.title,
        "occurred_at": inc.occurred_at.isoformat(),
        "structured_fields": {
            "signature": inc.symptom.signature,
            "protocols": [p.value for p in inc.symptom.protocols],
            "affected_layer": inc.symptom.affected_layer.value,
            "scope": inc.symptom.scope.value,
            "severity": inc.symptom.severity.value,
            "devices": inc.context.devices,
        },
        "symptom": inc.symptom.description,
        "root_cause": inc.resolution.root_cause,
        "fix_description": inc.resolution.fix_description,
        "commands_applied": inc.resolution.commands_applied,
        "outcome": inc.outcome.status.value,
        "engram_scores": {
            "vector_score": r.vector_score,
            "structured_score": r.structured_score,
            "final_score": r.final_score,
            "match_explanation": r.match_explanation,
        },
        "staleness": r.staleness,
        "outcome_flag": r.outcome_flag,
    }


def build_user_prompt(query: FaultQuery, retrieved: list[RetrievedIncident]) -> str:
    payload = {
        "new_fault": {
            "description": query.description,
            "affected_layer": query.affected_layer.value if query.affected_layer else None,
            "protocols": [p.value for p in query.protocols],
            "scope": query.scope.value if query.scope else None,
            "severity": query.severity.value if query.severity else None,
            "devices": query.devices,
            "signature_hint": query.signature,
            "current_topology_hash": query.current_topology_hash,
        },
        "retrieved_past_incidents": [_incident_brief(r) for r in retrieved],
        "respond_with_strict_json_matching": OUTPUT_SCHEMA_HINT,
    }
    return (
        "Compare the NEW fault against each retrieved past incident from THIS "
        "network and produce the strict-JSON ReasoningResult.\n\n"
        + json.dumps(payload, indent=2)
    )
