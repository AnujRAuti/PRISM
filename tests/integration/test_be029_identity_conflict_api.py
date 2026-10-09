"""BE-029 follow-up (OQ-5): a duplicate identity is a 409 — and not every
``IntegrityError`` is a duplicate identity.

What the audit found (stated here because the plan assumed otherwise)
--------------------------------------------------------------------
``POST /api/v1/auth/users`` has *had* an ``IntegrityError`` -> 409 handler since
BE-016 (``backend/api/v1/endpoints/auth.py``), so the defect was not "a raw 500
reaches the client". It was the opposite: the handler keyed on the exception
**type**, so a primary-key clash, a NOT NULL breach or a foreign-key violation
inside the same request was reported to the caller as "Username, email, or
identity already exists" — blaming the client for a server fault, and naming an
identity that was never duplicated.

What these tests pin
--------------------
* duplicate username / duplicate email -> 409, the answer the new
  ``ix_users_username`` / ``ix_users_email`` indexes make reachable.
* an ``(identity_provider, external_subject)`` clash -> still 409; the
  narrowing must not lose the mapping BE-016 already had.
* the failed transaction is rolled back at the request boundary, so the request
  *after* the 409 still works on the same session and pooled connection.
* a valid unique pair still succeeds exactly as before.
* genuine non-identity integrity failures — produced by real SQL against the
  real database, including one that shares the duplicate-key SQLSTATE 23505 —
  are not classified as identity conflicts, and the HTTP response carries no
  constraint name, SQL text or stack trace.
* the discriminator's message fallback recognises each protected object by name
  and invents nothing for anything else.

Self-cleaning: rows created here are deleted by id and by identity value in
teardown, and every deliberately failing statement is rolled back. The suite
runs on the pinned test database; ``pofa_dev`` is never a target.
"""

from __future__ import annotations

import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.main import app
from backend.db.session import get_session
from backend.services import authorization as auth_service

client = TestClient(app)

#: A server-fault assertion needs the deployed behaviour, not the harness's:
#: ``TestClient`` re-raises an unhandled exception by default, so without this
#: flag there is no response to inspect and "did it become a 409?" is
#: unanswerable. With it, the application's catch-all answers as uvicorn would.
server_client = TestClient(app, raise_server_exceptions=False)

CONFLICT_DETAIL = "Username, email, or identity already exists"

#: Strings that must never appear in a client-visible body from these routes.
LEAK_MARKERS = ("violates", "constraint", "insert into", "select", "psycopg",
                "traceback", "users_pkey", "not_null", "null value")


class Created:
    """Rows this file inserted, removed by id *and* by identity value."""

    def __init__(self, session):
        self.session = session
        self.user_ids: list[str] = []
        self.values: list[tuple[str, str]] = []

    def user(self, user_id: str) -> str:
        self.user_ids.append(str(user_id))
        return str(user_id)

    def values_of(self, username: str, email: str) -> None:
        self.values.append((username.strip(), email.strip().lower()))

    def purge(self) -> None:
        for user_id in self.user_ids:
            self.session.execute(text("DELETE FROM users WHERE id = :id"),
                                 {"id": user_id})
        for username, email in self.values:
            self.session.execute(
                text("DELETE FROM users WHERE username = :u OR email = :e"),
                {"u": username, "e": email})
        if self.user_ids or self.values:
            self.session.commit()


@pytest.fixture()
def db():
    session = get_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def created(db):
    tracker = Created(db)
    try:
        yield tracker
    finally:
        db.rollback()
        tracker.purge()


def unique(tag: str) -> str:
    return f"be029f-{tag}-{uuid4().hex[:10]}"


def admin_headers(db, created) -> dict:
    """A GLOBAL ADMINISTRATOR, created through the shipped service."""
    row = auth_service.create_user(db, username=unique("admin"),
                                   email=f"{unique('admin')}@example.com")
    created.user(row.id)
    created.values_of(row.username, row.email)
    auth_service.assign_role(db, user_id=str(row.id), role_name="ADMINISTRATOR",
                             scope_type="GLOBAL")
    db.commit()
    return {"Authorization": f"Bearer dev-user-{row.id}"}


def post_user(headers, *, username, email, subject=None, provider="local"):
    body = {"username": username, "email": email, "identity_provider": provider}
    if subject is not None:
        body["external_subject"] = subject
    return client.post("/api/v1/auth/users", json=body, headers=headers)


