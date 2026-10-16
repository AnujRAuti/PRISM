"""Stage 02-3: nobody can sign an action with someone else's identity.

Audit register row 1.4 measured decision makers and audit actors taken straight
from the request body. ``review_cases.decided_by`` and the two event tables have
no foreign key to ``users``, so a caller could name *any* id and the row
accepted it; six lifecycle transitions went the other way and recorded no actor
at all. Every test here pins ``auth_mode=enforcing`` — the deployed posture —
because under the development default an anonymous caller bypasses the very
policy these tests measure.

Non-vacuity: each ``403`` is paired with the same caller succeeding on the same
route with only the actor field omitted, so the refusal can only come from that
field's value and never from a missing row, a missing grant or a typo. And each
"nothing was written" claim compares real row counts.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    Activity,
    ApiClient,
    EvidenceRequest,
    EvidenceRequestEvent,
    Notification,
    Project,
    ReviewCase,
    ReviewCaseEvent,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service


client = TestClient(app)


@pytest.fixture(autouse=True)
def enforcing():
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


def user_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def api_client_headers(client_id: str) -> dict:
    return {"Authorization": f"Bearer dev-client-{client_id}"}


def new_user(label: str) -> str:
    session = get_session()
    try:
        row = User(username=f"attrib-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@stage02.test")
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def new_project(owner_id: str) -> str:
    session = get_session()
    try:
        row = Project(name=f"attrib {uuid4().hex[:6]}", owner_id=owner_id)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def new_api_client(label: str, scopes: list[str]) -> str:
    session = get_session()
    try:
        row = ApiClient(name=f"attrib-{label}-{uuid4().hex[:8]}", scopes=scopes,
                        status="ACTIVE")
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def grant(user_id: str, role: str, scope_type: str = "GLOBAL",
          project_id: str | None = None) -> None:
    session = get_session()
    try:
        kwargs = {"project_id": project_id} if project_id else {}
        auth_service.assign_role(session, user_id=user_id, role_name=role,
                                 scope_type=scope_type, **kwargs)
        session.commit()
    finally:
        session.close()


def seed_case(project_id: str, status: str) -> str:
    """A workflow row, created directly: this module tests attribution only."""
    session = get_session()
    try:
        row = ReviewCase(project_id=project_id, origin="AUTHORIZED_USER", status=status)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def seed_request(project_id: str, requester_id: str, status: str = "OPEN") -> str:
    session = get_session()
    try:
        row = EvidenceRequest(project_id=project_id, requester_id=requester_id,
                              recipient_id=requester_id, instructions="Second photo",
                              status=status)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def case_row(case_id: str):
    session = get_session()
    try:
        row = session.query(ReviewCase).filter(ReviewCase.id == case_id).one()
        return row.status, row.decided_by, row.decision
    finally:
        session.close()


def request_row(request_id: str):
    session = get_session()
    try:
        row = session.query(EvidenceRequest).filter(EvidenceRequest.id == request_id).one()
        return row.status, row.requester_id
    finally:
        session.close()


def case_history(case_id: str) -> list[tuple[str, str | None]]:
    return _history(ReviewCaseEvent, ReviewCaseEvent.case_id, case_id)


def request_history(request_id: str) -> list[tuple[str, str | None]]:
    return _history(EvidenceRequestEvent, EvidenceRequestEvent.request_id, request_id)


def _history(model, column, parent_id: str) -> list[tuple[str, str | None]]:
    session = get_session()
    try:
        rows = session.query(model).filter(column == parent_id).order_by(
            model.created_at, model.id).all()
        return [(row.event_type, row.actor_id) for row in rows]
    finally:
        session.close()


def activity_row(activity_id: str):
    session = get_session()
    try:
        row = session.query(Activity).filter(Activity.id == activity_id).one()
        return row.actor_id, row.verb
    finally:
        session.close()


def count(model, column, value: str) -> int:
    session = get_session()
    try:
        return session.query(model).filter(column == value).count()
    finally:
        session.close()


def cleanup(*, users=(), projects=(), cases=(), requests=(), clients=(),
            activities=()) -> None:
    """FK-safe order: children (events) up to the parents, then users last."""
    session = get_session()
    try:
        if cases:
            session.query(ReviewCaseEvent).filter(
                ReviewCaseEvent.case_id.in_(cases)).delete(synchronize_session=False)
            session.query(ReviewCase).filter(
                ReviewCase.id.in_(cases)).delete(synchronize_session=False)
        if requests:
            session.query(EvidenceRequestEvent).filter(
                EvidenceRequestEvent.request_id.in_(requests)).delete(
                    synchronize_session=False)
            session.query(EvidenceRequest).filter(
                EvidenceRequest.id.in_(requests)).delete(synchronize_session=False)
        if activities:
            session.query(Activity).filter(
                Activity.id.in_(activities)).delete(synchronize_session=False)
        if users:
            session.query(Notification).filter(
                Notification.recipient_id.in_(users)).delete(synchronize_session=False)
            session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id.in_(users)).delete(synchronize_session=False)
        if projects:
            session.query(Project).filter(
                Project.id.in_(projects)).delete(synchronize_session=False)
        if users:
            session.query(User).filter(User.id.in_(users)).delete(
                synchronize_session=False)
        if clients:
            session.query(ApiClient).filter(
                ApiClient.id.in_(clients)).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


DECISION_BODY = {"decision": "INCONCLUSIVE", "rationale": "needs a field visit"}


def test_forged_decided_by_is_refused_and_writes_nothing():
    owner = new_user("owner")
    supervisor = new_user("supervisor")
    victim = new_user("victim")
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    url = f"/api/v1/review-cases/{case_id}/decision"
    try:
        grant(supervisor, "SUPERVISOR")
        # Non-vacuity: the case really is decidable and the forged id really is
        # a user, so a refusal below cannot be a not-found or a bad payload.
        assert case_row(case_id) == ("INVESTIGATING", None, None)
        events_before = len(case_history(case_id))

        forged = client.post(url, json={**DECISION_BODY, "decided_by": victim},
                             headers=user_headers(supervisor))
        assert forged.status_code == 403, forged.text
        assert "decided_by" in forged.json()["detail"]
        assert case_row(case_id) == ("INVESTIGATING", None, None)
        assert len(case_history(case_id)) == events_before

        # The same caller, the same route, only the actor field dropped.
        allowed = client.post(url, json=DECISION_BODY, headers=user_headers(supervisor))
        assert allowed.status_code == 200, allowed.text
        assert case_row(case_id)[0] == "DECISION_PENDING"
    finally:
        cleanup(users=[owner, supervisor, victim], projects=[project_id],
                cases=[case_id])


def test_omitted_and_restated_actors_both_attribute_the_credential():
    owner = new_user("owner")
    supervisor = new_user("supervisor")
    project_id = new_project(owner)
    cases, ids = [], []
    try:
        grant(supervisor, "SUPERVISOR")
        headers = user_headers(supervisor)

        omitted = seed_case(project_id, "INVESTIGATING")
        cases.append(omitted)
        first = client.post(f"/api/v1/review-cases/{omitted}/decision",
                            json=DECISION_BODY, headers=headers)
        assert first.status_code == 200, first.text
        assert case_row(omitted)[1] == supervisor

        # A caller who restates their own identity is believed, not blocked.
        restated = seed_case(project_id, "INVESTIGATING")
        cases.append(restated)
        second = client.post(f"/api/v1/review-cases/{restated}/decision",
                             json={**DECISION_BODY, "decided_by": supervisor},
                             headers=headers)
        assert second.status_code == 200, second.text
        assert case_row(restated)[1] == supervisor

        for case_id in cases:
            recorded = [actor for event, actor in case_history(case_id)
                        if event == "DECISION_RECORDED"]
            assert recorded == [supervisor]
    finally:
        cleanup(users=[owner, supervisor], projects=[project_id], cases=cases)


def test_transitions_that_recorded_no_actor_now_record_the_principal():
    """investigate/resolve/reopen and assign took no actor at all before #214."""
    owner = new_user("owner")
    supervisor = new_user("supervisor")
    project_id = new_project(owner)
    case_id = seed_case(project_id, "OPEN")
    try:
        grant(supervisor, "SUPERVISOR")
        headers = user_headers(supervisor)
        assert client.post(f"/api/v1/review-cases/{case_id}/assign",
                           json={"assigned_to": supervisor},
                           headers=headers).status_code == 200
        assert client.post(f"/api/v1/review-cases/{case_id}/investigate",
                           headers=headers).status_code == 200
        assert client.post(f"/api/v1/review-cases/{case_id}/decision",
                           json=DECISION_BODY, headers=headers).status_code == 200
        assert client.post(f"/api/v1/review-cases/{case_id}/resolve",
                           headers=headers).status_code == 200

        history = case_history(case_id)
        assert [event for event, _ in history] == [
            "ASSIGNED", "INVESTIGATION_STARTED", "DECISION_RECORDED", "RESOLVED"]
        unattributed = [event for event, actor in history if actor != supervisor]
        assert unattributed == [], f"events without the credential: {unattributed}"
    finally:
        cleanup(users=[owner, supervisor], projects=[project_id], cases=[case_id])


