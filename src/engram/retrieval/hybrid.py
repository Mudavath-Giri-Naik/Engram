"""HybridRetriever — the technical core of Engram: filter-then-rank.

The pipeline is implemented explicitly (NOT hidden inside a framework's default
retriever) so it is inspectable and explainable end to end:

    1. Tenant hard filter      — Qdrant `must` network_id == query.network_id.
                                  Cross-tenant leakage is impossible by construction.
    2. Structured candidate     — prefer incidents sharing >=1 protocol / the layer
       filter (soft, relaxable)   / the signature. If too few candidates come back
                                  (< k*2), relax to tenant-only so retrieval is
                                  never empty when memory exists.
    3. Vector rank              — embed the query locally, vector-search within the
                                  filtered candidates, take top N.
    4. Re-score                 — structured_score (scoring.py) + final weighted
                                  score. This is where two prose-similar but
                                  operationally-different incidents get separated.
    5. Staleness                — age + topology_hash mismatch, surfaced not dropped.
    6. Explain                  — plain-English match_explanation naming matched
                                  fields; outcome_flag when a prior fix FAILED.
    7. Return top-k by final_score.
"""

from __future__ import annotations

from engram.domain.enums import Outcome
from engram.domain.models import FaultQuery, Incident, RetrievedIncident
from engram.embedding.embedder import Embedder, get_embedder
from engram.retrieval import scoring, staleness
from engram.storage.incident_repo import IncidentRepo
from engram.storage.vector_store import VectorStore


class HybridRetriever:
    def __init__(
        self,
        repo: IncidentRepo,
        vector_store: VectorStore,
        embedder: Embedder | None = None,
        *,
        candidate_pool: int = 20,
    ) -> None:
        self.repo = repo
        self.vs = vector_store
        self.embedder = embedder or get_embedder()
        self.candidate_pool = candidate_pool

    def retrieve(self, query: FaultQuery, k: int = 3) -> list[RetrievedIncident]:
        qvec = self.embedder.embed_query(query.description)

        has_structured = bool(query.protocols or query.affected_layer or query.signature)

        # --- step 1+2+3: tenant filter + structured candidate filter + vector rank
        hits = self.vs.search(
            network_id=query.network_id,
            vector=qvec,
            limit=self.candidate_pool,
            protocols=[p.value for p in query.protocols],
            layer=query.affected_layer.value if query.affected_layer else None,
            signature=query.signature,
            structured=has_structured,
        )

        # --- relax: if the structured filter starved us, drop to tenant-only ---
        if has_structured and len(hits) < k * 2:
            hits = self.vs.search(
                network_id=query.network_id,
                vector=qvec,
                limit=self.candidate_pool,
                structured=False,
            )

        if not hits:
            return []

        # Fetch full incidents from Postgres (source of truth), tenant-scoped.
        ids = [h[0] for h in hits]
        incidents: dict[str, Incident] = self.repo.get_many(query.network_id, ids)
        vscore_by_id = {h[0]: h[1] for h in hits}

        results: list[RetrievedIncident] = []
        for inc_id, inc in incidents.items():
            vscore = vscore_by_id.get(inc_id, 0.0)
            sscore, breakdown = scoring.structured_score(query, inc)
            fscore = scoring.final_score(vscore, sscore)
            stale = staleness.assess(inc, query.current_topology_hash)
            results.append(
                RetrievedIncident(
                    incident=inc,
                    vector_score=round(vscore, 4),
                    structured_score=round(sscore, 4),
                    final_score=round(fscore, 4),
                    match_explanation=_explain(breakdown, stale),
                    staleness=stale,
                    outcome_flag=_outcome_flag(inc, stale),
                )
            )

        results.sort(key=lambda r: r.final_score, reverse=True)
        return results[:k]


def _explain(breakdown: dict, stale: dict) -> str:
    parts: list[str] = []
    if breakdown.get("protocol_overlap"):
        parts.append("protocol=" + "+".join(breakdown["protocol_overlap"]))
    if breakdown.get("layer_match"):
        parts.append("layer match")
    if breakdown.get("signature_match"):
        parts.append("signature match")
    if breakdown.get("device_overlap"):
        parts.append("device overlap=" + ",".join(breakdown["device_overlap"]))
    if breakdown.get("severity_proximity", 0) >= 0.75:
        parts.append("similar severity")
    if not parts:
        parts.append("semantic similarity only (no structured field overlap)")
    msg = "matched on " + ", ".join(parts)
    if stale.get("stale"):
        msg += "  [STALE: " + "; ".join(stale.get("reasons", [])) + "]"
    return msg


def _outcome_flag(inc: Incident, stale: dict) -> str | None:
    if inc.outcome.status == Outcome.FAILED:
        return "PRIOR FIX FAILED — do not repeat without adapting"
    if inc.outcome.status == Outcome.PARTIAL:
        return "PRIOR FIX ONLY PARTIALLY RESOLVED the issue"
    if stale.get("topology_changed"):
        return "TOPOLOGY CHANGED since this incident — fix may be invalid"
    return None
