"""add BE-009 vision intelligence (job_type + vision_detections)

Revision ID: b2c3d4e5f009
Revises: a1b2c3d4e008
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "b2c3d4e5f009"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs",
        sa.Column("job_type", sa.String(length=50), nullable=False, server_default="fingerprint"),
    )
    op.create_table(
        "vision_detections",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("analysis_result_id", UUID(as_uuid=False), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("class_name", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("x_min", sa.Float(), nullable=False),
        sa.Column("y_min", sa.Float(), nullable=False),
        sa.Column("x_max", sa.Float(), nullable=False),
        sa.Column("y_max", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["analysis_result_id"], ["analysis_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vision_detections_analysis_result_id", "vision_detections", ["analysis_result_id"])
    op.create_index("ix_vision_detections_class_name", "vision_detections", ["class_name"])


def downgrade() -> None:
    op.drop_index("ix_vision_detections_class_name", table_name="vision_detections")
    op.drop_index("ix_vision_detections_analysis_result_id", table_name="vision_detections")
    op.drop_table("vision_detections")
    op.drop_column("analysis_jobs", "job_type")
