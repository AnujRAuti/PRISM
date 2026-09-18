"""BE-010 graph repository: persistence, queries, traversal, pagination.

Business rules (compatibility, provenance, lifecycle) live in
``backend.services.evidence_graph``; this module only persists and reads.
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.db.models import GraphNode, GraphRelationship


def get_node(db: Session, node_type: str, entity_id: str) -> GraphNode | None:
    return (
        db.query(GraphNode)
        .filter(GraphNode.node_type == node_type, GraphNode.entity_id == entity_id)
        .one_or_none()
    )


def get_or_create_node(db: Session, node_type: str, entity_id: str) -> tuple[GraphNode, bool]:
    existing = get_node(db, node_type, entity_id)
    if existing is not None:
        return existing, False
    node = GraphNode(node_type=node_type, entity_id=entity_id)
    db.add(node)
    db.flush()
    return node, True


def find_active_by_dedupe(db: Session, dedupe_key: str) -> GraphRelationship | None:
    return (
        db.query(GraphRelationship)
        .filter(
            GraphRelationship.dedupe_key == dedupe_key,
            GraphRelationship.relationship_status == "ACTIVE",
        )
        .one_or_none()
    )


def insert_relationship(
    db: Session,
    *,
    source_node_id: str,
    target_node_id: str,
    relationship_type: str,
    dedupe_key: str,
    analysis_run_id: str | None,
    method: str | None,
    method_version: str | None,
    provenance: dict,
    explanation: str | None,
) -> GraphRelationship:
    relationship = GraphRelationship(
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relationship_type=relationship_type,
        relationship_status="ACTIVE",
        analysis_run_id=analysis_run_id,
        method=method,
        method_version=method_version,
        dedupe_key=dedupe_key,
        provenance=provenance,
        explanation=explanation,
    )
    db.add(relationship)
    db.flush()
    return relationship


def get_relationship(db: Session, relationship_id: str) -> GraphRelationship | None:
    return (
        db.query(GraphRelationship).filter(GraphRelationship.id == relationship_id).one_or_none()
    )


def query_for_node(
    db: Session,
    node_id: str,
    *,
    direction: str,
    relationship_type: str | None,
    relationship_status: str | None,
):
    """Base one-hop traversal query (indexed source/target columns only)."""
    query = db.query(GraphRelationship)
    if direction == "outgoing":
        query = query.filter(GraphRelationship.source_node_id == node_id)
    elif direction == "incoming":
        query = query.filter(GraphRelationship.target_node_id == node_id)
    else:  # both
        query = query.filter(
            or_(
                GraphRelationship.source_node_id == node_id,
                GraphRelationship.target_node_id == node_id,
            )
        )
    if relationship_type is not None:
        query = query.filter(GraphRelationship.relationship_type == relationship_type)
    if relationship_status is not None:
        query = query.filter(GraphRelationship.relationship_status == relationship_status)
    return query.order_by(GraphRelationship.created_at.desc(), GraphRelationship.id.desc())
