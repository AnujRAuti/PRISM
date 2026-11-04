"""BE-021: dispute, correction & intelligence invalidation governance.

Adds:
  - staleness columns on analysis_jobs / fusion_runs / explanation_runs
  - disputes, dispute_events
  - correction_requests, correction_events
  - intelligence_invalidations, reprocessing_requests

Historical rows are never rewritten: staleness marks derived intelligence
as CURRENT/STALE/INVALIDATED/SUPERSEDED while the underlying records stay
queryable. Partial unique indexes enforce idempotency for active disputes
(one active challenge per target+initiator) and pending reprocessing
requests (one pending request per evidence item).

Revision ID: m3n4o5p6q021
Revises: l2g3h4i5j019
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "m3n4o5p6q021"
down_revision = "l2g3h4i5j019"
branch_labels = None
depends_on = None


STALENESS_CHECK = "staleness IN ('CURRENT', 'STALE', 'INVALIDATED', 'SUPERSEDED')"


def upgrade() -> None:
    # --- staleness columns on derived intelligence -------------------------
    for table in ("analysis_jobs", "fusion_runs", "explanation_runs"):
        op.add_column(
            table,
            sa.Column(
                "staleness",
                sa.String(20),
                nullable=False,
                server_default="CURRENT",
            ),
        )
    op.create_check_constraint(
        "ck_analysis_job_staleness", "analysis_jobs", STALENESS_CHECK
    )
    op.create_check_constraint("ck_fusion_run_staleness", "fusion_runs", STALENESS_CHECK)
    op.create_check_constraint(
        "ck_explanation_run_staleness", "explanation_runs", STALENESS_CHECK
    )
    op.create_index("ix_analysis_jobs_staleness", "analysis_jobs", ["staleness"])
    op.create_index("ix_fusion_runs_staleness", "fusion_runs", ["staleness"])
    op.create_index("ix_explanation_runs_staleness", "explanation_runs", ["staleness"])

    # --- disputes -----------------------------------------------------------
    op.create_table(
        "disputes",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("initiator_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="OPEN"),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_to", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        sa.Column("resolution", sa.String(50), nullable=True),
        sa.Column("resolution_rationale", sa.Text(), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.CheckConstraint(
            "target_type IN ('EVIDENCE', 'EVIDENCE_CLAIM_RELATIONSHIP', 'CLAIM', "
            "'EXTERNAL_ASSERTION', 'FUSION_ASSESSMENT', 'REVIEW_CASE')",
            name="ck_dispute_target_type",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'UNDER_REVIEW', 'RESOLVED', 'REJECTED', "
            "'WITHDRAWN', 'ESCALATED')",
            name="ck_dispute_status",
        ),
        sa.CheckConstraint(
            "resolution IN ('UPHELD', 'REJECTED', 'INCONCLUSIVE', "
            "'INSUFFICIENT_EVIDENCE') OR resolution IS NULL",
            name="ck_dispute_resolution",
        ),
        sa.CheckConstraint(
            "(resolution IS NULL AND resolved_by IS NULL AND resolved_at IS NULL) "
            "OR (resolution IS NOT NULL AND resolved_by IS NOT NULL "
            "AND resolved_at IS NOT NULL)",
            name="ck_dispute_resolution_complete",
        ),
        sa.CheckConstraint(
            "(resolution IS NULL) = (status <> 'RESOLVED')",
            name="ck_dispute_resolution_status_consistent",
        ),
    )
    op.create_index("ix_disputes_target", "disputes", ["target_type", "target_id"])
    op.create_index("ix_disputes_status", "disputes", ["status"])
    op.create_index("ix_disputes_project", "disputes", ["project_id"])
    op.create_index("ix_disputes_initiator", "disputes", ["initiator_id"])
    op.create_index("ix_disputes_assigned", "disputes", ["assigned_to"])
    op.create_index("ix_disputes_created", "disputes", ["created_at"])
    op.create_index(
        "uq_disputes_active_target_initiator",
        "disputes",
        ["target_type", "target_id", "initiator_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('OPEN', 'UNDER_REVIEW', 'ESCALATED')"),
    )

    # --- dispute_events (append-only) ---------------------------------------
    op.create_table(
        "dispute_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("dispute_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("from_status", sa.String(50), nullable=True),
        sa.Column("to_status", sa.String(50), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"], ["disputes.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_dispute_events_dispute", "dispute_events", ["dispute_id", "created_at"]
    )

    # --- correction_requests -------------------------------------------------
    op.create_table(
        "correction_requests",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column(
            "requested_change", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="REQUESTED"
        ),
        sa.Column("resolver_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("resolution_rationale", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_change", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.CheckConstraint(
            "target_type IN ('EVIDENCE')", name="ck_correction_target_type"
        ),
        sa.CheckConstraint(
            "category IN ('PROJECT_ASSOCIATION', 'CLAIM_ASSOCIATION', "
            "'LOCATION_CONTEXT', 'CONTEXTUAL_METADATA', 'DESCRIPTIVE_FIELD', "
            "'EVIDENCE_FILE')",
            name="ck_correction_category",
        ),
        sa.CheckConstraint(
            "status IN ('REQUESTED', 'UNDER_REVIEW', 'APPROVED', 'APPLIED', "
            "'REJECTED', 'CANCELLED')",
            name="ck_correction_status",
        ),
        sa.CheckConstraint(
            "(status = 'APPLIED') = (applied_at IS NOT NULL AND applied_by IS NOT NULL)",
            name="ck_correction_application_consistent",
        ),
    )
    op.create_index(
        "ix_correction_requests_target",
        "correction_requests",
        ["target_type", "target_id"],
    )
    op.create_index("ix_correction_requests_status", "correction_requests", ["status"])
    op.create_index(
        "ix_correction_requests_project", "correction_requests", ["project_id"]
    )
    op.create_index(
        "ix_correction_requests_requester", "correction_requests", ["requester_id"]
    )
    op.create_index(
        "ix_correction_requests_created", "correction_requests", ["created_at"]
    )
    # Idempotency (§28): at most one ACTIVE request per
    # (target, category, requester) — mirrors models.py partial unique.
    op.create_index(
        "uq_correction_active_target_category_requester",
        "correction_requests",
        ["target_type", "target_id", "category", "requester_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('REQUESTED', 'UNDER_REVIEW', 'APPROVED')"
        ),
    )

    # --- correction_events (append-only) ------------------------------------
    op.create_table(
        "correction_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("correction_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("from_status", sa.String(50), nullable=True),
        sa.Column("to_status", sa.String(50), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["correction_id"], ["correction_requests.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_correction_events_correction",
        "correction_events",
        ["correction_id", "created_at"],
    )

    # --- intelligence_invalidations -----------------------------------------
    op.create_table(
        "intelligence_invalidations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("cause", sa.String(50), nullable=False),
        sa.Column("dispute_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("correction_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("invalidated_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "affected_analysis", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "affected_fusion", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "affected_explanations", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "affected_relationships", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "affected_assessments", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(
            ["dispute_id"], ["disputes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["correction_id"], ["correction_requests.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "target_type IN ('EVIDENCE', 'EVIDENCE_CLAIM_RELATIONSHIP', 'CLAIM', "
            "'EXTERNAL_ASSERTION', 'FUSION_ASSESSMENT', 'REVIEW_CASE')",
            name="ck_invalidation_target_type",
        ),
        sa.CheckConstraint(
            "cause IN ('DISPUTE', 'CORRECTION', 'DIRECT')", name="ck_invalidation_cause"
        ),
    )
    op.create_index(
        "ix_intelligence_invalidations_target",
        "intelligence_invalidations",
        ["target_type", "target_id"],
    )
    op.create_index(
        "ix_intelligence_invalidations_dispute",
        "intelligence_invalidations",
        ["dispute_id"],
    )
    op.create_index(
        "ix_intelligence_invalidations_correction",
        "intelligence_invalidations",
        ["correction_id"],
    )
    op.create_index(
        "ix_intelligence_invalidations_created",
        "intelligence_invalidations",
        ["created_at"],
    )

    # --- reprocessing_requests ----------------------------------------------
    op.create_table(
        "reprocessing_requests",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("invalidation_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="PENDING"
        ),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["invalidation_id"],
            ["intelligence_invalidations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"], ["analysis_jobs.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'COMPLETED', 'FAILED')",
            name="ck_reprocessing_status",
        ),
    )
    op.create_index(
        "ix_reprocessing_requests_evidence", "reprocessing_requests", ["evidence_id"]
    )
    op.create_index("ix_reprocessing_requests_status", "reprocessing_requests", ["status"])
    op.create_index(
        "ix_reprocessing_requests_invalidation",
        "reprocessing_requests",
        ["invalidation_id"],
    )
    op.create_index(
        "ix_reprocessing_requests_created", "reprocessing_requests", ["created_at"]
    )
    op.create_index(
        "uq_reprocessing_pending_evidence",
        "reprocessing_requests",
        ["evidence_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    # reprocessing_requests
    op.drop_index("uq_reprocessing_pending_evidence", table_name="reprocessing_requests")
    op.drop_index("ix_reprocessing_requests_created", table_name="reprocessing_requests")
    op.drop_index(
        "ix_reprocessing_requests_invalidation", table_name="reprocessing_requests"
    )
    op.drop_index("ix_reprocessing_requests_status", table_name="reprocessing_requests")
    op.drop_index(
        "ix_reprocessing_requests_evidence", table_name="reprocessing_requests"
    )
    op.drop_table("reprocessing_requests")

    # intelligence_invalidations
    op.drop_index(
        "ix_intelligence_invalidations_created", table_name="intelligence_invalidations"
    )
    op.drop_index(
        "ix_intelligence_invalidations_correction",
        table_name="intelligence_invalidations",
    )
    op.drop_index(
        "ix_intelligence_invalidations_dispute", table_name="intelligence_invalidations"
    )
    op.drop_index(
        "ix_intelligence_invalidations_target", table_name="intelligence_invalidations"
    )
    op.drop_table("intelligence_invalidations")

    # correction_events
    op.drop_index(
        "ix_correction_events_correction", table_name="correction_events"
    )
    op.drop_table("correction_events")

    # correction_requests
    op.drop_index(
        "ix_correction_requests_created", table_name="correction_requests"
    )
    op.drop_index(
        "uq_correction_active_target_category_requester",
        table_name="correction_requests",
    )
    op.drop_index(
        "ix_correction_requests_requester", table_name="correction_requests"
    )
    op.drop_index(
        "ix_correction_requests_project", table_name="correction_requests"
    )
    op.drop_index("ix_correction_requests_status", table_name="correction_requests")
    op.drop_index(
        "ix_correction_requests_target", table_name="correction_requests"
    )
    op.drop_table("correction_requests")

    # dispute_events
    op.drop_index("ix_dispute_events_dispute", table_name="dispute_events")
    op.drop_table("dispute_events")

    # disputes
    op.drop_index("uq_disputes_active_target_initiator", table_name="disputes")
    op.drop_index("ix_disputes_created", table_name="disputes")
    op.drop_index("ix_disputes_assigned", table_name="disputes")
    op.drop_index("ix_disputes_initiator", table_name="disputes")
    op.drop_index("ix_disputes_project", table_name="disputes")
    op.drop_index("ix_disputes_status", table_name="disputes")
    op.drop_index("ix_disputes_target", table_name="disputes")
    op.drop_table("disputes")

    # staleness columns
    op.drop_index("ix_explanation_runs_staleness", table_name="explanation_runs")
    op.drop_index("ix_fusion_runs_staleness", table_name="fusion_runs")
    op.drop_index("ix_analysis_jobs_staleness", table_name="analysis_jobs")
    op.drop_column("explanation_runs", "staleness")
    op.drop_column("fusion_runs", "staleness")
    op.drop_column("analysis_jobs", "staleness")