def test_forged_decline_actor_is_refused_then_decline_attributes_the_credential():
    """The decline endpoint used to ignore payload.actor_id entirely."""
    owner = new_user("owner")
    responder = new_user("responder")
    victim = new_user("victim")
    project_id = new_project(owner)
    request_id = seed_request(project_id, victim)
    url = f"/api/v1/evidence-requests/{request_id}/decline"
    try:
        grant(responder, "SUPERVISOR")
        assert request_row(request_id) == ("OPEN", victim)
        events_before = len(request_history(request_id))

        forged = client.post(url, json={"reason": "out of range", "actor_id": victim},
                             headers=user_headers(responder))
        assert forged.status_code == 403, forged.text
        assert "actor_id" in forged.json()["detail"]
        assert request_row(request_id) == ("OPEN", victim)
        assert len(request_history(request_id)) == events_before

        allowed = client.post(url, json={"reason": "out of range"},
                              headers=user_headers(responder))
        assert allowed.status_code == 200, allowed.text
        assert request_row(request_id)[0] == "DECLINED"
        recorded = [actor for event, actor in request_history(request_id)
                    if event == "DECLINED"]
        assert recorded == [responder]
    finally:
        cleanup(users=[owner, responder, victim], projects=[project_id],
                requests=[request_id])