def assert_no_internals(response) -> None:
    body = response.text.lower()
    leaked = [marker for marker in LEAK_MARKERS if marker in body]
    assert not leaked, f"response body exposes database internals {leaked}: {response.text}"


# -- the two identity attributes the new unique indexes protect ----------------


def test_duplicate_username_returns_409(db, created):
    headers = admin_headers(db, created)
    username = unique("name")

    first = post_user(headers, username=username, email=f"{unique('a')}@example.com")
    assert first.status_code == 201, first.text
    created.user(first.json()["id"])
    created.values_of(username, first.json()["email"])

    clash = post_user(headers, username=username, email=f"{unique('b')}@example.com")
    assert clash.status_code == 409, clash.text
    assert clash.json()["detail"] == CONFLICT_DETAIL
    assert_no_internals(clash)

    # The database refused it, not just the API: still exactly one account.
    assert db.execute(text("SELECT count(*) FROM users WHERE username = :u"),
                      {"u": username}).scalar_one() == 1


def test_duplicate_email_returns_409_even_in_a_normalised_variant_form(db, created):
    """``create_user`` stores ``strip().lower()``, and the index covers that form."""
    headers = admin_headers(db, created)
    local = unique("mail")

    first = post_user(headers, username=unique("c"), email=f"{local}@example.com")
    assert first.status_code == 201, first.text
    created.user(first.json()["id"])
    created.values_of(first.json()["username"], f"{local}@example.com")

    clash = post_user(headers, username=unique("d"),
                      email=f"  {local.upper()}@EXAMPLE.com  ")
    assert clash.status_code == 409, clash.text
    assert clash.json()["detail"] == CONFLICT_DETAIL
    assert_no_internals(clash)


def test_identity_subject_clash_is_still_409(db, created):
    """BE-016's authoritative key keeps its mapping after the narrowing."""
    headers = admin_headers(db, created)
    subject = str(uuid4())

    first = post_user(headers, username=unique("e"), email=f"{unique('e')}@example.com",
                      subject=subject)
    assert first.status_code == 201, first.text
    created.user(first.json()["id"])
    created.values_of(first.json()["username"], first.json()["email"])

    clash = post_user(headers, username=unique("f"), email=f"{unique('f')}@example.com",
                      subject=subject)
    assert clash.status_code == 409, clash.text
    assert_no_internals(clash)


# -- the rollback boundary -----------------------------------------------------


