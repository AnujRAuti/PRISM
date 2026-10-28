"""add BE-017 retention and data governance

Revision ID: j0e1f2g3h017
Revises: i9d0e1f2g016
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "j0e1f2g3h017"
down_revision: Union[str, Sequence[str], None] = "i9d0e1f2g016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RESOURCE_TYPES = (
    "'EVIDENCE', 'ANALYSIS_RESULT', 'FUSION_RUN', "
    "'REVIEW_CASE', 'EVIDENCE_REQUEST', 'AUDIT_LEDGER_EVENT'"
)
STATES = (
    "'ACTIVE', 'ELIGIBLE_FOR_ARCHIVE', 'ARCHIVED', "
    "'ELIGIBLE_FOR_DELETION', 'DELETION_PENDING', 'DELETED'"
)
SCOPES = "'GLOBAL', 'ORGANIZATION', 'ORGANIZATIONAL_UNIT', 'PROJECT'"
VERSION_STATUSES = "'DRAFT', 'ACTIVE', 'SUPERSEDED', 'RETIRED'"
HOLD_STATUSES = "'ACTIVE', 'RELEASED', 'EXPIRED', 'CANCELLED'"
HOLD_SCOPES = "'RESOURCE', 'PROJECT', 'CASE', 'CLAIM', 'ORGANIZATION'"
OPERATIONS = "'ARCHIVE', 'RESTORE', 'DELETE'"
OPERATION_STATUSES = "'RUNNING', 'COMPLETED', 'FAILED'"


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=False), nullable=True),
        sa.Column("organizational_unit_id", UUID(as_uuid=False), nullable=True),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"resource_type IN ({RESOURCE_TYPES})",
                           name="ck_retention_policy_resource"),
        sa.CheckConstraint(f"scope_type IN ({SCOPES})", name="ck_retention_policy_scope"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["organizational_unit_id"], ["organizational_units.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retention_policies_resource", "retention_policies", ["resource_type"])
    op.create_index("ix_retention_policies_project", "retention_policies", ["project_id"])
    op.create_index("ix_retention_policies_org", "retention_policies", ["organization_id"])

    op.create_table(
        "retention_policy_versions",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("policy_id", UUID(as_uuid=False), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=50), server_default="DRAFT", nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"status IN ({VERSION_STATUSES})",
                           name="ck_policy_version_status"),
        sa.ForeignKeyConstraint(["policy_id"], ["retention_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "version", name="uq_policy_version"),
    )
    op.create_index("ix_policy_versions_policy", "retention_policy_versions", ["policy_id"])

    op.create_table(
        "retention_states",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("organization_id", UUID(as_uuid=False), nullable=True),
        sa.Column("state", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("policy_version_id", UUID(as_uuid=False), nullable=True),
        sa.Column("anchor", sa.String(length=50), nullable=True),
        sa.Column("anchor_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiry_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_storage_key", sa.Text(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"state IN ({STATES})", name="ck_retention_state"),
        sa.ForeignKeyConstraint(["policy_version_id"], ["retention_policy_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource_type", "resource_id", name="uq_retention_state_resource"),
    )
    op.create_index("ix_retention_states_resource", "retention_states",
                    ["resource_type", "resource_id"])
    op.create_index("ix_retention_states_state", "retention_states", ["state"])
    op.create_index("ix_retention_states_expiry", "retention_states", ["expiry_timestamp"])
    op.create_index("ix_retention_states_project", "retention_states", ["project_id"])
    op.create_index("ix_retention_states_policy", "retention_states", ["policy_version_id"])

    op.create_table(
        "retention_holds",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("scope", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", UUID(as_uuid=False), nullable=True),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("claim_id", UUID(as_uuid=False), nullable=True),
        sa.Column("case_id", UUID(as_uuid=False), nullable=True),
        sa.Column("organization_id", UUID(as_uuid=False), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("authority", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        sa.Column("released_by", UUID(as_uuid=False), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"scope IN ({HOLD_SCOPES})", name="ck_hold_scope"),
        sa.CheckConstraint(f"status IN ({HOLD_STATUSES})", name="ck_hold_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["review_cases.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_holds_status", "retention_holds", ["status"])
    op.create_index("ix_holds_project", "retention_holds", ["project_id"])
    op.create_index("ix_holds_resource", "retention_holds", ["resource_type", "resource_id"])

    op.create_table(
        "retention_operations",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=False), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="RUNNING", nullable=False),
        sa.Column("policy_version_id", UUID(as_uuid=False), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=False), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"operation IN ({OPERATIONS})",
                           name="ck_retention_operation_type"),
        sa.CheckConstraint(f"status IN ({OPERATION_STATUSES})",
                           name="ck_retention_operation_status"),
        sa.ForeignKeyConstraint(["policy_version_id"], ["retention_policy_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retention_operations_resource", "retention_operations",
                    ["resource_type", "resource_id"])
    op.create_index("ix_retention_operations_status", "retention_operations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_retention_operations_status", table_name="retention_operations")
    op.drop_index("ix_retention_operations_resource", table_name="retention_operations")
    op.drop_table("retention_operations")
    op.drop_index("ix_holds_resource", table_name="retention_holds")
    op.drop_index("ix_holds_project", table_name="retention_holds")
    op.drop_index("ix_holds_status", table_name="retention_holds")
    op.drop_table("retention_holds")
    op.drop_index("ix_retention_states_policy", table_name="retention_states")
    op.drop_index("ix_retention_states_project", table_name="retention_states")
    op.drop_index("ix_retention_states_expiry", table_name="retention_states")
    op.drop_index("ix_retention_states_state", table_name="retention_states")
    op.drop_index("ix_retention_states_resource", table_name="retention_states")
    op.drop_table("retention_states")
    op.drop_index("ix_policy_versions_policy", table_name="retention_policy_versions")
    op.drop_table("retention_policy_versions")
    op.drop_index("ix_retention_policies_org", table_name="retention_policies")
    op.drop_index("ix_retention_policies_project", table_name="retention_policies")
    op.drop_index("ix_retention_policies_resource", table_name="retention_policies")
    op.drop_table("retention_policies")
