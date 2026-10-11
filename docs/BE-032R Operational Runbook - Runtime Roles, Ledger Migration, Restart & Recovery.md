# BE-032R Operational Runbook — Runtime Roles, Ledger Migration, Restart & Recovery

Status: **prepared and disposable-verified; NOT executed against `pofa_dev`,
`pofa_test`, or any live/production system.** Every operational action below that
mutates a protected or live database, changes roles on a live cluster, restarts a
real service, or sets a production secret requires its own explicit authorization.
This document turns those actions from guesses into checked procedures.

Scope of evidence in this runbook (all measured 2026-10-11 on named disposable
databases inside the `pofa_db` container; the host has no `pg_dump`, so dump/restore
run in-container):

- `poa_b032r_roles` — fresh DB at head `t0u1v2w3x030`; F-05 role proof.
- `poa_b032r_devclone` — `pg_dump`/`pg_restore` clone of the current `pofa_dev`;
  D-PFD migration + downgrade/re-upgrade proof.

`pofa_dev` was only ever connected to **read-only** (baseline facts); it remains at
`s9t0u1v2w029` with no enforcement and no new rows.

---

## 1. Current-state facts (re-measured, not assumed)

| Item | Value | How re-verified |
|---|---|---|
| Alembic heads | one linear head `t0u1v2w3x030`, no branches | `alembic heads` / `alembic branches` |
| `pofa_test` | at `t0u1v2w3x030`, enforcement present | `alembic current`, catalog probe |
| `pofa_dev` | at `s9t0u1v2w029`, enforcement **absent** | `alembic current`, catalog probe |
| `pofa_dev` ledger | 6023 rows, seq 1..6059, **7** gap ranges, 0 hash mismatches | read-only SQL + `verify_chain_classified` |
| `pofa_dev` users | 1054 | read-only SQL |
| Application DB role today | `postgres` (owner) for both databases | `docker exec pofa_db psql ... pg_roles` |
| Legacy `audit_events` | present, 0 rows, no known consumer | (untouched — retirement is out of scope per BE-032R §15) |

---

## 2. F-05 — move the application off the owner role, close the TRUNCATE hole

### 2.1 Why a trigger is not enough

BE-030 installed `trg_audit_ledger_append_only` (a `BEFORE UPDATE OR DELETE FOR
EACH ROW` refusing trigger). A row-level trigger **does not fire on `TRUNCATE`**,
and `TRUNCATE` only requires **table ownership**. As long as the application
connects as `postgres` (the owner), it can wipe the ledger; the fresh chain would
then re-baseline from sequence 1 and `verify_chain` would report `valid=True`. Only
a **non-owner runtime role** closes this.

### 2.2 Design (least privilege, migration/runtime separation)

- `poa_migrator` — owns schema objects, performs DDL. Used by Alembic only.
- `poa_runtime` — the application identity. Non-owner; `NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS`; not a member of the owner role
  (no `SET ROLE` elevation). Holds `USAGE` on `public`, full DML on ordinary tables,
  and **`SELECT, INSERT` only** on `audit_ledger_events`.
- Provisioning artifact: `scripts/provision_runtime_roles.sql` (idempotent; the
  runtime password is passed in via `-v runtime_password=...`, never stored here;
  the script refuses to run without it).

### 2.3 Disposable proof (measured on `poa_b032r_roles` and `poa_b032r_devclone`)

Connecting AS `poa_runtime`:

- ledger privileges: `insert=t / update=f / delete=f / truncate=f`;
- append (advisory lock + `INSERT`) **succeeds** — authorized writes unaffected;
- `UPDATE` / `DELETE` → `permission denied for table audit_ledger_events`;
- `TRUNCATE` → `permission denied for table audit_ledger_events` (**the F-05 fix**);
- `SET ROLE postgres` → `permission denied to set role "postgres"` (no elevation);
- `CREATE TABLE` → `permission denied for schema public` (no DDL from runtime).

