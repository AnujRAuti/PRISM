"""Stage 02-1: the nine context.py routes must refuse anonymous callers.

The backend acceptance audit (2026-10-16) measured `GET /api/v1/evidence/nearby`
returning `200` with a data envelope with no credential at all, while guarded
routes returned `401`. Every test here therefore pins `auth_mode=enforcing`:
under the default development mode an anonymous request bypasses authorization
entirely, so an assertion written in that mode would pass against the very hole
this task exists to close.

Non-vacuity rules used below: the anonymous probes target ids that genuinely
exist (proved by reading them back), so a `401` can only come from the guard and
never from a missing row; and each permitted caller is contrasted with a caller
who lacks the permission, so `403`/`404` proves the permission check rather than
mere authentication.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, text

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import Activity, Claim, Evidence, Project, User, UserRoleAssignment
from backend.db.session import get_session
from backend.services import authorization as auth_service


client = TestClient(app)

ROUTES_NEEDING_AUTH = [
    ("post", "/api/v1/projects/{project}/activities", {"verb": "saw", "details": {}}),
    ("get", "/api/v1/projects/{project}/activities", None),
    ("get", "/api/v1/projects/{project}/activities/{activity}", None),
    ("post", "/api/v1/projects/{project}/claims", {"title": "Claim", "description": "d"}),
    ("get", "/api/v1/projects/{project}/claims", None),
    ("get", "/api/v1/projects/{project}/claims/{claim}", None),
    ("patch", "/api/v1/projects/{project}/claims/{claim}", {"title": "Renamed"}),
    ("get", "/api/v1/evidence/nearby?latitude=18.5204&longitude=73.8567&radius=1000", None),
    (
        "get",
        "/api/v1/projects/{project}/evidence/nearby?latitude=18.5204&longitude=73.8567&radius=1000",
        None,
    ),
]

LATITUDE, LONGITUDE = 18.5204, 73.8567


@pytest.fixture(autouse=True)
def enforcing():
    """Pin the production credential posture for every test in this module."""
    original = settings.auth_mode
    settings.auth_mode = "enforcing"
    try:
        session = get_session()
        try:
            auth_service.ensure_default_catalogue(session)
        finally:
            session.close()
        yield
    finally:
        settings.auth_mode = original


def headers_for(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def new_project(name: str, owner_id: str) -> str:
    session = get_session()
    try:
        project = Project(name=f"{name} {uuid4().hex[:6]}", owner_id=owner_id)
        session.add(project)
        session.commit()
        return str(project.id)
    finally:
        session.close()


def new_owner() -> str:
    """A bare user, granted nothing: exists only to satisfy projects.owner_id."""
    return new_user("owner")


def new_user(username: str) -> str:
    session = get_session()
    try:
        user = User(username=f"{username}-{uuid4().hex[:8]}",
                    email=f"{uuid4().hex[:8]}@stage02.test")
        session.add(user)
        session.commit()
        return str(user.id)
    finally:
        session.close()


def grant(user_id: str, role: str, scope_type: str, scope_id: str | None = None) -> None:
    session = get_session()
    try:
        kwargs: dict = {}
        if scope_id is not None:
            kwargs[f"{scope_id_column(scope_type)}_id"] = scope_id
        auth_service.assign_role(session, user_id=user_id, role_name=role,
                                 scope_type=scope_type, **kwargs)
        session.commit()
    finally:
        session.close()


def scope_id_column(scope_type: str) -> str:
    return {"PROJECT": "project", "ORGANIZATION": "organization",
            "ORGANIZATIONAL_UNIT": "organizational_unit"}[scope_type]


def new_activity(project_id: str) -> str:
    session = get_session()
    try:
        activity = Activity(project_id=project_id, actor_id=None, verb="seeded", details={})
        session.add(activity)
        session.commit()
        return str(activity.id)
    finally:
        session.close()


def new_claim(project_id: str) -> str:
    session = get_session()
    try:
        claim = Claim(project_id=project_id, title="Seeded claim", description="body")
        session.add(claim)
        session.commit()
        return str(claim.id)
    finally:
        session.close()


def new_located_evidence(project_id: str) -> str:
    session = get_session()
    try:
        evidence = Evidence(project_id=project_id, filename="seeded.jpg",
                            sha256=uuid4().hex, storage_key=f"stage02/{uuid4().hex}")
        session.add(evidence)
        session.commit()
        session.execute(
            text("UPDATE evidence SET location = "
                 "ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326) WHERE id = :id"),
            {"longitude": LONGITUDE, "latitude": LATITUDE, "id": str(evidence.id)},
        )
        session.commit()
        return str(evidence.id)
    finally:
        session.close()


def resolve(path: str, ids: dict[str, str]) -> str:
    return path.format(**ids)


def exists(model, row_id: str) -> bool:
    session = get_session()
    try:
        return session.query(model).filter(model.id == row_id).count() == 1
    finally:
        session.close()


def cleanup(project_ids, user_ids, evidence_ids) -> None:
    session = get_session()
    try:
        for model, column in ((Activity, Activity.project_id), (Claim, Claim.project_id)):
            session.query(model).filter(column.in_(project_ids)).delete(
                synchronize_session=False)
        if evidence_ids:
            session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(
                synchronize_session=False)
        # user_role_assignments references both projects and users, and
        # projects.owner_id references users, so the deletes run in that order.
        session.query(UserRoleAssignment).filter(
            UserRoleAssignment.user_id.in_(user_ids)).delete(synchronize_session=False)
        session.query(Project).filter(Project.id.in_(project_ids)).delete(
            synchronize_session=False)
        session.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_every_context_route_refuses_anonymous_callers():
    """The nine handlers must answer 401, not run and answer 200/404/422."""
    owner = new_owner()
    project_id = new_project("anon", owner)
    activity_id, claim_id = new_activity(project_id), new_claim(project_id)
    evidence_id = new_located_evidence(project_id)
    ids = {"project": project_id, "activity": activity_id, "claim": claim_id}
    try:
        # Prove the rows really exist, so a refusal below cannot be a not-found.
        assert exists(Project, project_id) and exists(Activity, activity_id)
        assert exists(Claim, claim_id) and exists(Evidence, evidence_id)

        refused, still_open = [], []
        for method, template, body in ROUTES_NEEDING_AUTH:
            path = resolve(template, ids)
            response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
            (refused if response.status_code == 401 else still_open).append(
                (method.upper(), path, response.status_code))
        assert not still_open, f"handlers still executed anonymously: {still_open}"
        assert len(refused) == len(ROUTES_NEEDING_AUTH) == 9
    finally:
        cleanup([project_id], [owner], [evidence_id])


def test_authenticated_caller_still_needs_the_permission_not_just_a_credential():
    """A credential alone is not enough: a role without the permission is denied."""
    owner = new_owner()
    project_id = new_project("permission", owner)
    activity_id, claim_id = new_activity(project_id), new_claim(project_id)
    citizen = new_user("citizen")  # CITIZEN has claim.read, never activity.*
    try:
        grant(citizen, "CITIZEN", "PROJECT", project_id)
        assert client.get(f"/api/v1/projects/{project_id}/activities",
                          headers=headers_for(citizen)).status_code == 403
        assert client.post(f"/api/v1/projects/{project_id}/activities",
                           json={"verb": "sneak", "details": {}},
                           headers=headers_for(citizen)).status_code == 403
        assert client.patch(f"/api/v1/projects/{project_id}/claims/{claim_id}",
                            json={"title": "hijacked"},
                            headers=headers_for(citizen)).status_code == 403
        # The same caller may read claims, which proves the denial above is
        # permission-specific rather than a blanket rejection of the caller.
        assert client.get(f"/api/v1/projects/{project_id}/claims/{claim_id}",
                          headers=headers_for(citizen)).status_code == 200
        assert client.get(f"/api/v1/projects/{project_id}/activities/{activity_id}",
                          headers=headers_for(citizen)).status_code == 403
    finally:
        cleanup([project_id], [citizen, owner], [])


def test_granted_project_scope_allows_reads_and_writes():
    owner = new_owner()
    project_id = new_project("officer", owner)
    claim_id = new_claim(project_id)
    officer = new_user("officer")
    try:
        grant(officer, "FIELD_OFFICER", "PROJECT", project_id)
        created = client.post(f"/api/v1/projects/{project_id}/activities",
                              json={"verb": "inspected", "details": {"k": 1}},
                              headers=headers_for(officer))
        assert created.status_code == 201, created.text
        activity_id = created.json()["id"]
        assert client.get(f"/api/v1/projects/{project_id}/activities",
                          headers=headers_for(officer)).status_code == 200
        assert client.get(f"/api/v1/projects/{project_id}/activities/{activity_id}",
                          headers=headers_for(officer)).status_code == 200
        made_claim = client.post(f"/api/v1/projects/{project_id}/claims",
                                 json={"title": "Second", "description": "d"},
                                 headers=headers_for(officer))
        assert made_claim.status_code == 201, made_claim.text
        assert client.get(f"/api/v1/projects/{project_id}/claims",
                          headers=headers_for(officer)).status_code == 200
        assert client.get(f"/api/v1/projects/{project_id}/claims/{claim_id}",
                          headers=headers_for(officer)).status_code == 200
        assert client.patch(f"/api/v1/projects/{project_id}/claims/{claim_id}",
                            json={"title": "Renamed"},
                            headers=headers_for(officer)).status_code == 200
    finally:
        cleanup([project_id], [officer, owner], [])


def test_scope_denied_on_a_foreign_project_is_indistinguishable_from_absent():
    owner = new_owner()
    visible_project, hidden_project = new_project("mine", owner), new_project("theirs", owner)
    hidden_claim = new_claim(hidden_project)
    hidden_activity = new_activity(hidden_project)
    officer = new_user("scoped-officer")
    try:
        # Without this a 404 could just mean "no such row"; the refusal below
        # must come from scope, so prove the hidden rows really exist first.
        assert exists(Project, hidden_project) and exists(Claim, hidden_claim)
        assert exists(Activity, hidden_activity)
        grant(officer, "FIELD_OFFICER", "PROJECT", visible_project)
        for method, path, body in [
            ("get", f"/api/v1/projects/{hidden_project}/activities", None),
            ("post", f"/api/v1/projects/{hidden_project}/activities", {"verb": "x", "details": {}}),
            ("get", f"/api/v1/projects/{hidden_project}/activities/{hidden_activity}", None),
            ("get", f"/api/v1/projects/{hidden_project}/claims", None),
            ("get", f"/api/v1/projects/{hidden_project}/claims/{hidden_claim}", None),
            ("patch", f"/api/v1/projects/{hidden_project}/claims/{hidden_claim}", {"title": "y"}),
        ]:
            response = (getattr(client, method)(path, json=body, headers=headers_for(officer))
                        if body else
                        getattr(client, method)(path, headers=headers_for(officer)))
            assert response.status_code == 404, (method, path, response.status_code, response.text)
    finally:
        cleanup([visible_project, hidden_project], [officer, owner], [])


def test_global_nearby_search_is_filtered_to_the_callers_visible_projects():
    """The audit's decisive probe: /evidence/nearby served any location anonymously.

    Two projects hold evidence at the same coordinates. A project-scoped caller
    must see exactly one of them, and a global caller both — otherwise the route
    is a cross-project location disclosure even once authenticated.
    """
    owner = new_owner()
    project_a, project_b = new_project("geo-a", owner), new_project("geo-b", owner)
    evidence_a, evidence_b = new_located_evidence(project_a), new_located_evidence(project_b)
    scoped = new_user("geo-scoped")
    global_reader = new_user("geo-global")
    query = (f"/api/v1/evidence/nearby?latitude={LATITUDE}&longitude={LONGITUDE}&radius=1000")
    try:
        grant(scoped, "FIELD_OFFICER", "PROJECT", project_a)
        grant(global_reader, "FIELD_OFFICER", "GLOBAL")

        mine = client.get(query, headers=headers_for(scoped)).json()
        assert {item["evidence_id"] for item in mine["items"]} == {evidence_a}
        assert mine["total"] == 1

        everything = client.get(query, headers=headers_for(global_reader)).json()
        assert {evidence_a, evidence_b} <= {item["evidence_id"] for item in everything["items"]}

        # The project-prefixed variant additionally requires that project's scope.
        assert client.get(
            f"/api/v1/projects/{project_b}/evidence/nearby"
            f"?latitude={LATITUDE}&longitude={LONGITUDE}&radius=1000",
            headers=headers_for(scoped),
        ).status_code == 404
    finally:
        cleanup([project_a, project_b], [scoped, global_reader, owner], [evidence_a, evidence_b])
