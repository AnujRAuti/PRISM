# BE-027 — Backend Foundation & Core API Stabilization: Implementation Report

**Task:** BE-027 (`docs/Production Task Files/BE-027 — Backend Foundation & API Contract.md`)
**Branch:** `Backend` · **Date:** 2026-10-06
**Gate decision:** **PASS as a foundation/stabilization task**, with three open blockers (§7) that BE-027 explicitly instructs be reported rather than improvised around.
**Headline:** the foundation this task asks for **already exists** in this repository and was **not** replaced. BE-027 found two real defects in it, fixed both with the smallest possible change, proved the foundation works from an empty database, and closed the one genuinely missing obligation (§24 dedicated tests).

---

## 1. Repository Audit

Task file §4 required a complete audit before any modification. Answers to its thirteen questions, each with the evidence that produced it.

| # | Question | Answer | Evidence |
|---|---|---|---|
| 1 | Backend framework | FastAPI 0.141.1 on uvicorn 0.23.1, Python 3.12 | `requirements.txt:1-2`, `backend/app/main.py:25` |
| 2 | Entry point | `backend/app/main.py` → ASGI app object `app` (`backend.app.main:app`) | `backend/app/main.py:25` |
| 3 | Database access | SQLAlchemy 2.0.52 ORM; one lazily-created engine + `get_db()` request generator | `backend/db/session.py:13-33` |
| 4 | ORM/query layer | SQLAlchemy declarative models; per-domain repository modules for the newer surfaces (audit, field, governance, publication, retention…) — the BE-007-era context CRUD still queries the ORM inside the endpoint | `backend/repositories/` (14 modules), `backend/api/v1/endpoints/context.py:43` |
| 5 | Database configured | PostgreSQL 15 + PostGIS 3.4.2 + pgvector 0.7.4 in container `pofa_db` (image `garapadev/postgres-postgis-pgvector:15-stable`); dev DB `pofa_dev`, test DB `pofa_test` | `docker-compose.yml:4`, `pg_extension` measured |
| 6 | PostGIS configured | Yes — `CREATE EXTENSION IF NOT EXISTS postgis; vector;` runs inside the initial migration, so every fresh database gets both | `alembic/versions/bb4bf0dd8fb7_initial_migration.py:25-26` |
| 7 | Models existing | 70 model classes, including all five entities §7 asks for: `User` (`:41`), `Project` (`:67`), `Evidence` (`:110`), `ReviewDecision` (`:234`) + `ReviewCase` (`:715`), `AuditEvent` (`:244`) + hash-chained `AuditLedgerEvent` (`:1063`) | `backend/db/models.py` (3400 lines) |
| 8 | Routes existing | 21 routers under a single `/api/v1` prefix, 154 paths / 180 operations, plus the BE-020 probe family at root | `backend/api/v1/router.py:29-53`, live `/openapi.json` |
| 9 | Working | Startup, config, migrations, DB connectivity, PostGIS, project/activity/claim/evidence CRUD, auth+authz, audit ledger, health/readiness/metrics, OpenAPI, 695 passing tests (420 unit + 275 integration) | §5 below |
| 10 | Incomplete or broken | 3 blockers (§7): declared user uniqueness not enforced by the schema; `alembic check` fails with 16 unreviewed drift operations; CORS opened every origin with credentials on. Plus the debt list in §8 | measured, §3/§4/§7 |
| 11 | Migrations existing | 21 revisions, single linear chain, head `p6q7r8s9t026`, graph pinned by `tests/unit/test_migrations.py` (`EXPECTED_HEAD`, `EXPECTED_REVISION_COUNT = 21`) | `alembic/versions/`, test green |
| 12 | Tests existing | 420 unit + 275 integration tests against a dedicated test database with a hard refusal to fall back to `pofa_dev` | `tests/conftest.py`, `backend/db/test_target.py` |
| 13 | Preserve | Everything in #1–#12. No framework, ORM, database, routing or auth replacement was made or is needed | §2 changes list |

