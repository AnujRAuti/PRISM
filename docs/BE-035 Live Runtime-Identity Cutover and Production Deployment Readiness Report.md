# BE-035 — Live Runtime-Identity Cutover and Production Deployment Readiness Report

Date: 2026-10-11
Branch: `Backend` · HEAD at start: `d5685abf` · Interpreter: `backend/.venv312_repro/Scripts/python.exe` (3.12)
Verdict: **DEVELOPMENT RUNTIME CUTOVER VERIFIED — PRODUCTION DEPLOYMENT PENDING**
Production clearance: **NOT CLEARED FOR PRODUCTION.**

> This milestone executes the development runtime-identity cutover that BE-034 deliberately held back.
> It is authorized by the BE-035 task file §1/§2 for the **development** target only, subject to the
> preflight (A), role (B) and fresh-backup (C) gates — all of which passed before any live change was made.
> No production deployment, credential exposure, or protected-data rewrite was performed.

---

## 1. What was actually changed (the cutover)

The development application's runtime database identity was switched from the schema **owner**
(`postgres`, a superuser) to the non-owner least-privilege role **`poa_runtime`**.

- **Config source:** the app, every worker, and Alembic all read a single value
  `settings.database_url` (`backend/core/config.py`), resolved from `.env` (`env_file = ".env"`).
  `.env` is **git-ignored** (`git check-ignore .env` → `.env`; not in `git ls-files`), so this is a
  local, untracked config change — nothing tracked was modified and nothing was committed.
- **Precedence:** no OS-level `DATABASE_URL` was set in the launch shell, so `.env` is authoritative.
  To avoid the "silently inherit the owner URL" hazard (spec §6.2), the cutover was made in the durable
  config (`.env`) rather than as a one-off process-env override.
- **The change:** `.env` `DATABASE_URL` rewritten from
  `postgresql+psycopg2://postgres:***@localhost:5432/pofa_dev`
  to
  `postgresql+psycopg2://poa_runtime:***@localhost:5432/pofa_dev`
  (password read from the existing out-of-band secret file at execution time and never echoed; the
  rewrite was performed by a script that printed only the redacted URL).
- **Migration / runtime separation:** `poa_runtime` has **no DDL** (schema `CREATE=false`) and is not
  the table owner, so Alembic/DDL must **not** run under this identity. `pofa_dev` is already at head
  `t0u1v2w3x030`, so no migration was needed in this milestone. Any future migration must be run with
  an explicit owner/migration `DATABASE_URL` override at invocation time (documented in §10 / backlog).

No source code was changed and no database data was mutated on `pofa_dev` by the cutover.

---

## 2. Phase A — Preflight (reconnaissance, read-only)

Confirmed against current state (not assumed):

| Item | Measured value |
|---|---|
| Branch / HEAD | `Backend` / `d5685abf` |
| Uncommitted at start | `M docs/Backend Technical Debt and Deferred Fixes Backlog.md`; `??` BE-033 report, BE-034 report, BE-033 spec, BE-035 spec |
| API launch mechanism | `uvicorn backend.app.main:app` (programmatic entry `backend/app/run.py:main`, host 127.0.0.1:8000) |
| Workers | `backend/workers/{analysis,notification,retention,webhook}_worker.py`, each `python -m backend.workers.<name>` |
| Current effective dev DB identity | `postgres` (owner / superuser) on `pofa_dev` — the pre-cutover state |
| `pofa_dev` revision / ledger | `t0u1v2w3x030` / **6023** |
| `poa_runtime` on live | exists; non-superuser; can login |
| Long-running owner process | **none found** (`tasklist` empty, no `:8000` listener) — the dev app/workers are started on demand |
| Backup location (outside repo) | `D:/CODING/Scratch/be035/` |
| Recovery method | restore prior `.env` (owner `postgres`) from `D:/CODING/Scratch/be035/env.owner.backup`, restart |

Reported paths confirmed to exist: BE-033/BE-034 reports, canonical backlog, BE-032R runbook,
`scripts/provision_runtime_roles.sql`, `backend/services/audit_integrity_baseline.py`, config/session/auth/
worker/health/Alembic wiring.

---

## 3. Phase B — Runtime-role readiness on live `pofa_dev` (read-only)

Catalog + a real read-only login as `poa_runtime`. No UPDATE/DELETE/TRUNCATE was attempted on the
protected DB (those experiments were done on the disposable clone in §7).

- `poa_runtime`: `super=false login=true createrole=false createdb=false bypassrls=false inherit=false`
  — exactly `NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS`.
