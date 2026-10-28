"""add BE-003 evidence upload fields

Revision ID: c6e8a9d4b001
Revises: bb4bf0dd8fb7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6e8a9d4b001"
down_revision: Union[str, Sequence[str], None] = "bb4bf0dd8fb7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("evidence", "project_id", nullable=True)
    op.add_column(
        "evidence",
        sa.Column("storage_key", sa.String(length=1024), nullable=True, server_default="legacy/unknown"),
    )
    op.add_column(
        "evidence",
        sa.Column("file_size", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column(
        "evidence",
        sa.Column("status", sa.String(length=50), nullable=False, server_default="uploaded_quarantine"),
    )
    op.execute("UPDATE evidence SET storage_key = 'legacy/' || id, file_size = 0")
    op.alter_column("evidence", "storage_key", nullable=False)
    op.alter_column("evidence", "file_size", nullable=False)


def downgrade() -> None:
    op.drop_column("evidence", "status")
    op.drop_column("evidence", "file_size")
    op.drop_column("evidence", "storage_key")
    op.alter_column("evidence", "project_id", nullable=False)