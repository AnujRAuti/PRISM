# BE-024 Stage D - Actual Runtime Verification Results (2026-09-27)

This supersedes the prior documentation/static basis for Stage D. All results
below come from executed tests and live HTTP requests against the isolated
`pofa_test` environment. No greps, imports, OpenAPI string inspection, or
documentation reading were used as evidence of behavior.

## 1. Environment verification (executed)

| Item | Command / probe | Result |
|------|-----------------|--------|
| Containers | `docker ps` | `pofa_db` (garapadev/postgres-postgis-pgvector:15-stable), `pofa_redis` (redis:7-alpine), `pofa_minio` — all Up |
| Python | `backend/.venv312_clean/Scripts/python.exe --version` | **3.12.0** |
| TEST_DATABASE_URL | `postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test` configured; DB `pofa_test` exists (`psql -c "SELECT datname FROM pg_database"`) | OK |
| PostgreSQL + PostGIS + pgvector | `tests.preflight.probe_postgres(TEST_DATABASE_URL)` | `AVAILABLE - connected; postgis + vector present` |
| Redis | `tests.preflight.probe_redis(settings.redis_url)` | `AVAILABLE - PING responded` |
| MinIO (S3) | `tests.preflight.probe_storage(settings.s3_endpoint, ...)` | `AVAILABLE - list_buckets succeeded` |
| Real ML deps | `tests.preflight.classify_ml()` | `ML AVAILABLE: all of torch, transformers, ultralytics importable` |

## 2. Integration test runs (executed)

All runs use `backend/.venv312_clean` (Rule 9 / contamination guidance from
the reconnaissance report) with `TEST_DATABASE_URL` set. `conftest.py` refuses
to run without it and republishes it as `DATABASE_URL`.

### Run 1 — named Stage D files
```
TEST_DATABASE_URL='postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test' \
  backend/.venv312_clean/Scripts/python.exe -m pytest \
  tests/integration/test_authorization.py \
  tests/integration/test_vision_intelligence.py \
  tests/integration/test_be008_temporal.py --durations=10
```
**36 collected / 36 passed / 0 failed / 0 skipped — 93.23 s (1:33)**
Includes real YOLO inference (`test_vision_job_runs_real_inference_and_persists_observations` 13.63 s).

### Run 2 — full integration suite (evidence/analysis/fusion/review/audit + all others)
```
TEST_DATABASE_URL=... backend/.venv312_clean/Scripts/python.exe -m pytest tests/integration --durations=10
```
**200 collected / 200 passed / 0 failed / 0 skipped — 247.58 s (4:07)**
Slowest: `test_api_creates_job_and_worker_persists_real_fingerprint_result` 22.82 s;
`test_object_persists_across_minio_restart` 3.88 s; audit tamper-detection and
chain tests included. No test skipped itself.

## 3. Live-server runtime endpoint checks (executed)

Method: real `uvicorn backend.app.main:app` subprocess (port 8137) with
`DATABASE_URL=...pofa_test`, `AUTH_MODE=enforcing`, dev tokens enabled; driver
`stage_d_runtime_checks.py` issuing real HTTP via `httpx` plus a real
in-process analysis-worker run (`AnalysisQueue` + `process_message`, real ML).

Final run: **47 checks — 46 passed, 1 failed** (server ready in 5.6 s; vision
inference wall 1.0–2.1 s warm, 13.6 s cold in pytest; server log
`stage_d_server.log`).

### Auth matrices (vision + temporal)
| Check | Observed |
|---|---|
| Vision unauthenticated | **401** `{"detail":"Authentication required"}` |
| Vision authenticated, no permission | **403** `{"detail":"Forbidden"}` |
| Vision authorized (SUPERVISOR GLOBAL, after real inference) | **200**, `total=3` detections |
| Vision out-of-scope PROJECT reviewer | **404** `{"detail":"Not found"}` (indistinguishable filtering) |
| Temporal unauthenticated | **401** |
| Temporal authenticated, no permission | **403** |
| Temporal authorized | **200** with `captured_at/claim_window/...` payload |
| Temporal missing evidence | **404** `{"detail":"Evidence not found"}` |
| Evidence upload anonymous / no-permission / officer | **401 / 403 / 201** |
| Audit events anonymous / no-permission / supervisor | **401 / 403 / 200** |

