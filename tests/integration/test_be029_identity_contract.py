"""BE-029 §25: the user-identity contract, asserted against the real database.

Product policy (BE-029 OQ-1 = Option A): ``username`` and ``email`` are identity
attributes, so a duplicate must be rejected *by the database*, and the
authoritative external identity key remains ``UNIQUE(identity_provider,
external_subject)`` introduced by BE-016.

Why these tests are written before the migration lands
-----------------------------------------------------
BE-029's required sequence is "identity tests first, then the archive/retirement
migration, then the unique indexes". Until the second BE-029 revision creates
``ix_users_username`` / ``ix_users_email`` as UNIQUE indexes, the duplicate
rejection tests below fail -- they assert the contract the ORM has always
claimed and the database never enforced, which is precisely the defect BE-029
exists to close. The pass state is verified after step 8 (scratch clone at
``head``), not before.

What each test pins, and how
----------------------------
* identity key: same ``(identity_provider, external_subject)`` is one account;
  the pair -- not either column alone -- is the key, so the same subject under
  two providers is two accounts.
* NULL ``external_subject``: PostgreSQL treats NULL as distinct, so such rows
  are *not* resolved by the identity key. That is documented here rather than
  left accidental; repairing it is OQ-3 and is deliberately NOT asserted.
* duplicate username / email: rejected with the unique index's own constraint
  name, so a regression that quietly drops ``unique=True`` is caught by name and
  not just by "some error happened".
* normalisation: ``create_user`` strips and lowercases the email before it
  reaches the index, so ``Foo@Example.COM`` and ``foo@example.com`` collide.
* post-state: zero duplicate groups and zero synthetic residue triples
  (the 19 ``testuser`` rows in the test database are BE-029's retirement set).

Every test is self-cleaning: rows it creates are deleted in teardown, and
failed inserts are rolled back. No fixture data is mutated.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.db.session import get_session
from backend.services import authorization as auth_service

IDENTITY_CONSTRAINT = "uq_user_identity_subject"


class Created:
    """Track rows a test inserted so teardown can remove exactly them.

    Both the primary keys and the identity values are recorded: a "must be
    refused" insert that is *not* refused (a pre-migration database, or a
    regression) still produces a row, and without the value-based delete it
    would leak and leave a duplicate group behind for the next run.
    """

    def __init__(self, session):
        self._session = session
        self.user_ids: list[str] = []
        self.values: list[tuple[str, str]] = []

    def user(self, user_id: str) -> str:
        self.user_ids.append(str(user_id))
        return str(user_id)

    def values_of(self, username: str, email: str) -> None:
        """Record the identity values, normalised exactly as ``create_user`` does."""
        self.values.append((username.strip(), email.strip().lower()))

    def purge(self) -> None:
        for user_id in self.user_ids:
            self._session.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        for username, email in self.values:
            self._session.execute(
                text("DELETE FROM users WHERE username = :u OR email = :e"),
                {"u": username, "e": email})
        if self.user_ids or self.values:
            self._session.commit()


@pytest.fixture()
def db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def created(db):
    tracker = Created(db)
    try:
        yield tracker
    finally:
        db.rollback()
        tracker.purge()


def make_user(db, created, *, username=None, email=None, subject=None,
              provider="local"):
    """Create a user through the shipped service (normalisation + audit included)."""
    suffix = uuid4().hex[:12]
    row = auth_service.create_user(
        db,
        username=username or f"be029-{suffix}",
        email=email or f"{suffix}@example.com",
        external_subject=subject,
        identity_provider=provider,
    )
    created.user(row.id)
    created.values_of(row.username, row.email)
    return row


def insert_raw(db, created, *, username, email, provider="local", subject=None):
    """Insert bypassing the service: the only way to reach a NULL subject."""
    user_id = str(uuid4())
    db.execute(
        text("INSERT INTO users (id, username, email, is_active, status,"
             " identity_provider, external_subject, created_at, updated_at)"
             " VALUES (:id, :username, :email, true, 'ACTIVE', :provider,"
             " :subject, now(), now())"),
        {"id": user_id, "username": username, "email": email,
         "provider": provider, "subject": subject},
    )
    db.commit()
    created.user(user_id)
    created.values_of(username, email)
    return user_id


def refused_user(db, created, *, constraint: str, username: str, email: str,
                 subject: str | None = None, provider: str = "local"):
    """Assert the database refuses this user, by the named constraint.

    The values are registered for teardown first: on a database that does not
    enforce the contract yet, the insert succeeds and would otherwise leak.
    """
    created.values_of(username, email)

    def attempt():
        auth_service.create_user(
            db, username=username, email=email, external_subject=subject,
            identity_provider=provider)

    with pytest.raises(IntegrityError) as excinfo:
        attempt()
    db.rollback()
    message = str(excinfo.value.orig)
    assert constraint in message, (
        f"expected violation of {constraint!r}, got: {message}"
    )
    return message


# -- §8/§25: the authoritative identity key ----------------------------------


def test_same_provider_and_subject_cannot_create_two_users(db, created):
    """``(identity_provider, external_subject)`` identifies exactly one account."""
    subject = str(uuid4())
    first = make_user(db, created, subject=subject)
    assert first.external_subject == subject

    clash = f"be029-clash-{uuid4().hex[:8]}"
    refused_user(db, created, constraint=IDENTITY_CONSTRAINT,
                 username=clash, email=f"{clash}@example.com", subject=subject)
    count = db.execute(
        text("SELECT count(*) FROM users WHERE identity_provider = 'local'"
             " AND external_subject = :s"), {"s": subject}).scalar_one()
    assert count == 1


def test_same_subject_under_different_providers_is_allowed(db, created):
    """The key is the pair, not the subject alone: one person, two providers."""
    subject = str(uuid4())
    make_user(db, created, subject=subject, provider="local")
    row = make_user(db, created, subject=subject, provider="okta")
    assert row.identity_provider == "okta"
    assert db.execute(
        text("SELECT count(*) FROM users WHERE external_subject = :s"),
        {"s": subject}).scalar_one() == 2


def test_different_subject_under_same_provider_is_allowed(db, created):
    make_user(db, created, subject=str(uuid4()))
    assert make_user(db, created, subject=str(uuid4())).external_subject is not None


# -- §25: username and email are identity attributes (Option A) ---------------


def test_duplicate_username_is_rejected_by_the_database(db, created):
    username = f"be029-name-{uuid4().hex[:10]}"
    make_user(db, created, username=username)
    refused_user(db, created, constraint="ix_users_username", username=username,
                 email=f"be029-alt-{uuid4().hex[:8]}@example.com")


def test_duplicate_email_is_rejected_by_the_database(db, created):
    email = f"be029-{uuid4().hex[:12]}@example.com"
    make_user(db, created, email=email)
    refused_user(db, created, constraint="ix_users_email",
                 username=f"be029-alt-{uuid4().hex[:8]}", email=email)


def test_email_normalisation_makes_case_and_padding_variants_collide(db, created):
    """``create_user`` stores ``strip().lower()``, and the index covers that form."""
    local = f"be029{uuid4().hex[:10]}"
    make_user(db, created, email=f"{local}@example.com")
    refused_user(db, created, constraint="ix_users_email",
                 username=f"be029-alt-{uuid4().hex[:8]}",
                 email=f"  {local.upper()}@EXAMPLE.com  ")


def test_stored_email_is_lowercased_and_username_keeps_its_case(db, created):
    suffix = uuid4().hex[:10]
    row = make_user(db, created, username=f"  Be029Mixed{suffix}  ",
                    email=f"  BE029{suffix}@EXAMPLE.com  ")
    assert row.email == f"be029{suffix}@example.com"
    assert row.username == f"Be029Mixed{suffix}"


def test_blank_username_or_email_is_refused_before_insert(db, created):
    for kwargs in ({"username": "   ", "email": "a@b.example"},
                   {"username": "ok-name", "email": "   "}):
        with pytest.raises(ValueError):
            auth_service.create_user(db, **kwargs)
        db.rollback()


# -- §25: NULL external_subject must be defined, not accidental ---------------


def test_null_external_subject_rows_are_permitted_and_do_not_collide(db, created):
    """Documented behaviour, not a decision: PostgreSQL treats NULL as distinct.

    ``uq_user_identity_subject`` therefore resolves nothing for a NULL subject,
    which is why BE-028 flagged NULL-subject duplicates as unresolved. Making
    the column NOT NULL (or backfilling it) is OQ-3 and is out of scope here;
    this test only pins that such rows are insertable today and never resolve
    each other through the identity key.
    """
    provider = f"be029-nullprov-{uuid4().hex[:8]}"
    insert_raw(db, created, username=f"be029-n1-{uuid4().hex[:8]}",
               email=f"be029-n1-{uuid4().hex[:8]}@example.com",
               provider=provider, subject=None)
    second_id = insert_raw(db, created, username=f"be029-n2-{uuid4().hex[:8]}",
                           email=f"be029-n2-{uuid4().hex[:8]}@example.com",
                           provider=provider, subject=None)
    assert db.execute(
        text("SELECT count(*) FROM users WHERE identity_provider = :p"
             " AND external_subject IS NULL"),
        {"p": provider}).scalar_one() == 2
    assert second_id


def test_service_never_creates_a_null_subject(db, created):
    """The application path always supplies a subject, so NULLs are legacy/seed."""
    assert make_user(db, created, subject=None).external_subject


# -- §19/§21: post-remediation database state ---------------------------------


def duplicate_groups(db, column: str) -> list[tuple]:
    """Values held by more than one account -- §19 requires this to be empty."""
    assert column in ("username", "email")
    return db.execute(
        text(f"SELECT {column}, count(*) FROM users GROUP BY {column}"
             " HAVING count(*) > 1 ORDER BY count(*) DESC")).fetchall()


def test_no_duplicate_username_groups_remain(db):
    assert duplicate_groups(db, "username") == []


def test_no_duplicate_email_groups_remain(db):
    assert duplicate_groups(db, "email") == []


def test_no_synthetic_identity_residue_remains(db):
    """The BE-029 retirement set: the ``testuser``/``test@example.com`` triples.

    These rows were written repeatedly by the pre-BE-027 ``test_basic_crud``
    fixture and are the only duplicate group in the test database (19 members).
    BE-029 archives them and retires them in evidence -> projects -> users
    order; nothing else may match this predicate, so a re-run of an old fixture
    fails loudly here instead of silently re-growing a duplicate group.
    """
    assert db.execute(
        text("SELECT count(*) FROM users WHERE username = 'testuser'"
             " AND email = 'test@example.com'")).scalar_one() == 0


def test_username_and_email_indexes_are_unique_in_the_catalog(db):
    """§21: the model, the migration and PostgreSQL must all say UNIQUE.

    Asserted from ``pg_index`` rather than through the ORM so a declaration that
    drifted away from the database cannot pass this file.
    """
    rows = db.execute(
        text("SELECT c.relname, i.indisunique FROM pg_index i"
             " JOIN pg_class c ON c.oid = i.indexrelid"
             " WHERE c.relname IN ('ix_users_username', 'ix_users_email')"
             " ORDER BY c.relname")).fetchall()
    assert [r[0] for r in rows] == ["ix_users_email", "ix_users_username"], (
        f"expected both unique indexes to exist, found {rows}")
    assert all(r[1] for r in rows), f"index exists but is not UNIQUE: {rows}"


def test_identity_key_constraint_definition_is_unchanged(db):
    """BE-029 must not disturb the existing authoritative identity key."""
    row = db.execute(
        text("SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
             " JOIN pg_class t ON t.oid = c.conrelid"
             " WHERE c.conname = 'uq_user_identity_subject'")).scalar_one()
    assert row == "UNIQUE (identity_provider, external_subject)"
