"""BE-022: publication, transparency & public evidence governance.

Revision ID: n4o5p6q7r022
Revises: m3n4o5p6q021
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "n4o5p6q7r022"
down_revision = "m3n4o5p6q021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- publication_policies: named policy identity ---
    op.create_table(
        "publication_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_publication_policy_name"),
    )

    # --- publication_policy_versions: immutable versioned rules ---
    op.create_table(
        "publication_policy_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("allowed_target_types", postgresql.JSONB(), nullable=False),
        sa.Column("public_fields", postgresql.JSONB(), nullable=False),
        sa.Column("prohibited_fields", postgresql.JSONB(), nullable=False),
        sa.Column("allow_media_exposure", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allow_derived_intelligence", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allow_review_outcomes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("min_authorization_level", sa.String(length=20), nullable=False, server_default="REVIEWER"),
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("require_separation_of_duties", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("location_precision", sa.String(length=20), nullable=False, server_default="HIDDEN"),
        sa.Column("retention_publication_duration_days", sa.Integer(), nullable=True),
        sa.Column("geographic_restrictions", postgresql.JSONB(), nullable=True),
        sa.Column("privacy_restrictions", postgresql.JSONB(), nullable=True),
        sa.Column("redaction_level", sa.String(length=20), nullable=False, server_default="STANDARD"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_publication_policy_version_status",
        ),
        sa.CheckConstraint(
            "min_authorization_level IN ('REVIEWER', 'SUPERVISOR', 'ADMINISTRATOR')",
            name="ck_publication_policy_auth_level",
        ),
        sa.CheckConstraint(
            "location_precision IN ('EXACT', 'APPROXIMATE', 'AREA', 'HIDDEN')",
            name="ck_publication_policy_location_precision",
        ),
        sa.CheckConstraint(
            "redaction_level IN ('NONE', 'STANDARD', 'STRICT')",
            name="ck_publication_policy_redaction",
        ),
        sa.CheckConstraint("required_approvals >= 1", name="ck_publication_policy_required_approvals"),
        sa.CheckConstraint("version ~ '^\\d+\\.\\d+$'", name="ck_publication_policy_version_format"),
        sa.ForeignKeyConstraint(["policy_id"], ["publication_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "version", name="uq_publication_policy_version"),
    )
    op.create_index(
        "uq_publication_policy_active_version",
        "publication_policy_versions",
        ["policy_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_publication_policy_versions_policy",
        "publication_policy_versions",
        ["policy_id"],
    )

    # --- public_identifiers: stable non-sensitive public IDs ---
    op.create_table(
        "public_identifiers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("public_id", sa.String(length=50), nullable=False),
        sa.Column("namespace", sa.String(length=20), nullable=False, server_default="POA"),
        sa.Column("identifier_type", sa.String(length=20), nullable=False, server_default="SEQUENTIAL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('PROJECT', 'ACTIVITY', 'CLAIM', 'EVIDENCE', "
            "'REVIEW_CASE', 'FUSION_ASSESSMENT')",
            name="ck_public_identifier_target_type",
        ),
        sa.CheckConstraint(
            "identifier_type IN ('SEQUENTIAL', 'HASHED', 'RANDOM')",
            name="ck_public_identifier_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_public_identifier_public_id"),
        sa.UniqueConstraint("target_type", "target_id", name="uq_public_identifier_target"),
    )
    op.create_index("ix_public_identifiers_public_id", "public_identifiers", ["public_id"])
    op.create_index(
        "ix_public_identifiers_target", "public_identifiers", ["target_type", "target_id"]
    )

    # --- publications: governed container, one per target ---
    op.create_table(
        "publications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=False),
        sa.Column("policy_version_id", sa.UUID(), nullable=True),
        sa.Column("public_id", sa.String(length=50), nullable=True),
        sa.Column("current_version_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("reviewer_id", sa.UUID(), nullable=True),
        sa.Column("approver_id", sa.UUID(), nullable=True),
        sa.Column("publisher_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unpublished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('PROJECT', 'ACTIVITY', 'CLAIM', 'EVIDENCE', "
            "'REVIEW_CASE', 'FUSION_ASSESSMENT')",
            name="ck_publication_target_type",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'PUBLISHED', "
            "'UNPUBLISHED', 'REJECTED')",
            name="ck_publication_status",
        ),
        sa.CheckConstraint("current_version_number >= 0", name="ck_publication_version_number"),
        sa.CheckConstraint(
            "(status = 'PUBLISHED') = (published_at IS NOT NULL AND unpublished_at IS NULL)",
            name="ck_publication_published_consistent",
        ),
        sa.CheckConstraint(
            "(status = 'UNPUBLISHED') = (unpublished_at IS NOT NULL)",
            name="ck_publication_unpublished_consistent",
        ),
        sa.ForeignKeyConstraint(["policy_id"], ["publication_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["policy_version_id"], ["publication_policy_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_type", "target_id", name="uq_publication_active_target"),
    )
    op.create_index("ix_publications_target", "publications", ["target_type", "target_id"])
    op.create_index("ix_publications_status", "publications", ["status"])
    op.create_index("ix_publications_public_id", "publications", ["public_id"])
    op.create_index("ix_publications_created", "publications", ["created_at"])

    # --- publication_versions: immutable snapshots ---
    op.create_table(
        "publication_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("public_id", sa.String(length=50), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("policy_version_id", sa.UUID(), nullable=True),
        sa.Column("source_version_references", postgresql.JSONB(), nullable=True),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("published_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unpublished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version_number >= 1", name="ck_publication_version_positive"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'PUBLISHED', "
            "'UNPUBLISHED', 'REJECTED')",
            name="ck_publication_version_status",
        ),
        sa.CheckConstraint(
            "(status = 'PUBLISHED') = (published_at IS NOT NULL AND unpublished_at IS NULL)",
            name="ck_publication_version_published_consistent",
        ),
        sa.ForeignKeyConstraint(
            ["publication_id"], ["publications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id"], ["publication_policy_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "publication_id", "version_number", name="uq_publication_version_number"
        ),
    )
    op.create_index(
        "ix_publication_versions_publication", "publication_versions", ["publication_id"]
    )
    op.create_index("ix_publication_versions_status", "publication_versions", ["status"])
    op.create_index("ix_publication_versions_public_id", "publication_versions", ["public_id"])
    op.create_index("ix_publication_versions_created", "publication_versions", ["created_at"])

    # --- publication_events: append-only workflow history ---
    op.create_table(
        "publication_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_publication_events_publication", "publication_events", ["publication_id", "created_at"]
    )
    op.create_index("ix_publication_events_created", "publication_events", ["created_at"])

    # --- public_media_derivatives: approved public-safe derivatives ---
    op.create_table(
        "public_media_derivatives",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.Column("publication_version_id", sa.UUID(), nullable=True),
        sa.Column("original_evidence_id", sa.UUID(), nullable=False),
        sa.Column("derivative_type", sa.String(length=20), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("storage_bucket", sa.String(length=100), nullable=False),
        sa.Column("transformation", sa.Text(), nullable=True),
        sa.Column("transformation_version", sa.String(length=20), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "derivative_type IN ('ORIGINAL', 'THUMBNAIL', 'PREVIEW', "
            "'REDACTED', 'TRANSCODED')",
            name="ck_public_media_derivative_type",
        ),
        sa.ForeignKeyConstraint(
            ["publication_id"], ["publications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["publication_version_id"], ["publication_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["original_evidence_id"], ["evidence.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_public_media_derivatives_publication", "public_media_derivatives", ["publication_id"]
    )
    op.create_index(
        "ix_public_media_derivatives_evidence", "public_media_derivatives", ["original_evidence_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_public_media_derivatives_evidence", table_name="public_media_derivatives")
    op.drop_index("ix_public_media_derivatives_publication", table_name="public_media_derivatives")
    op.drop_table("public_media_derivatives")

    op.drop_index("ix_publication_events_created", table_name="publication_events")
    op.drop_index("ix_publication_events_publication", table_name="publication_events")
    op.drop_table("publication_events")

    op.drop_index("ix_publication_versions_created", table_name="publication_versions")
    op.drop_index("ix_publication_versions_public_id", table_name="publication_versions")
    op.drop_index("ix_publication_versions_status", table_name="publication_versions")
    op.drop_index("ix_publication_versions_publication", table_name="publication_versions")
    op.drop_table("publication_versions")

    op.drop_index("ix_publications_created", table_name="publications")
    op.drop_index("ix_publications_public_id", table_name="publications")
    op.drop_index("ix_publications_status", table_name="publications")
    op.drop_index("ix_publications_target", table_name="publications")
    op.drop_table("publications")

    op.drop_index("ix_public_identifiers_target", table_name="public_identifiers")
    op.drop_index("ix_public_identifiers_public_id", table_name="public_identifiers")
    op.drop_table("public_identifiers")

    op.drop_index("ix_publication_policy_versions_policy", table_name="publication_policy_versions")
    op.drop_index("uq_publication_policy_active_version", table_name="publication_policy_versions")
    op.drop_table("publication_policy_versions")

    op.drop_table("publication_policies")
