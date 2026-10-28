"""BE-026 Stage E, part C: real dependency outages, partial-ingestion rollback.

Task 23 lists these apart from the negative surface (part B) because they need
infrastructure control: MinIO down, Redis down "where applicable", Postgres
down, a partially completed evidence ingestion, and a rollback. Two rules govern
this file:

* "Do not fake unavailable dependency tests." Every outage is produced by
  stopping the real container or closing the real database, and each one is
  confirmed live from the outside before a single assertion runs. Where a
  dependency is genuinely not on a path, that is proven during a live outage
  rather than assumed.
* "If fault injection is used, restore infrastructure afterward" and "re-verify
  the audit chain after fault injection". Every injection has a guaranteed
  restore in a finally block, and the chain is verified after each restore, not
  only at the end.

The Postgres outage is scoped to this test database alone (ALLOW_CONNECTIONS is
turned off for it) instead of stopping pofa_db, so the shared server and the
developer database stay reachable; that is checked, not assumed.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import create_engine, text

from h import (BASE, BASE2, LABEL, RUN_STARTED, audit_count, chain, check, engine,
               jpeg, note, op_row, q, quarantine_keys, residue, scalar, section,
               summary, sync, teardown, track_evidence, tracked, wait_ready)
from fixtures import build_world, close, list_ops, open_session_http, work

if not re.fullmatch(r"[A-Za-z0-9_-]+", LABEL):
    raise SystemExit(f"LABEL {LABEL!r} is not safe to embed in probe SQL")

#: Identifiers this file creates inside the database, all removed in restore_all.
FAULT_FN = {
    "ingest": "be026_stage_e_refuse_evidence_insert",
    "finalize": "be026_stage_e_refuse_finalize",
}
FAULT_TRIGGER = {
    "ingest": ("be026_stage_e_ingest_fault", "evidence"),
    "finalize": ("be026_stage_e_finalize_fault", "field_capture_operations"),
}
#: The ingestion trigger keys on this exact upload filename, so no other
#: traffic in the shared database is disturbed by the injection.
SENTINEL_INGEST = "__stage_e_ingest_db_refused__"

CONTAINERS = {"minio": "pofa_minio", "redis": "pofa_redis"}
DBNAME = os.environ["DATABASE_URL"].rsplit("/", 1)[-1]
MAINTENANCE_URL = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
DEV_URL = re.sub(r"/[^/]+$", "/pofa_dev", os.environ["DATABASE_URL"])

C_ID, C_STATUS, C_SYNC, C_EVIDENCE = 0, 1, 2, 3

TRACE_MARKERS = ("traceback", "psycopg2.errors", "internalerror", "operationalerror",
                 "sqlalchemy.exc", "stack trace", "greenlet")

#: Client-asserted times, frozen once for the whole run. Recomputing them per
#: call would make two retries of one identity differ, so a replay probe would
#: report a payload conflict it never sent, and an abandoned-reservation retry
#: could never be adopted (adoption requires an identical request hash).
_CAPTURED_AT = (RUN_STARTED - timedelta(minutes=10)).isoformat()
_QUEUED_AT = (RUN_STARTED - timedelta(minutes=5)).isoformat()
_UPLOADED_AT = (RUN_STARTED - timedelta(minutes=1)).isoformat()
PAYLOAD = jpeg(size=28, color=(3, 93, 193))


def meta(**over):
    fields = {"captured_at": _CAPTURED_AT, "queued_at": _QUEUED_AT,
              "uploaded_at": _UPLOADED_AT, "latitude": "53.3498",
              "longitude": "-6.2603", "location_source": "DEVICE_GPS",
              "capture_accuracy_m": "8.5"}
    fields.update(over)
    return {k: v for k, v in fields.items() if v is not None}


def op(name):
    return f"se-{LABEL}-c-{name}"


def rows_named(name):
    return scalar("select count(*) from field_capture_operations"
                  " where client_operation_id = :c", c=op(name))


def evidence_total():
    return scalar("select count(*) from evidence")


def body_of(response):
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text[:300]}


def detail_of(response):
    body = body_of(response)
    if isinstance(body, dict) and isinstance(body.get("detail"), dict):
        return body["detail"]
    return body if isinstance(body, dict) else {"raw": str(body)[:200]}


def leak_free(response):
    """Design 12: no failure collapses to a 500, and no stack trace escapes."""
    body_text = (response.text or "").lower()
    return not any(marker in body_text for marker in TRACE_MARKERS)


def do_sync(w, name, *, session=None, filename="capture.jpg", base=None, **over):
    """One synchronization of identity `name`, byte-identical across retries."""
    r = sync(w["officer"], op(name), session_id=session or w["session"],
             data=PAYLOAD, filename=filename, base=base or BASE, **meta(**over))
    if r.status_code == 201:
        try:
            track_evidence(r.json().get("evidence_id"))
        except ValueError:
            pass
    return r


# ---------------------------------------------------------------------------
# infrastructure control
# ---------------------------------------------------------------------------

def docker(*args, timeout=180):
    return subprocess.run(("docker", *args), capture_output=True, text=True,
                          timeout=timeout)


def container_state(name):
    out = docker("ps", "-a", "--filter", f"name=^/{name}$",
                 "--format", "{{.State}}").stdout.strip()
    return out or "absent"


def stop_container(name):
    docker("stop", name)
    deadline = time.time() + 90
    while time.time() < deadline:
        if container_state(name) != "running":
            return True
        time.sleep(1.0)
    return False


def start_container(name):
    docker("start", name)
    deadline = time.time() + 120
    while time.time() < deadline:
        if container_state(name) == "running":
            return True
        time.sleep(1.0)
    return False


def storage_reachable():
    try:
        quarantine_keys()
        return True
    except Exception:  # noqa: BLE001 - reachability is the whole question
        return False


def wait_storage(want, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if storage_reachable() == want:
            return True
        time.sleep(2.0)
    return False


def readiness():
    try:
        return requests.get(f"{BASE}/ready", timeout=30).json()
    except Exception as error:  # noqa: BLE001 - the probe is itself a signal
        return {"status": f"unreachable: {type(error).__name__}", "checks": {}}


def readiness_check(name):
    return (readiness().get("checks") or {}).get(name, {})


def maintenance():
    """Autocommit connection to the `postgres` database, for DDL on a peer DB.

    `isolation_level=None` is *not* autocommit under psycopg2: the ALTER would
    be rolled back when the connection closes and would never reach any other
    backend. It has to be spelled out.
    """
    return create_engine(MAINTENANCE_URL, isolation_level="AUTOCOMMIT")


def _backends(conn):
    return conn.execute(
        text("select pid, state from pg_stat_activity where datname = :d"
             " and pid <> pg_backend_pid()"), {"d": DBNAME}).fetchall()


def _set_allow_connections(conn, value):
    conn.execute(text(f'ALTER DATABASE "{DBNAME}" WITH ALLOW_CONNECTIONS'
                      f' {"true" if value else "false"}'))


def _terminate_backends(conn):
    return conn.execute(
        text("select count(pg_terminate_backend(pid)) from pg_stat_activity"
             " where datname = :d and pid <> pg_backend_pid()"),
        {"d": DBNAME}).scalar()


def close_test_database():
    """Refuse new connections to this test database and drop the live ones.

    ALLOW_CONNECTIONS only stops *new* connections, so the servers' idle pooled
    connections have to be terminated as well or the outage is not real.
    """
    eng = maintenance()
    try:
        with eng.connect() as c:
            try:
                _set_allow_connections(c, False)
            except Exception as error:  # noqa: BLE001 - live backends can block it
                note(f"close: first ALTER refused ({str(error)[:120]});"
                     " terminating backends and retrying")
                _terminate_backends(c)
                _set_allow_connections(c, False)
            killed = _terminate_backends(c)
            flag = c.execute(text("select datallowconn from pg_database"
                                  " where datname = :d"), {"d": DBNAME}).scalar()
            left = len(_backends(c))
        note(f"close: datallowconn={flag} terminated={killed} backends left={left}")
    finally:
        eng.dispose()


def open_test_database():
    eng = maintenance()
    try:
        with eng.connect() as c:
            _set_allow_connections(c, True)
    finally:
        eng.dispose()


def fresh_connection_refused():
    """A brand-new engine: a pooled connection would hide a real outage."""
    eng = None
    try:
        eng = create_engine(os.environ["DATABASE_URL"])
        with eng.connect() as c:
            c.execute(text("select 1")).scalar()
        return False
    except Exception:  # noqa: BLE001 - reachability is the whole question
        return True
    finally:
        if eng is not None:
            eng.dispose()


def database_reachable():
    if fresh_connection_refused():
        engine.dispose()
        return False
    return True


def wait_database(want, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if database_reachable() == want:
            engine.dispose()  # never hand a dead pooled connection to a later probe
            return True
        time.sleep(2.0)
    return False


def dev_row_count():
    """Read-only proof that the shared server and the developer DB are untouched."""
    try:
        eng = create_engine(DEV_URL)
        try:
            with eng.connect() as c:
                return c.execute(text("select count(*) from users")).scalar()
        finally:
            eng.dispose()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# in-database fault injection
# ---------------------------------------------------------------------------

injected: list[str] = []
containers_stopped = {"minio": False, "redis": False}
database_closed = False


def _drop(kind, label):
    name, table = FAULT_TRIGGER[kind]
    with engine.begin() as c:
        c.execute(text(f"DROP TRIGGER IF EXISTS {name} ON {table}"))
        c.execute(text(f"DROP FUNCTION IF EXISTS {FAULT_FN[kind]}() CASCADE"))
    if kind in injected:
        injected.remove(kind)
    left = scalar("select count(*) from pg_trigger where tgname = :t"
                  " and not tgisinternal", t=name)
    check(f"{label}.{kind}-injection-removed", left == 0, f"{name} still present")


def drop_injections(label):
    for kind in list(injected):
        _drop(kind, label)


def install_ingest_fault():
    """Refuse the Evidence INSERT, but only for this probe's own filename."""
    with engine.begin() as c:
        c.execute(text(f"""
            CREATE OR REPLACE FUNCTION {FAULT_FN['ingest']}() RETURNS trigger
            LANGUAGE plpgsql AS $fn$
            BEGIN
              IF NEW.filename = '{SENTINEL_INGEST}' THEN
                RAISE EXCEPTION 'stage E injection: database refused the evidence write';
              END IF;
              RETURN NEW;
            END $fn$;
        """))
        c.execute(text(f"DROP TRIGGER IF EXISTS {FAULT_TRIGGER['ingest'][0]}"
                       " ON evidence;"))
        c.execute(text(f"""
            CREATE TRIGGER {FAULT_TRIGGER['ingest'][0]}
            BEFORE INSERT ON evidence FOR EACH ROW
            EXECUTE FUNCTION {FAULT_FN['ingest']}();
        """))
    injected.append("ingest")
    check("C18.0.ingestion-fault-is-live",
          scalar("select count(*) from pg_trigger where tgname = :t"
                 " and not tgisinternal", t=FAULT_TRIGGER["ingest"][0]) == 1,
          "trigger not installed")


