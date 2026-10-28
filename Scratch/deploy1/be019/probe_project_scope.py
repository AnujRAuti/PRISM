"""Throwaway probe (delete after use): does a scoped creator keep access to the
project it creates through POST /projects?

The POST takes no scope field, so the row is born with organization_id NULL.
``_scope_covers`` only matches an ORGANIZATION grant against a non-NULL
resource.organization_id, so the prediction from code reading is that the
creator cannot see their own new project. This measures it.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import Organization, Project, User, UserRoleAssignment
from backend.db.session import get_session
from backend.services import authorization as auth_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def enforcing_mode():
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


def _close(rows):
    session = get_session()
    try:
        if rows["users"]:
            session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id.in_(rows["users"])).delete(synchronize_session=False)
        if rows["projects"]:
            session.query(Project).filter(Project.id.in_(rows["projects"])).delete(
                synchronize_session=False)
        if rows["orgs"]:
            session.query(Organization).filter(Organization.id.in_(rows["orgs"])).delete(
                synchronize_session=False)
        if rows["users"]:
            session.query(User).filter(User.id.in_(rows["users"])).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def rows():
    r = {"users": [], "orgs": [], "projects": []}
    yield r
    _close(r)


def make_user(rows, label):
    session = get_session()
    try:
        row = User(username=f"probe-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@probe.test")
        session.add(row)
        session.commit()
        rows["users"].append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def make_org(rows, label):
    session = get_session()
    try:
        row = Organization(name=f"PROBE {label} {uuid4().hex[:6]}",
                           code=f"PRB-{label}-{uuid4().hex[:8]}", status="ACTIVE")
        session.add(row)
        session.commit()
        rows["orgs"].append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def grant_org_supervisor(user_id, organization_id):
    session = get_session()
    try:
        auth_service.assign_role(session, user_id=user_id, role_name="SUPERVISOR",
                                 scope_type="ORGANIZATION", organization_id=organization_id)
        session.commit()
    finally:
        session.close()


def test_org_scoped_supervisor_can_create_a_project_and_see_it(rows):
    supervisor = make_user(rows, "sup")
    org = make_org(rows, "a")
    grant_org_supervisor(supervisor, org)
    headers = {"Authorization": f"Bearer dev-user-{supervisor}"}

    created = client.post("/api/v1/projects", headers=headers,
                          json={"name": "probe project", "owner_id": supervisor})
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    rows["projects"].append(project_id)

    session = get_session()
    try:
        row = session.query(Project).filter(Project.id == project_id).one()
        born_org = str(row.organization_id) if row.organization_id else None
    finally:
        session.close()

    read = client.get(f"/api/v1/projects/{project_id}", headers=headers)
    listed = client.get("/api/v1/projects", headers=headers, params={"limit": 100})
    ids = {item["id"] for item in listed.json()["items"]}

    print(f"\nPROBE born_organization_id={born_org} "
          f"own_project_read={read.status_code} "
          f"listed={project_id in ids} "
          f"list_total={listed.json()['total']}")

    assert born_org is None, "expected an unscoped birth; POST /projects takes no scope"
    assert read.status_code == 200, "creator lost read access to the project they created"
    assert project_id in ids, "created project missing from the creator's own list"