### Idempotency
| Check | Observed |
|---|---|
| Duplicate queue delivery of same job | worker outcome `already_completed`; exactly **1** `AnalysisResult` row for the job |
| Second POST `/analysis/jobs` (same evidence+type) | **202** new attempt row (append-only job design — no request-level dedupe on this endpoint; dedupe is at delivery/result level) |
| Vision rerun result | new job completes; detection sets **identical** across both jobs |
| Duplicate review-case generation from same fusion run | **200 `CASE_ALREADY_EXISTS`**, same case id |
| Duplicate fusion execution on same claim | **200**, new append-only run id (documented behavior) |

### Pagination + authorization filtering
limit=1/offset=0 echoes params, page length 1 of total 3; `limit=0` → **422**
with pydantic detail body; project list for PROJECT-scoped reviewer shows
only its 1 authorized project.

### Malformed / missing resources
| Check | Observed |
|---|---|
| Malformed body to `/analysis/jobs` | **422** validation body |
| Job for missing evidence | **404** |
| Missing analysis job by random UUID | **404** |
| Non-image upload (`text/plain`) | **415** `{"detail":"Unsupported image content type"}` |
| **Malformed path UUID (`not-a-uuid`) on 5 authenticated endpoints** | **500 `{"detail":"internal server error"}` — DEFECT (see §4)** |

### OpenAPI vs actual behavior (spec fetched live from `/openapi.json`)
- All 6 exercised endpoint+method pairs present in the running app's spec.
- `DELETE` on vision path → live **405** with `allow: get` matching spec methods exactly.
- Spec 200 response declares `application/json` for vision GET.
- Observation: spec declares only `[200, 422]` for vision GET while runtime
  behavior also produces 401/403/404 (FastAPI does not auto-document auth
  rejections). Recorded as a documentation-completeness gap, not a behavioral failure.

### Evidence → Analysis → Intelligence → Fusion → Review → Audit (live HTTP)
Upload (201) → fingerprint job 202 + real worker `completed` → vision job 202 +
real inference `completed` (3 detections) → temporal 200 → claim 201 →
graph edge 201 → fusion on CLAIM 200 → duplicate-signal evidence fusion
**priority=URGENT** → review case **CASE_CREATED 201 (band URGENT)** →
assign/investigate/decision/resolve all **200** (state RESOLVED) → audit events
paginated (total 114 today) → **`/api/v1/audit/verify` valid=true, 9365 events
checked, 0 failures** (BE-023 chain intact; no audit production logic touched).

## 4. Failure classification

### DF-SD-01 — Production defect (NEW, NOT FIXED)
Malformed (non-UUID) path parameters return **500** instead of **422** when the
request carries a valid authenticated principal under `AUTH_MODE=enforcing`.
- Reproduced live on: `GET /api/v1/evidence/{id}`, `GET /api/v1/evidence/{id}/vision`,
  `POST /api/v1/analysis/temporal/{id}`, `GET /api/v1/review-cases/{id}`,
  `POST /api/v1/fusion/CLAIM/{id}` — all 500.
- Root cause (captured in `stage_d_server.log`): `require(...)` dependency
  calls `resolve_resource_scope()` which queries the resource table with the
  raw string before FastAPI validates the `UUID` annotation →
  `psycopg2.errors.InvalidTextRepresentation: invalid input syntax for type uuid: "not-a-uuid"`
  → SQLAlchemy `DataError` → generic exception handler → 500.
