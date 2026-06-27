"""initial schema: tenants + incidents

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-27
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("api_key", sa.String(length=128), primary_key=True),
        sa.Column("network_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenants_network_id", "tenants", ["network_id"])

    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("network_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), server_default="", nullable=False),
        sa.Column("affected_layer", sa.String(length=16), server_default="UNKNOWN", nullable=False),
        sa.Column("signature", sa.String(length=128), server_default="", nullable=False),
        sa.Column("scope", sa.String(length=32), server_default="DEVICE", nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="SEV3", nullable=False),
        sa.Column("outcome_status", sa.String(length=16), server_default="UNKNOWN", nullable=False),
        sa.Column("protocols_csv", sa.String(length=255), server_default="", nullable=False),
        sa.Column("topology_hash", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("embedding_text", sa.Text(), server_default="", nullable=False),
        sa.Column("embedding_model", sa.String(length=128), server_default="", nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_incidents_network_id", "incidents", ["network_id"])
    op.create_index("ix_incidents_affected_layer", "incidents", ["affected_layer"])
    op.create_index("ix_incidents_signature", "incidents", ["signature"])
    op.create_index("ix_incidents_outcome_status", "incidents", ["outcome_status"])
    op.create_index("ix_incidents_occurred_at", "incidents", ["occurred_at"])
    op.create_index("ix_incidents_network_layer", "incidents", ["network_id", "affected_layer"])
    op.create_index("ix_incidents_network_signature", "incidents", ["network_id", "signature"])
    op.create_index("ix_incidents_network_outcome", "incidents", ["network_id", "outcome_status"])


def downgrade() -> None:
    op.drop_table("incidents")
    op.drop_index("ix_tenants_network_id", table_name="tenants")
    op.drop_table("tenants")
