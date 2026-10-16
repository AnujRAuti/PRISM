# Backend Acceptance Audit Register — 2026-10-16

Target: the deployed backend on Azure VM `poa-submission-vm` (172.198.77.149), commit
`1e8ecd16`, database `poa_prod` at Alembic head `v2w3x4y5z032`, runtime identity
`poa_runtime`, 4 workers + API container, image 3.05 GB, disk 13 % used.

Purpose: record, for every acceptance requirement, whether the current backend
**passes, fails, or is unverified** — measured, not assumed. This is stage 01 of the
48-hour plan. No defects were fixed while writing it.

Verdict shorthand: `PASS` = measured true · `FAIL` = measured or code-confirmed false ·
`UNVERIFIED` = not proven either way · `PARTIAL` = the requirement holds for part of the
surface and not the rest.

---

## 1. Real-user authentication and authorization — CRITICAL

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1.1 | Every endpoint requires authentication in the deployed mode | **FAIL** | Live 181-route sweep of `GET /openapi.json` on the VM against the running API. Guarded routes answer `401` anonymously; **9 routes answer `404`/`422`, i.e. the handler executed**: `backend/api/v1/endpoints/context.py:107,118,125,134,148,155,164,257,262` (project activities POST/GET/get-one, claims POST/GET/get-one/PATCH, `/evidence/nearby`, `/projects/{id}/evidence/nearby`). Decisive anonymous probe on the deployment: `GET /api/v1/evidence/nearby?latitude=-6.2&longitude=106.8&radius=5000` → **`200 {"items":[],"limit":50,"offset":0,"total":0}`** (a served query, not a refusal), while `GET /api/v1/projects` and `GET /api/v1/review-cases` → `401 {"detail":"Authentication required"}`, and `GET /api/v1/projects/<random-uuid>/activities` → `404 {"detail":"Project not found"}`. None of those nine signatures declares a `principal` dependency, and `_require_project()` (`context.py:42`) only checks existence. |
| 1.2 | A reviewer can sign in as themselves | **FAIL — absent** | No JWT/OIDC verification exists anywhere under `backend/` (zero hits for `jwt.decode`, PyJWT, `python-jose`, `jwks`, issuer/audience validation). `/api/v1/auth` is admin CRUD only — no login, token or callback route. `settings.jwt_secret` is validated in production mode but never read by auth code. |
| 1.3 | Browser never holds a privileged API-client secret | **FAIL** | Consequence of 1.2: in `AUTH_MODE=enforcing` + `AUTH_DEV_TOKENS_ENABLED=false` the only credential the deployed API accepts is `<client_id>:<secret>` (`backend/security/authentication.py:52-67`). A frontend could integrate today only by embedding that secret, which is prohibited. |
| 1.4 | Caller cannot forge the actor identity | **FAIL** | `_actor(principal, request_actor)` returns "explicit actor wins" in `correction.py:80-83`, `dispute.py:91-95`, `governance.py:67-70`; direct body values at `review_case.py:183` (assignee), `review_case.py:229` (`decided_by`), `review_case.py:256`, `evidence_request.py:222`, `retention.py:464`, `context.py:60,78,110-111,137`. A holder of `review_case.decide` can attribute a decision to another user. |
| 1.5 | Cross-project / cross-organization access is denied | **PARTIAL** | Tests exist and pass: `test_authorization.py::test_project_isolation:237`, `::test_organization_isolation:260`, `::test_unit_scope_narrowing:281`, `test_be026::test_assignment_rejects_context_from_another_project:515`, `::test_cross_organization_assignment_denial:584`. But they exercise user paths with development tokens (see 1.7). |
| 1.6 | Suspended / disabled principals are denied over HTTP | **PARTIAL** | Unit level: `tests/unit/test_authorization.py::test_disabled_principals_denied_despite_permissions:31`. HTTP level: only `DISABLED` is proven (`test_authorization.py::test_enforcing_mode_rejects_anonymous_bad_and_disabled:206`). No HTTP test puts a user in `SUSPENDED`. |
| 1.7 | The suite runs in the production credential posture | **FAIL** | `tests/conftest.py` never sets `auth_mode`, so the whole authorization suite inherits `development` + dev tokens. Exactly one test asserts the production posture (`test_dev_tokens_disabled_rejects_tokens:227`) and it checks nothing beyond a `401`. |
| 1.8 | Object-level (BOLA) reads are proven denied | **PARTIAL** | Evidence: covered (`test_authorization.py::test_evidence_download_protection:529`, `::test_cross_project_graph_redaction:571`). Review-case and decision retrieval by an authenticated foreign principal: **not covered** — the probes in `test_review_case.py:538,582` send no auth header, which in development mode means anonymous-bypass, i.e. the test proves nothing about identity. |
| 1.9 | Impersonation has a regression test | **FAIL** | No test asserts `decided_by`/`actor_id` equals the authenticated principal. |