**Architecture verdict.** §3's target chain (router → validation → service → repository → PostgreSQL/PostGIS) is already the shape of this codebase for every domain added from BE-015 onward. §4's instruction — *"DO NOT replace existing architecture simply because another architecture may look cleaner"* — is the governing finding: this repository is **six milestones past** a "foundation" milestone (BE-022 publication, BE-023 test environment, BE-024 production hardening, BE-025 admin plane, BE-026 field operations). §5's "previously considered" list (Drizzle, Zod, Supabase) is not in use and was not introduced; §6's reference directory layout differs from the real one (`backend/api|core|db|engines|observability|repositories|schemas|security|services|workers`) and was not forced onto it, per §6's own warning.

---

## 2. Changes Made

Five modified files, two new test files. **No dependency was added** (§31) and **no production response contract changed** (§29 evidence: the live OpenAPI document is byte-identical to the committed `openapi.json`).

| File | Change | Why |
|---|---|---|
| `backend/core/logging.py` | `RequestIdFilter` moved from the root logger to the handler; format string promoted to `LOG_FORMAT` | F-BE027-02 (§23) |
| `backend/core/config.py` | new `cors_allow_origins` setting (default `"*"`, so nothing changes by itself) + `cors_origin_list` parser | F-BE027-01 (§20/§21) |
| `backend/app/main.py` | `CORSMiddleware` now built from `settings.cors_origin_list` instead of a hardcoded `["*"]` | F-BE027-01 |
| `.env.example` | documents `CORS_ALLOW_ORIGINS` with the credentials warning | §20 — no secrets added |
| `tests/integration/test_be027_foundation_contract.py` | **new**, 17 tests: the §24 foundation contract | §24 was the one genuinely missing obligation |
| `tests/unit/test_configuration_and_logging.py` | **new**, 5 tests: CORS wiring + log-filter placement | pins both fixes |
| `tests/integration/test_migration_and_crud.py` | `test_basic_crud` given per-run identifiers and a `finally` cleanup; assertions kept and extended | §25 test-database safety |

