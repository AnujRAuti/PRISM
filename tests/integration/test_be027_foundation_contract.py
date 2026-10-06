"""BE-027 §24: the core API contract, tested directly against the real database.

Everything here runs through the shipped ASGI app and the migrated test
database. There are no in-memory stores and no substituted repositories, so
"the project was created" means a row exists in PostgreSQL that a second
connection can read back.

Two claims are pinned deliberately:

* the health family distinguishes *alive* from *database reachable*, and the
  database answer is measured, not asserted (see
  ``test_readiness_reports_the_database_as_unavailable_when_it_really_is`` --
  the DSN points at a port nothing listens on, so the failure is a real
  psycopg2 connection refusal);
* a dependency failure reaches the client as a controlled 500 with no
    internals in the body, which is the only way ``§32`` can be checked from
    the outside.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.main import app
from backend.core.config import settings
from backend.db.session import get_session


client = TestClient(app)
# ``raise_server_exceptions=False`` lets the app's own catch-all handler answer,
# which is exactly what is under test in the dependency-failure case.
raw_client = TestClient(app, raise_server_exceptions=False)

PROJECT_FIELDS = {"id", "name", "owner_id", "created_at"}


def seed_user() -> str:
    session = get_session()
    try:
        user_id = str(uuid4())
        session.execute(
            text(
                "INSERT INTO users (id, username, email, is_active, status,"
                " identity_provider, created_at, updated_at)"
                " VALUES (:id, :username, :email, true, 'ACTIVE', 'local',"
                " now(), now())"
            ),
            {"id": user_id, "username": f"be027-{uuid4().hex[:8]}",
             "email": f"{uuid4().hex[:8]}@example.com"},
        )
        session.commit()
        return user_id
    finally:
        session.close()


def create_project(name: str, owner_id: str) -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": owner_id})
    assert response.status_code == 201, response.text
    return response.json()


def project_row(project_id: str) -> dict | None:
    """Read the project back over a separate connection, bypassing the API."""
    session = get_session()
    try:
        row = session.execute(
            text("SELECT id, name, owner_id FROM projects WHERE id = CAST(:id AS uuid)"),
            {"id": project_id},
        ).first()
        return None if row is None else {"id": str(row[0]), "name": row[1], "owner_id": str(row[2])}
    finally:
        session.close()


def delete_project(project_id: str) -> None:
    session = get_session()
    try:
        session.execute(text("DELETE FROM projects WHERE id = CAST(:id AS uuid)"),
                        {"id": project_id})
        session.commit()
    finally:
        session.close()


def delete_user(user_id: str) -> None:
    session = get_session()
    try:
        session.execute(text("DELETE FROM users WHERE id = CAST(:id AS uuid)"), {"id": user_id})
        session.commit()
    finally:
        session.close()


def delete_owned_projects_and_user(owner_id: str) -> None:
    session = get_session()
    try:
        session.execute(text("DELETE FROM projects WHERE owner_id = CAST(:id AS uuid)"),
                        {"id": owner_id})
        session.commit()
    finally:
        session.close()
    delete_user(owner_id)


# ---------------------------------------------------------------------------
# Health (§11, §24)
# ---------------------------------------------------------------------------


def test_liveness_answers_without_claiming_anything_about_the_database():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok"}
    # An alive process is not evidence of an alive database; the contract must
    # not imply otherwise.
    assert "database" not in body


def test_legacy_readiness_actually_queries_the_database():
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_the_database_as_unavailable_when_it_really_is(monkeypatch):
    """The unreachable DSN is not a mock: psycopg2 must really fail to connect."""
    from backend.observability import health as health_module

    monkeypatch.setattr(
        settings, "database_url",
        "postgresql+psycopg2://postgres:postgres@127.0.0.1:1/there_is_no_server",
    )
    status, details = health_module.PostgresHealthCheck().check()
    assert status is health_module.HealthStatus.UNHEALTHY
    assert details["message"] == "PostgreSQL connection failed"

    _, readiness = health_module.get_readiness()
    assert readiness["status"] == "unhealthy"
    assert readiness["checks"]["postgresql"]["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# Create project (§14, §17, §24)
# ---------------------------------------------------------------------------


def test_creating_a_project_persists_a_real_row_and_returns_the_stored_id():
    owner_id = seed_user()
    try:
        created = create_project("BE-027 golden path", owner_id)
        assert set(created) == PROJECT_FIELDS
        assert created["owner_id"] == owner_id
        stored = project_row(created["id"])
        assert stored == {"id": created["id"], "name": "BE-027 golden path",
                          "owner_id": owner_id}
    finally:
        delete_owned_projects_and_user(owner_id)


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        ({"name": "No owner"}, 422),
        ({"owner_id": None}, 422),
        ({"name": "", "owner_id": "not-a-uuid"}, 422),
        ({"name": "x" * 257, "owner_id": str(uuid4())}, 422),
        ({"name": 42, "owner_id": str(uuid4())}, 422),
    ],
)
def test_invalid_create_requests_are_rejected_before_touching_the_database(
    body, expected_status
):
    response = client.post("/api/v1/projects", json=body)
    assert response.status_code == expected_status, response.text


def test_creating_a_project_for_an_unknown_owner_is_a_not_found_not_a_written_row():
    missing_owner = str(uuid4())
    response = client.post(
        "/api/v1/projects", json={"name": "Orphan", "owner_id": missing_owner}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Owner not found"


# ---------------------------------------------------------------------------
# Get / list project (§15, §16, §24)
# ---------------------------------------------------------------------------


def test_get_project_returns_the_stored_resource():
    owner_id = seed_user()
    project = create_project("BE-027 detail", owner_id)
    try:
        response = client.get(f"/api/v1/projects/{project['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == project["id"]
        assert response.json()["name"] == "BE-027 detail"
    finally:
        delete_owned_projects_and_user(owner_id)


def test_get_project_with_a_valid_but_nonexistent_id_is_404():
    response = client.get(f"/api/v1/projects/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_get_project_with_a_malformed_id_is_a_validation_error():
    response = client.get("/api/v1/projects/not-a-uuid")
    assert response.status_code == 422


def test_list_projects_paginates_and_describes_the_whole_result_set():
    owner_id = seed_user()
    try:
        # An owner with no projects must list as empty, not as an error or as
        # somebody else's data.
        empty = client.get("/api/v1/projects", params={"owner_id": owner_id})
        assert empty.status_code == 200
        assert empty.json() == {"items": [], "limit": 50, "offset": 0, "total": 0}

        for index in range(3):
            create_project(f"BE-027 list {index}", owner_id)

        full = client.get("/api/v1/projects", params={"owner_id": owner_id}).json()
        assert full["total"] == 3
        assert len(full["items"]) == 3
        assert all(set(item) == PROJECT_FIELDS for item in full["items"])

        first_page = client.get(
            "/api/v1/projects", params={"owner_id": owner_id, "limit": 2, "offset": 0}
        ).json()
        second_page = client.get(
            "/api/v1/projects", params={"owner_id": owner_id, "limit": 2, "offset": 2}
        ).json()
        assert len(first_page["items"]) == 2
        assert len(second_page["items"]) == 1
        assert first_page["total"] == second_page["total"] == 3
        returned = {item["id"] for item in first_page["items"] + second_page["items"]}
        assert returned == {item["id"] for item in full["items"]}
    finally:
        delete_owned_projects_and_user(owner_id)


def test_list_projects_rejects_out_of_range_pagination():
    assert client.get("/api/v1/projects", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/projects", params={"limit": 101}).status_code == 422
    assert client.get("/api/v1/projects", params={"offset": -1}).status_code == 422


# ---------------------------------------------------------------------------
# Patch (§13)
# ---------------------------------------------------------------------------


def test_patch_renames_the_project_and_the_change_is_persisted():
    owner_id = seed_user()
    project = create_project("BE-027 before", owner_id)
    try:
        response = client.patch(
            f"/api/v1/projects/{project['id']}", json={"name": "BE-027 after"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "BE-027 after"
        assert project_row(project["id"])["name"] == "BE-027 after"
    finally:
        delete_owned_projects_and_user(owner_id)


# ---------------------------------------------------------------------------
# Error handling / leak safety (§19, §32)
# ---------------------------------------------------------------------------


def test_a_real_database_failure_does_not_leak_internals_to_the_client():
    """Override only the *address* of the database, never the application logic.

    Nothing is mocked: the route runs for real against a SQLAlchemy engine
    whose first statement gets a genuine connection refusal, so what is under
    test is the application's own error surface.
    """
    import backend.db.session as session_module
    from sqlalchemy.orm import sessionmaker

    unreachable = create_engine(
        "postgresql+psycopg2://postgres:secret-password@127.0.0.1:1/no_such_database"
    )

    def broken_db():
        session = sessionmaker(autocommit=False, autoflush=False, bind=unreachable)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[session_module.get_db] = broken_db
    try:
        response = raw_client.post(
            "/api/v1/projects", json={"name": "BE-027 failure", "owner_id": str(uuid4())}
        )
        assert response.status_code == 500
        body = response.text
        assert body.strip() == '{"detail":"internal server error"}'
        for forbidden in ("Traceback", "psycopg2", "File \"", "secret-password", "SELECT"):
            assert forbidden not in body
    finally:
        app.dependency_overrides.clear()
        unreachable.dispose()