## 2. Evidence-to-decision lifecycle — CRITICAL

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 2.1 | Evidence is bound to the correct case/project from trusted server-side data | **FAIL** | `POST /integrations/evidence` takes a caller-supplied `project_id` with no scope or visibility check (`endpoints/integration.py:387,420-421`); the only gate is `require("external_data.write")`, which passes for a permission held in *any* scope. |
| 2.2 | Uploader identity is recorded in the audit trail | **FAIL** | The ingestion path appends `EVIDENCE_UPLOADED` with `actor_id=None` (`services/evidence_ingestion.py:118-129`); same for `evidence_graph.py:196-202,248-258` and `fusion.py:825-831`. The ledger row cannot answer "who put this here". |
| 2.3 | Quarantined evidence is never treated as verified | **FAIL** | Quarantine is a bucket location, not an enforced state: `Evidence.status` is written once at insert (`endpoints/evidence.py:53,72`) and never updated; no `VERIFIED` value exists in the domain; no read path filters on status (`vision.py:32-34`, `duplicate_intelligence.py:75-81`); quarantined bytes are presign-downloadable to any reader with `evidence.read` (`evidence.py:76-77`). Only `publication.py:423-426` consumes status. |
| 2.4 | Object / database / checksum / retrieval-permission agreement holds | **UNVERIFIED** | A checksum is computed at upload and stored, but there is no reconciliation that re-reads the object and compares, and nothing detects a record whose bytes were replaced or lost. Needs a verification probe before this can be called pass or fail. |
| 2.5 | Decisions persist with rationale, actor, timestamp, history | **PARTIAL** | Persistence and history are implemented and tested; attribution is wrong by construction (1.4). |
| 2.6 | A retry or a lost response does not duplicate | **FAIL** (except field sync) | `POST /evidence` has no dedupe key — `ingest_evidence` mints `uuid4()` (`:96`) and commits (`:130`), so a client retry creates a second evidence record. `POST /integrations/evidence` declares `Idempotency-Key` (`:389`) but never calls `_check_idempotency`/`record_idempotency` (`:392-457`). Decision submission has no payload dedupe. Genuinely strong: `/field/sync` — unique `(user_id, client_operation_id)` + `request_hash`, replay returns the stored outcome (`field_operations.py:1700-1727`). |

