"""add BE-015 tamper-evident audit ledger (audit_ledger_events)

Revision ID: h8c9d0e1f015
Revises: g7b8c9d0e014
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "h8c9d0e1f015"
down_revision: Union[str, Sequence[str], None] = "g7b8c9d0e014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_ledger_events",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=False), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=False), nullable=True),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("previous_hash", sa.String(length=256), nullable=False),
        sa.Column("event_hash", sa.String(length=256), nullable=False),
        sa.Column("hash_algorithm", sa.String(length=50), nullable=False,
                  server_default="SHA-256"),
        sa.Column("ledger_version", sa.String(length=50), nullable=False,
                  server_default="audit-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sequence_number", name="uq_audit_ledger_sequence"),
    )
    op.create_index("ix_audit_ledger_sequence", "audit_ledger_events", ["sequence_number"])
    op.create_index("ix_audit_ledger_created", "audit_ledger_events", ["created_at"])
    op.create_index("ix_audit_ledger_actor", "audit_ledger_events", ["actor_id"])
    op.create_index("ix_audit_ledger_type", "audit_ledger_events", ["event_type"])
    op.create_index(
        "ix_audit_ledger_resource", "audit_ledger_events", ["resource_type", "resource_id"]
    )
    op.create_index("ix_audit_ledger_project", "audit_ledger_events", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_ledger_project", table_name="audit_ledger_events")
    op.drop_index("ix_audit_ledger_resource", table_name="audit_ledger_events")
    op.drop_index("ix_audit_ledger_type", table_name="audit_ledger_events")
    op.drop_index("ix_audit_ledger_actor", table_name="audit_ledger_events")
    op.drop_index("ix_audit_ledger_created", table_name="audit_ledger_events")
    op.drop_index("ix_audit_ledger_sequence", table_name="audit_ledger_events")
    op.drop_table("audit_ledger_events")
