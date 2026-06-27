"""SQLAlchemy 2.0 ORM models.

Two tables:
  tenants    — maps an API key -> network_id (the multi-tenant boundary)
  incidents  — the structured store. The full Pydantic Incident is kept in `data`
               (JSONB) for fidelity, while hot fields are promoted to real columns
               so they can be indexed and filtered cheaply in Postgres.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    api_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    network_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IncidentRow(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    network_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # promoted hot fields (for cheap structured filters in Postgres)
    title: Mapped[str] = mapped_column(String(512), default="")
    affected_layer: Mapped[str] = mapped_column(String(16), default="UNKNOWN", index=True)
    signature: Mapped[str] = mapped_column(String(128), default="", index=True)
    scope: Mapped[str] = mapped_column(String(32), default="DEVICE")
    severity: Mapped[str] = mapped_column(String(16), default="SEV3")
    outcome_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN", index=True)
    # protocols/devices stored as comma-joined for simple LIKE filtering + in JSONB for truth
    protocols_csv: Mapped[str] = mapped_column(String(255), default="")
    topology_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    embedding_text: Mapped[str] = mapped_column(Text, default="")
    embedding_model: Mapped[str] = mapped_column(String(128), default="")

    # full fidelity copy of the Pydantic Incident
    data: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        Index("ix_incidents_network_layer", "network_id", "affected_layer"),
        Index("ix_incidents_network_signature", "network_id", "signature"),
        Index("ix_incidents_network_outcome", "network_id", "outcome_status"),
    )
