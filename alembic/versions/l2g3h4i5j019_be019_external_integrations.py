"""BE-019: external integrations and API client platform.

Creates tables:
  external_systems, api_credentials, external_references,
  external_assertions, idempotency_keys, webhook_subscriptions,
  webhook_events, webhook_deliveries, integration_events

Revision ID: l2g3h4i5j019
Revises: k1f2g3h4i018
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "l2g3h4i5j019"
down_revision = "k1f2g3h4i018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # external_systems
    op.create_table(
        "external_systems",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("system_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("code", name="uq_external_system_code"),
        sa.CheckConstraint(
            "system_type IN ('GOVERNMENT_PORTAL','FIELD_SYSTEM','PROJECT_MANAGEMENT',"
            "'DOCUMENT_SYSTEM','INSPECTION_SYSTEM','DATA_PLATFORM','OTHER')",
            name="ck_external_system_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name="ck_external_system_status",
        ),
    )
    op.create_index("ix_external_systems_org", "external_systems", ["organization_id"])
    op.create_index("ix_external_systems_code", "external_systems", ["code"])

    # api_credentials
    op.create_table(
        "api_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("credential_hash", sa.String(256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["api_clients.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_api_credentials_client", "api_credentials", ["client_id"])
    op.create_index(
        "ix_api_credentials_client_revoked", "api_credentials", ["client_id", "revoked_at"]
    )

    # external_references
    op.create_table(
        "external_references",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("external_system_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("external_version", sa.String(128), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["external_system_id"], ["external_systems.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "external_system_id",
            "resource_type",
            "external_id",
            name="uq_external_reference_source_id",
        ),
    )
    op.create_index("ix_external_references_system", "external_references", ["external_system_id"])
    op.create_index(
        "ix_external_references_resource",
        "external_references",
        ["resource_type", "resource_id"],
    )

    # external_assertions
    op.create_table(
        "external_assertions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("external_system_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("external_id", sa.String(512), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("api_client_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("request_id", sa.String(256), nullable=True),
        sa.ForeignKeyConstraint(
            ["external_system_id"], ["external_systems.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["api_client_id"], ["api_clients.id"]),
    )
    op.create_index("ix_external_assertions_system", "external_assertions", ["external_system_id"])
    op.create_index(
        "ix_external_assertions_resource",
        "external_assertions",
        ["resource_type", "resource_id"],
    )
    op.create_index("ix_external_assertions_ingested", "external_assertions", ["ingested_at"])

    # idempotency_keys
    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("request_hash", sa.String(256), nullable=False),
        sa.Column("result_payload", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["api_clients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("client_id", "idempotency_key", name="uq_idempotency_client_key"),
    )
    op.create_index("ix_idempotency_keys_client", "idempotency_keys", ["client_id"])
    op.create_index("ix_idempotency_keys_expires", "idempotency_keys", ["expires_at"])

    # webhook_subscriptions
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("external_system_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("endpoint_url", sa.String(2048), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column("subscribed_events", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("secret_hash", sa.String(256), nullable=False),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
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
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["external_system_id"], ["external_systems.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name="ck_webhook_subscription_status",
        ),
    )
    op.create_index(
        "ix_webhook_subscriptions_system", "webhook_subscriptions", ["external_system_id"]
    )
    op.create_index("ix_webhook_subscriptions_status", "webhook_subscriptions", ["status"])

    # webhook_events
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PUBLISHED', 'FAILED')",
            name="ck_webhook_event_status",
        ),
    )
    op.create_index("ix_webhook_events_status", "webhook_events", ["status", "created_at"])
    op.create_index("ix_webhook_events_project", "webhook_events", ["project_id"])

    # webhook_deliveries
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("webhook_event_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_status_code", sa.Integer, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["webhook_event_id"], ["webhook_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["webhook_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "webhook_event_id", "subscription_id", name="uq_webhook_delivery_event_sub"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'DELIVERED', 'RETRYING', 'FAILED', 'DISABLED')",
            name="ck_webhook_delivery_status",
        ),
    )
    op.create_index(
        "ix_webhook_deliveries_status_next", "webhook_deliveries", ["status", "next_attempt_at"]
    )
    op.create_index("ix_webhook_deliveries_event", "webhook_deliveries", ["webhook_event_id"])
    op.create_index(
        "ix_webhook_deliveries_subscription", "webhook_deliveries", ["subscription_id"]
    )

    # integration_events
    op.create_table(
        "integration_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PUBLISHED', 'FAILED')",
            name="ck_integration_event_status",
        ),
    )
    op.create_index("ix_integration_events_status", "integration_events", ["status", "created_at"])
    op.create_index(
        "ix_integration_events_aggregate",
        "integration_events",
        ["aggregate_type", "aggregate_id"],
    )
    op.create_index("ix_integration_events_project", "integration_events", ["project_id"])


def downgrade() -> None:
    op.drop_table("integration_events")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_events")
    op.drop_table("webhook_subscriptions")
    op.drop_table("idempotency_keys")
    op.drop_table("external_assertions")
    op.drop_table("external_references")
    op.drop_table("api_credentials")
    op.drop_table("external_systems")