- Owns the ledger? **No** — `audit_ledger_events` owner = `postgres`.
- Role memberships: **(none)** — cannot `SET ROLE` into the owner; no elevation path.
- Schema `public`: `USAGE=true`, `CREATE=false` — no DDL from the runtime identity.
- Ledger privileges: `SELECT=true INSERT=true UPDATE=false DELETE=false TRUNCATE=false`.
- Ordinary tables (workers' normal DML): `users` `SELECT/INSERT/UPDATE/DELETE=true`; `webhook_deliveries` `UPDATE=true`.
- Live login as `poa_runtime` reads the ledger: `current_user=session_user=poa_runtime`, `count=6023`.

All documented properties match the live state; no divergence. Proceed.

---

## 4. Phase C — Fresh recovery point (backup + restore proof)

- Dump: `pg_dump -U postgres --format=custom pofa_dev` **in-container** (host has no `pg_dump`), exit 0.
- Stored outside the repo: `D:/CODING/Scratch/be035/be035_pofa_dev_current.dump`
  - size **1,778,724 bytes**
  - SHA-256 `f9583a51d199ec06a24f7c69036ca7a615c7d38d3fac7f3fcef5224abd26aeae`
  - **distinct** from the BE-034 dump SHA (`ff8255a9…`) → this is a fresh dump of the *current* DB, not the
    pre-BE-033 artifact.
- Restore proof: `pg_restore -U postgres --no-owner` into disposable `poa_b035_restore`, exit 0, zero stderr.
  Restored state matches live source exactly: `rev=t0u1v2w3x030`, `ledger=6023`,
  `trg_audit_ledger_append_only=1`, `audit_ledger_refuse_mutation=1`, `ck_audit_ledger_event_type_domain=1`,
  `users=1054` readable. `poa_runtime` grants carried over and it can read the clone (`ledger=6023`).
- **Limitation (documented accurately):** the container runs `archive_mode=off`, so a `pg_dump` is a
  *consistent snapshot*, **not** point-in-time recovery.

Backup and restore verification both passed → proceed to the cutover.

---

## 5. Phase D — Cutover result: the running dev API uses `poa_runtime`

After rewriting `.env`:

- Started the real API: `uvicorn backend.app.main:app --host 127.0.0.1 --port 8000` (pid 11444);
  startup log clean, `Application startup complete`, **no fallback / no auth error**.
- **Effective identity proof** — `pg_stat_activity` on `pofa_dev` while the app ran:
  ```
  poa_runtime | 1  (application_name empty = the app's psycopg2 connection)
  postgres    | 1  (application_name=psql = my own read-only probe)
  ```
  The running application's database connection is `poa_runtime`. The only `postgres` connection was the
  operator probe. **No silent fallback to the owner.**

---

## 6. Phase E — Health surface of the running `poa_runtime` API

All six routes are registered (`/api/v1/health`, `/api/v1/ready`, `/health`, `/ready`, `/healthz`,
`/metrics`). No unregistered path was counted.

| Endpoint | HTTP | Result (safe fields) |
|---|---|---|
| `/api/v1/health` | 200 | `{"status":"ok"}` |
| `/api/v1/ready` | 200 | `{"status":"ok"}` |
| `/health` | 200 | liveness: application healthy |
| `/ready` | 200 | **`postgresql`: healthy "PostgreSQL connection successful" (required:true)**, `redis`: healthy, `storage`: healthy |
| `/healthz` | 200 | liveness + readiness combined; postgresql healthy |
| `/metrics` | 200 | Prometheus exposition present (`prometheus_enabled`) |

PostgreSQL connectivity is established by the readiness probe + `pg_stat_activity` identity, not inferred
from a static 200.

---

## 7. Phase F — Worker behavior (safe) + Phase G — integrity & append-only

### 7.1 Worker startup / identity (Phase F)

- `analysis_worker`, `notification_worker`, `retention_worker` **import cleanly**.
- All workers build their engine from the same `backend.db.session` + `settings.database_url` the API uses,
  which §5 proved connects as `poa_runtime`. Ordinary reads/writes are within the §3 grants.
- **Finding BE-035-D1 (pre-existing defect, not caused by the cutover):**
  `backend/workers/webhook_worker.py:20` does `from backend.db.session import SessionLocal`, but
  `backend/db/session.py` exports no `SessionLocal` symbol (only `get_session()` / `_SessionLocal`). The
  module therefore raises `ImportError: cannot import name 'SessionLocal' from 'backend.db.session'` and
  **cannot start at all** — independent of database identity. It uses `SessionLocal()` at lines 269 and 294.
  The other three workers already use `get_session()`. Minimal remediation would be to switch those two
  call sites to `get_session()` and add an import/startup test; this is a **source-code change outside the
  operational-cutover scope**. **Owner decision (2026-10-11): leave it as a documented finding — not fixed
  in BE-035; deferred to a narrow follow-up.** Per spec: the webhook delivery loop performs real `urllib`
  network calls, so it was **not** loop-started against live `pofa_dev` regardless.

### 7.2 Ledger append + append-only enforcement (Phase G) — executed on the disposable clone

Because `pofa_dev`/`pofa_test` are protected (no destructive experiments), the write/denial smoke ran on the
faithful clone `poa_b035_restore` through the app's own code path, as `poa_runtime`:

| Check | Result |
|---|---|
| identity | `current_user=session_user=poa_runtime` |
| `verify_chain_classified(baseline="pofa-dev-pre-be030-test-cleanup")` **before** | `known_historical_only`, known=**7**, new=**0**, hard=**0**, writer_policy=`controlled_continuation` |
| app-path `append_event` (`ANALYSIS_COMPLETED`, valid UUID resource_id) | **APPEND_OK** (seq 6060, 6061) — authorized appends work under the least-privilege role |
| `verify_chain_classified` **after** | `known_historical_only`, known=7, **new=0**, **hard=0** — appends introduce no new gaps/mismatches and hide nothing |
| `UPDATE` ledger | **DENIED** `InsufficientPrivilege: permission denied for table audit_ledger_events` |
| `DELETE` ledger | **DENIED** `InsufficientPrivilege` |
| `TRUNCATE` ledger | **DENIED** `InsufficientPrivilege` (the F-05 non-ownership fix) |
| `SET ROLE postgres` | **DENIED** `permission denied to set role "postgres"` |
| ordinary-table write (`users`) | **PERMITTED** |

The denials occur at the **permission layer** (before the trigger), which is defense-in-depth: it no longer
depends on the mutation-hatch GUC being unset.

### 7.3 Live integrity, read-only (Phase G against `pofa_dev`)

Through the running `poa_runtime` API (read-only):

- `GET /api/v1/audit/verify/anchored?baseline=pofa-dev-pre-be030-test-cleanup` →
  `valid=false`, `checked_events=6023`, `first_sequence=1`, `last_sequence=6059`, the **7 known historical
  gaps** listed verbatim (not concealed), `classification.status=known_historical_only`, `degraded=false`,
  checkpoint `tail_event_hash=c1c012687c44563a…`.
- `GET /api/v1/audit/verify/anchored` (no baseline) → the same 7 gaps are reported against the safe
  default-deny baseline (nothing is auto-blessed as historical) — the baseline contract behaves as designed.
- **Protected-DB integrity after the whole milestone:** live `pofa_dev` still `rev=t0u1v2w3x030`,
  **ledger=6023**, enforcement trigger present; the clone's appends (6060/6061) and the smoke writes never
  touched it. `poa_runtime` active connection count after cleanup = 0.

---

## 8. Phase H — JWT secret and production-deployment readiness

Application-side validator (`backend/core/config.py`) exercised at config level:

| environment | jwt_secret | outcome |
|---|---|---|
| production | `changeme` | **REJECTED** |
| production | `""` (empty) | **REJECTED** |
| production | `<32 chars` | **REJECTED** |
| production | 32-char valid | **ACCEPTED** |
| development | `changeme` | ACCEPTED (permissive default preserved) |
| staging | `""` | ACCEPTED (non-prod unaffected) |

- **No-secret-leak check:** a distinctive short secret in production is rejected and the canary value does
  **not** appear in the `ValidationError` text (`CANARY_LEAKED_IN_ERROR: False`).
- **Production store status:** this environment has **no production deployment target and no production
  JWT secret store** (only the dev stack containers `pofa_db`/`pofa_redis`/`pofa_minio` are running).
  Therefore a real production secret has **not** been injected and none is claimed. Configuring the
  production `JWT_SECRET` (distinct, ≥32 chars) via a real secret store, and the production runtime
  identity, remain **external deployment actions** (§11).

The application-side validator working does **not** make the project production-ready.

---

## 9. Phase I — Regression

Focused suites run on `pofa_test` with an explicit `TEST_DATABASE_URL` (never `pofa_dev`, never `.env`
fallback), repro interpreter:

```
TEST_DATABASE_URL=postgresql+psycopg2://postgres:***@localhost:5432/pofa_test \
  python -m pytest -q \
  tests/unit/{test_audit_guard,test_audit_integrity_baseline,test_be030_ledger_contract,
              test_configuration_and_logging,test_database_safety,test_health,test_audit_ledger,
              test_authorization}.py \
  tests/integration/{test_be030_ledger_enforcement,test_be032r_anchored_verification,
                     test_be029_audit_ledger_history,test_be029_database_safety_guard,
                     test_audit_ledger,test_authorization}.py
```

Result: **168 passed, 0 failed** (306s). Coverage: database safety, ledger enforcement, historical-gap
classification, anchored verification, health/readiness, auth + JWT config, authorization. No security
assertion was weakened and no ledger history was altered to achieve this.

(BE-032R baseline 821/1/0 and BE-034 focused 84 are prior comparison points; 168 here is this run's fresh
count, not a claim about them.)

---

## 10. Recovery / rollback

- **Was recovery needed?** No. The cutover succeeded on the first attempt; no rollback was performed.
- **Rollback path (matches the actual config):** the original owner configuration is preserved securely
  outside the repo at `D:/CODING/Scratch/be035/env.owner.backup`. Restoring `.env` to that `postgres`
  `DATABASE_URL` and restarting returns the dev app to the prior identity. Roles/grants on `pofa_dev` were
  not altered in this milestone, so no role rollback is implicated.
- **Recovery point:** `D:/CODING/Scratch/be035/be035_pofa_dev_current.dump` (SHA-256 §4), restore-proven into
  `poa_b035_restore` (since dropped).

---

## 11. Completion gates

### Development runtime cutover
- [x] API uses `poa_runtime` (`pg_stat_activity`).
- [~] Relevant workers use `poa_runtime` — analysis/notification/retention import and share the `poa_runtime`
      engine; **webhook worker cannot start (BE-035-D1), so its running identity is unverified.**
- [x] No unintended owner-level application connection remains (only the operator `psql` probe was `postgres`).
- [x] Legitimate operations succeed (readiness, app-path append, ordinary writes).
- [x] Unauthorized ledger mutations remain denied (UPDATE/DELETE/TRUNCATE/`SET ROLE` denied on the clone).

### Running-service verification
- [x] Actual health/readiness endpoints pass (all six, 200).
- [x] PostgreSQL readiness verified, not inferred (explicit `postgresql: healthy` + identity).
- [~] Worker checks completed safely — three verified; webhook blocked by BE-035-D1.
- [x] Ledger appends + integrity classification behave as expected (7/0/0 stable).
- [x] Historical gaps preserved (all 7 still reported).
- [x] No new unexplained anomalies (0 new gaps, 0 hash mismatches).

### Security and recovery
- [x] Fresh backup + restore proof recorded (§4).
- [x] Runtime and migration identities separated by capability (no DDL for `poa_runtime`).
- [x] No secrets exposed (password redacted throughout; not written to tracked files).
- [x] Recovery instructions match the actual config (§10).

### Production deployment — **PENDING**
- [ ] Production deployment target identified — **none exists in this environment.**
- [ ] Distinct valid production JWT secret configured — **no prod secret store.**
- [ ] Production runtime identity configured — external action.
- [ ] Production health and integrity checks performed — external action.

---

## 12. Files changed

- `.env` (git-ignored, local only): `DATABASE_URL` owner→`poa_runtime`. **Not tracked, not committed.**
- `docs/BE-035 Live Runtime-Identity Cutover and Production Deployment Readiness Report.md` (this file).
- `docs/Backend Technical Debt and Deferred Fixes Backlog.md` (F-05 + D-RESTART rows; §8 BE-035 reconciliation).
- No backend source code was modified (BE-035-D1 was reported, not fixed — owner decision).

---

## 13. Final verdict & remaining actions

**DEVELOPMENT RUNTIME CUTOVER VERIFIED — PRODUCTION DEPLOYMENT PENDING.**

The actual development API now runs as the non-owner least-privilege `poa_runtime` against live `pofa_dev`,
with readiness confirming PostgreSQL, all six health endpoints passing, the app-path ledger append working
while UPDATE/DELETE/TRUNCATE/`SET ROLE` stay denied, the seven historical gaps still correctly classified,
no secrets exposed, and 168 focused tests passing. Production is **not** cleared.

**Open items / owner decisions**
1. **BE-035-D1** — `webhook_worker` cannot start (`ImportError` on `SessionLocal`). Pre-existing, unrelated
   to the identity switch; the fix is a one-line change to `get_session()` plus an import test. **Owner
   decision (2026-10-11): leave as a documented finding; deferred to a narrow follow-up** (not applied in
   this operational-cutover milestone).
2. **Production deployment actions (out of this milestone's scope):** identify a production target, create a
   production JWT secret store with a distinct ≥32-char secret, configure the production runtime identity as
   `poa_runtime`, run production health + integrity checks, and split runtime vs migration `DATABASE_URL`
   secrets for real Alembic operation.
3. **Durable dev state:** `.env` intentionally remains on `poa_runtime`; the original owner config is
   recoverable from `D:/CODING/Scratch/be035/env.owner.backup`.
