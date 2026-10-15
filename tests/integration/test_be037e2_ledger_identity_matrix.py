"""BE-037 WS-E2: ledger integrity measured per database identity.

Earlier milestones proved one face of the append-only guard at a time. This
module measures the three identities that actually matter, side by side, on a
disposable database:

  * the application runtime shape -- a non-owner LOGIN role holding SELECT /
    INSERT / UPDATE / DELETE on ordinary tables but only SELECT + INSERT on
    ``audit_ledger_events`` (the shape ``scripts/provision_runtime_roles.sql``
    grants);
  * a privileged disposable owner -- the identity that created the schema;
  * a read-only ledger identity and an insufficient-permission identity (schema
    USAGE and nothing else).

What each one shows, and the distinction the task asks to be documented rather
than glossed over:

  * The runtime role is protected by the *permission layer*, not by the
    enforcement trigger. ``has_table_privilege`` says it holds no UPDATE, no
    DELETE and no TRUNCATE on the ledger, so PostgreSQL refuses those statements
    with SQLSTATE 42501 before the ``BEFORE UPDATE OR DELETE`` row trigger is
    ever consulted. It also cannot ``SET ROLE`` its way to the owner.
  * The owner is a different threat model, and an application-level trigger does
    NOT defeat a database owner. The row trigger does refuse the owner's UPDATE
    and DELETE (measured on a disposable clone in BE-030 and re-measured in this
    run's Scratch evidence, because this repository's audit guard deliberately
    forbids writing destructive ledger statements into the test tree). But
    TRUNCATE is a statement-level operation that a ``FOR EACH ROW`` trigger never
    sees, and TRUNCATE requires only ownership -- so an owner can empty the
    ledger, and a few fresh appends then rebuild a chain that a windowed
    ``verify_chain`` reports as valid from sequence 1. The compensating control
    for that is identity separation plus an externally stored checkpoint digest
    and backups, not this trigger. This module asserts the privilege facts that
    make the statement measurable; it does not truncate anything.
  * Verification must fail loudly under an identity that cannot read the chain.
    A connection with no SELECT must not be able to return "valid".

Safety: armed only by ``POA_DISPOSABLE_OWNER_DATABASE_URL``, which must name a
disposable database. A URL pointing at ``pofa_dev``/``pofa_test`` is a hard
failure, not a skip: roles, grants and one appended event are written here. The
roles created carry a per-run random suffix and are dropped in a ``finally``; no
existing role (including ``poa_runtime``) is read, altered or reused, because
``ALTER ROLE`` is cluster-wide. No credential is ever printed: the generated
passwords exist only inside this fixture.
"""

from __future__ import annotations

import os
import secrets
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker

from backend.db.safety import PROTECTED_DATABASE_NAMES, database_name
from backend.services.audit_ledger import append_event, verify_chain, verify_chain_anchored

OWNER_URL_ENV = "POA_DISPOSABLE_OWNER_DATABASE_URL"
LEDGER = "public.audit_ledger_events"
PROBE_SOURCE = "be037e2-identity-matrix"

#: The same probe vocabulary the earlier ledger milestones use (BE-029/BE-030/
#: BE-032R): an accurate registered event type, with the payload marking the
#: row as a verification probe. ``AUDIT_EVENT_TYPES`` has no synthetic/system
#: type and the database CHECK refuses anything else.
PROBE_EVENT_TYPE = "ORGANIZATION_CREATED"


def _owner_url() -> str:
    url = os.environ.get(OWNER_URL_ENV, "").strip()
    if not url:
        pytest.skip(
            f"{OWNER_URL_ENV} is unset. This module creates roles and writes one "
            "audit event, so it only runs against a disposable database supplied "
            "explicitly; the repository's long-lived databases are protected."
        )
    name = database_name(url)
    if name in PROTECTED_DATABASE_NAMES:
        pytest.fail(
            f"{OWNER_URL_ENV} names the protected database {name!r}; refusing to "
            "create roles or write ledger rows there."
        )
    if name is None:
        pytest.fail(f"{OWNER_URL_ENV} does not name a database")
    return url


def _session(engine):
    return sessionmaker(bind=engine, autocommit=False)()


def _scalar(engine, query: str) -> object:
    with engine.connect() as conn:
        return conn.execute(text(query)).scalar()