def install_finalize_fault():
    """Refuse the ACCEPTED finalization of this probe's own operation identities."""
    pattern = f"se-{LABEL}-c-faultB%"
    with engine.begin() as c:
        c.execute(text(f"""
            CREATE OR REPLACE FUNCTION {FAULT_FN['finalize']}() RETURNS trigger
            LANGUAGE plpgsql AS $fn$
            BEGIN
              IF NEW.status = 'ACCEPTED'
                 AND OLD.client_operation_id LIKE '{pattern}' THEN
                RAISE EXCEPTION 'stage E injection: database refused the finalization';
              END IF;
              RETURN NEW;
            END $fn$;
        """))
        c.execute(text(f"DROP TRIGGER IF EXISTS {FAULT_TRIGGER['finalize'][0]}"
                       " ON field_capture_operations;"))
        c.execute(text(f"""
            CREATE TRIGGER {FAULT_TRIGGER['finalize'][0]}
            BEFORE UPDATE ON field_capture_operations FOR EACH ROW
            EXECUTE FUNCTION {FAULT_FN['finalize']}();
        """))
    injected.append("finalize")
    check("C18b.0.finalization-fault-is-live",
          scalar("select count(*) from pg_trigger where tgname = :t"
                 " and not tgisinternal", t=FAULT_TRIGGER["finalize"][0]) == 1,
          "trigger not installed")