Deliberately **not** changed, with reasons in §7/§8: the wildcard CORS *default* (tightening is a deployment decision that needs the frontend's real origins), `ProjectCreate`'s tolerance of unknown fields, `review_decisions`' missing status constraint, the legacy context-CRD layering, and every historical migration.

---

## 3. Database

**Models added/modified: none.** §7's five entities and §8's relationships already exist; §7.3's "do not implement all of those unless the repository already requires them" is moot because `Evidence` already carries `sha256`, `phash`, `location`, `content_type`, `file_size`, `status`, `project_id`, `claim_id` (`backend/db/models.py:110-127`) with EXIF in `evidence_metadata`.

**Migrations added: none.** Existing history untouched, unmodified, undeleted (§9). Head is `p6q7r8s9t026`; `pofa_test` is at that head.

**The schema reproduces from empty — measured, not asserted.** A database created for this report (`pofa_be027_scratch`) and dropped afterwards took all 21 revisions from nothing:

```
tables 74 · head p6q7r8s9t026 · extensions plpgsql, postgis 3.4.2, vector 0.7.4
foreign keys 113 (17 ON DELETE CASCADE) · unique constraints 79
check constraints 102 · indexes 261 · geometry columns 1
```

and the live API served the whole Project lifecycle against it (§5, "from-scratch" block). This is the §9/§37 requirement: a clean database is initializable from the repository's documented process.

**PostGIS (§28): enabled and used.** `evidence.location` is `Geometry(geometry_type="POINT", srid=4326)` (`backend/db/models.py:122`), and `GET /api/v1/projects/{id}/evidence/nearby` runs a real radius query — covered by the shipped `test_nearby_queries_use_postgis_radius_and_project_scope`. No geofence engine was built.

**Constraints (§34): mostly strong, with one measured hole.**

- Delete rules, counted over `pg_constraint`: 60 `NO ACTION`, 35 `RESTRICT`, 17 `ON DELETE CASCADE`, 1 `SET NULL`. The 17 cascades are all derived-artifact edges (`vision_detections→analysis_results`, `webhook_deliveries→webhook_events`, `role_permissions→roles`, …).
- §8's audit warning is satisfied and this is the check that proves it: **`0` foreign keys reference `audit_ledger_events` or `audit_events`**, and no cascade reaches either table. Audit rows cannot be deleted as a side effect of domain deletes.
- **Hole (B-1):** `User.username` and `User.email` are declared `unique=True` (`backend/db/models.py:44-45`) but the initial migration created them as non-unique indexes (`alembic/versions/bb4bf0dd8fb7_initial_migration.py:139-140`, `unique=False`). `\d users` confirms: `ix_users_username btree (username)` — not unique. The only database-enforced identity constraint on `users` is `uq_user_identity_subject (identity_provider, external_subject)` from BE-016.
- `review_decisions.decision` is a `varchar(50)` with **no CHECK** and **0 rows** in `pofa_test`; §7.4's pending/approved/rejected/needs_review vocabulary is actually enforced in the BE-013 `review_cases` tables, so the legacy table is unconstrained and unused.

---

## 4. API

**Endpoints added: 0. Endpoints modified: 0.** §12's "preserve `/api/v1/...`" was followed literally; no second prefix was introduced.

**§13–§16 asked for a complete minimal Project API. It already exists and works** — `backend/api/v1/endpoints/context.py:54,68,84,93`:

| Endpoint | Status | Verified behaviour |
|---|---|---|
| `POST /api/v1/projects` | 201 | validates, writes, returns the **persisted** id — a second connection reads the row back and matches |
| `GET /api/v1/projects` | 200 | `ProjectListResponse{items,limit,offset,total}`, owner filter, scope-filtered by `filter_by_project_scope`, `limit 1..100`/`offset ≥ 0` enforced |
| `GET /api/v1/projects/{id}` | 200 / 404 / 422 | exists → real row; valid UUID but absent → `404 Project not found`; malformed → 422 |
| `PATCH /api/v1/projects/{id}` | 200 | rename persists to the database |

All four are guarded by `require("project.*")` — and that guard is real: with `AUTH_MODE=enforcing`, an anonymous `GET /api/v1/projects` returns **401** (measured against a live server). §22's "if authentication is already implemented, preserve it" is satisfied; nothing was added, replaced or disabled.

**§17/§18 schemas.** `ProjectCreate` (`name` 1–256 chars, `owner_id` UUID) and `ProjectResponse` (`id`, `name`, `owner_id`, `created_at`, `from_attributes`) are explicit; the shipped test asserts the response key set is **exactly** those four, so no ORM column can leak in unnoticed. One deviation is reported rather than patched: `ProjectCreate` does not set `extra="forbid"` (measured: a body carrying `is_admin`, `status` and `role` returned 201 — the values were dropped, never persisted, and never consulted for authorization, so this is a strictness gap, not an escalation). §30 forbids breaking a contract for an unseen client unilaterally, and no client in this repository sends extra keys.

**§11 health.** The repository separates the two questions, which is what §11 actually needs, and the separation is now pinned by tests:

- `/api/v1/health` → `{"status":"ok"}` — process alive, and **makes no database claim at all** (the test asserts `"database"` is absent, so nobody can quietly turn it into the §42 anti-pattern "always says the database is healthy").
- `/api/v1/ready` → runs `SELECT 1` on the real pool; 503 `{"status":"unavailable"}` if it fails.
- `/health`, `/ready`, `/healthz`, `/metrics` (BE-020 family) → liveness vs readiness vs combined, with `postgresql`/`redis`/`storage` reported individually and required-check failure flipping the status. Measured live: `healthy · {application, postgresql, redis, storage: healthy}`.
- The honest-DB obligation is tested with a **real** connection refusal, not a fake: `PostgresHealthCheck` against a DSN on a port nothing listens on returns `UNHEALTHY`, and `get_readiness()` then reports `unhealthy` with `postgresql: unhealthy`.

**§19 error handling.** Validation → 422, unknown owner → 404 `Owner not found`, absent project → 404, malformed id → 422, unexpected → 500 `{"detail":"internal server error"}` via the app's catch-all (`backend/app/main.py:69-71`). The no-leak requirement is tested with a genuine `SQLAlchemyError` (route executed against an engine pointed at a dead address): the body is exactly `{"detail":"internal server error"}` and contains no `Traceback`, no `psycopg2`, no source path, no `SELECT`, and not the password planted in the DSN.

**§21 CORS — defect and fix.** With `allow_origins=["*"]` **and** `allow_credentials=True`, Starlette echoes whatever `Origin` the caller sent. Measured on the pre-fix wiring: a request from `https://evil.example` received `access-control-allow-origin: https://evil.example` plus `access-control-allow-credentials: true`, and the preflight did the same. The origin list is now built from `CORS_ALLOW_ORIGINS`. Verified both directions against live servers:

- default (unset) → behaviour identical to before, so nothing that works today stops working;
- `CORS_ALLOW_ORIGINS="http://localhost:3000,http://127.0.0.1:5173"` → listed origin gets its own origin echoed; `https://not-configured.example` gets **no** `access-control-allow-origin` header, which is what makes a browser block the cross-origin read.

The remaining decision — what the real allowlist should *be* — is B-2 in §7, because this repository contains no frontend to read the answer from.

**§29 documentation.** `/docs` and `/redoc` return 200. The generated spec documents every project route with request body and response codes (`POST /api/v1/projects → 201/422`, `GET → 200/422`, `PATCH → 200/422`, plus activities and claims). The committed `openapi.json` is **byte-identical** to the live spec (154 paths, 180 operations, zero added, zero removed), which also proves no response contract drifted.

---

## 5. Tests

Every run below names its exact command and its exact result. `TEST_DATABASE_URL` was explicit in every pytest invocation; the suite refuses to fall back to `pofa_dev` (`tests/conftest.py:10`), and every standalone script/alembic/uvicorn run exported `DATABASE_URL` for `pofa_test` or the scratch database.

**Commands**

```bash
# unit
TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test" \
backend/.venv312_repro/Scripts/python.exe -m pytest -q -p no:randomly -p no:cacheprovider \
  --tb=line -W ignore tests/unit

# integration
… same interpreter and flags … tests/integration

# targeted (new + rewritten foundation file)
… same … tests/integration/test_migration_and_crud.py tests/integration/test_be027_foundation_contract.py

# migration graph / drift
DATABASE_URL="…pofa_test" backend/.venv312_repro/Scripts/python.exe -m alembic check
DATABASE_URL="…pofa_be027_scratch" … -m alembic upgrade head

# live server
DATABASE_URL="…pofa_test" AUTH_MODE=enforcing … -m uvicorn backend.app.main:app --port 8123
```

**Results**

```
Backend startup (uvicorn, fresh process, migrated DB)      PASS
  /api/v1/health 200 · /api/v1/ready 200 · /health 200
  /ready 200 · /healthz 200 · /metrics 200 · /openapi.json 200
Health endpoint: alive ≠ database-healthy                  PASS
Health endpoint: real connection refusal -> UNHEALTHY      PASS
  (test_readiness_reports_the_database_as_unavailable_when_it_really_is)
Project creation                                           PASS
  golden path persists a readable row + returns its id
  5 invalid-body variants -> 422 · unknown owner -> 404
Project retrieval                                          PASS
  existing 200 · valid-but-absent 404 · malformed 422
Project listing                                            PASS
  owner with no projects -> {items: [], total: 0}
  3 projects -> total 3, schema-exact items, limit/offset pages
  partition exactly, out-of-range limit/offset -> 422
Project patch                                              PASS
Validation (request schemas, path ids, pagination bounds)  PASS
Error handling / no internal leak on a real DB failure     PASS
Migration check — apply                                    PASS
  test_alembic_upgrade_head green; 21 revisions from empty
  -> 74 tables, postgis+vector present, head p6q7r8s9t026
  and the API served create/read/list/404 on that schema
Migration check — schema drift                             **FAIL**
  `alembic check` reports 16 operations (see B-1/B-3 §7)
PostGIS capability                                         PASS
  Geometry(POINT,4326) column + shipped radius-query test
Existing suite — full unit                                 420 passed, 1 skipped
Existing suite — full integration (run twice, before/after) 275 passed, 1 failed
  the one failure predates BE-027 and is unrelated: see §6
Audit chain after all runs                                 PASS
  {valid: true, checked_events: 28582, first_sequence: 1,
   last_sequence: 28582, failures: []}
New BE-027 tests                                           22 passed (17 + 5)
Rewritten test_basic_crud, run twice back-to-back           2 passed x2
  (the non-repeatable name collision it used to rely on is gone;
   residue afterwards: testuser-% / be027-% / probe-% = 0 rows)
Residue from BE-027's own tests                            0 rows
  the two new files alone: users 1960 -> 1960, projects 983 -> 983
  username LIKE 'be027-%' / 'testuser-%' / 'probe-%' = 0
  (absolute totals move between sessions because other suites' fixtures
   create rows; BE-027's tests create and remove their own)
```

**Test-database safety (§25).** Nothing in this task touched `pofa_dev`, truncated anything, or deleted a single audit row. The scratch database was created, used, and dropped by the same session that created it.

---

## 6. Existing Functionality

**Verified, with no regression attributable to BE-027.** The full integration suite ran twice: once with all BE-027 production changes in place, and once again after the test-file rewrite. Both times: **275 passed, 1 failed** — identical, and the failure is pre-existing and known:

`tests/integration/test_be025_admin_control_plane.py:535` — `test_organization_lifecycle_noop_audit_and_isolation` asserts the organization it just created appears in the **first page** of `GET /api/v1/auth/organizations`, which returns `limit=50` of the **94** organizations currently in `pofa_test`. It is a volume-sensitive assertion against a shared, never-truncated test database, recorded before BE-027 and left exactly as it is: **not weakened, not skipped, not "fixed" by raising the limit.** Its cause is accumulation, not behavior — and BE-027's own tests are provably residue-free (§5), so this task neither created nor worsened it.

Also verified as still intact: the project/activity/claim contracts (`test_be007_contracts`), the authorization suite (`test_authorization`), the field-operations suite (`test_be026_field_operations`, 43 tests) and the admin plane apart from the one known assertion, the append-only audit guard (`test_audit_guard`, `test_audit_ledger`), and the response contracts themselves — `openapi.json` unchanged to the byte.

**§30 frontend compatibility:** this repository contains no frontend (no `package.json`, no `.tsx`/`.vue` anywhere). Every endpoint's contract was left byte-identical, so any client outside this repository is unaffected by default; the only way behaviour changes at all is if an operator opts into `CORS_ALLOW_ORIGINS`.

**Working-tree observation (not caused by this task).** During BE-027, 27 tracked documentation files — the root BE-020/021/024 summaries and `docs/BE-022 … BE-026 Stage A–E` plus the Final Acceptance reports, 9,234 lines, including the FOUND→FIXED→VERIFIED history this task depends on — were deleted from the working tree by a parallel process (directory mtimes 22:22/22:24; `docs/Production Task Files/PoA — Codebase Cleanup, Efficiency & Deferred Fixes.md` is present as a task file). Nothing was committed, so all of it is recoverable from `HEAD`. Per the operator's instruction this session left those deletions alone rather than restoring them. **BE-027 did not delete, restore, stage, commit or stash any of them.**

---

## 7. Issues / Blockers

Reported instead of acted on, exactly as §43 directs.

**B-1 · The schema does not enforce the identity uniqueness the models declare. (High, data-integrity.)**
`users.username` / `users.email` are non-unique in the migrated database (§3). Consequences measured: 19 duplicate `testuser` rows in `pofa_test`; **1 duplicated username group and 1 duplicated email group already exist in `pofa_dev`**, the real development data. Adding `UNIQUE` therefore cannot be done safely: the migration would fail on existing rows, and making it pass requires choosing which duplicate survives — a destructive decision about data BE-027 does not own. Note the interaction: the old `test_basic_crud` kept "passing" *because* of this hole, which is how the gap stayed invisible. §43 stop condition — *"the database cannot be safely migrated without destroying existing data"* — applies; §43 says report and wait.

**B-2 · `alembic check` fails, and no gate catches it. (Medium, drift.)**
Sixteen unreviewed operations separate `Base.metadata` from the migrated schema. They are not all the same thing, and the distinction matters for any fix:
- *genuine*: the two `users` unique indexes (B-1).
- *reflection/naming drift, harmless but noise*: metadata wants `ix_projects_name` while the DB has `ix_projects_owner`; wants `ix_analysis_jobs_status` and `ix_evidence_metadata_evidence_id` (auto-named) while the migrations created explicitly-named indexes; and reports `uq_user_role_scoped` as changed on `nulls_not_distinct` alone.
- *DB has it, metadata doesn't*: `uq_duplicate_match_pair`, `uq_graph_relationships_dedupe_active`, `uq_review_case_active_run` — three integrity rules that exist only because a migration wrote them by hand, so `create_all` would silently omit them.
- *expected noise*: `spatial_ref_sys` (a PostGIS system table).
`tests/unit/test_migrations.py` validates the revision **graph** only, so a drifting schema is invisible to the suite.

**B-3 · CORS is configurable but the default is still every origin. (Medium, deployment.)**
The mechanism is fixed and proven (§4). The remaining half is a decision, not code: the safe value is the real frontend's origin list, and there is no frontend in this repository to derive it from. Changing the shipped default from `*` to a guessed list would break the first non-guessed client. **Action required from the operator:** set `CORS_ALLOW_ORIGINS` for every shared deployment, alongside `AUTH_MODE=enforcing` (the default `development` mode logs `AUTH_MODE=development: anonymous requests bypass authorization` on every anonymous call — measured).

**Carried forward, unchanged and not worked around:** DF-SE-01 (`resolve_principal` converts any `SQLAlchemyError` into a 401 credential failure, so a Postgres outage answers 401 rather than 503 — recorded in the BE-024 Final Acceptance Report §8 as Low/non-blocking/intentionally deferred, re-measured in BE-026 Stage E) and DF-SE-02. Both predate BE-027 and both are outside its authority to redesign.

---

## 8. Technical Debt

Intentionally deferred, with the reason for each.

- **D-1 · `ProjectCreate`/`ProjectUpdate` accept unknown fields.** Measured 201 with `is_admin`/`status`/`role` in the body; values dropped, never persisted, never trusted for authorization. Making them `extra="forbid"` is a one-line change and a contract tightening; it belongs with B-2's drift decision, not smuggled into a stabilization task.
- **D-2 · `review_decisions.decision` is an unconstrained `varchar(50)`** and the table holds 0 rows. §7.4's status vocabulary is enforced in the BE-013 `review_cases` surface instead. A CHECK here would be correct but is dead weight until the legacy table is either populated or retired.
- **D-3 · The BE-007-era context CRUD (`/projects`, `/activities`, `/claims`) queries the ORM from the endpoint**, while every later domain goes through `backend/repositories/` + `backend/services/`. §3's concern ("future features must not turn the backend into one large collection of route handlers") is met for new work; retrofitting the old four endpoints into the repository pattern is churn with no behavioural gain and would touch contracts §30 protects.
- **D-4 · `PostgresHealthCheck` builds and disposes an engine per probe** (`backend/observability/health.py:84-101`) instead of reusing the app pool. Defensible — a probe must not inherit a poisoned pool, and it does dispose — but it costs a fresh connection per readiness poll. Left alone: BE-024/BE-026 verified this behaviour under outage conditions.
- **D-5 · `pofa_test` accumulates rows across milestones** (94 organizations, 19 duplicate `testuser` users, ~1,960 users). It is the direct cause of the §6 known failure and will block B-1's unique index until the table is reconciled.
- **D-6 · Repository-root clutter predating this task**: `pofa_dev.db` (a SQLite file in a PostgreSQL project), `stage_d_runtime_checks.py`, `stage_e_runtime_checks.py`, `test_vision_temporal_auth.py`, `yolo11n.pt`, `temp_test_env/`, `tmp_test_env/`. Several are git-tracked. Untouched — §38 excludes unrelated cleanup, and one parallel session is already working on exactly that.
- **D-7 · `backend/services/BE-019 … .md`** — a task file stored inside a source package. Cosmetic, harmless, left alone.

---

## 9. Next Recommended Task

**BE-027b — Schema Integrity & Drift Containment.** Not the next feature milestone; the foundation has one unclosed hole and it is now precisely measured.

1. **Decide the identity contract first** (B-1): either enforce `UNIQUE` on `users(username)` / `users(email)` with an explicit, reviewed deduplication of `pofa_dev` and `pofa_test` — or record that `identity_provider + external_subject` is the *only* real identity and remove the `unique=True` declarations so the models stop lying. Both endings are acceptable; the current state (code claims it, database declines to enforce it) is the one outcome that is not.
2. **Make `alembic check` a reviewed gate** (B-2): reconcile the metadata naming drifts until the only reported operations are deliberate, then add a CI step that fails on unreviewed operations. This is the mechanism that would have caught B-1 at authoring time.
3. **Close the CORS deployment item** (B-3) by supplying the frontend origins and shipping `CORS_ALLOW_ORIGINS` with `AUTH_MODE=enforcing` for shared environments.
4. Then, and only then, return to feature work — evidence ingestion, integrity analysis, geofence verification and reviewer workflows all sit on `User`, `Project` and `Evidence`, and an intelligence pipeline that trusts a non-unique identity inherits B-1 as a data-quality bug.

**Per §44: this task does not implement the next one.**

---

## Appendix A — §40 completion checklist, as measured

| §40 item | State | Evidence |
|---|---|---|
| Backend starts successfully | ALREADY SATISFIED | uvicorn process, 7 endpoints 200 |
| Database connection configured | ALREADY SATISFIED | `backend/db/session.py`, env-driven |
| PostgreSQL connection works | ALREADY SATISFIED | `SELECT 1` via `/api/v1/ready` + chain query |
| Core models exist | ALREADY SATISFIED | 70 models, §7's five entities present |
| Migrations run cleanly | ALREADY SATISFIED | 21 revisions from empty → 74 tables |
| Project API functional | ALREADY SATISFIED | create/read/list/patch, live + 17 shipped tests |
| Health endpoint functional | ALREADY SATISFIED | 6-endpoint family, DB state measured |
| API validation working | PARTIAL | strict on types/lengths/ids; `extra` keys ignored (D-1) |
| Error handling working | PARTIAL | field path answers 503 (BE-026); project path relies on the catch-all 500, and a DB outage during auth still answers 401 (DF-SE-01, carried forward) |
| Automated tests passing | ALREADY SATISFIED | 420 unit; 275 integration + 1 known pre-existing failure (§6) |
| Existing functionality preserved | ALREADY SATISFIED | `openapi.json` byte-identical; same failure set before and after |
| No unnecessary architectural changes | SATISFIED BY CONSTRUCTION | 3 production files, 14 lines of intent; no framework/ORM/routing/auth change |
| No fake implementations | SATISFIED BY CONSTRUCTION | every §24 test hits the migrated database; the one "unavailable DB" test uses a real connection refusal |

## Appendix B — why nothing was replaced

§4's thirteen questions were answerable without writing any code, and §5/§6/§31/§43 all point the same way: the correct output of a foundation task against a repository this far along is a *verified inventory plus the smallest fix set*, not a rewrite. Two defects were found that a foundation task is obliged to fix; both were fixed without changing a single response contract; three findings need decisions that belong to the operator, and are reported as blockers rather than resolved by guessing.