## 3. Backups and proven recovery — CRITICAL

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 3.1 | Consistent backup via a documented procedure | **PARTIAL** | `pg_dump -Fc poa_prod` executed and checksummed (270 156 bytes, sha256 prefix `f5f4f88b0b12a9d4c5719a8e7a0358d0`). The procedure exists only as a scratch script (`Scratch/deploy1/vmbackup.py`), is not in the repository, and nothing schedules it. |
| 3.2 | Evidence objects backed up separately | **UNVERIFIED** | `mc mirror` ran against both buckets and reported `0 listing lines` — the deployment holds no objects yet, so the object half of the backup is untested with real data. |
| 3.3 | Backups stored outside the VM | **PASS (with one weak point)** | Dump copied to `D:\CODING\Backups\poa\`, local sha256 equals the VM's. Weak point: the VM and the operator laptop are the only two copies, so a simultaneous loss (or a laptop loss) is still an outage; no off-site/immutable copy exists. |
| 3.4 | Restore into an isolated environment and verify records + audit history | **PASS** | `pg_restore --no-owner --exit-on-error` into a throwaway database, exit 0, and five surfaces equal to source: tables 75=75, ledger rows 1=1, Alembic revision `v2w3x4y5z032`=`v2w3x4y5z032`, sequence span `1..1`=`1..1`, ordered ledger event digest `c15c1ac445bade39`=`c15c1ac445bade39`. |
| 3.5 | Evidence retrieval works after a restore | **UNVERIFIED** | No objects to retrieve; the restored cluster was never asked to presign and download a real file. |
| 3.6 | Recovery if the VM itself is lost | **FAIL** | No runbook, and no reproducible rebuild path: the MinIO images are no longer pullable from any public registry (this deployment needed `docker save` + `ssh docker load`), so a from-zero VM rebuild is currently blocked on that step. |

## 4. Azure VM and network hardening — CRITICAL

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 4.1 | HTTPS termination decision made | **FAIL (open decision)** | The API listens on `127.0.0.1:8000` inside the VM only. No reverse proxy, no TLS certificate, no domain. Plain HTTP over an SSH tunnel works for the operator; it is not a public-HTTPS deployment. |
| 4.2 | Inbound ports restricted at the network layer | **PASS (measured externally)** | Probed the VM from outside: `22 OPEN`, and `80`, `443`, `8000`, `5432`, `6379`, `9000`, `9001` **not reachable**. The VM's own listener table agrees — only `sshd` binds `0.0.0.0`, everything else is loopback. Two caveats: `ufw` reports `Status: inactive`, so there is no host-firewall layer behind that (the exposure is controlled by what binds and by the NSG, not by a firewall); and the Azure NSG rule set was never enumerated, because no Azure CLI is installed on the operator machine. The API is therefore *not* publicly reachable at all today. |
| 4.3 | PostgreSQL / Redis / MinIO stay private | **PASS** | `docker-compose.prod.yml` resets every datastore publish (`!reset []`); measured no host listener on 5432/6379/9000/9001. |
| 4.4 | SSH access, key permissions, recovery access | **PARTIAL** | Key-auth only from the operator's `.pem`; `PasswordAuthentication` state and a break-glass admin account were not verified. |
| 4.5 | Restart policy, health checks, disk and log monitoring | **PARTIAL** | Container restart policies and `/health`,`/ready` work (four endpoints `200`); disk 7.7 GB of 61 GB used, journal logs 29 MB. Growth is not watched by anything: `docker system df` reports 7.228 GB of images with **7.072 GB (97 %) reclaimable**, i.e. stale build layers, and no prune, rotation limit or alert exists. The largest disk risk today is the image cache, not the data. |
| 4.6 | A VM reboot brings the services back correctly | **UNTESTED** | Requires `sudo reboot` on live infrastructure — deliberately not performed; needs the owner's explicit go-ahead. |

## 5. Operational safeguards — HIGH

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 5.1 | Request-rate limiting | **FAIL** | No limiter anywhere in `backend/`; cross-worker/Redis-backed limiting absent. Note `main.py:107` gates `/metrics` exposure, not traffic. |
| 5.2 | `/metrics` is not anonymous | **FAIL** | Measured on the VM: unauthenticated `GET /metrics` returns 3 537 lines of Prometheus text (HTTP and GC counters). |
| 5.3 | Request and upload size limits at the transport | **PARTIAL** | Pagination is capped (`le=100` on list routes) and the upload limit is enforced in-handler (`config.py:83`, `evidence_ingestion.py:91` → `413`), but there is no body-size cap at the server/proxy layer, and some list-building queries are unbounded (`retention.py:163-171,207`, `evidence_request.py:178-184`; `auth.py:544-548` slices only for display). |
| 5.4 | Database timeouts and pool bounds | **FAIL** | `backend/db/session.py:42` creates the engine with no `statement_timeout`, no pool size ceiling and no pool recycle. |
| 5.5 | Workers: retries, failed/stale/duplicate jobs, dead-letter | **PARTIAL** | Analysis queue timeouts are configured and proven (`test_be037c_*`), webhook retry/auto-disable tested (BE-036); but a corrupt payload is silently dropped with no dead-letter record (`analysis_worker.py:307-309`), and the queue-depth gauges have no caller. |
| 5.6 | Structured logs contain no tokens, secrets, presigned URLs or raw evidence | **FAIL** | Redaction exists but only covers OpenTelemetry span attributes: `observability/tracing.py:204,245,270,293` call `redact_sensitive_data`, gated by `settings.observability_redact_sensitive` and reachable only inside `if settings.otel_enabled:` (`app/main.py:123-125`) — and the deployed `.env` sets no `OTEL_*`/observability key (measured), so `otel_enabled` stays at its `False` default (`core/config.py:105`) and that path never runs on the VM at all. The ordinary log stream has no redaction either — `core/logging.py:18-29` (`setup_logging`) attaches only a `RequestIdFilter`, no processor, and all four worker entrypoints configure `logging.basicConfig` directly (`analysis_worker.py:408`, `notification_worker.py:85`, `webhook_worker.py:288`, `retention_worker.py:42`), bypassing even that setup. Anything a `logger.*` call interpolates reaches stdout verbatim. |
| 5.7 | Request IDs end-to-end | **PARTIAL** | Generated and echoed as a response header (measured live); the middleware trusts a client-supplied header verbatim (`core/middleware.py:9`) and error bodies do not carry the ID (`main.py:74`). |
| 5.8 | Repeatable health check / alert | **FAIL** | `/ready` answers correctly, but nothing schedules it and no alert exists. |

Confirmed **PASS** in this section: CORS actually enforced (`http://evil.example` gets no
`Access-Control-Allow-Origin`), development tokens dead in production, the append-only
ledger refuses `UPDATE`/`DELETE`/`TRUNCATE`/`SET ROLE` to `poa_runtime` (provisioning
self-check `insert=t update=f delete=f truncate=f`), and workers sweep without error.