def restore_all():
    """Every fault this file can raise, undone, in dependency-safe order."""
    global database_closed
    if database_closed:
        try:
            open_test_database()
        except Exception as error:  # noqa: BLE001 - restore must never abort
            note(f"restore: could not reopen {DBNAME}: {error}")
        if wait_database(True):
            database_closed = False
            note(f"restore: {DBNAME} accepting connections again")
        else:
            note(f"restore: {DBNAME} still refusing connections")
    for kind, container in CONTAINERS.items():
        if not containers_stopped.get(kind):
            continue
        if start_container(container):
            containers_stopped[kind] = False
            note(f"restore: {container} started again")
        else:
            note(f"restore: {container} NOT verified running")
    try:
        drop_injections("C99")
    except Exception as error:  # noqa: BLE001 - restore must never abort
        note(f"restore: injections could not be dropped: {error}")


# ---------------------------------------------------------------------------
# C15 MinIO outage
# ---------------------------------------------------------------------------

def c15_minio_outage(w):
    section("C15 MinIO outage: object storage unavailable during ingestion")
    check("C15.0.storage-reachable-before-the-fault", wait_storage(True),
          "boto3 could not list the quarantine bucket")
    baseline = do_sync(w, "minio-baseline")
    check("C15.1.lifecycle-works-before-the-fault", baseline.status_code == 201,
          f"{baseline.status_code} {baseline.text[:180]}")
    ev0, ops0 = evidence_total(), scalar("select count(*) from field_capture_operations")
    keys0 = set(quarantine_keys())

    assert stop_container(CONTAINERS["minio"]), "docker stop pofa_minio failed"
    containers_stopped["minio"] = True
    check("C15.2.storage-confirmed-unreachable", wait_storage(False, timeout=60),
          "boto3 still reached the bucket after the container stopped")
    note(f"C15.2b pofa_minio state during the fault: {container_state(CONTAINERS['minio'])}")

    down = do_sync(w, "minio-down")
    det = detail_of(down)
    check("C15.3.sync-answers-503-during-a-storage-outage", down.status_code == 503,
          f"{down.status_code} {json.dumps(det)[:220]}")
    check("C15.4.outage-uses-the-declared-vocabulary",
          det.get("sync_status") == "temporarily_unavailable", json.dumps(det)[:200])
    check("C15.5.outage-response-carries-no-stack-trace", leak_free(down), down.text[:200])
    check("C15.6.outage-wrote-no-operation-row", rows_named("minio-down") == 0,
          str(rows_named("minio-down")))
    check("C15.7.outage-created-no-evidence-row", evidence_total() == ev0,
          f"ev0={ev0} now={evidence_total()}")
    check("C15.8.total-operations-unchanged-by-the-outage",
          scalar("select count(*) from field_capture_operations") == ops0,
          f"ops0={ops0} now={scalar('select count(*) from field_capture_operations')}")

    # surfaces that store no objects must keep working through the outage
    feed = work(w["officer"])
    listed = list_ops(w["admin"], project_id=w["project_a"], limit=20)
    reopened = open_session_http(w["officer"], w["assignment"],
                                 device=f"minio-{LABEL}")
    check("C15.9.read-and-session-surfaces-are-storage-independent",
          feed.status_code == 200 and listed.status_code == 200
          and reopened.status_code in (201, 409),
          f"work={feed.status_code} list={listed.status_code} open={reopened.status_code}")
    if reopened.status_code == 201:
        tracked["sessions"].append(reopened.json().get("id"))

    assert start_container(CONTAINERS["minio"]), "docker start pofa_minio failed"
    containers_stopped["minio"] = False
    check("C15.10.storage-restored", wait_storage(True, timeout=120),
          "bucket still unreachable after restart")

    retry = do_sync(w, "minio-down")
    check("C15.11.identity-stayed-retryable-after-the-outage", retry.status_code == 201,
          f"{retry.status_code} {retry.text[:200]}")
    check("C15.12.retry-landed-exactly-one-row", rows_named("minio-down") == 1,
          str(rows_named("minio-down")))
    replay = do_sync(w, "minio-down")
    check("C15.13.post-restoration-replay-is-idempotent",
          replay.status_code == 200
          and detail_of(replay).get("sync_status") == "already_synchronized",
          f"{replay.status_code} {json.dumps(detail_of(replay))[:180]}")

    referenced = {str(r[0]) for r in q("select storage_key from evidence")}
    orphans = sorted(set(quarantine_keys()) - keys0 - referenced)
    check("C15.14.refused-outage-uploads-left-no-orphan-objects", not orphans,
          f"orphans={orphans[:5]}")
    result = chain()
    check("C15.15.chain-valid-after-storage-fault-and-restore", result["valid"],
          str(result["failures"][:2]))


