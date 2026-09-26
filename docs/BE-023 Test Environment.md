# BE-023 — Test Environment & Dependencies

This document records what the PoA verification suite needs in order to run
against a **clean, trustworthy database**, and what each dependency's absence
means for the results.

The governing rule: **a missing dependency must never be reported as a
passing test.** Every check below either works or says loudly that it did not.

---

## 1. The one rule that matters most

The suite reads its database from **`TEST_DATABASE_URL`**, and refuses to run
without it.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"
```

If `TEST_DATABASE_URL` is unset, blank, malformed, or points at `pofa_dev`,
the suite **stops during collection** with an actionable message. It never
falls back to `DATABASE_URL`.

This exists because the development database accumulated seven permanent
gaps in the append-only audit ledger (36 missing sequence numbers) caused by
test cleanup deleting `AuditLedgerEvent` rows. Those deletions are now
prevented by a static guard (`tests/audit_guard.py`), but pointing tests at a
fresh database is the second line of defence: history you cannot corrupt is
history you do not have to reason about.

`tests/conftest.py` publishes `TEST_DATABASE_URL` as `DATABASE_URL` for the
duration of the run (stashing the original as `POA_ORIGINAL_DATABASE_URL`)
so the app, the ORM and Alembic all bind to the same test database. Every run
prints which database it used:

```
PoA test database: pofa_test
PoA test database source: TEST_DATABASE_URL
```

---

## 2. Creating a clean test database

```powershell
# 1. Start PostgreSQL (PostGIS + pgvector image)
docker compose up -d db

# 2. Create the test database (once)
docker compose exec db createdb -U postgres pofa_test

# 3. Enable the required extensions
docker compose exec db psql -U postgres -d pofa_test -c "CREATE EXTENSION IF NOT EXISTS postgis;"
docker compose exec db psql -U postgres -d pofa_test -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 4. Apply all migrations
$env:TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"
python -m alembic upgrade head
```

Step 4 should report the head revision `n4o5p6q7r022`. The migration graph
is verified on every test run by `tests/unit/test_migrations.py`, which
asserts there is exactly one head, exactly one root, no merge revisions, no
dangling `down_revision`, and that every revision is reachable from the head.

> **Never point `TEST_DATABASE_URL` at `pofa_dev`.** The resolver rejects it
> by name, and you should not override that check.

---

## 3. Service dependencies

| Dependency | Used for | Started with | If missing |
|---|---|---|---|
| PostgreSQL 15 | all persistence | `docker compose up -d db` | suite cannot run |
| PostGIS | geospatial evidence | enabled via `CREATE EXTENSION postgis` | probe reports `UNREACHABLE` |
| pgvector | vector similarity | enabled via `CREATE EXTENSION vector` | probe reports `UNREACHABLE` |
| Redis | analysis job queue | `docker compose up -d redis` | probe reports `UNREACHABLE` |
| MinIO | evidence object storage | `docker compose up -d minio minio-init` | probe reports `UNREACHABLE` |

`tests/preflight.py` provides `probe_postgres`, `probe_redis` and
`probe_storage`. Each returns a `DependencyStatus` — never a bare boolean —
carrying the failure detail and the exact command that fixes it. Calling
`require(statuses)` raises `MissingDependencyError` naming every unmet
dependency.

`NOT_INSTALLED` (the Python client library is missing) is reported
separately from `UNREACHABLE` (the client exists, the service does not
answer), because the fixes are different.

---

## 4. ML dependencies

PoA uses real ML: CLIP embeddings and YOLO vision inference.

| Package | Pinned version |
|---|---|
| `torch` | 2.8.0 |
| `transformers` | 4.56.2 |
| `ultralytics` | 8.4.155 |
| `numpy` | 1.26.2 |

**Python: 3.12.0** (from `backend/.venv312/pyvenv.cfg`).

The suite distinguishes four states, and they are not interchangeable:

| State | Meaning |
|---|---|
| `ML AVAILABLE` | all three packages import; ML tests really ran |
| `ML UNAVAILABLE` | a package is missing — nothing ML-related was verified |
| `ML TEST SKIPPED` | you set `POA_SKIP_ML_TESTS=1` deliberately |
| `ML TEST FAILED` | packages are installed but importing one raised — a real defect |

The state is printed in the pytest header on every run. A **broken** ML
install is reported as `FAILED`, not `UNAVAILABLE` — a missing package and a
package that explodes on import are different problems.

ML tests that cannot run skip with the state in the reason string
(`ml_skip_reason()`), so the report says *why* rather than showing a bare
"skipped". This is deliberate: a skip is honest, a silent pass is not.

**Model weights are never committed to Git.** Weights download at runtime
into the standard cache:

- HuggingFace CLIP → `%USERPROFILE%\.cache\huggingface`
- Ultralytics YOLO → `%USERPROFILE%\.config\Ultralytics\weights`
  (or `%USERPROFILE%\AppData\Roaming\Ultralytics`)

The first ML test run needs network access to populate these caches; later
runs work offline.

The repository runs on CPU. `vision_device` defaults to `auto`, which
resolves to CPU when no GPU is present. `YOLO_AUTOINSTALL` is forced to
`False` by the detector at import — ML packages must never spawn package
manager subprocesses from inside a test run.

---

## 5. Running the suite

```powershell
# Everything
python -m pytest

# Unit tests only (no services required)
python -m pytest tests/unit -v

# Integration tests
python -m pytest tests/integration -v

# Only the BE-023 hardening tests
python -m pytest -m be023 -v
```

`pytest.ini` sets `pythonpath = .` and `--strict-markers`, so `backend` and
`tests` import without a manually configured `PYTHONPATH`, and an unknown
marker is an error rather than a silent no-op.

---

## 6. Anti-contamination guarantees

`tests/audit_guard.py` statically scans the test tree and fails on any
attempt to destroy audit history:

- ORM `.delete()` against `AuditLedgerEvent` — always a violation
- Raw SQL `DELETE FROM audit_ledger_events` — always a violation
- `TRUNCATE audit_ledger_events` — always a violation
- `.update({...})` bulk update — always a violation
- Raw SQL `UPDATE audit_ledger_events` — a violation **unless** it is inside
  `test_tamper_detection_with_rollback` or
  `test_broken_link_detection_with_rollback` **and** that function contains a
  real `rollback()` call

The allowlist is conditional on an actual rollback call, not on the test's
name, so renaming a test does not grant permission. Comments and docstrings
that merely *describe* the forbidden SQL are not flagged.

The guard's own behaviour is pinned by `tests/unit/test_audit_guard.py`
(17 regression tests) so it cannot be silently weakened into uselessness.