## 6. Analysis capabilities must be honest — HIGH

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 6.1 | CPU/RAM/disk feasibility decided | **UNVERIFIED** | 2 vCPU / 7 GB RAM / 61 GB disk measured; a real vision job has never run on that box. |
| 6.2 | Model licensing and trusted weights | **FAIL (blocked)** | `yolo11n.pt` exists in the repository working tree but is **not in the image** — `/app` contains no `*.pt` — so vision analysis cannot execute in the deployment. Weights are also not tracked by any licence record. Fetching them is an owner-approved action, not performed. |
| 6.3 | A real job runs end-to-end with timeouts/failures/retries | **UNVERIFIED** | Queue plumbing and outage behaviour are tested; an end-to-end job against a real image in this deployment is not. |
| 6.4 | Absent capability returns pending/unavailable/failed, not simulated findings | **PARTIAL (code-confirmed, not yet measured)** | The engine refuses to fake: `VisionModelError` is raised when ultralytics/weights are unavailable and the docstring makes the contract explicit (`engines/vision/detector.py:1-7`, `:113-119`). In the worker, an escaping exception leads to retries and then `status="failed"` through `_fail` (`workers/analysis_worker.py:292-297`, `:314`), and a temporal sub-analysis failure is stored as `"status": "unknown"` **with** the error string rather than a verdict (`:249-264`). So nothing manufactures findings. What is missing is the measurement: no job has been run end-to-end against the deployed image, so the honest-failure path is asserted from code, not observed. |