# ---------------------------------------------------------------------------
# C16 Redis outage ("where applicable")
# ---------------------------------------------------------------------------

def c16_redis_outage(w):
    section("C16 Redis outage: the field path is Redis-free, proven not assumed")
    before = readiness_check("redis")
    check("C16.0.redis-healthy-before-the-fault", before.get("status") == "healthy",
          json.dumps(before)[:200])

    assert stop_container(CONTAINERS["redis"]), "docker stop pofa_redis failed"
    containers_stopped["redis"] = True
    during = readiness_check("redis")
    check("C16.1.fault-is-live-readiness-sees-redis-down",
          during.get("status") != "healthy", json.dumps(during)[:220])

    # A whole field lifecycle, while Redis is down, over real HTTP.
    opened = open_session_http(w["officer"], w["assignment"], device=f"redis-{LABEL}")
    check("C16.2.session-open-during-the-outage", opened.status_code in (201, 409),
          f"{opened.status_code} {opened.text[:160]}")
    sid = opened.json().get("id") if opened.status_code == 201 else w["session"]
    if opened.status_code == 201:
        tracked["sessions"].append(sid)
    accepted = do_sync(w, "redis-ok", session=sid)
    check("C16.3.capture-accepted-during-the-outage", accepted.status_code == 201,
          f"{accepted.status_code} {accepted.text[:200]}")
    dup = do_sync(w, "redis-ok", session=sid)
    check("C16.4.duplicate-replay-during-the-outage",
          dup.status_code == 200
          and detail_of(dup).get("sync_status") == "already_synchronized",
          f"{dup.status_code} {json.dumps(detail_of(dup))[:180]}")
    feed = work(w["officer"])
    listed = list_ops(w["admin"], project_id=w["project_a"], limit=20)
    closed = close(sid, w["officer"], reason="redis outage probe")
    check("C16.5.read-and-close-surfaces-during-the-outage",
          feed.status_code == 200 and listed.status_code == 200
          and closed.status_code == 200,
          f"work={feed.status_code} list={listed.status_code} close={closed.status_code}")
    check("C16.6.no-field-surface-degraded-because-of-redis",
          rows_named("redis-ok") == 1
          and scalar("select count(*) from field_capture_operations"
                     " where status <> 'ACCEPTED' and client_operation_id like :p",
                     p=f"se-{LABEL}-c-%") == 0,
          str(rows_named("redis-ok")))
    note("C16.7 Redis is a required dependency of /ready and of the analysis worker "
         "(backend/observability/health.py, backend/services/analysis_queue.py). The "
         "synchronization path never enqueues: the reused ingestion pipeline has no "
         "Redis import. So 'Redis outage where applicable' is answered as NOT "
         "APPLICABLE to BE-026, demonstrated through a live container outage.")

    assert start_container(CONTAINERS["redis"]), "docker start pofa_redis failed"
    containers_stopped["redis"] = False
    deadline, after = time.time() + 90, {}
    while time.time() < deadline and after.get("status") != "healthy":
        time.sleep(2.0)
        after = readiness_check("redis")
    check("C16.8.redis-restored", after.get("status") == "healthy", json.dumps(after)[:200])
    result = chain()
    check("C16.9.chain-valid-after-redis-fault-and-restore", result["valid"],
          str(result["failures"][:2]))


