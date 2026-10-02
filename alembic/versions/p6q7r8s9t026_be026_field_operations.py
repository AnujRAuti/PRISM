"""BE-026: field operations and offline evidence capture tables.

Revision ID: p6q7r8s9t026
Revises: o5p6q7r8s025

Three additive tables only — ``evidence``, ``evidence_metadata``,
``user_role_assignments``, ``idempotency_keys`` and the audit ledger are not
touched, and no existing table gains a column:

* ``field_assignments`` — operational field work with a real lifecycle
  (revocation closes the row instead of deleting it);
* ``field_sessions`` — the server-minted execution context that stops a stale
  offline snapshot from authorizing itself;
* ``field_capture_operations`` — the idempotent synchronization ledger and
  provenance record, with client-asserted and server-observed timestamps in
  separate independently-nullable columns and GPS CHECKs that make "missing"
  un-collapsible into ``0,0``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "p6q7r8s9t026"
down_revision: Union[str, Sequence[str], None] = "o5p6q7r8s025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ASSIGNMENT_STATUSES = "'ACTIVE', 'RELEASED', 'REVOKED', 'EXPIRED'"
SESSION_STATUSES = "'ACTIVE', 'CLOSED', 'EXPIRED'"
OPERATION_STATUSES = "'PENDING', 'ACCEPTED', 'VALIDATION_FAILED', 'CONFLICT'"
CONFLICT_REASONS = (
    "'PAYLOAD_MISMATCH', 'ASSIGNMENT_REVOKED', 'ASSIGNMENT_EXPIRED',"
    " 'SESSION_CLOSED', 'OPERATION_SESSION_MISMATCH',"
    " 'CONTEXT_RESOURCE_MISSING', 'ASSIGNMENT_SUPERSEDED'"
)
LOCATION_SOURCES = "'DEVICE_GPS', 'DEVICE_MANUAL', 'CLIENT_INFERRED', 'UNKNOWN'"
RESOLUTION_STATUSES = "'UNRESOLVED', 'RESOLVED'"

TIMESTAMPTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "field_assignments",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=False), nullable=True),
        sa.Column("organizational_unit_id", UUID(as_uuid=False), nullable=True),
        sa.Column("claim_id", UUID(as_uuid=False), nullable=True),
        sa.Column("activity_id", UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("valid_from", TIMESTAMPTZ, nullable=True),
        sa.Column("expires_at", TIMESTAMPTZ, nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        sa.Column("revoked_by", UUID(as_uuid=False), nullable=True),
        sa.Column("revoked_at", TIMESTAMPTZ, nullable=True),
        sa.Column("closed_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint(f"status IN ({ASSIGNMENT_STATUSES})",
                           name="ck_field_assignment_status"),
        sa.CheckConstraint(
            "expires_at IS NULL OR valid_from IS NULL OR expires_at > valid_from",
            name="ck_field_assignment_validity_window"),
        sa.CheckConstraint("closed_reason IS NULL OR status <> 'ACTIVE'",
                           name="ck_field_assignment_closed_reason"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["organizational_unit_id"], ["organizational_units.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_field_assignments_active_general", "field_assignments",
        ["user_id", "project_id"], unique=True,
        postgresql_where=sa.text("status = 'ACTIVE' AND claim_id IS NULL"))
    op.create_index(
        "uq_field_assignments_active_claim", "field_assignments",
        ["user_id", "project_id", "claim_id"], unique=True,
        postgresql_where=sa.text("status = 'ACTIVE' AND claim_id IS NOT NULL"))
    op.create_index("ix_field_assignments_user_status", "field_assignments",
                    ["user_id", "status"])
    op.create_index("ix_field_assignments_project", "field_assignments", ["project_id"])

    op.create_table(
        "field_sessions",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("assignment_id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("session_label", sa.String(length=128), nullable=True),
        sa.Column("client_device_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("server_time_at_open", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("closed_at", TIMESTAMPTZ, nullable=True),
        sa.Column("close_reason", sa.String(length=255), nullable=True),
        sa.Column("last_sync_at", TIMESTAMPTZ, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint(f"status IN ({SESSION_STATUSES})",
                           name="ck_field_session_status"),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND closed_at IS NULL)"
            " OR (status <> 'ACTIVE' AND closed_at IS NOT NULL)",
            name="ck_field_session_close_shape"),
        sa.ForeignKeyConstraint(["assignment_id"], ["field_assignments.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_field_sessions_active_device", "field_sessions",
        ["assignment_id", "client_device_id"], unique=True,
        postgresql_where=sa.text("status = 'ACTIVE' AND client_device_id IS NOT NULL"))
    op.create_index("ix_field_sessions_user_status", "field_sessions",
                    ["user_id", "status"])
    op.create_index("ix_field_sessions_assignment", "field_sessions", ["assignment_id"])

    op.create_table(
        "field_capture_operations",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column("client_operation_id", sa.String(length=128), nullable=False),
        sa.Column("client_capture_id", sa.String(length=128), nullable=True),
        sa.Column("client_device_id", sa.String(length=128), nullable=True),
        sa.Column("session_id", UUID(as_uuid=False), nullable=True),
        sa.Column("assignment_id", UUID(as_uuid=False), nullable=True),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("claim_id", UUID(as_uuid=False), nullable=True),
        sa.Column("evidence_id", UUID(as_uuid=False), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("declared_content_type", sa.String(length=128), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("validation_errors", JSONB(), nullable=False,
                  server_default=sa.text("'[]'")),
        sa.Column("captured_at", TIMESTAMPTZ, nullable=True),
        sa.Column("queued_at", TIMESTAMPTZ, nullable=True),
        sa.Column("uploaded_at", TIMESTAMPTZ, nullable=True),
        sa.Column("received_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("processed_at", TIMESTAMPTZ, nullable=True),
        sa.Column("timestamp_flags", JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("capture_accuracy_m", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("altitude_m", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("location_source", sa.String(length=32), nullable=True),
        sa.Column("zero_island_confirmed", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
        sa.Column("conflict_reason", sa.String(length=64), nullable=True),
        sa.Column("conflict_detail", JSONB(), nullable=True),
        sa.Column("resolution_status", sa.String(length=32), server_default="UNRESOLVED",
                  nullable=False),
        sa.Column("resolved_by", UUID(as_uuid=False), nullable=True),
        sa.Column("resolved_at", TIMESTAMPTZ, nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolution_outcome", sa.String(length=32), nullable=True),
        sa.Column("sync_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("last_synced_at", TIMESTAMPTZ, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint("char_length(client_operation_id) >= 8",
                           name="ck_field_operations_operation_id_length"),
        sa.CheckConstraint(f"status IN ({OPERATION_STATUSES})",
                           name="ck_field_operations_status"),
        sa.CheckConstraint(
            "status <> 'VALIDATION_FAILED' OR validation_errors <> '[]'::jsonb",
            name="ck_field_operations_validation_shape"),
        sa.CheckConstraint("status <> 'PENDING' OR evidence_id IS NULL",
                           name="ck_field_operations_pending_is_reservation"),
        sa.CheckConstraint(f"conflict_reason IN ({CONFLICT_REASONS})",
                           name="ck_field_operations_conflict_reason"),
        sa.CheckConstraint(
            "(status = 'CONFLICT' AND conflict_reason IS NOT NULL)"
            " OR (status <> 'CONFLICT' AND conflict_reason IS NULL)",
            name="ck_field_operations_conflict_shape"),
        sa.CheckConstraint("resolution_status = 'UNRESOLVED' OR status = 'CONFLICT'",
                           name="ck_field_operations_resolution_needs_conflict"),
        sa.CheckConstraint(f"resolution_status IN ({RESOLUTION_STATUSES})",
                           name="ck_field_operations_resolution_status"),
        # Deliberately no "ACCEPTED implies evidence_id IS NOT NULL" CHECK: the
        # evidence FK is ON DELETE SET NULL, so a retention purge legitimately
        # clears the reference. The pairing is enforced in the service instead.
        sa.CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
                           name="ck_field_operations_latitude_range"),
        sa.CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
                           name="ck_field_operations_longitude_range"),
        sa.CheckConstraint("capture_accuracy_m IS NULL OR (capture_accuracy_m > 0"
                           " AND capture_accuracy_m <= 100000)",
                           name="ck_field_operations_accuracy_range"),
        sa.CheckConstraint("altitude_m IS NULL OR (altitude_m >= -1000 AND altitude_m <= 10000)",
                           name="ck_field_operations_altitude_range"),
        sa.CheckConstraint("num_nonnulls(latitude, longitude) IN (0, 2)",
                           name="ck_field_operations_coordinate_pair"),
        sa.CheckConstraint(
            "NOT (latitude = 0 AND longitude = 0 AND zero_island_confirmed IS NOT TRUE)",
            name="ck_field_operations_zero_island_confirmed"),
        sa.CheckConstraint("latitude IS NULL OR location_source IS NOT NULL",
                           name="ck_field_operations_source_when_located"),
        sa.CheckConstraint("capture_accuracy_m IS NULL OR latitude IS NOT NULL",
                           name="ck_field_operations_accuracy_needs_fix"),
        sa.CheckConstraint(
            f"location_source IS NULL OR location_source IN ({LOCATION_SOURCES})",
            name="ck_field_operations_location_source"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["field_sessions.id"]),
        sa.ForeignKeyConstraint(["assignment_id"], ["field_assignments.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_operation_id",
                            name="uq_field_operations_user_client_id"),
    )
    op.create_index("ix_field_operations_user_status", "field_capture_operations",
                    ["user_id", "status"])
    op.create_index("ix_field_operations_session", "field_capture_operations", ["session_id"])
    op.create_index("ix_field_operations_evidence", "field_capture_operations", ["evidence_id"])
    op.create_index(
        "ix_field_operations_open_conflicts", "field_capture_operations", ["created_at"],
        postgresql_where=sa.text("status = 'CONFLICT' AND resolution_status = 'UNRESOLVED'"))


def downgrade() -> None:
    op.drop_index("ix_field_operations_open_conflicts",
                  table_name="field_capture_operations")
    op.drop_index("ix_field_operations_evidence", table_name="field_capture_operations")
    op.drop_index("ix_field_operations_session", table_name="field_capture_operations")
    op.drop_index("ix_field_operations_user_status", table_name="field_capture_operations")
    op.drop_table("field_capture_operations")
    op.drop_index("ix_field_sessions_assignment", table_name="field_sessions")
    op.drop_index("ix_field_sessions_user_status", table_name="field_sessions")
    op.drop_index("uq_field_sessions_active_device", table_name="field_sessions")
    op.drop_table("field_sessions")
    op.drop_index("ix_field_assignments_project", table_name="field_assignments")
    op.drop_index("ix_field_assignments_user_status", table_name="field_assignments")
    op.drop_index("uq_field_assignments_active_claim", table_name="field_assignments")
    op.drop_index("uq_field_assignments_active_general", table_name="field_assignments")
    op.drop_table("field_assignments")
