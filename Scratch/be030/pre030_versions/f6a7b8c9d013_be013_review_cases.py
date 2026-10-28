"""add BE-013 review cases (cases, generation configs/runs, events)

Revision ID: f6a7b8c9d013
Revises: e5f6a7b8c012
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "f6a7b8c9d013"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ORIGINS = "'SYSTEM_SIGNAL', 'AUTHORIZED_USER', 'CITIZEN_REPORT', 'EXTERNAL_SYSTEM'"
STATUSES = "'OPEN', 'ASSIGNED', 'INVESTIGATING', 'DECISION_PENDING', 'RESOLVED', 'ESCALATED'"
RUN_STATUSES = "'RUNNING', 'COMPLETED', 'FAILED'"


def upgrade() -> None:
    op.create_table(
        "case_generation_configurations",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", name="uq_case_generation_config_version"),
    )

    op.create_table(
        "case_generation_runs",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("fusion_run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("configuration_id", UUID(as_uuid=False), nullable=False),
        sa.Column("method", sa.String(length=256), nullable=False),
        sa.Column("method_version", sa.String(length=50), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=50), server_default="RUNNING", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status IN ({RUN_STATUSES})", name="ck_case_generation_run_status"),
        sa.ForeignKeyConstraint(["fusion_run_id"], ["fusion_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["configuration_id"], ["case_generation_configurations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_generation_runs_run", "case_generation_runs", ["fusion_run_id"])

    op.create_table(
        "review_cases",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("claim_id", UUID(as_uuid=False), nullable=True),
        sa.Column("evidence_id", UUID(as_uuid=False), nullable=True),
        sa.Column("fusion_run_id", UUID(as_uuid=False), nullable=True),
        sa.Column("case_generation_run_id", UUID(as_uuid=False), nullable=True),
        sa.Column("origin", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="OPEN", nullable=False),
        sa.Column("priority_band", sa.String(length=50), nullable=True),
        sa.Column("priority_value", sa.Float(), nullable=True),
        sa.Column("priority_source", sa.String(length=256), nullable=True),
        sa.Column("priority_config_version", sa.String(length=50), nullable=True),
        sa.Column("assigned_to", UUID(as_uuid=False), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.String(length=50), nullable=True),
        sa.Column("decision_rationale", sa.Text(), nullable=True),
        sa.Column("decided_by", UUID(as_uuid=False), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_to", UUID(as_uuid=False), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"origin IN ({ORIGINS})", name="ck_review_case_origin"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_review_case_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.ForeignKeyConstraint(["fusion_run_id"], ["fusion_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["case_generation_run_id"], ["case_generation_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_cases_project", "review_cases", ["project_id"])
    op.create_index("ix_review_cases_status", "review_cases", ["status"])
    op.create_index("ix_review_cases_priority", "review_cases", ["priority_band"])
    op.create_index("ix_review_cases_assigned", "review_cases", ["assigned_to"])
    op.create_index("ix_review_cases_run", "review_cases", ["fusion_run_id"])
    op.create_index("ix_review_cases_created", "review_cases", ["created_at"])
    # One active system-generated case per fusion run (DB-enforced; resolved
    # cases never block, manual origins never collide via NULL run ids).
    op.create_index(
        "uq_review_case_active_run",
        "review_cases",
        ["fusion_run_id"],
        unique=True,
        postgresql_where=sa.text("origin = 'SYSTEM_SIGNAL' AND status <> 'RESOLVED'"),
    )

    op.create_table(
        "review_case_events",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("case_id", UUID(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=50), nullable=True),
        sa.Column("to_status", sa.String(length=50), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=False), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["review_cases.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_case_events_case", "review_case_events", ["case_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_review_case_events_case", table_name="review_case_events")
    op.drop_table("review_case_events")
    op.drop_index("uq_review_case_active_run", table_name="review_cases")
    op.drop_index("ix_review_cases_created", table_name="review_cases")
    op.drop_index("ix_review_cases_run", table_name="review_cases")
    op.drop_index("ix_review_cases_assigned", table_name="review_cases")
    op.drop_index("ix_review_cases_priority", table_name="review_cases")
    op.drop_index("ix_review_cases_status", table_name="review_cases")
    op.drop_index("ix_review_cases_project", table_name="review_cases")
    op.drop_table("review_cases")
    op.drop_index("ix_case_generation_runs_run", table_name="case_generation_runs")
    op.drop_table("case_generation_runs")
    op.drop_table("case_generation_configurations")
