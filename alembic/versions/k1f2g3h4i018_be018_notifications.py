"""add BE-018 notifications and event delivery

Revision ID: k1f2g3h4i018
Revises: j0e1f2g3h017
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "k1f2g3h4i018"
down_revision: Union[str, Sequence[str], None] = "j0e1f2g3h017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NOTIFICATION_STATUSES = "'UNREAD', 'READ'"
NOTIFICATION_SEVERITIES = "'INFO', 'WARNING', 'CRITICAL'"
NOTIFICATION_CHANNELS = "'IN_APP', 'EMAIL'"
DELIVERY_STATUSES = "'PENDING', 'PROCESSING', 'DELIVERED', 'FAILED', 'RETRYING', 'CANCELLED'"
OUTBOX_STATUSES = "'PENDING', 'PROCESSING', 'PUBLISHED', 'FAILED'"


def upgrade() -> None:
    # 1. notifications table
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("recipient_id", UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=False), nullable=True),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("notification_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", UUID(as_uuid=False), nullable=True),
        sa.Column("severity", sa.String(length=20), server_default="INFO", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="UNREAD", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({NOTIFICATION_STATUSES})", name="ck_notification_status"
        ),
        sa.CheckConstraint(
            f"severity IN ({NOTIFICATION_SEVERITIES})", name="ck_notification_severity"
        ),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_recipient_status",
        "notifications",
        ["recipient_id", "status"],
    )
    op.create_index("ix_notifications_project", "notifications", ["project_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    # 2. notification_deliveries table
    op.create_table(
        "notification_deliveries",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("notification_id", UUID(as_uuid=False), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_message_id", sa.String(length=256), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"channel IN ({NOTIFICATION_CHANNELS})", name="ck_notification_delivery_channel"
        ),
        sa.CheckConstraint(
            f"status IN ({DELIVERY_STATUSES})", name="ck_notification_delivery_status"
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "channel", name="uq_delivery_notification_channel"),
    )
    op.create_index(
        "ix_notification_deliveries_status_next_attempt",
        "notification_deliveries",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_notification_deliveries_notification",
        "notification_deliveries",
        ["notification_id"],
    )

    # 3. notification_preferences table
    op.create_table(
        "notification_preferences",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column("notification_type", sa.String(length=50), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("email_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "notification_type", name="uq_notification_preference_user_type"
        ),
    )
    op.create_index("ix_notification_preferences_user", "notification_preferences", ["user_id"])

    # 4. notification_outbox table
    op.create_table(
        "notification_outbox",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_id", UUID(as_uuid=False), nullable=False),
        sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"status IN ({OUTBOX_STATUSES})", name="ck_notification_outbox_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_outbox_status",
        "notification_outbox",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_status", table_name="notification_outbox")
    op.drop_table("notification_outbox")

    op.drop_index("ix_notification_preferences_user", table_name="notification_preferences")
    op.drop_table("notification_preferences")

    op.drop_index(
        "ix_notification_deliveries_notification", table_name="notification_deliveries"
    )
    op.drop_index(
        "ix_notification_deliveries_status_next_attempt",
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")

    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_project", table_name="notifications")
    op.drop_index("ix_notifications_recipient_status", table_name="notifications")
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_table("notifications")