def _latest_sequence(engine) -> int:
    return int(
        _scalar(
            engine,
            f"select coalesce(max(sequence_number), 0) from {LEDGER}",
        )
    )


def _privileges(engine) -> dict:
    """One row of has_table_privilege facts about the ledger, per statement kind."""
    return {
        kind: bool(
            _scalar(
                engine,
                "select has_table_privilege(current_user, 'audit_ledger_events', "
                f"'{kind}')",
            )
        )
        for kind in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
    }


@pytest.fixture(scope="module")
def identities():
    """Throwaway roles on this run's disposable database, then removed."""
    url = _owner_url()
    owner = create_engine(url)
    tag = f"be037e2_{uuid.uuid4().hex[:8]}"
    passwords = {kind: secrets.token_urlsafe(18) for kind in ("rt", "ro", "none")}
    created: list[str] = []
    engines = {"owner": owner}

    def create_role(kind: str) -> str:
        role = f"{tag}_{kind}"
        with owner.begin() as conn:
            conn.execute(
                text(
                    f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOCREATEDB '
                    "NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD :pw"
                ),
                {"pw": passwords[kind]},
            )
        created.append(role)
        return role

    try:
        # --- the application runtime shape (non-owner, ledger INSERT+SELECT) ---
        runtime = create_role("rt")
        with owner.connect() as conn:
            ordinary = [
                row[0]
                for row in conn.execute(
                    text(
                        "select c.relname from pg_class c "
                        "join pg_namespace n on n.oid = c.relnamespace "
                        "where n.nspname = 'public' and c.relkind = 'r' "
                        "and c.relname not in ('audit_ledger_events', 'spatial_ref_sys') "
                        "order by 1"
                    )
                )
            ]
        with owner.begin() as conn:
            conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{runtime}"'))
            for table in ordinary:
                conn.execute(
                    text(
                        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} '
                        f'TO "{runtime}"'
                    )
                )
            conn.execute(text(f"GRANT SELECT, INSERT ON TABLE {LEDGER} TO \"{runtime}\""))

        # --- SELECT on the ledger and nothing else ---
        reader = create_role("ro")
        with owner.begin() as conn:
            conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{reader}"'))
            conn.execute(text(f"GRANT SELECT ON TABLE {LEDGER} TO \"{reader}\""))

        # --- schema USAGE, no table privileges at all ---
        no_access = create_role("none")
        with owner.begin() as conn:
            conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{no_access}"'))

        dsn = f"postgresql+psycopg2://{{}}:{{}}@{url.split('://', 1)[1].split('@', 1)[1]}"
        for kind, role in (("rt", runtime), ("ro", reader), ("none", no_access)):
            engines[kind] = create_engine(dsn.format(role, passwords[kind]))

        yield {
            "owner": owner,
            "rt": engines["rt"],
            "ro": engines["ro"],
            "none": engines["none"],
            "roles": {"runtime": runtime, "reader": reader, "no_access": no_access},
            "owner_name": str(_scalar(owner, "select current_user")),
        }
    finally:
        for engine in engines.values():
            engine.dispose()
        with owner.begin() as conn:
            for role in created:
                # DROP OWNED BY is what makes a throwaway role actually droppable:
                # it removes the objects the role owns *and* every privilege granted
                # to it, which a couple of REVOKE ALL statements do not cover.
                conn.execute(text(f'DROP OWNED BY "{role}"'))
                conn.execute(text(f'DROP ROLE "{role}"'))


def _identity(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "select current_user as who, "
                "pg_get_userbyid((select c.relowner from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relname = 'audit_ledger_events' "
                "and c.relkind = 'r')) as ledger_owner"
            )
        ).mappings().one()
    return dict(row)


def test_runtime_role_is_not_the_ledger_owner(identities) -> None:
    facts = _identity(identities["rt"])
    assert facts["who"] == identities["roles"]["runtime"]
    assert facts["ledger_owner"] == identities["owner_name"]
    assert facts["ledger_owner"] != facts["who"], (
        "the runtime identity must not own the ledger, or TRUNCATE is open to it"
    )