The provisioning script re-runs idempotently and its self-check prints the
`insert=t / update=f / delete=f / truncate=f` line.

### 2.4 Live rollout (requires explicit authorization)

1. Create `poa_migrator` and `poa_runtime` on the cluster (owner roles separate).
2. Reassign schema-object ownership to `poa_migrator`
   (`ALTER TABLE ... OWNER TO poa_migrator` for every table, sequence and the
   ledger; also `ALTER FUNCTION audit_ledger_refuse_mutation() OWNER TO poa_migrator`).
3. Apply `scripts/provision_runtime_roles.sql` as `poa_migrator`.
4. Point the **runtime** `DATABASE_URL` at `poa_runtime`; point the **migration**
   `DATABASE_URL` at `poa_migrator`. Keep them in different secrets.
5. Smoke-test on a non-production target first: one append, one read, one refused
   `UPDATE`/`TRUNCATE`.
6. Recovery: `poa_runtime` can be dropped and re-granted idempotently; ownership is
   restorable to `poa_migrator` (or `postgres`) with `ALTER ... OWNER TO`.

Do **not** alter roles/memberships/ownership/grants in `pofa_dev` or `pofa_test` as
part of this task — that is a separately-approved live operation.

---

## 3. D-PFD — the `pofa_dev` enforcement migration (`s9t0u1v2w029` → `t0u1v2w3x030`)

### 3.1 Disposable-clone proof (measured on `poa_b032r_devclone`)

A `pg_dump --no-owner --no-privileges -Fc` of `pofa_dev`, restored into a named
disposable DB, reproduced the source exactly: `alembic=s9t0u1v2w029`, 6023 ledger
rows (seq 1..6059), 1054 users, **7 gap ranges, no enforcement**. Applying the real
migration path to the clone gave:

- `alembic upgrade head` → `t0u1v2w3x030`; trigger=1, function=1, CHECK=1.
- **Row preservation:** ledger still 6023 rows after the upgrade (the migration
  only adds a trigger, a function and a CHECK — it never touches data).
- **No new integrity findings:** `verify_chain_classified` with baseline
  `pofa-dev-pre-be030-test-cleanup` → `known_historical_only`, 7 known gaps, 0 new
  gaps, 0 hash mismatches. The upgrade neither created anomalies nor hid the
  historical ones.
- Append on the gapped ledger still works (seq 6060), classification unchanged.
- `UPDATE` refused by the now-live trigger.
- **Reversibility:** `alembic downgrade s9t0u1v2w029` removed the trigger/CHECK and
  kept all rows (6024 incl. the test append); `alembic upgrade head` restored
  enforcement with rows intact. Symmetric and history-preserving.

### 3.2 The one precondition the migration enforces

`t0u1v2w3x030.upgrade()` re-measures out-of-domain rows **before** any DDL and
aborts (`EnforcementPreconditionFailed`) if any `event_type` is outside
`AUDIT_EVENT_TYPES`. On the clone (real `pofa_dev` data) this precondition passed
(0 offenders), because BE-029 already reconciled the vocabulary. It also refuses to
double-install objects. Both guards are proven inert-but-correct on the clone.

### 3.3 Live change plan for `pofa_dev` (requires explicit authorization)

- **Preflight:** verified recoverable backup of `pofa_dev` (see §5); confirm
  `alembic current = s9t0u1v2w029`; confirm out-of-domain row count is 0; stop API
  + workers that write to the ledger (they need not stop for reads).
- **Apply:** `DATABASE_URL=<pofa_dev migration URL> alembic upgrade head` (uses the
  armed `verification`/approved context; `alembic/env.py:declare_target` prints the
  server-reported target so the operator sees which DB is touched).
- **Success conditions:** `alembic current = t0u1v2w3x030`; trigger+function+CHECK
  present; ledger row count unchanged vs preflight; `verify_chain_classified` still
  `known_historical_only` (7 gaps, 0 new, 0 hash mismatch); one smoke append lands.
