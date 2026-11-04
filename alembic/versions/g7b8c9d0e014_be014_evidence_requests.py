"""add BE-014 evidence requests (requests, items, events)

Revision ID: g7b8c9d0e014
Revises: f6a7b8c9d013
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "g7b8c9d0e014"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATUSES = (
    "'DRAFT', 'OPEN', 'ACKNOWLEDGED', 'FULFILLED', "
    "'PARTIALLY_FULFILLED', 'DECLINED', 'EXPIRED', 'CANCELLED'"
)
PRIORITIES = "'LOW', 'NORMAL', 'HIGH', 'URGENT'"
ITEM_STATUSES = "'REQUESTED', 'RECEIVED', 'ACCEPTED_FOR_REQUEST', 'REJECTED_FOR_REQUEST'"


def upgrade() -> None:
    op.create_table(
        "evidence_requests",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("review_case_id", UUID(as_uuid=False), nullable=True),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("activity_id", UUID(as_uuid=False), nullable=True),
        sa.Column("claim_id", UUID(as_uuid=False), nullable=True),
        sa.Column("evidence_id", UUID(as_uuid=False), nullable=True),
        sa.Column("requester_id", UUID(as_uuid=False), nullable=True),
        sa.Column("recipient_id", UUID(as_uuid=False), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.String(length=50), server_default="NORMAL", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="DRAFT", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_evidence_request_status"),
        sa.CheckConstraint(f"priority IN ({PRIORITIES})", name="ck_evidence_request_priority"),
        sa.ForeignKeyConstraint(["review_case_id"], ["review_cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_requests_project", "evidence_requests", ["project_id"])
    op.create_index("ix_evidence_requests_case", "evidence_requests", ["review_case_id"])
    op.create_index("ix_evidence_requests_status", "evidence_requests", ["status"])
    op.create_index("ix_evidence_requests_priority", "evidence_requests", ["priority"])
    op.create_index("ix_evidence_requests_requester", "evidence_requests", ["requester_id"])
    op.create_index("ix_evidence_requests_recipient", "evidence_requests", ["recipient_id"])
    op.create_index("ix_evidence_requests_due", "evidence_requests", ["due_at"])

    op.create_table(
        "evidence_request_items",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("request_id", UUID(as_uuid=False), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("evidence_id", UUID(as_uuid=False), nullable=True),
        sa.Column("item_status", sa.String(length=50), server_default="REQUESTED", nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_by", UUID(as_uuid=False), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"item_status IN ({ITEM_STATUSES})", name="ck_evidence_request_item_status"),
        sa.ForeignKeyConstraint(["request_id"], ["evidence_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "evidence_id", name="uq_request_evidence_link"),
    )
    op.create_index("ix_evidence_request_items_request", "evidence_request_items", ["request_id"])
    op.create_index("ix_evidence_request_items_evidence", "evidence_request_items", ["evidence_id"])

    op.create_table(
        "evidence_request_events",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("request_id", UUID(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=50), nullable=True),
        sa.Column("to_status", sa.String(length=50), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=False), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["evidence_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_request_events_request", "evidence_request_events", ["request_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_request_events_request", table_name="evidence_request_events")
    op.drop_table("evidence_request_events")
    op.drop_index("ix_evidence_request_items_evidence", table_name="evidence_request_items")
    op.drop_index("ix_evidence_request_items_request", table_name="evidence_request_items")
    op.drop_table("evidence_request_items")
    op.drop_index("ix_evidence_requests_due", table_name="evidence_requests")
    op.drop_index("ix_evidence_requests_recipient", table_name="evidence_requests")
    op.drop_index("ix_evidence_requests_requester", table_name="evidence_requests")
    op.drop_index("ix_evidence_requests_priority", table_name="evidence_requests")
    op.drop_index("ix_evidence_requests_status", table_name="evidence_requests")
    op.drop_index("ix_evidence_requests_case", table_name="evidence_requests")
    op.drop_index("ix_evidence_requests_project", table_name="evidence_requests")
    op.drop_table("evidence_requests")