def test_runtime_role_verifies_and_appends_and_the_chain_stays_valid(identities) -> None:
    """The authorised path under the least-privileged application identity."""
    db = _session(identities["rt"])
    try:
        before = verify_chain_anchored(db)
        before_max = _latest_sequence(identities["rt"])
        row = append_event(
            db,
            event_type=PROBE_EVENT_TYPE,
            action="create",
            resource_type="organizations",
            payload={"probe": PROBE_SOURCE, "identity": "runtime"},
            source=PROBE_SOURCE,
        )
        db.commit()
        after = verify_chain_anchored(db)
    finally:
        db.close()

    assert before["valid"] is True, before["failures"]
    assert after["valid"] is True, after["failures"]
    assert int(row.sequence_number) == before_max + 1
    assert after["checked_events"] > before["checked_events"]
    assert after["checkpoint"]["max_sequence"] == before_max + 1
    assert after["checkpoint"]["rows"] == before["checkpoint"]["rows"] + 1


def test_read_only_identity_verifies_but_cannot_append(identities) -> None:
    db = _session(identities["ro"])
    try:
        report = verify_chain(db)
        assert report["valid"] is True, report["failures"]
        assert report["checked_events"] == int(
            _scalar(identities["ro"], f"select count(*) from {LEDGER}")
        )
        assert report["first_sequence"] == 1

        with pytest.raises(ProgrammingError) as raised:
            append_event(
                db,
                event_type=PROBE_EVENT_TYPE,
                action="create",
                resource_type="organizations",
                payload={"probe": PROBE_SOURCE, "identity": "reader"},
                source=PROBE_SOURCE,
            )
            db.commit()
    finally:
        db.rollback()
        db.close()
    message = str(raised.value).lower()
    assert "42501" in str(raised.value) or "permission denied" in message, message[:300]


def test_insufficient_identity_cannot_produce_a_verdict(identities) -> None:
    """No read path, no verdict: failing loudly beats a vacuous 'valid'."""
    db = _session(identities["none"])
    try:
        with pytest.raises(ProgrammingError) as raised:
            verify_chain_anchored(db)
    finally:
        db.rollback()
        db.close()
    message = str(raised.value).lower()
    assert "42501" in str(raised.value) or "permission denied" in message, message[:300]


def test_runtime_role_holds_no_write_privilege_on_the_ledger(identities) -> None:
    """The permission layer, measured rather than assumed.

    The runtime role has UPDATE/DELETE on every *ordinary* table (it must, or the
    application cannot work) and none of them on the ledger. That asymmetry, not
    the trigger, is what stops the application identity from tampering.
    """
    ledger = _privileges(identities["rt"])
    assert ledger == {
        "SELECT": True,
        "INSERT": True,
        "UPDATE": False,
        "DELETE": False,
        "TRUNCATE": False,
    }, ledger

    with identities["rt"].connect() as conn:
        ordinary_update = conn.execute(
            text(
                "select has_table_privilege(current_user, 'analysis_jobs', "
                "'UPDATE') or has_table_privilege(current_user, 'evidence', 'UPDATE')"
            )
        ).scalar_one()
    assert bool(ordinary_update) is True, (
        "the runtime shape must still be able to update application tables; if it "
        "cannot, the ledger asymmetry above proves nothing about role design"
    )


def test_owner_holds_truncate_and_the_runtime_role_does_not(identities) -> None:
    """The measured boundary of the trigger's threat model.

    A ``FOR EACH ROW`` trigger cannot see TRUNCATE, and TRUNCATE needs only
    ownership -- so the owner's privilege is precisely the hole the application
    layer cannot close. This is asserted as a privilege fact; nothing is
    truncated, so this run's ledger stays intact for the records that depend on
    it.
    """
    owner = _privileges(identities["owner"])
    reader = _privileges(identities["ro"])
    assert owner["TRUNCATE"] is True, owner
    assert owner["DELETE"] is True, owner
    assert reader == {
        "SELECT": True,
        "INSERT": False,
        "UPDATE": False,
        "DELETE": False,
        "TRUNCATE": False,
    }, reader


def test_runtime_role_cannot_escalate_to_the_owner(identities) -> None:
    """SET ROLE is refused, so privilege separation cannot be stepped around."""
    conn = identities["rt"].connect()
    try:
        with pytest.raises(ProgrammingError) as raised:
            conn.execute(text(f'SET ROLE "{identities["owner_name"]}"'))
    finally:
        conn.rollback()
        conn.close()
    message = str(raised.value).lower()
    assert "42501" in str(raised.value) or "permission denied" in message, message[:300]
    with identities["rt"].connect() as check:
        assert check.execute(text("select current_user")).scalar() == (
            identities["roles"]["runtime"]
        )
