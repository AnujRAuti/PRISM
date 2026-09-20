"""BE-016 endpoint enforcement (thin; rules live in the service layer).

Usage inside an endpoint::

    principal: Principal = Depends(require("evidence.read", "evidence", "evidence_id"))

The dependency resolves the principal, evaluates ``can(...)`` against the
server-side resource scope, and either returns the principal or raises a
structured 401/403/404. Endpoints must never branch on roles directly.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import false
from sqlalchemy.orm import Session

from backend.db.models import Project
from backend.db.session import get_db
from backend.security.authentication import (
    get_current_principal,
    is_development_bypass,
    secure_log_decision,
)
from backend.services.authorization import (
    ACTION_PERMISSIONS,
    Principal,
    Resource,
    can,
    resolve_resource_scope,
)


def require(action: str, resource_type: str | None = None, id_param: str | None = None):
    """Dependency factory enforcing one action against an optional resource.

    Without a resource, the permission must simply be present in any scope
    (creation-style endpoints where scope cannot be evaluated yet). With a
    resource, scope is enforced server-side: missing permission -> 403,
    out-of-scope resource -> 404 (indistinguishable from absent).
    """
    permission = ACTION_PERMISSIONS.get(action, action)

    def dependency(
        request: Request,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if is_development_bypass(principal):
            return principal
        if resource_type is None:
            if not principal.authenticated:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                    detail="Authentication required")
            if principal.status != "ACTIVE":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail="Forbidden")
            if permission not in principal.permissions:
                secure_log_decision(request, principal, action,
                                    Resource("global"), False, "NO_PERMISSION")
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail="Forbidden")
            return principal
        resource_id = None
        if id_param is not None:
            resource_id = request.path_params.get(id_param)
        resource = (
            resolve_resource_scope(db, resource_type, str(resource_id))
            if resource_id is not None
            else Resource(resource_type)
        )
        decision = can(principal, action, resource)
        secure_log_decision(request, principal, action, resource,
                            decision.allowed, decision.reason)
        if decision.allowed:
            return principal
        if decision.reason in ("SCOPE_DENIED", "RESOURCE_UNSCOPEABLE"):
            # Indistinguishable from "not found" where disclosure matters.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Not found")
        if decision.reason == "UNAUTHENTICATED":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Authentication required")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Forbidden")
    return dependency


def visible_project_ids(
    db: Session, principal: Principal, permission: str
) -> set[str] | None:
    """Projects a principal may act on for a permission (None = all).

    Anonymous development-bypass callers see everything (existing
    behavior); everyone else sees global grants or explicit scope chains.
    """
    if is_development_bypass(principal):
        return None
    scopes = principal.permissions.get(permission, ())
    project_ids: set[str] = set()
    org_ids: set[str] = set()
    unit_ids: set[str] = set()
    for scope in scopes:
        if scope.scope_type == "GLOBAL":
            return None
        if scope.scope_type == "PROJECT" and scope.project_id:
            project_ids.add(scope.project_id)
        elif scope.scope_type == "ORGANIZATION" and scope.organization_id:
            org_ids.add(scope.organization_id)
        elif scope.scope_type == "ORGANIZATIONAL_UNIT" and scope.organizational_unit_id:
            unit_ids.add(scope.organizational_unit_id)
    if org_ids or unit_ids:
        query = db.query(Project.id)
        if org_ids and unit_ids:
            query = query.filter(
                (Project.organization_id.in_(org_ids))
                | (Project.organizational_unit_id.in_(unit_ids))
            )
        elif org_ids:
            # Projects directly in the org plus projects in its units.
            from backend.db.models import OrganizationalUnit

            unit_rows = (
                db.query(OrganizationalUnit.id)
                .filter(OrganizationalUnit.organization_id.in_(org_ids))
                .all()
            )
            all_units = list(unit_ids) + [str(row[0]) for row in unit_rows]
            query = query.filter(
                (Project.organization_id.in_(org_ids))
                | (Project.organizational_unit_id.in_(all_units))
            )
        else:
            query = query.filter(Project.organizational_unit_id.in_(unit_ids))
        project_ids |= {str(row[0]) for row in query.all()}
    return project_ids


def permission_description(action: str) -> str:
    """Human-readable required permission for OpenAPI documentation."""
    return f"Requires permission: {ACTION_PERMISSIONS.get(action, action)}"


def filter_graph_edges(db: Session, principal: Principal, rows: list):
    """Drop traversal edges touching projects outside the caller's scope.

    Bypass callers (anonymous development) see everything. Everyone else
    needs ``graph.read``; edges are kept only when every endpoint with a
    known project lies inside the visible set (endpoints whose project
    cannot be resolved do not exclude the edge, mirroring the graph
    service's own project filter). Cross-project intelligence therefore
    never leaks unauthorized project details.
    """
    from backend.db.models import GraphNode
    from backend.services import evidence_graph as graph_service

    if is_development_bypass(principal):
        return rows
    if "graph.read" not in principal.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Forbidden")
    visible = visible_project_ids(db, principal, "graph.read")
    if visible is None:
        return rows
    node_ids = {row.source_node_id for row in rows} | {row.target_node_id for row in rows}
    nodes = (
        db.query(GraphNode).filter(GraphNode.id.in_(node_ids)).all() if node_ids else []
    )
    projects = graph_service._node_project_map(db, nodes)
    node_by_id = {node.id: node for node in nodes}
    kept = []
    for row in rows:
        if node_by_id.get(row.source_node_id) is None or node_by_id.get(
            row.target_node_id
        ) is None:
            continue
        endpoint_projects = {
            projects.get(row.source_node_id), projects.get(row.target_node_id)
        } - {None}
        if endpoint_projects and not endpoint_projects <= visible:
            continue
        if not endpoint_projects and not visible:
            continue
        kept.append(row)
    return kept


def require_target(action: str):
    """Dependency enforcing an action on CLAIM/EVIDENCE target path params.

    Reads ``target_type``/``target_id`` from the path (as used by the
    fusion and explainability endpoints) and enforces scope server-side.
    """

    def dependency(
        request: Request,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if is_development_bypass(principal):
            return principal
        target_type = str(request.path_params.get("target_type", "")).lower()
        target_id = request.path_params.get("target_id")
        if target_type not in ("claim", "evidence") or target_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Unsupported fusion target")
        resource = resolve_resource_scope(db, target_type, str(target_id))
        decision = can(principal, action, resource)
        secure_log_decision(request, principal, action, resource,
                            decision.allowed, decision.reason)
        if decision.allowed:
            return principal
        if decision.reason in ("SCOPE_DENIED", "RESOURCE_UNSCOPEABLE"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Not found")
        if decision.reason == "UNAUTHENTICATED":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Authentication required")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Forbidden")
    return dependency


def require_global(action: str):
    """Dependency requiring a permission held in GLOBAL scope (admin APIs)."""

    def dependency(
        request: Request,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if is_development_bypass(principal):
            return principal
        if not principal.authenticated:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Authentication required")
        permission = ACTION_PERMISSIONS.get(action, action)
        scopes = principal.permissions.get(permission, ())
        if not any(scope.scope_type == "GLOBAL" for scope in scopes):
            secure_log_decision(request, principal, action, Resource("global"),
                                False, "SCOPE_DENIED")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Forbidden")
        return principal
    return dependency


def filter_by_project_scope(query, project_column, db: Session,
                            principal: Principal, permission: str):
    """Restrict a listing query to authorized projects (None-safe passthrough).

    Anonymous development-bypass callers keep existing unfiltered behavior.
    Authenticated callers without the permission get 403; scoped callers see
    only their projects (GLOBAL sees all); unscoped rows require GLOBAL.
    """
    if is_development_bypass(principal):
        return query
    if permission not in principal.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Forbidden")
    visible = visible_project_ids(db, principal, permission)
    if visible is None:
        return query
    if not visible:
        return query.filter(false())
    return query.filter(project_column.in_(visible))
