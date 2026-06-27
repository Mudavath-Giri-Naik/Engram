"""Staleness assessment for a retrieved incident.

A past fix can be *wrong now* for two reasons:
  1. Age — the incident is old enough that the environment likely drifted.
  2. Topology change — the network's topology hash differs from when the
     incident was recorded, so a fix that depended on the old wiring/peering
     may no longer apply.

Staleness is surfaced, never used to silently drop a candidate: an old incident
is often still the most relevant memory, the engineer just needs to be warned.
"""

from __future__ import annotations

from datetime import datetime, timezone

from engram.config import get_settings
from engram.domain.models import Incident


def assess(inc: Incident, current_topology_hash: str | None) -> dict:
    s = get_settings()
    age_days = max(0, int((datetime.now(timezone.utc) - inc.occurred_at).total_seconds() // 86400))

    topology_changed = False
    if current_topology_hash and inc.context.topology_hash:
        topology_changed = current_topology_hash != inc.context.topology_hash

    age_stale = age_days > s.staleness_age_days
    stale = age_stale or topology_changed

    reasons = []
    if age_stale:
        reasons.append(f"older than {s.staleness_age_days} days")
    if topology_changed:
        reasons.append("topology changed since incident")

    return {
        "age_days": age_days,
        "topology_changed": topology_changed,
        "stale": stale,
        "reasons": reasons,
    }