# ---------------------------------------------------------------------------
# C17 Postgres outage
# ---------------------------------------------------------------------------

def c17_postgres_outage(w):
    global database_closed
    section("C17 Postgres outage: this test database closed, server kept up")
    dev_before = dev_row_count()
    check("C17.0.developer-database-readable-before-the-fault",
          dev_before is not None, f"{DEV_URL} unreadable")

    close_test_database()
    database_closed = True
    probe_eng = maintenance()
    try:
        with probe_eng.connect() as probe:
            flag = probe.execute(text("select datallowconn from pg_database"
                                      " where datname = :d"), {"d": DBNAME}).scalar()
            backends = len(_backends(probe))
    finally:
        probe_eng.dispose()
    check("C17.1.fault-is-live-datallowconn-is-false", flag is False, str(flag))
    check("C17.2.fault-is-live-a-brand-new-connection-is-refused",
          wait_database(False, timeout=60), "a new connection still reached pofa_test")
    check("C17.3.no-surviving-backends-on-the-closed-database", backends == 0,
          f"{backends} live backends would make the outage fake")
    check("C17.4.fault-is-scoped-dev-database-still-reachable",
          dev_row_count() is not None, "pofa_dev became unreachable: fault too wide")
    note(f"C17.4b readiness postgres sub-check during the outage: "
         f"{json.dumps(readiness_check('postgresql'))[:200]}")

    # The decisive test of the F-SE-06 fix: the shipped service, the real closed
    # database, no stub and no monkeypatch.
    from types import SimpleNamespace

    from backend.db.session import get_session
    from backend.services import field_operations as svc

    principal = SimpleNamespace(principal_id=w["officer"])
    req = svc.build_sync_request(
        principal=principal, data=PAYLOAD, filename="capture.jpg",
        declared_content_type="image/jpeg",
        client_operation_id=op("db-down-inprocess"), session_id=w["session"], **meta())
    down_at = datetime.now(timezone.utc)
    raised = None
    session = get_session()
    try:
        try:
            svc.sync_capture(session, req, principal)
            raised = "returned without raising"
        except Exception as error:  # noqa: BLE001 - the exception is the measurement
            raised = error
    finally:
        session.close()
    check("C17.5.service-answers-503-not-a-raw-database-error",
          isinstance(raised, svc.FieldOperationError) and raised.status_code == 503
          and raised.sync_status == "temporarily_unavailable",
          f"{type(raised).__name__}: {str(raised)[:180]}")

    http = do_sync(w, "db-down")
    up_at = datetime.now(timezone.utc)
    det = detail_of(http)
    note(f"MEASURED: the same outage over HTTP answers {http.status_code}: "
         f"{json.dumps(det)[:200]} (resolve_principal in"
         " backend/security/authentication.py, which predates BE-026, turns any"
         " SQLAlchemyError into 401 'Invalid credentials' before the field route runs)")
    check("C17.6.database-outage-leaks-no-stack-trace", leak_free(http), http.text[:220])

    read = requests.get(f"{BASE}/api/v1/field/work", headers={"Authorization":
                                                              f"Bearer dev-user-{w['officer']}"},
                        timeout=60)
    note(f"MEASURED: read surface during the outage answered {read.status_code}")
    check("C17.7.database-outage-leaks-no-stack-trace-on-reads", leak_free(read),
          read.text[:220])

    open_test_database()
    check("C17.8.database-reopened", wait_database(True, timeout=90),
          "still refusing connections after ALLOW_CONNECTIONS true")
    database_closed = False
    check("C17.9.dev-database-untouched-by-the-fault", dev_row_count() == dev_before,
          f"{dev_before} -> {dev_row_count()}")

    # Nothing partial may survive the outage window, in either store or the ledger.
    check("C17.10.neither-outage-attempt-wrote-an-operation-row",
          rows_named("db-down") == 0 and rows_named("db-down-inprocess") == 0,
          f"down={rows_named('db-down')} inprocess={rows_named('db-down-inprocess')}")
    window_ops = scalar("select count(*) from field_capture_operations"
                        " where created_at between :a and :b", a=down_at, b=up_at)
    window_ev = scalar("select count(*) from evidence"
                       " where created_at between :a and :b", a=down_at, b=up_at)
    window_field_audit = scalar(
        "select count(*) from audit_ledger_events where created_at between :a and :b"
        " and (event_type like 'FIELD%' or event_type = 'EVIDENCE_UPLOADED')",
        a=down_at, b=up_at)
    check("C17.11.no-operation-row-inside-the-outage-window", window_ops == 0, str(window_ops))
    check("C17.12.no-evidence-row-inside-the-outage-window", window_ev == 0, str(window_ev))
    check("C17.13.no-field-audit-row-inside-the-outage-window", window_field_audit == 0,
          str(window_field_audit))

    # the servers must recover through their pools, without a restart
    recovered = do_sync(w, "db-recovered")
    check("C17.14.servers-recovered-without-a-restart", recovered.status_code == 201,
          f"{recovered.status_code} {recovered.text[:200]}")
    retry = do_sync(w, "db-down")
    check("C17.15.identity-tried-during-the-outage-stayed-retryable",
          retry.status_code == 201, f"{retry.status_code} {retry.text[:200]}")
    check("C17.16.retry-landed-exactly-one-row", rows_named("db-down") == 1,
          str(rows_named("db-down")))
    result = chain()
    check("C17.17.chain-valid-after-database-fault-and-restore", result["valid"],
          str(result["failures"][:2]))
    check("C17.18.ledger-still-contiguous-after-the-outage",
          scalar("select count(*) from audit_ledger_events")
          == scalar("select coalesce(max(sequence_number),0) from audit_ledger_events"),
          "row count diverged from max(sequence_number)")

    note("C17.19 design 6 promises 503 temporarily_unavailable when Postgres is "
         "unavailable. BE-026's own path now keeps that (C17.5, measured against the "
         "closed database). Over HTTP the credential layer answers first, and that "
         "401-during-outage behaviour belongs to pre-BE-026 authentication; it is "
         "recorded as a cross-cutting finding, not fixed here.")


