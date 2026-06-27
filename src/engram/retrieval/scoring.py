"""Structured + final scoring for retrieval.

Why this exists (and why embeddings-alone are not enough):
    Two incident write-ups can read almost identically in English ("BGP session
    to the upstream is down") yet be *different faults* — different device,
    different AS, different root cause. A pure cosine-similarity ranker will
    happily rank a semantically-similar-but-operationally-wrong incident first.
    The structured score injects hard network facts (shared protocol, same
    layer, same signature, device overlap, severity proximity, recency) so the
    final ranking reflects operational similarity, not just prose similarity.

`final_score = w_v * vector_score + w_s * structured_score`, weights from config.
Both component scores are normalized to [0, 1].
"""

from __future__ import annotations

from datetime import datetime, timezone

from engram.config import get_settings
from engram.domain.enums import Layer, Severity
from engram.domain.models import FaultQuery, Incident

# Sub-weights for the structured score components (sum = 1.0). Documented so the
# scoring is fully inspectable.
_W_PROTOCOL = 0.30
_W_LAYER = 0.15
_W_SIGNATURE = 0.30
_W_DEVICE = 0.15
_W_SEVERITY = 0.05
_W_RECENCY = 0.05

# Recency half-life: an incident this many days old contributes ~0.5 recency.
_RECENCY_HALFLIFE_DAYS = 120.0


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _recency_score(occurred_at: datetime) -> float:
    age_days = max(0.0, (datetime.now(timezone.utc) - occurred_at).total_seconds() / 86400.0)
    # exponential decay, 1.0 today -> 0.5 at half-life
    return 0.5 ** (age_days / _RECENCY_HALFLIFE_DAYS)


def structured_score(query: FaultQuery, inc: Incident) -> tuple[float, dict]:
    """Return (score in [0,1], breakdown of which fields matched)."""
    breakdown: dict = {}

    q_protos = {p.value for p in query.protocols}
    i_protos = {p.value for p in inc.symptom.protocols}
    proto_overlap = len(q_protos & i_protos)
    proto_score = _jaccard(q_protos, i_protos)
    breakdown["protocol_overlap"] = sorted(q_protos & i_protos)

    layer_match = bool(query.affected_layer and query.affected_layer == inc.symptom.affected_layer
                       and inc.symptom.affected_layer != Layer.UNKNOWN)
    layer_score = 1.0 if layer_match else 0.0
    breakdown["layer_match"] = layer_match

    sig_match = bool(query.signature and query.signature == inc.symptom.signature)
    sig_score = 1.0 if sig_match else 0.0
    breakdown["signature_match"] = sig_match

    q_dev = {d.lower() for d in query.devices}
    i_dev = {d.lower() for d in inc.context.devices}
    device_overlap = sorted({d for d in (q_dev & i_dev)})
    device_score = _jaccard(q_dev, i_dev)
    breakdown["device_overlap"] = device_overlap

    # severity proximity: 1.0 if same, decreasing with distance (only when the
    # query supplies a severity; otherwise this component is neutral/zero).
    if query.severity is not None:
        sev_score = severity_proximity(query.severity, inc.symptom.severity)
    else:
        sev_score = 0.0
    breakdown["severity_proximity"] = round(sev_score, 3)

    recency = _recency_score(inc.occurred_at)
    breakdown["recency"] = round(recency, 3)

    score = (
        _W_PROTOCOL * proto_score
        + _W_LAYER * layer_score
        + _W_SIGNATURE * sig_score
        + _W_DEVICE * device_score
        + _W_SEVERITY * sev_score
        + _W_RECENCY * recency
    )
    breakdown["protocol_overlap_count"] = proto_overlap
    return min(1.0, score), breakdown


def severity_proximity(a: Severity, b: Severity) -> float:
    """Helper: 1.0 if equal severity, linearly down to 0.25 for max distance."""
    dist = abs(a.rank - b.rank)
    return max(0.0, 1.0 - dist / 4.0)


def final_score(vector_score: float, struct_score: float) -> float:
    s = get_settings()
    return s.retrieval_w_vector * vector_score + s.retrieval_w_structured * struct_score
