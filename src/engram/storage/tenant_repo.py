"""Tenant / API-key lookups. Maps an X-API-Key header to a network_id."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from engram.storage.orm import Tenant


class TenantRepo:
    def __init__(self, session: Session):
        self.s = session

    def resolve(self, api_key: str) -> str | None:
        """Return the network_id for an API key, or None if unknown."""
        row = self.s.get(Tenant, api_key)
        return row.network_id if row else None

    def upsert(self, api_key: str, network_id: str, name: str = "") -> Tenant:
        row = self.s.get(Tenant, api_key)
        if row is None:
            row = Tenant(
                api_key=api_key,
                network_id=network_id,
                name=name,
                created_at=datetime.now(timezone.utc),
            )
            self.s.add(row)
        else:
            row.network_id = network_id
            row.name = name or row.name
        self.s.flush()
        return row