# ---------------------------------------------------------------------------
# C18 partial evidence ingestion, rolled back
# ---------------------------------------------------------------------------

def c18_partial_ingestion_rollback(w):
    section("C18 partial ingestion: object landed, database refused, nothing kept")
    ev0 = evidence_total()
    audit0 = audit_count("EVIDENCE_UPLOADED")
    keys0 = set(quarantine_keys())
    install_ingest_fault()

    refused = do_sync(w, "ingest-refused", filename=SENTINEL_INGEST)
    det = detail_of(refused)
    check("C18.1.post-storage-database-failure-answers-503", refused.status_code == 503,
          f"{refused.status_code} {json.dumps(det)[:220]}")
    check("C18.2.refusal-keeps-the-declared-vocabulary",
          det.get("sync_status") == "temporarily_unavailable", json.dumps(det)[:180])
    check("C18.3.refusal-carries-no-stack-trace", leak_free(refused), refused.text[:200])
    check("C18.4.no-operation-row-from-an-undecided-ingestion",
          rows_named("ingest-refused") == 0, str(rows_named("ingest-refused")))
    check("C18.5.no-evidence-row-was-committed", evidence_total() == ev0,
          f"ev0={ev0} now={evidence_total()}")
    check("C18.6.the-audit-twin-rolled-back-with-its-row",
          audit_count("EVIDENCE_UPLOADED") == audit0,
          f"audit0={audit0} now={audit_count('EVIDENCE_UPLOADED')}")
    dangling = q("select id from evidence where filename = :f", f=SENTINEL_INGEST)
    check("C18.7.the-refused-ingestion-left-no-row-to-find", not dangling, str(dangling)[:120])

    _drop("ingest", "C18")
    referenced = {str(x[0]) for x in q("select storage_key from evidence")}
    orphans = sorted(set(quarantine_keys()) - keys0 - referenced)
    check("C18.8.rolled-back-ingestion-removed-its-object", not orphans,
          f"orphans={orphans[:5]}")

    retry = do_sync(w, "ingest-refused")
    check("C18.9.once-the-fault-is-gone-the-identity-lands-exactly-once",
          retry.status_code == 201 and rows_named("ingest-refused") == 1,
          f"{retry.status_code} rows={rows_named('ingest-refused')}")
    result = chain()
    check("C18.10.chain-valid-after-ingestion-rollback", result["valid"],
          str(result["failures"][:2]))


