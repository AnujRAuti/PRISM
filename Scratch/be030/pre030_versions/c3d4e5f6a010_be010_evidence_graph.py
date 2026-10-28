"""add BE-010 evidence graph (graph_nodes + graph_relationships)

Revision ID: c3d4e5f6a010
Revises: b2c3d4e5f009
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "c3d4e5f6a010"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NODE_TYPES = (
    "'PROJECT', 'ACTIVITY', 'CLAIM', 'EVIDENCE', "
    "'ANALYSIS_RESULT', 'VISION_DETECTION', 'DUPLICATE_MATCH'"
)

RELATIONSHIP_TYPES = (
    "'BELONGS_TO', 'CONTAINS_ACTIVITY', 'RELATES_TO_CLAIM', 'SUPPORTS', "
    "'CONTRADICTS', 'ASSOCIATED_WITH', 'DUPLICATE_OF', 'TEMPORALLY_RELATED_TO', "
    "'HAS_ANALYSIS', 'HAS_DETECTION', 'DERIVED_FROM'"
)

RELATIONSHIP_STATUSES = "'ACTIVE', 'SUPERSEDED', 'INVALIDATED'"


def upgrade() -> None:
    op.create_table(
        "graph_nodes",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("node_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"node_type IN ({NODE_TYPES})", name="ck_graph_node_type"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_type", "entity_id", name="uq_graph_node_identity"),
    )
    op.create_index("ix_graph_nodes_type_entity", "graph_nodes", ["node_type", "entity_id"])

    op.create_table(
        "graph_relationships",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("source_node_id", UUID(as_uuid=False), nullable=False),
        sa.Column("target_node_id", UUID(as_uuid=False), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column("relationship_status", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("analysis_run_id", UUID(as_uuid=False), nullable=True),
        sa.Column("method", sa.String(length=256), nullable=True),
        sa.Column("method_version", sa.String(length=256), nullable=True),
        sa.Column("dedupe_key", sa.String(length=512), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"relationship_type IN ({RELATIONSHIP_TYPES})", name="ck_graph_relationship_type"),
        sa.CheckConstraint(f"relationship_status IN ({RELATIONSHIP_STATUSES})", name="ck_graph_relationship_status"),
        sa.CheckConstraint("source_node_id != target_node_id", name="ck_graph_no_self_loop"),
        sa.ForeignKeyConstraint(["source_node_id"], ["graph_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_node_id"], ["graph_nodes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_graph_relationships_source", "graph_relationships", ["source_node_id"])
    op.create_index("ix_graph_relationships_target", "graph_relationships", ["target_node_id"])
    op.create_index("ix_graph_relationships_type", "graph_relationships", ["relationship_type"])
    op.create_index("ix_graph_relationships_run", "graph_relationships", ["analysis_run_id"])
    op.create_index("ix_graph_relationships_dedupe", "graph_relationships", ["dedupe_key"])
    # Idempotency among live edges only: re-assertion of the same analytical
    # relationship returns the ACTIVE row; superseded/invalidated history
    # never blocks a new assertion.
    op.create_index(
        "uq_graph_relationships_dedupe_active",
        "graph_relationships",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("relationship_status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_graph_relationships_dedupe_active", table_name="graph_relationships")
    op.drop_index("ix_graph_relationships_dedupe", table_name="graph_relationships")
    op.drop_index("ix_graph_relationships_run", table_name="graph_relationships")
    op.drop_index("ix_graph_relationships_type", table_name="graph_relationships")
    op.drop_index("ix_graph_relationships_target", table_name="graph_relationships")
    op.drop_index("ix_graph_relationships_source", table_name="graph_relationships")
    op.drop_table("graph_relationships")
    op.drop_index("ix_graph_nodes_type_entity", table_name="graph_nodes")
    op.drop_table("graph_nodes")
