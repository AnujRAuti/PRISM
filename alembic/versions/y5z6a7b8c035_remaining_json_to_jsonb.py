"""Align the remaining legacy JSON columns with the JSONB model contract.

Revision ID: y5z6a7b8c035
Revises: x4y5z6a7b034
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "y5z6a7b8c035"
down_revision: Union[str, Sequence[str], None] = "x4y5z6a7b034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSON_COLUMNS = (
    ("review_case_events", "metadata"),
    ("review_priorities", "signal_summary"),
)


def upgrade() -> None:
    for table_name, column_name in JSON_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.JSON(),
            type_=postgresql.JSONB(),
            postgresql_using=f'"{column_name}"::jsonb',
        )


def downgrade() -> None:
    for table_name, column_name in reversed(JSON_COLUMNS):
        op.alter_column(
            table_name,
            column_name,
            existing_type=postgresql.JSONB(),
            type_=sa.JSON(),
            postgresql_using=f'"{column_name}"::json',
        )