- **Abort conditions:** `EnforcementPreconditionFailed` (out-of-domain rows or
  pre-existing enforcement objects) → migration applies **no DDL**; investigate as
  a separate incident, do not clean data to fit the constraint.
- **Recovery:** `alembic downgrade s9t0u1v2w029` (drops trigger/CHECK, preserves
  rows — proven on the clone) or restore from the preflight backup.

**Boundary:** this document does **not** apply the migration to `pofa_dev`. The
live execution is a separate, explicitly authorized operation.

---

## 4. D-RESTART — API and worker restart procedure

### 4.1 Distinguish the two kinds of restart

- **Disposable restart test** (allowed during verification): start the API/workers
  against a named disposable DB in a scratch container; nothing operational depends
  on it.
- **Operational restart** of `pofa_dev`/production services: a live action requiring
  explicit authorization; not performed as part of BE-032R.

### 4.2 Prerequisite checklist (before any restart that will write)

1. Database reachable and at the expected revision (`alembic current`).
2. Ledger enforcement objects present if the target is meant to be at head.
3. Runtime identity configured per §2 (non-owner) **or** the consciously-accepted
   interim owner model, documented, never both silently.
4. `DATABASE_URL` / `TEST_DATABASE_URL` correct for the environment; production
   `JWT_SECRET` set to a distinct ≥32-char value (see §4.5).
5. Redis, MinIO reachable (readiness depends on them).

### 4.3 API restart + health verification

- Start: `uvicorn backend.app.main:app` (host/port/reload per deployment; the
  programmatic entrypoint is `backend/app/run.py:main`).
- Liveness: `GET /health` (process alive, dependency-agnostic).
- Readiness: `GET /ready` (required dependencies: it builds a **guarded** engine via
  `backend/db/session.build_guarded_engine`, so the armed-context database guard
  applies to the probe itself; also checks Redis).
- Combined snapshot: `GET /healthz`. Metrics: `GET /metrics` (404 unless
  `prometheus_enabled`).
- Acceptance: `/ready` returns success with the intended runtime identity and the
  correct target database reported in logs.

### 4.4 Worker restart + safe-workload check

- Workers: `analysis_worker`, `notification_worker`, `retention_worker`,
  `webhook_worker` — each runs `run_worker()` under `python -m backend.workers.<name>`.
- Start one worker, feed a **safe, disposable** workload (a single analysis job
  against a scratch project), confirm it consumes, produces, and — if it emits an
  audit event — that the ledger append succeeds and the chain verifies.
- Recovery: workers are stateless loop consumers; restart is safe. A worker that
  cannot append (damaged tail → `PredecessorInvalid`) must be investigated, not
  bypassed — no automatic repair exists (D-CHAIN).

### 4.5 JWT-secret / production config

- `backend/core/config.py` now refuses to construct `Settings` in
  `production`/`prod` when `jwt_secret` is the unsafe default, blank, or shorter
  than 32 chars — the value is never echoed in the error. Development/staging keep
  the permissive default so local flow is unaffected.
- Injection/rotation: provide `JWT_SECRET` via the deployment secret store (env),
  never in `.env` committed to the repo. Rotate by setting a new value and doing a
  rolling restart; tokens signed with the old secret stop validating, so schedule
  rotation with the session lifetime in mind. The validation is startup-time and
  does not log the secret.

---

## 5. Backup / restore

- The verified recovery artifact for `pofa_dev` predates this task (BE-029 G3:
  `pg_dump` + restore proof). Note the standing limitation: `archive_mode=off` in
  the container means there is **no true PITR**; `pg_dump` exists only inside the
  container. Re-take a fresh `pg_dump` immediately before any live `pofa_dev`
  migration (§3.3) and restore-test it into a disposable DB before relying on it.
- Keep dumps **outside** the Git repository; never commit them; record location,
  not contents. Do not delete prior backups or recovery artifacts.