# ---------------------------------------------------------------------------
# C18b finalization refused between the reused pipeline's two commits
# ---------------------------------------------------------------------------

def c18b_finalize_failure(w):
    section("C18b finalization refused: the reused pipeline's two-commit seam")
    ev0 = evidence_total()
    install_finalize_fault()

    failed = do_sync(w, "faultB-finalize-failed")
    det = detail_of(failed)
    check("C18b.1.finalization-failure-answers-503-not-201", failed.status_code == 503,
          f"{failed.status_code} {json.dumps(det)[:220]}")
    check("C18b.2.refusal-carries-no-stack-trace", leak_free(failed), failed.text[:200])
    row = op_row(client_op=op("faultB-finalize-failed"), user=w["officer"])
    check("C18b.3.the-reservation-survives-as-pending-and-undecided",
          row is not None and row[C_STATUS] == "PENDING" and row[C_EVIDENCE] is None,
          str(row[:4]) if row else "no row")

    stranded = [str(r[0]) for r in q(
        "select id from evidence where project_id is null and created_at >= :s",
        s=RUN_STARTED)]
    tracked["evidence"].extend(stranded)
    note(f"C18b.4 Evidence rows committed by the reused pipeline and then orphaned by "
         f"the injected failure: {len(stranded)} (delta from {ev0} is "
         f"{evidence_total() - ev0}). ingest_evidence commits its own row (design 5), "
         "and BE-026 associates and finalizes in a second transaction, so a failure "
         "between the two leaves one real, unlinked quarantine object. Stage E does "
         "not redesign the shared ingestion pipeline; the rows are tracked and removed "
         "by teardown.")
    for eid in stranded:
        linked = scalar("select count(*) from field_capture_operations where evidence_id=:i",
                        i=eid)
        check(f"C18b.5.orphan-{eid[:8]}-is-linked-from-no-operation", linked == 0,
              f"operation rows pointing at it: {linked}")

    again = do_sync(w, "faultB-finalize-failed")
    check("C18b.6.immediate-retry-is-protected-by-the-in-flight-window",
          again.status_code == 503
          and detail_of(again).get("sync_status") == "temporarily_unavailable",
          f"{again.status_code} {json.dumps(detail_of(again))[:180]}")
    check("C18b.7.protection-did-not-double-create",
          rows_named("faultB-finalize-failed") == 1,
          str(rows_named("faultB-finalize-failed")))

    _drop("finalize", "C18b")
    with engine.begin() as c:
        c.execute(text("update field_capture_operations set received_at ="
                       " received_at - interval '20 minutes'"
                       " where client_operation_id = :c"),
                  {"c": op("faultB-finalize-failed")})
    recovered = do_sync(w, "faultB-finalize-failed")
    check("C18b.8.a-stale-reservation-is-adopted-and-lands", recovered.status_code == 201,
          f"{recovered.status_code} {recovered.text[:200]}")
    row = op_row(client_op=op("faultB-finalize-failed"), user=w["officer"])
    check("C18b.9.exactly-one-operation-row-in-the-end",
          row is not None and row[C_STATUS] == "ACCEPTED" and row[C_EVIDENCE] is not None
          and rows_named("faultB-finalize-failed") == 1,
          str(row[:4]) if row else "no row")
    replay = do_sync(w, "faultB-finalize-failed")
    check("C18b.10.replay-after-recovery-is-idempotent",
          replay.status_code == 200
          and detail_of(replay).get("sync_status") == "already_synchronized",
          f"{replay.status_code} {json.dumps(detail_of(replay))[:160]}")
    result = chain()
    check("C18b.11.chain-valid-after-finalization-fault-and-restore", result["valid"],
          str(result["failures"][:2]))


