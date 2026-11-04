"""add BE-008 claim temporal boundaries

Revision ID: a1b2c3d4e008
Revises: f9b5d7e3c006
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e008"
down_revision: Union[str, Sequence[str], None] = "f9b5d7e3c006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("temporal_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("claims", sa.Column("temporal_end_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("claims", "temporal_end_at")
    op.drop_column("claims", "temporal_start_at")
