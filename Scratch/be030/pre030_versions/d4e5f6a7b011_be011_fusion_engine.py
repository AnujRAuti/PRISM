"""add BE-011 fusion engine (runs, signals, assessments, priorities, configs)

Revision ID: d4e5f6a7b011
Revises: c3d4e5f6a010
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "d4e5f6a7b011"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TARGETS = "'CLAIM', 'EVIDENCE'"
RUN_STATUSES = "'RUNNING', 'COMPLETED', 'FAILED'"
ASSESSMENT_VALUES = "'SUPPORTED', 'MIXED', 'CONTRADICTED', 'INSUFFICIENT_EVIDENCE', 'UNKNOWN'"
ASSESSMENT_STATUSES = "'ACTIVE', 'SUPERSEDED', 'INVALIDATED'"
PRIORITIES = "'LOW', 'NORMAL', 'HIGH', 'URGENT'"
SIGNAL_STATES = (
    "'POSITIVE', 'NEGATIVE', 'NEUTRAL', 'UNKNOWN', 'UNAVAILABLE', "
    "'CONFLICTING', 'NOT_APPLICABLE', 'NOT_GENERATED'"
)


def upgrade() -> None:
    op.create_table(
        "fusion_configurations",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("method_version", sa.String(length=50), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("thresholds", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("priority", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("signals", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", name="uq_fusion_config_version"),
    )

    op.create_table(
        "fusion_runs",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="RUNNING", nullable=False),
        sa.Column("method", sa.String(length=256), nullable=False),
        sa.Column("method_version", sa.String(length=50), nullable=False),
        sa.Column("configuration_version", sa.String(length=50), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"target_type IN ({TARGETS})", name="ck_fusion_target_type"),
        sa.CheckConstraint(f"status IN ({RUN_STATUSES})", name="ck_fusion_run_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fusion_runs_target", "fusion_runs", ["target_type", "target_id"])
    op.create_index("ix_fusion_runs_status", "fusion_runs", ["status"])
    op.create_index("ix_fusion_runs_created", "fusion_runs", ["created_at"])

    op.create_table(
        "fusion_signals",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("fusion_run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("signal_type", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=256), nullable=False),
        sa.Column("source_entity_id", UUID(as_uuid=False), nullable=True),
        sa.Column("source_analysis_run_id", UUID(as_uuid=False), nullable=True),
        sa.Column("raw_value", sa.JSON(), nullable=True),
        sa.Column("normalized_value", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("method", sa.String(length=256), nullable=False),
        sa.Column("method_version", sa.String(length=50), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"state IN ({SIGNAL_STATES})", name="ck_fusion_signal_state"),
        sa.ForeignKeyConstraint(["fusion_run_id"], ["fusion_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fusion_signals_run", "fusion_signals", ["fusion_run_id"])
    op.create_index("ix_fusion_signals_type", "fusion_signals", ["signal_type"])

    op.create_table(
        "integrity_assessments",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("fusion_run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", UUID(as_uuid=False), nullable=False),
        sa.Column("assessment_status", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("assessment_value", sa.String(length=50), nullable=False),
        sa.Column("integrity_score", sa.Float(), nullable=True),
        sa.Column("signal_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"target_type IN ({TARGETS})", name="ck_assessment_target"),
        sa.CheckConstraint(f"assessment_value IN ({ASSESSMENT_VALUES})", name="ck_assessment_value"),
        sa.CheckConstraint(f"assessment_status IN ({ASSESSMENT_STATUSES})", name="ck_assessment_status"),
        sa.ForeignKeyConstraint(["fusion_run_id"], ["fusion_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fusion_run_id", name="uq_assessment_run"),
    )
    op.create_index("ix_assessments_target", "integrity_assessments", ["target_type", "target_id"])
    op.create_index("ix_assessments_run", "integrity_assessments", ["fusion_run_id"])

    op.create_table(
        "review_priorities",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("fusion_run_id", UUID(as_uuid=False), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", UUID(as_uuid=False), nullable=False),
        sa.Column("priority", sa.String(length=50), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("signal_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"target_type IN ({TARGETS})", name="ck_priority_target"),
        sa.CheckConstraint(f"priority IN ({PRIORITIES})", name="ck_priority_value"),
        sa.ForeignKeyConstraint(["fusion_run_id"], ["fusion_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fusion_run_id", name="uq_priority_run"),
    )
    op.create_index("ix_priorities_target", "review_priorities", ["target_type", "target_id"])
    op.create_index("ix_priorities_run", "review_priorities", ["fusion_run_id"])


def downgrade() -> None:
    op.drop_index("ix_priorities_run", table_name="review_priorities")
    op.drop_index("ix_priorities_target", table_name="review_priorities")
    op.drop_table("review_priorities")
    op.drop_index("ix_assessments_run", table_name="integrity_assessments")
    op.drop_index("ix_assessments_target", table_name="integrity_assessments")
    op.drop_table("integrity_assessments")
    op.drop_index("ix_fusion_signals_type", table_name="fusion_signals")
    op.drop_index("ix_fusion_signals_run", table_name="fusion_signals")
    op.drop_table("fusion_signals")
    op.drop_index("ix_fusion_runs_created", table_name="fusion_runs")
    op.drop_index("ix_fusion_runs_status", table_name="fusion_runs")
    op.drop_index("ix_fusion_runs_target", table_name="fusion_runs")
    op.drop_table("fusion_runs")
    op.drop_table("fusion_configurations")
