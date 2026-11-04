"""Add analysis lifecycle events to the enforced audit vocabulary.

Revision ID: v2w3x4y5z032
Revises: u1v2w3x4y031
"""

from typing import Sequence, Union

from alembic import op

from backend.db.models import AUDIT_EVENT_TYPES


revision: str = "v2w3x4y5z032"
down_revision: Union[str, Sequence[str], None] = "u1v2w3x4y031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "audit_ledger_events"
CHECK_NAME = "ck_audit_ledger_event_type_domain"


def _event_type_in_list() -> str:
    return ", ".join(f"'{value}'" for value in sorted(AUDIT_EVENT_TYPES))


def upgrade() -> None:
    # Rebuild only the vocabulary CHECK; the append-only trigger is unchanged.
    op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    op.create_check_constraint(
        CHECK_NAME, TABLE, f"event_type IN ({_event_type_in_list()})"
    )


def downgrade() -> None:
    # Downgrade is deliberately refused: existing queued/started events cannot
    # be deleted or rewritten because the ledger is append-only.
    raise RuntimeError("BE-038 cannot downgrade an append-only audit vocabulary")
