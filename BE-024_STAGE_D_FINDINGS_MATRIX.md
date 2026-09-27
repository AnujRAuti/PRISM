# BE-024 Stage D - API / Workflow Integration Findings Matrix

| Area | Workflow/API | Verification | Result | Defect | Classification | Fix |
|------|--------------|--------------|--------|--------|----------------|-----|
| Evidence → Analysis | Evidence upload → Analysis job creation | Verified endpoint connectivity and basic flow | ✅ WORKING | None | N/A | N/A |
| Analysis → Intelligence | Temporal analysis → Vision intelligence | Code inspection shows proper service calls | ✅ WORKING | None | N/A | N/A |
| Intelligence → Fusion | Vision/Temporal analysis → Fusion service | Code inspection shows proper service calls | ✅ WORKING | None | N/A | N/A |
| Fusion → Review | Fusion results → Review case creation | Code inspection shows proper service calls | ✅ WORKING | None | N/A | N/A |
| Review → Audit | Review case actions → Audit logging | Code inspection shows audit service integration | ✅ WORKING | None | N/A | N/A |
| Authorization | Vision endpoint (`/evidence/{evidence_id}/vision`) | Added `Depends(require("evidence.read", "evidence", "evidence_id"))` | ✅ FIXED | Previously missing authorization dependency | Security gap | Added principal dependency |
| Authorization | Temporal endpoint (`/analysis/temporal/{evidence_id}`) | Added `Depends(require("evidence.read", "evidence", "evidence_id"))` | ✅ FIXED | Previously missing authorization dependency | Security gap | Added principal dependency |
| Idempotency | Analysis job creation endpoint | Verified idempotency key handling in AnalysisQueue | ✅ WORKING | None | N/A | N/A |
| Pagination | Vision endpoint (`/evidence/{evidence_id}/vision`) | Verified limit/offset query parameters | ✅ WORKING | None | N/A | N/A |
| Error handling | Malformed evidence ID in vision/temporal endpoints | Returns 422 validation error | ✅ WORKING | None | N/A | N/A |
| Error handling | Nonexistent evidence in vision/temporal endpoints | Returns 404 not found | ✅ WORKING | None | N/A | N/A |
| Error handling | Unauthorized access to vision/temporal endpoints | Returns 401/403 based on auth mode | ✅ WORKING | None | N/A | N/A |
| OpenAPI accuracy | Vision endpoint (`/evidence/{evidence_id}/vision`) | Verified in OpenAPI spec - path, method, params, responses | ✅ WORKING | None | N/A | N/A |
| OpenAPI accuracy | Temporal endpoint (`/analysis/temporal/{evidence_id}`) | Verified in OpenAPI spec - path, method, params, responses | ✅ WORKING | None | N/A | N/A |
## Runtime verification pass (2026-09-27) — actual HTTP/test evidence

History preserved: rows above are the 2026-09-26 static/documentation pass. The
authorization rows remain FOUND → FIXED → **VERIFIED AT RUNTIME** (live 401/403
matrix, §3 of BE-024_STAGE_D_RUNTIME_RESULTS.md). Rows below record executed
runtime outcomes; where they contradict a static row, the runtime row governs.

| Area | Workflow/API | Runtime verification | Result | Defect | Classification | Fix |
|------|--------------|----------------------|--------|--------|----------------|-----|
| Authorization | Vision + temporal endpoints | Live uvicorn AUTH_MODE=enforcing: unauth 401, no-perm 403, authorized 200, out-of-scope 404 | ✅ VERIFIED | None (defect was FOUND→FIXED, now runtime-VERIFIED) | Security gap (historical) | Previously added `require(...)` deps |
| Error handling | Malformed path UUID on 5 authenticated endpoints | Live `not-a-uuid` requests → **500** (server log: psycopg2 InvalidTextRepresentation via `resolve_resource_scope` before UUID validation) | ❌ FOUND (2026-09-27 morning) | **DF-SD-01** (supersedes static "Returns 422 WORKING" row above) | Production defect — error contract; static check missed it because dev-mode bypass skips the scope query | see DF-SD-01 resolution row below |
| Error handling | DF-SD-01 resolution | UUID-shape validation added to `require()`/`require_target()` in `backend/security/authorization.py`; 5 endpoints re-probed live -> **422** `{"detail":"Invalid resource identifier"}`; 47/47 runtime checks pass; 200/200 integration + 348/349 unit regression | ✅ FIXED → VERIFIED (runtime) | DF-SD-01 closed | Production defect — fixed within Stage D scope | `reject_malformed_resource_id()` pre-query guard |
| Error handling | Missing resources / non-image upload / malformed body | Live 404s with detail bodies; 415 unsupported content type; 422 validation bodies | ✅ VERIFIED | None | N/A | N/A |
| Idempotency | Duplicate job delivery; vision rerun; case generation; fusion | `already_completed` (1 result row); identical detections; `CASE_ALREADY_EXISTS` (same id); append-only new run | ✅ VERIFIED | None; note POST /analysis/jobs intentionally creates new attempt per request | N/A | N/A |
| Pagination | Vision limit/offset + authz filtering | Page echo + len<=limit; limit=0 → 422; out-of-scope reviewer → 404; scoped project list total=1 | ✅ VERIFIED | None | N/A | N/A |
| OpenAPI parity | Spec from running app vs behavior | All exercised paths present; 405 allow-list == spec methods; 401/403/404 not declared in spec (FastAPI default) | ✅ VERIFIED | Documentation-completeness gap only | Observation | N/A |
| E2E path | Evidence→Analysis→Intelligence→Fusion→Review→Audit | Real HTTP + real ML worker; URGENT fusion → CASE_CREATED → assign/investigate/decision/resolve → audit verify valid=true (9365 events, 0 failures) | ✅ VERIFIED | None | N/A | N/A |
| Worker logs | Reprocessing completion hook | Error-level `LookupError` traceback logged for every normal job completion (caught; outcome unaffected) | ⚠️ NOISY | **DF-SD-02** | Pre-existing production issue (observability, low severity) | OPEN |
| Integration suite | tests/integration (200 tests incl. authorization/vision/temporal named files 36) | Executed on pofa_test with real PostGIS/pgvector, Redis, MinIO, torch/transformers/ultralytics | ✅ 200 passed / 0 failed / 0 skipped (93.23s named subset) | None | N/A | N/A |

**Stage D gate: PASS (2026-09-27)** — DF-SD-01 FOUND → FIXED → runtime-VERIFIED (history preserved above); DF-SD-02 remains open as documented pre-existing low-severity observability issue, outside the gate.
