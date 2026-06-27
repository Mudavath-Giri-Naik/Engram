"""Postgres CRUD for incidents — ALWAYS tenant-scoped.

Every method takes a `network_id` and filters on it. There is deliberately no
"get any incident by id" path that ignores the tenant: tenant isolation is a
hard invariant of the system, not a convenience.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from engram.domain.enums import Outcome
from engram.domain.models import Incident, OutcomeRecord
from engram.storage.orm import IncidentRow


def _row_from_incident(inc: Incident) -> IncidentRow:
    return IncidentRow(
        id=str(inc.id),
        network_id=inc.network_id,
        title=inc.title,
        affected_layer=inc.symptom.affected_layer.value,
        signature=inc.symptom.signature,
        scope=inc.symptom.scope.value,
        severity=inc.symptom.severity.value,
        outcome_status=inc.outcome.status.value,
        protocols_csv=",".join(p.value for p in inc.symptom.protocols),
        topology_hash=inc.context.topology_hash,
        occurred_at=inc.occurred_at,
        created_at=inc.created_at,
        updated_at=inc.updated_at,
        embedding_text=inc.embedding_text,
        embedding_model=inc.embedding_model,
        data=inc.model_dump(mode="json"),
    )


def _incident_from_row(row: IncidentRow) -> Incident:
    return Incident.model_validate(row.data)


class IncidentRepo:
    def __init__(self, session: Session):
        self.s = session

    # ---- writes -------------------------------------------------------------
    def upsert(self, inc: Incident) -> Incident:
        existing = self.s.get(IncidentRow, str(inc.id))
        inc.updated_at = datetime.now(timezone.utc)
        row = _row_from_incident(inc)
        if existing is None:
            self.s.add(row)
        else:
            if existing.network_id != inc.network_id:
                raise PermissionError("tenant mismatch on incident upsert")
            for col in (
                "title", "affected_layer", "signature", "scope", "severity",
                "outcome_status", "protocols_csv", "topology_hash", "occurred_at",
                "updated_at", "embedding_text", "embedding_model", "data",
            ):
                setattr(existing, col, getattr(row, col))
        self.s.flush()
        return inc

    def update_outcome(self, network_id: str, incident_id: str, outcome: OutcomeRecord) -> Incident | None:
        row = self._get_row(network_id, incident_id)
        if row is None:
            return None
        inc = _incident_from_row(row)
        inc.outcome = outcome
        inc.updated_at = datetime.now(timezone.utc)
        row.outcome_status = outcome.status.value
        row.updated_at = inc.updated_at
        row.data = inc.model_dump(mode="json")
        self.s.flush()
        return inc

    # ---- reads --------------------------------------------------------------
    def _get_row(self, network_id: str, incident_id: str) -> IncidentRow | None:
        row = self.s.get(IncidentRow, incident_id)
        if row is None or row.network_id != network_id:
            return None  # never leak across tenants
        return row

    def get(self, network_id: str, incident_id: str) -> Incident | None:
        row = self._get_row(network_id, incident_id)
        return _incident_from_row(row) if row else None

    def list_incidents(
        self,
        network_id: str,
        *,
        protocol: str | None = None,
        layer: str | None = None,
        outcome: Outcome | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        stmt = select(IncidentRow).where(IncidentRow.network_id == network_id)
        if protocol:
            stmt = stmt.where(IncidentRow.protocols_csv.like(f"%{protocol}%"))
        if layer:
            stmt = stmt.where(IncidentRow.affected_layer == layer)
        if outcome:
            stmt = stmt.where(IncidentRow.outcome_status == outcome.value)
        if since:
            stmt = stmt.where(IncidentRow.occurred_at >= since)
        if until:
            stmt = stmt.where(IncidentRow.occurred_at <= until)
        stmt = stmt.order_by(IncidentRow.occurred_at.desc()).limit(limit).offset(offset)
        return [_incident_from_row(r) for r in self.s.scalars(stmt).all()]

    def get_many(self, network_id: str, ids: list[str]) -> dict[str, Incident]:
        if not ids:
            return {}
        stmt = select(IncidentRow).where(
            IncidentRow.network_id == network_id, IncidentRow.id.in_(ids)
        )
        return {r.id: _incident_from_row(r) for r in self.s.scalars(stmt).all()}

    def stats(self, network_id: str) -> dict:
        rows = self.s.scalars(
            select(IncidentRow).where(IncidentRow.network_id == network_id)
        ).all()
        by_protocol: dict[str, int] = {}
        by_outcome: dict[str, int] = {}
        mttrs: list[int] = []
        for r in rows:
            for p in filter(None, r.protocols_csv.split(",")):
                by_protocol[p] = by_protocol.get(p, 0) + 1
            by_outcome[r.outcome_status] = by_outcome.get(r.outcome_status, 0) + 1
            mttr = (r.data.get("outcome") or {}).get("mttr_seconds")
            if isinstance(mttr, int):
                mttrs.append(mttr)
        return {
            "total": len(rows),
            "by_protocol": by_protocol,
            "by_outcome": by_outcome,
            "failed_fixes_remembered": by_outcome.get(Outcome.FAILED.value, 0),
            "avg_mttr_seconds": round(sum(mttrs) / len(mttrs)) if mttrs else None,
        }