def test_session_is_usable_immediately_after_a_conflict(db, created):
    """A refused insert must not poison the session or the pooled connection.

    Without ``db.rollback()`` at the boundary the transaction stays aborted and
    every later statement on that connection fails, so the proof is not "the
    409 came back" but "the request after the 409 still works".
    """
    headers = admin_headers(db, created)
    username = unique("g")
    first = post_user(headers, username=username, email=f"{unique('g')}@example.com")
    assert first.status_code == 201, first.text
    created.user(first.json()["id"])
    created.values_of(username, first.json()["email"])

    assert post_user(headers, username=username,
                     email=f"{unique('h')}@example.com").status_code == 409

    ok = post_user(headers, username=unique("i"), email=f"{unique('i')}@example.com")
    assert ok.status_code == 201, ok.text
    created.user(ok.json()["id"])
    created.values_of(ok.json()["username"], ok.json()["email"])

    fetched = client.get(f"/api/v1/auth/users/{ok.json()['id']}", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["username"] == ok.json()["username"]


def test_valid_unique_pair_still_succeeds(db, created):
    """Unchanged success behaviour: 201, row persisted, normalised email."""
    headers = admin_headers(db, created)
    username = unique("j")
    local = unique("mail-j")
    response = post_user(headers, username=username, email=f"  {local.upper()}@EXAMPLE.com  ")
    assert response.status_code == 201, response.text
    body = response.json()
    created.user(body["id"])
    created.values_of(username, body["email"])
    assert body["username"] == username
    assert body["email"] == f"{local}@example.com"
    assert db.execute(text("SELECT count(*) FROM users WHERE id = :id"),
                      {"id": body["id"]}).scalar_one() == 1


# -- integrity failures that are NOT duplicate identities ----------------------

#: (id, label, statements, params factory). Each probe violates a real,
#: unrelated constraint; the failing transaction is rolled back, so nothing
#: created here persists.
NON_IDENTITY_VIOLATIONS = (
    (
        "users_pkey",
        "PRIMARY KEY clash on users_pkey — the same SQLSTATE 23505 as a duplicate",
        (
            "INSERT INTO users (id, username, email, status, identity_provider)"
            " VALUES (:id, :u1, :e1, 'ACTIVE', 'local')",
            "INSERT INTO users (id, username, email, status, identity_provider)"
            " VALUES (:id, :u2, :e2, 'ACTIVE', 'local')",
        ),
        lambda: {"id": str(uuid4()),
                 "u1": unique("pk1"), "e1": f"{unique('pk1')}@example.com",
                 "u2": unique("pk2"), "e2": f"{unique('pk2')}@example.com"},
    ),
    (
        "not_null",
        "NOT NULL breach on users.username",
        ("INSERT INTO users (id, username, email, status, identity_provider)"
         " VALUES (gen_random_uuid(), NULL, :e, 'ACTIVE', 'local')",),
        lambda: {"e": f"{unique('nn')}@example.com"},
    ),
    (
        "foreign_key",
        "foreign key projects.owner_id -> users",
        ("INSERT INTO projects (id, name, owner_id)"
         " VALUES (gen_random_uuid(), 'be029f-fk-probe', :missing)",),
        lambda: {"missing": str(uuid4())},
    ),
)

PK_CLASH = NON_IDENTITY_VIOLATIONS[0]


def capture_integrity_error(db, statements, params) -> IntegrityError:
    """Run the statements in one transaction and return the error they raise."""
    raised = None
    for statement in statements:
        try:
            db.execute(text(statement), params)
        except IntegrityError as error:
            raised = error
            break
    db.rollback()
    assert raised is not None, "the probe statements violated nothing"
    return raised


@pytest.mark.parametrize(
    "label, statements, params",
    [(label, statements, params) for _i, label, statements, params in NON_IDENTITY_VIOLATIONS],
    ids=[entry[0] for entry in NON_IDENTITY_VIOLATIONS],
)
def test_non_identity_violation_is_not_a_conflict(db, label, statements, params):
    """The discriminator keys on the object name, not the exception type."""
    error = capture_integrity_error(db, statements, params())
    assert auth_service.identity_conflict(error) is None, (
        f"{label} was classified as an identity conflict: {error}")


def test_the_pkey_clash_really_does_share_the_duplicate_sqlstate(db):
    """Why the type-based mapping was wrong, stated as a fact.

    ``users_pkey`` and ``ix_users_username`` are both SQLSTATE 23505 / both
    ``IntegrityError``, so neither the class nor the sqlstate can tell a
    duplicated identity from a broken primary key. Only the object name can.
    """
    error = capture_integrity_error(db, PK_CLASH[2], PK_CLASH[3]())
    diag = error.orig.diag
    assert diag.sqlstate == "23505", diag.sqlstate
    assert diag.constraint_name == "users_pkey", diag.constraint_name
    assert auth_service.identity_conflict(error) is None


def test_pkey_clash_over_http_is_not_reported_as_a_duplicate(db, created, monkeypatch):
    """End-to-end for that same genuine error.

    The error object is real, produced by the database above; only its routing
    into the request is induced, because no client payload can make the service
    clash on a primary key.
    """
    headers = admin_headers(db, created)
    real_error = capture_integrity_error(db, PK_CLASH[2], PK_CLASH[3]())

    def clash(*args, **kwargs):
        raise real_error

    monkeypatch.setattr(auth_service.auth_repo, "insert_user", clash)
    try:
        response = server_client.post(
            "/api/v1/auth/users",
            json={"username": unique("k"), "email": f"{unique('k')}@example.com"},
            headers=headers)
    finally:
        monkeypatch.undo()

    assert response.status_code != 409, (
        f"a primary-key clash was reported as a duplicate identity: {response.text}")
    assert response.status_code == 500, response.text
    assert response.json() == {"detail": "internal server error"}
    assert_no_internals(response)


# -- the message fallback (a driver object with no diagnostic) -----------------


class _OnlyMessage:
    """A DBAPI error exposing just its text, as a non-psycopg2 driver would."""

    def __init__(self, message: str):
        self._message = message

    def __str__(self) -> str:
        return self._message


def fake_integrity(message: str) -> IntegrityError:
    return IntegrityError("INSERT INTO users ...", {}, _OnlyMessage(message))


def test_message_fallback_recognises_each_protected_object():
    for name in sorted(auth_service.IDENTITY_UNIQUE_OBJECTS):
        error = fake_integrity(
            f'duplicate key value violates unique constraint "{name}" already exists')
        assert auth_service.identity_conflict(error) == name


def test_message_fallback_invents_no_conflict():
    for message in (
            'duplicate key value violates unique constraint "users_pkey"',
            'duplicate key value violates unique constraint "ix_projects_name"',
            'null value in column "email" violates not-null constraint',
            'insert or update on table "projects" violates foreign key constraint',
            'string exceeds maximum length'):
        assert auth_service.identity_conflict(fake_integrity(message)) is None, message


# -- classifier robustness across error representations ------------------------


class _Diag:
    def __init__(self, constraint_name=None, sqlstate="23505"):
        self.constraint_name = constraint_name
        self.sqlstate = sqlstate


class _Orig:
    def __init__(self, diag=None, message=""):
        self.diag = diag
        self._message = message

    def __str__(self):
        return self._message


def wrapped(orig) -> IntegrityError:
    return IntegrityError("INSERT INTO users ...", {}, orig)


def test_a_diagnostic_object_takes_precedence_over_the_message():
    """psycopg2 reports the real object; the message must not second-guess it."""
    error = wrapped(_Orig(_Diag(constraint_name="users_pkey"),
                          'duplicate key value violates unique constraint "ix_users_email"'))
    assert auth_service.identity_conflict(error) is None


def test_a_diagnostic_without_a_constraint_name_falls_back_to_the_message():
    error = wrapped(_Orig(_Diag(constraint_name=None),
                          'duplicate key value violates unique constraint "ix_users_email"'))
    assert auth_service.identity_conflict(error) == "ix_users_email"


def test_an_error_object_with_no_diagnostic_is_recognised_from_text_only():
    error = wrapped(_Orig(None, 'duplicate key value violates unique constraint "uq_user_identity_subject"'))
    assert auth_service.identity_conflict(error) == "uq_user_identity_subject"


def test_the_classifier_never_raises_on_an_unfamiliar_error_shape():
    """A shape it has not seen must classify as "not an identity conflict", not explode.

    An exception inside the 409 handler would turn a client's duplicate into a
    server fault, which is the failure mode this narrowing exists to remove.
    """
    assert auth_service.identity_conflict(object()) is None
    assert auth_service.identity_conflict(wrapped(None)) is None
    assert auth_service.identity_conflict(IntegrityError("sql", {}, None)) is None


# -- concurrency: the index decides, not the endpoint --------------------------


def test_concurrent_duplicate_username_ends_with_one_account_and_two_answers(db, created):
    """§3.3 case 11, run for real on two connections.

    Which request wins is not fixed and must not be asserted. What is fixed is
    the outcome the unique index guarantees: one row, one ``201``, one ``409``,
    and no ``500`` for the loser. A pre-check could not promise that, which is
    exactly why the database constraint stays authoritative.
    """
    headers = admin_headers(db, created)
    username = unique("race")
    emails = {tag: f"{unique('race-' + tag)}@example.com" for tag in ("p", "q")}
    for email in emails.values():
        created.values_of(username, email)

    barrier = threading.Barrier(2)
    attempts: list[tuple[int, str, dict]] = []

    def attempt(tag: str) -> None:
        # raise_server_exceptions=False: with the default, a server fault in the
        # loser would raise inside its thread and leave one recorded answer, so
        # "the duplicate became a 500" would be indistinguishable from a crash
        # in the harness. This way the application answers the way uvicorn would.
        thread_client = TestClient(app, raise_server_exceptions=False)
        barrier.wait(30)
        response = thread_client.post(
            "/api/v1/auth/users",
            json={"username": username, "email": emails[tag], "identity_provider": "local"},
            headers=headers)
        attempts.append((response.status_code, response.text, response.json()))

    threads = [threading.Thread(target=attempt, args=(tag,)) for tag in ("p", "q")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
        assert not thread.is_alive(), "a racing request hung"

    assert len(attempts) == 2, attempts
    codes = sorted(code for code, _body, _payload in attempts)
    assert codes == [201, 409], attempts
    for code, body, _payload in attempts:
        lowered = body.lower()
        assert not any(marker in lowered for marker in LEAK_MARKERS), (code, body)
    loser = next(payload for code, _body, payload in attempts if code == 409)
    assert loser["detail"] == CONFLICT_DETAIL, loser

    assert db.execute(text("SELECT count(*) FROM users WHERE username = :u"),
                      {"u": username}).scalar_one() == 1