def test_forged_activity_actor_is_refused_and_writes_no_row():
    owner = new_user("owner")
    officer = new_user("officer")
    victim = new_user("victim")
    project_id = new_project(owner)
    url = f"/api/v1/projects/{project_id}/activities"
    created_ids = []
    try:
        grant(officer, "FIELD_OFFICER", "PROJECT", project_id)
        before = count(Activity, Activity.project_id, project_id)

        forged = client.post(url, json={"actor_id": victim, "verb": "inspected",
                                        "details": {}}, headers=user_headers(officer))
        assert forged.status_code == 403, forged.text
        assert "actor_id" in forged.json()["detail"]
        assert count(Activity, Activity.project_id, project_id) == before

        allowed = client.post(url, json={"verb": "inspected", "details": {}},
                              headers=user_headers(officer))
        assert allowed.status_code == 201, allowed.text
        created_ids.append(allowed.json()["id"])
        assert activity_row(allowed.json()["id"]) == (officer, "inspected")
    finally:
        cleanup(users=[owner, officer, victim], projects=[project_id],
                activities=created_ids)


def test_an_api_client_never_writes_an_actor_into_the_user_foreign_key():
    """activities.actor_id references users, so a machine caller records none."""
    owner = new_user("owner")
    victim = new_user("victim")
    project_id = new_project(owner)
    integration = new_api_client("integrations", ["activity.create"])
    url = f"/api/v1/projects/{project_id}/activities"
    created_ids = []
    try:
        anonymousish = client.post(url, json={"verb": "ingested", "details": {}},
                                   headers=api_client_headers(integration))
        assert anonymousish.status_code == 201, anonymousish.text
        created_ids.append(anonymousish.json()["id"])
        assert activity_row(anonymousish.json()["id"])[0] is None

        # A machine credential may not claim a human either.
        forged = client.post(url, json={"actor_id": victim, "verb": "ingested"},
                             headers=api_client_headers(integration))
        assert forged.status_code == 403, forged.text
    finally:
        cleanup(users=[owner, victim], projects=[project_id], clients=[integration],
                activities=created_ids)
