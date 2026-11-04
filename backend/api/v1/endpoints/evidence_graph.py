"""BE-010 Evidence Graph endpoints (recorded structure, not verdicts)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.evidence_graph import (
    Direction,
    NodeResponse,
    NodeType,
    RelationshipCreate,
    RelationshipListResponse,
    RelationshipResponse,
    RelationshipStatus,
    RelationshipStatusUpdate,
    RelationshipType,
)
from backend.services import evidence_graph as graph_service
from backend.security.authentication import get_current_principal
from backend.security.authorization import filter_graph_edges, require
from backend.services.authorization import Principal


router = APIRouter(prefix="/graph")


def _to_response(relationship) -> RelationshipResponse:
    created = relationship.created_at
    return RelationshipResponse(
        id=UUID(relationship.id),
        source=NodeResponse(
            id=UUID(relationship.source_node.id),
            node_type=NodeType(relationship.source_node.node_type),
            entity_id=UUID(relationship.source_node.entity_id),
        ),
        target=NodeResponse(
            id=UUID(relationship.target_node.id),
            node_type=NodeType(relationship.target_node.node_type),
            entity_id=UUID(relationship.target_node.entity_id),
        ),
        relationship_type=RelationshipType(relationship.relationship_type),
        relationship_status=RelationshipStatus(relationship.relationship_status),
        provenance=dict(relationship.provenance or {}),
        method=relationship.method,
        method_version=relationship.method_version,
        analysis_run_id=UUID(relationship.analysis_run_id)
        if relationship.analysis_run_id
        else None,
        explanation=relationship.explanation,
        created_at=created.isoformat() if created is not None else None,
    )


@router.post(
    "/relationships",
    status_code=status.HTTP_201_CREATED,
    summary="Record a graph relationship (intelligence structure, not truth)",
)
def create_relationship(
    request: RelationshipCreate,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("graph.read")),
) -> RelationshipResponse:
    try:
        relationship, created = graph_service.create_relationship(
            db,
            source_type=request.source.node_type.value,
            source_id=str(request.source.entity_id),
            target_type=request.target.node_type.value,
            target_id=str(request.target.entity_id),
            relationship_type=request.relationship_type.value,
            provenance=request.provenance.model_dump(exclude_none=True, mode="json"),
            explanation=request.explanation,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    # Idempotent re-assertion of the same analytical edge returns the
    # existing ACTIVE row rather than a duplicate.
    if not created:
        response.status_code = status.HTTP_200_OK
    return _to_response(relationship)


@router.get(
    "/{node_type}/{entity_id}",
    summary="One-hop graph traversal for an entity (direction-filterable)",
    description="Requires graph.read. Returned edges are filtered to projects "
    "visible to the caller: cross-project intelligence never leaks "
    "unauthorized project details. Total counts pre-filter traversal matches.",
)
def get_entity_graph(
    node_type: NodeType,
    entity_id: UUID,
    direction: Direction = Direction.BOTH,
    relationship_type: RelationshipType | None = None,
    relationship_status: RelationshipStatus | None = None,
    project_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> RelationshipListResponse:
    try:
        rows, total = graph_service.list_for_entity(
            db,
            node_type.value,
            str(entity_id),
            direction=direction.value,
            relationship_type=relationship_type.value if relationship_type else None,
            relationship_status=relationship_status.value if relationship_status else None,
            project_id=str(project_id) if project_id else None,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    rows = filter_graph_edges(db, principal, list(rows))
    try:
        node = graph_service.resolve_node(db, node_type.value, str(entity_id), create=False)
    except (ValueError, LookupError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    node_response = (
        NodeResponse(id=UUID(node.id), node_type=node_type, entity_id=entity_id)
        if node is not None
        else None
    )
    return RelationshipListResponse(
        node=node_response,
        items=[_to_response(row) for row in rows],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.patch(
    "/relationships/{relationship_id}",
    summary="Supersede or invalidate a relationship (history-preserving)",
)
def update_relationship_status(
    relationship_id: UUID,
    request: RelationshipStatusUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("graph.read")),
) -> RelationshipResponse:
    try:
        relationship = graph_service.set_relationship_status(
            db, str(relationship_id), request.relationship_status.value
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _to_response(relationship)
