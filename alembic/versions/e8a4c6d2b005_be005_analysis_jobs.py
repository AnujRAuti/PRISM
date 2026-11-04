"""add BE-005 analysis job lifecycle fields

Revision ID: e8a4c6d2b005
Revises: d7f3b2a1c004
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8a4c6d2b005"
down_revision: Union[str, Sequence[str], None] = "d7f3b2a1c004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analysis_jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analysis_jobs", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("analysis_jobs", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_jobs", "error")
    op.drop_column("analysis_jobs", "attempt_count")
    op.drop_column("analysis_jobs", "completed_at")
    op.drop_column("analysis_jobs", "started_at")