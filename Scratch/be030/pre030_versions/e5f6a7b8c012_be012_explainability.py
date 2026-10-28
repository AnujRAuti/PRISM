"""add BE-012 explainability (explanation_runs)

Revision ID: e5f6a7b8c012
Revises: d4e5f6a7b011
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "e5f6a7b8c012"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATUSES = "'GENERATED', 'FAILED'"


def upgrade() -> None:
    op.create_table(
        "explanation_runs",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("fusion_run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="GENERATED", nullable=False),
        sa.Column("method", sa.String(length=256), nullable=False),
        sa.Column("method_version", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_explanation_run_status"),
        sa.ForeignKeyConstraint(["fusion_run_id"], ["fusion_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fusion_run_id", name="uq_explanation_run"),
    )
    op.create_index("ix_explanation_runs_run", "explanation_runs", ["fusion_run_id"])


def downgrade() -> None:
    op.drop_index("ix_explanation_runs_run", table_name="explanation_runs")
    op.drop_table("explanation_runs")
