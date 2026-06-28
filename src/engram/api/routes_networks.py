"""Networks overview — the multi-tenant 'all your networks' view (SaaS dashboard)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from engram.api.deps import current_network_id, incident_repo
from engram.storage.incident_repo import IncidentRepo
from engram.storage.orm import IncidentRow, Tenant

router = APIRouter(tags=["networks"])


@router.get("/networks")
def networks(
    network_id: str = Depends(current_network_id),
    repo: IncidentRepo = Depends(incident_repo),
) -> dict:
    """List every network (tenant) with its incident + FAILED-fix counts."""
    s = repo.s
    counts = dict(
        s.execute(select(IncidentRow.network_id, func.count()).group_by(IncidentRow.network_id)).all()
    )
    failed = dict(
        s.execute(
            select(IncidentRow.network_id, func.count())
            .where(IncidentRow.outcome_status == "FAILED")
            .group_by(IncidentRow.network_id)
        ).all()
    )
    tenant_nets = [t.network_id for t in s.execute(select(Tenant)).scalars().all()]
    all_nets = sorted(set(tenant_nets) | set(counts))
    return {
        "networks": [
            {
                "network_id": n,
                "incidents": int(counts.get(n, 0)),
                "failed_fixes": int(failed.get(n, 0)),
                "current": n == network_id,
            }
            for n in all_nets
        ]
    }