## 7. Easy to integrate and deploy — HIGH

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 7.1 | OpenAPI contract reviewed and current | **PASS (operation set) / PARTIAL (bodies)** | Measured: the live deployed `/openapi.json` and the committed `openapi.json` both carry **155 paths / 181 operations**, with 0 operations present only live and 0 only in the committed copy. The snapshot is not stale at the route level. Not compared: request/response schema bodies, so a changed field set could still be invisible here — the repo has no gate that regenerates and diffs this file. |
| 7.2 | Reviewer request/response schemas defined | **PARTIAL** | Schemas exist per endpoint; there is no reviewer-facing subset document, because there is no reviewer identity (1.2). |
| 7.3 | Repeatable end-to-end smoke test | **PARTIAL** | Proven steps exist (credential bootstrap via the app's own service, `GET /api/v1/projects` `401` anonymous vs `200` authenticated, health endpoints, `/ready` postgresql healthy) but as ad-hoc scratch scripts, not one committed command. |
| 7.4 | Migrations verified on a disposable database first | **PASS** | Two fresh disposable databases were created and migrated to `v2w3x4y5z032` with 75 tables this session; earlier clone proofs remain valid. |
| 7.5 | Reproducible deployment from a pinned commit with config supplied securely | **PARTIAL** | VM runs commit `1e8ecd16`; `.env` is mode 600 with rotated secrets, secrets never printed. Not reproducible: the MinIO image had to be smuggled (`docker save`/`load`), and the production Compose overrides live on the VM, not in the repository. |
| 7.6 | Full test suite run with the required disposable environment | **IN PROGRESS — measured correctly this time** | The previous run was `1 failed, 919 passed, 14 skipped`. The failure was real and instructional: `test_verification_context_accepts_this_runs_disposable_database` asserts the suite's own database is *not* a protected name, which cannot pass on `pofa_test`. Thirteen skips are obligations gated on `TEST_DATABASE_URL` + `POA_DISPOSABLE_OWNER_DATABASE_URL` + `POA_PROTECTED_NAME_PROBE_DATABASE_URL` + `POA_DISPOSABLE_REDIS_URL/_CONTAINER` + `POA_DISPOSABLE_MINIO_CONTAINER`. All six are now armed against a disposable suite database, a disposable Redis, a disposable MinIO and a second disposable Postgres cluster whose database deliberately answers as `pofa_test`; the re-run is recorded in §Results. |

---

## Verdict

**Not accepted for public production.** The infrastructure milestone is real and measured:
least-privilege runtime identity enforced by the database, append-only ledger, private
datastores, a restore that reproduces the audit chain byte-for-byte, and a backup now held
off the VM.

Blocking, in order of risk:

1. **1.1 — nine endpoints run with no authentication at all** on a live deployment. Today
   they return nothing because `poa_prod` has no user data; the moment projects, claims and
   geotagged evidence exist, `GET /evidence/nearby` hands any anonymous caller evidence IDs,
   project IDs and coordinates across every project. This is the cheapest Critical gap to
   close and needs no design decision.
2. **1.2/1.3 — no human identity path.** A Reviewer website cannot be built honestly on top
   of the current backend without either adding a JWT/OIDC verifier in `resolve_principal` or
   putting an API-client secret in the browser, which is prohibited.
3. **1.4/2.2 — attribution is forgeable and often absent.** A tamper-evident ledger whose
   actor column is chosen by the caller records *a* story, not *the* story.
4. **2.3/2.6 — quarantine is cosmetic and retries duplicate.** Both are data-integrity
   defects that get worse with volume, not better.
5. **5.1/5.2/5.6 — no rate limiting, anonymous `/metrics`, and redaction that covers only
   OTel spans** (the plain log stream is unprotected).

Requirements 4.1 and 4.6 cannot be closed by code at all — they are owner decisions plus one
approved reboot.

## Owner decisions required before stage 02

| Decision | Options | Why it is not mine to make |
|---|---|---|
| Public ingress | (a) keep SSH-tunnel-only, no domain; (b) reverse proxy + TLS on a domain | Changes what "deployed" means and exposes a port; also determines whether the CORS/`AUTH_MODE` posture can be relaxed for a real frontend. |
| Reviewer identity provider | (a) Supabase Auth + JWKS verification in `resolve_principal`; (b) self-issued JWT with the existing `jwt_secret`; (c) postpone the frontend | Picks the auth contract the whole authorization suite will have to be re-fixture'd against (1.7). |
| Caller-supplied actor fields | remove them from the request models (breaking API change) or ignore-but-log them | Contract change; affects existing integrations that pass `actor_id`/`decided_by`. |
| Idempotency | enforce `Idempotency-Key` on the two evidence routes (rejecting repeats) or dedupe on content hash | Retry semantics that clients must agree to. |
| Quarantine enforcement | make `status` a real lifecycle column and filter reads | Decides whether existing quarantined rows need backfill. |
| Model weights | approve or refuse an outbound fetch of the vision weights, and record their licence | Bandwidth/egress and licensing call. |
| VM reboot test | approve one `sudo reboot` of the live VM to close 4.6 | Briefly takes the deployment down. |
| Backup destination | where the second, off-laptop copy lives | Cost and durability trade-off. |

## Results

### Full suite, run correctly armed against a disposable database

Command: `python armfull.py suite` — the run's own `poa_disp_suite` / `poa_disp_owner`
databases (both at alembic `v2w3x4y5z032`, 75 tables), `poa_disp_redis`, `poa_disp_minio`
with both buckets verified by read-back listing, and `poa_disp_pg` for the protected-name
probe. No `pofa_dev` or `pofa_test` was read or written; `backend/db/safety.py:49` refuses
those names and the run confirms it.

**933 passed, 1 skipped, 0 failed** — exit code 0, 307.17s.

Reconciled against the earlier unarmed baseline (`1 failed, 919 passed, 14 skipped`):

| Movement | Count | Explanation |
|---|---|---|
| Skips that became runs | 13 | The arming-gated integration tests (`POA_DISPOSABLE_*` / `POA_PROTECTED_NAME_PROBE_*`). All 13 pass once genuinely armed. |
| The baseline failure | 1 | `test_be029_database_safety_guard.py::test_verification_context_accepts_this_runs_disposable_database` — it was only ever complaining that the target was not disposable. Armed correctly it passes; it was never a code defect, and it was never a reason to call the suite green either. |
| Remaining skip | 1 | `tests/unit/test_preflight.py::test_ml_missing_never_becomes_available_without_importer`. It skips *because* `.venv312_repro` really does import the ML stack, so `classify_ml` legitimately reports `AVAILABLE` and the test's own "either outcome is acceptable" branch fires. Not an unverified gap. |

Total collected is unchanged at 934, so nothing was deselected between the two runs.

### What this green result does and does not mean

It means the implemented behaviour is self-consistent at HEAD `1e8ecd16` on a disposable
database. It does **not** close any FAIL row above. Grep over `tests/` found **zero** tests
for rate limiting, `statement_timeout`, or inbound JWT verification (the only `jwt` tests
are `test_configuration_and_logging.py:110-133`, which validate the secret's *length*, not
any token verification). And the forgeable-actor gap is worse than untested — the current
contract is *enshrined*: `test_authorization.py:406-412`, `test_audit_ledger.py:505-512`
(whose `decided_by` is a bare `uuid4()` with no principal behind it) and
`test_review_case.py:372-378` all POST a caller-chosen `decided_by` and assert `200`. No
test anywhere asserts that a mismatched or absent actor is rejected or overridden, so
closing 1.4 will require changing what these tests expect, not just adding new ones. A
passing suite over an untested requirement is silence, not evidence; a passing suite over a
tested-but-wrong requirement is a lock on the wrong contract.
