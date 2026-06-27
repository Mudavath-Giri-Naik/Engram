"""Generate `embedding_text` from a structured incident.

The embedding text is a compact, information-dense rendering of the incident that
the local embedder turns into a vector. We deliberately fold the structured
fields (signature, protocols, layer, devices) into the text so the vector itself
carries some structured signal, while still leading with the human narrative for
semantic recall.
"""

from __future__ import annotations

from engram.domain.models import Incident


def build_embedding_text(inc: Incident) -> str:
    sym = inc.symptom
    res = inc.resolution
    parts: list[str] = []
    parts.append(f"TITLE: {inc.title}".strip())
    parts.append(f"SIGNATURE: {sym.signature}")
    parts.append(f"LAYER: {sym.affected_layer.value}  SCOPE: {sym.scope.value}  SEVERITY: {sym.severity.value}")
    if sym.protocols:
        parts.append("PROTOCOLS: " + ", ".join(p.value for p in sym.protocols))
    if inc.context.devices:
        parts.append("DEVICES: " + ", ".join(inc.context.devices))
    parts.append(f"SYMPTOM: {sym.description}")

    # A couple of representative investigation commands give the vector real
    # device-evidence signal without ballooning the text.
    if inc.investigation:
        cmds = "; ".join(f"{s.device}:{s.command}" for s in inc.investigation[:4])
        parts.append(f"INVESTIGATION: {cmds}")
    if res.root_cause:
        parts.append(f"ROOT_CAUSE: {res.root_cause}")
    if res.fix_description:
        parts.append(f"FIX: {res.fix_description}")
    parts.append(f"OUTCOME: {inc.outcome.status.value}")
    if inc.tags:
        parts.append("TAGS: " + ", ".join(inc.tags))
    return "\n".join(p for p in parts if p)
