"""add BE-006 duplicate intelligence fields

Revision ID: f9b5d7e3c006
Revises: e8a4c6d2b005
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "f9b5d7e3c006"
down_revision: Union[str, Sequence[str], None] = "e8a4c6d2b005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("analysis_results", "embedding", type_=Vector(512), postgresql_using="NULL")
    op.add_column("duplicate_matches", sa.Column("match_type", sa.String(length=50), nullable=False, server_default="candidate"))
    op.add_column("duplicate_matches", sa.Column("phash_distance", sa.Integer(), nullable=True))
    op.add_column("duplicate_matches", sa.Column("embedding_similarity", sa.Float(), nullable=True))
    op.add_column("duplicate_matches", sa.Column("signals", sa.JSON(), nullable=False, server_default="{}"))
    op.create_unique_constraint("uq_duplicate_match_pair", "duplicate_matches", ["evidence_id", "matched_evidence_id"])


def downgrade() -> None:
    op.drop_constraint("uq_duplicate_match_pair", "duplicate_matches", type_="unique")
    op.drop_column("duplicate_matches", "signals")
    op.drop_column("duplicate_matches", "embedding_similarity")
    op.drop_column("duplicate_matches", "phash_distance")
    op.drop_column("duplicate_matches", "match_type")
    op.alter_column("analysis_results", "embedding", type_=sa.ARRAY(sa.Float()), postgresql_using="NULL")