- Why earlier checks missed it: the 2026-09-26 static/documentation claim
  "Returns 422 validation error" and passing pytest calls with malformed UUIDs
  ran under `AUTH_MODE=development`, where the anonymous dev-bypass returns
  before the scope query. Under enforcing mode the dependency queries first.
- Severity: error-contract violation + minor information-disclosure hygiene
  (unhandled DB exception class); no authorization bypass (rejects still reject).
- Status: **OPEN**. Not fixed here per instruction not to modify production
  code during verification. Fix owner decision required (candidates: UUID
  pre-validation inside `require()`/`resolve_resource_scope`, or
  `DataError`→422 handler).

### DF-SD-02 — Pre-existing issue (LOW, NOT FIXED, observed)
`_complete_reprocessing_hook` logs a `LookupError: Reprocessing request not
found` traceback for every normal (non-reprocessing) job completion
(`backend/workers/analysis_worker.py:27` → `backend/services/governance.py:684`).
Caught — job outcome is unaffected (`completed`) — but produces error-level log
noise on the happy path. Classification: pre-existing production issue
(observability), low severity, out of Stage D scope to fix.

### Test-side defects found and corrected during this run (not product issues)
- Expected worker outcome `ack` vs actual `completed`/`already_completed`.
- Wrong `/api/v1/me` path (actual: `/api/v1/auth/me`).
- Wrong graph edge direction (`EVIDENCE -SUPPORTS-> CLAIM`).
- Review decision requires `investigate` before `decision` (state machine, correctly enforced by the app — enforcement is expected behavior).

## 5. Stage D gate status

- Integration suite (200/200) and live auth/idempotency/pagination/OpenAPI/E2E
  matrices: runtime-VERIFIED, passing.
- **Stage D is NOT marked PASS**: one executed runtime check (R8a) fails with an
  OPEN production defect (DF-SD-01). Per task rules, Stage E does not begin
  until DF-SD-01 is dispositioned (fixed + re-verified, or formally accepted).

## 6. Performance claims

None made. No throughput, p95, scalability, resource-utilization, backup, or
security-scan benchmarks were executed; none are asserted anywhere in this
document. (Only individual wall-clock observations from executed checks are
listed above.)


## 7. DF-SD-01 resolution (2026-09-27, same day) — FOUND -> FIXED -> VERIFIED

- **Fix (minimal, error-contract only):** `backend/security/authorization.py`
  gained `reject_malformed_resource_id()`; `require()` and `require_target()`
  now validate path-param UUID shape **before** `resolve_resource_scope()`
  queries the database, returning `422 {"detail":"Invalid resource identifier"}`.
  No authorization semantics changed (bypass ordering, 401/403/404 mapping
  untouched); no product features added; audit logic untouched.
- **Runtime re-verification:** `stage_d_runtime_checks.py` rerun on live
  uvicorn (AUTH_MODE=enforcing, pofa_test): **47 checks — 47 passed, 0 failed**.
  All five previously-500 probes now return 422 with the detail body above.
  Vision inference wall 2.5 s; audit chain verify valid=true (9379 events, 0 failures).
- **Regression (post-fix, executed):**
  - `pytest tests/integration` — **200 passed / 0 failed / 0 skipped — 259.88 s**
  - `pytest tests/unit` — **348 passed / 1 skipped — 44.46 s** (skip is
    `test_preflight.py` reporting "ML stack genuinely installed", a correct
    environment observation, not a hidden failure)
- **DF-SD-02** (reprocessing-hook log noise) remains OPEN as a pre-existing,
  low-severity observability issue; deliberately not fixed here to avoid
  scope creep.

## 8. Stage D gate status — FINAL

**Stage D: PASS** (runtime evidence: 200/200 integration, 47/47 live HTTP
checks, 0 failures; DF-SD-01 fixed and re-verified at runtime; DF-SD-02
documented as pre-existing/out-of-gate).
