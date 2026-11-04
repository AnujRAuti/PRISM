"""add BE-004 evidence fingerprints

Revision ID: d7f3b2a1c004
Revises: c6e8a9d4b001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7f3b2a1c004"
down_revision: Union[str, Sequence[str], None] = "c6e8a9d4b001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("sha256", sa.String(length=64), nullable=True))
    op.add_column("evidence", sa.Column("phash", sa.String(length=64), nullable=True))
    op.create_index("ix_evidence_sha256", "evidence", ["sha256"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_evidence_sha256", table_name="evidence")
    op.drop_column("evidence", "phash")
    op.drop_column("evidence", "sha256")