# ---------------------------------------------------------------------------
# C19 everything restored
# ---------------------------------------------------------------------------

def c19_restoration(w):
    section("C19 restored, and the system behaves as it did before the faults")
    for kind, container in CONTAINERS.items():
        check(f"C19.1.{kind}-container-running", container_state(container) == "running",
              container_state(container))
    check("C19.2.test-database-accepts-connections", database_reachable(), DBNAME)
    check("C19.3.storage-reachable", wait_storage(True, timeout=60), "bucket unreachable")
    check("C19.4.no-injection-tracked-as-still-installed", not injected, json.dumps(injected))
    check("C19.5.injection-triggers-are-gone",
          scalar("select count(*) from pg_trigger where tgname like 'be026_stage_e%'"
                 " and not tgisinternal") == 0,
          str(q("select tgname from pg_trigger where tgname like 'be026_stage_e%'")))
    check("C19.6.injection-functions-are-gone",
          scalar("select count(*) from pg_proc where proname like 'be026_stage_e%'") == 0,
          str(q("select proname from pg_proc where proname like 'be026_stage_e%'")))
    check("C19.7.redis-reachable-again",
          (readiness_check("redis").get("status") == "healthy")
          or container_state(CONTAINERS["redis"]) == "running",
          json.dumps(readiness_check("redis"))[:160])
    note(f"C19.8 readiness snapshot after restoration: {json.dumps(readiness())[:400]}")

    final = do_sync(w, "post-restore")
    check("C19.9.full-lifecycle-works-after-restoration", final.status_code == 201,
          f"{final.status_code} {final.text[:200]}")
    replay = do_sync(w, "post-restore")
    check("C19.10.idempotency-still-holds-after-restoration",
          replay.status_code == 200, f"{replay.status_code} {replay.text[:160]}")
    result = chain()
    check("C19.11.chain-valid-at-the-end", result["valid"], str(result["failures"][:2]))


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def main():
    print(f"part=C label={LABEL} base={BASE} db={scalar('select current_database()')}")
    assert wait_ready(), "primary server not reachable"
    assert wait_ready(BASE2), "second server not reachable"
    check("C0.0.chain-valid-at-start", chain()["valid"], "chain broken before the run")
    ledger0 = scalar("select count(*) from audit_ledger_events")

    world = build_world("c")
    try:
        c15_minio_outage(world)
        c16_redis_outage(world)
        c18_partial_ingestion_rollback(world)
        c18b_finalize_failure(world)
        c17_postgres_outage(world)
        c19_restoration(world)
    except Exception as error:  # noqa: BLE001 - a crash must not leave faults in
        check("C98.no-probe-crashed-the-harness", False,
              f"{type(error).__name__}: {str(error)[:300]}")
        raise
    finally:
        restore_all()
        end = chain()
        note(f"part-C ledger {ledger0} -> "
             f"{scalar('select count(*) from audit_ledger_events')}")
        check("C99.audit-chain-valid-after-all-fault-injection", end["valid"],
              str(end["failures"][:2]))
        teardown()

    print("teardown_remaining=" + json.dumps(residue()))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
