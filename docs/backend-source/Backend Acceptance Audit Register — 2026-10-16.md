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
| 1.1 | Every endpoint requires authentication in the deployed mode | **FAIL → FIXED (verified 2026-10-16)** | Live 181-route sweep of `GET /openapi.json` on the VM against the running API. Guarded routes answer `401` anonymously; **9 routes answer `404`/`422`, i.e. the handler executed**: `backend/api/v1/endpoints/context.py:107,118,125,134,148,155,164,257,262` (project activities POST/GET/get-one, claims POST/GET/get-one/PATCH, `/evidence/nearby`, `/projects/{id}/evidence/nearby`). Decisive anonymous probe on the deployment: `GET /api/v1/evidence/nearby?latitude=-6.2&longitude=106.8&radius=5000` → **`200 {"items":[],"limit":50,"offset":0,"total":0}`** (a served query, not a refusal), while `GET /api/v1/projects` and `GET /api/v1/review-cases` → `401 {"detail":"Authentication required"}`, and `GET /api/v1/projects/<random-uuid>/activities` → `404 {"detail":"Project not found"}`. None of those nine signatures declares a `principal` dependency, and `_require_project()` (`context.py:42`) only checks existence. **FIXED → VERIFIED (stage 02, committed `6a430c74`):** every one of the nine routes now declares a `require(...)` dependency with the resource it acts on — `project.create` (unscoped), `project.read`/`project.update`/`claim.*` scoped by `project_id`, `activity.create`/`activity.read` scoped by `project_id`, `evidence.update_context` scoped by `evidence_id`, and both nearby routes behind `evidence.read` (global-scope variant requires the permission in any scope, project variant enforces project scope server-side); `list_projects` stays on `get_current_principal` + `filter_by_project_scope`. Proven by `tests/integration/test_stage02_context_route_authz.py` (5 tests: anonymous 401 on each formerly-open route, and an authenticated caller still needing the right project scope) — passing in the 967-test run below. |
| 1.2 | A reviewer can sign in as themselves | **FAIL → FIXED (verified 2026-10-16)** | Original finding: no JWT/OIDC verification exists anywhere under `backend/` (zero hits for `jwt.decode`, PyJWT, `python-jose`, `jwks`, issuer/audience validation). `/api/v1/auth` is admin CRUD only — no login, token or callback route. `settings.jwt_secret` is validated in production mode but never read by auth code. **FIXED → VERIFIED (stage 02, uncommitted — staged at the time of writing):** `backend/security/oidc.py` verifies the caller's own access token in this process against the provider's published key set — signature, `kid`, algorithm allowlist, issuer, audience, `exp`/`iat`, and a refusal of refresh tokens and of `oct` (symmetric) key material — with the key set cached under a TTL and one bounded forced refetch per 30s so a rotation needs no restart and a flood of bad tokens cannot become a flood of outbound requests. A verified `sub` is mapped to the internal account through the pair `users(identity_provider, external_subject)` that BE-016/BE-029 already stored; there is deliberately **no auto-provisioning**, so an unknown subject gets a `401` that tells it to ask an administrator for a role. `resolve_principal` calls it before the development-token gate (`backend/security/authentication.py:72-82`), so the path is live on the existing guarded routes with no per-endpoint change. The whole feature is opt-in (`AUTH_OIDC_ENABLED=false` default) and `backend/core/config.py` refuses a half-configured or unsafe provider at startup in **any** environment (blank/non-HTTPS issuer or JWKS URI, blank audience, empty algorithm list, `none` or any `HS*` algorithm). Dependencies pinned in `requirements.txt`: `PyJWT[crypto]`, `cryptography`, `httpx`. Proven by `tests/unit/test_stage02_oidc_verification.py` (27, including a hand-built HS256 token signed with the provider's own public PEM, an `alg:none` token, an unknown `kid`, an expired token, a wrong audience/issuer, a planted `oct` entry and a key rotation) and `tests/integration/test_stage02_reviewer_identity.py` (12) — both in the 1006-test run below, with the key set served locally so no test touches the network. |
| 1.3 | Browser never holds a privileged API-client secret | **FAIL → FIXED (verified 2026-10-16)** | Original finding: consequence of 1.2: in `AUTH_MODE=enforcing` + `AUTH_DEV_TOKENS_ENABLED=false` the only credential the deployed API accepts is `<client_id>:<secret>` (`backend/security/authentication.py:52-67`). A frontend could integrate today only by embedding that secret, which is prohibited. **FIXED → VERIFIED (stage 02):** the prohibition is now satisfiable — `test_a_signed_in_reviewer_is_attributed_to_themselves` completes a real decision with only the reviewer's own bearer token in that posture, and `test_development_tokens_stay_refused_while_the_provider_is_enabled` proves the new path does not reopen the development door (`dev-user-…` → `401`, same account accepted with its own token). A human caller needs no service secret; the `<client_id>:<secret>` path stays for server-to-server integrations only. **Not yet true on the VM:** `AUTH_OIDC_*` is unset there, so the deployed API still accepts no human credential until the owner configures a provider (`.env.example` documents the seven keys; the issuer and JWKS URI are public provider metadata, not secrets). |
| 1.4 | Caller cannot forge the actor identity | **FAIL → FIXED (verified 2026-10-16)** | Original finding: `_actor(principal, request_actor)` returned "explicit actor wins" in `correction.py:80-83`, `dispute.py:91-95`, `governance.py:67-70`; direct body values at `review_case.py:183` (assignee), `review_case.py:229` (`decided_by`), `review_case.py:256`, `evidence_request.py:222`, `retention.py:464`, `context.py:60,78,110-111,137`. A holder of `review_case.decide` could attribute a decision to another user. **FIXED → VERIFIED (stage 02, uncommitted at the time of writing):** one policy point — `backend/security/attribution.py::derive_actor` — now sits behind every actor-bearing write in `review_case.py`, `correction.py`, `dispute.py`, `governance.py`, `retention.py`, `evidence_request.py` and `context.py`. It returns the authenticated principal's own id, refuses 403 with the field named when the body points at anyone else (logging `attribution_refused … reason=ACTOR_MISMATCH`), and refuses 401 when an unauthenticated caller in `enforcing` mode tries to name an actor; omitting the field attributes the credential. The request-body actor fields remain accepted-but-verified and their schema descriptions now state the rule (regenerated into `openapi.json`, 155 paths / 181 operations unchanged). One documented exception, deliberate: an anonymous principal under `auth_mode=development` still gets its supplied text, which is what keeps the pre-existing development-mode suite honest about the mode it runs in. API clients writing `activities.actor_id` are recorded with no actor rather than their client id, because that column is a foreign key to `users.id`. |
| 1.5 | Cross-project / cross-organization access is denied | **PARTIAL** | Tests exist and pass: `test_authorization.py::test_project_isolation:237`, `::test_organization_isolation:260`, `::test_unit_scope_narrowing:281`, `test_be026::test_assignment_rejects_context_from_another_project:515`, `::test_cross_organization_assignment_denial:584`. But they exercise user paths with development tokens (see 1.7). |
| 1.6 | Suspended / disabled principals are denied over HTTP | **PARTIAL → FIXED for SUSPENDED (verified 2026-10-16)** | Original finding: unit level: `tests/unit/test_authorization.py::test_disabled_principals_denied_despite_permissions:31`. HTTP level: only `DISABLED` is proven (`test_authorization.py::test_enforcing_mode_rejects_anonymous_bad_and_disabled:206`). No HTTP test puts a user in `SUSPENDED`. **CLOSED for `SUSPENDED` (stage 02):** `tests/integration/test_stage02_reviewer_identity.py::test_a_suspended_reviewers_token_is_refused` grants a suspended account the role and the project scope, presents a token the verifier accepts, and asserts `401 Invalid credentials` with the case row untouched — so the refusal is the account state, not a bad token or a missing grant. `DISABLED` remains proven only through the older dev-token path. |
| 1.7 | The suite runs in the production credential posture | **PARTIAL (improved 2026-10-16)** | Original finding: `tests/conftest.py` never sets `auth_mode`, so the whole authorization suite inherits `development` + dev tokens. Exactly one test asserted the production posture (`test_dev_tokens_disabled_rejects_tokens:227`) and it checked nothing beyond a `401`. **ADDED (stage 02):** 27 tests now pin the deployed posture with an autouse fixture and restore it afterwards — `test_stage02_context_route_authz.py` (5), `test_stage02_metrics_authz.py` (4), `test_stage02_actor_attribution.py` (6) on `auth_mode=enforcing`, plus `test_stage02_reviewer_identity.py` (12) on `auth_mode=enforcing` **and** `auth_dev_tokens_enabled=false` **and** the identity provider enabled, which is exactly the VM's environment plus one working human credential. **Still open:** `conftest.py` keeps its development default, so the pre-existing authorization suite (1.5, 1.8) still runs against dev tokens; that is now a test-harness migration rather than a missing capability, because a verifiable human credential exists. |
| 1.8 | Object-level (BOLA) reads are proven denied | **PARTIAL (improved 2026-10-16)** | Original finding: covered (`test_authorization.py::test_evidence_download_protection:529`, `::test_cross_project_graph_redaction:571`). Review-case and decision retrieval by an authenticated foreign principal: **not covered** — the probes in `test_review_case.py:538,582` send no auth header, which in development mode means anonymous-bypass, i.e. the test proves nothing about identity. **ADDED (stage 02):** `test_stage02_reviewer_identity.py::test_a_signed_in_reviewer_cannot_reach_a_foreign_project` signs in as a real mapped user and reads another project's case (row proven to exist), then reads its own project's case on the same route — so the refusal can only come from scope. The older `test_review_case.py` probes are still written without a credential and still prove nothing about identity. |
| 1.9 | Impersonation has a regression test | **FAIL → FIXED (verified 2026-10-16)** | Original finding: no test asserted `decided_by`/`actor_id` equals the authenticated principal. **FIXED → VERIFIED (stage 02):** `tests/unit/test_actor_attribution.py` (6) pins the policy point itself — omitted field → credential, restated own id → credential, another id → `403` naming the field, a `UUID` value comparing equal to the string principal id, unauthenticated-in-`enforcing` with a supplied actor → `401`, and the development-mode anonymous passthrough. `tests/integration/test_stage02_actor_attribution.py` (6) drives it over HTTP against the real API on a disposable database, with every refusal paired against a same-caller success and a row-count check so the assertion cannot pass vacuously: forged `decided_by` → 403 with the case row still `("INVESTIGATING", None, None)` and no new history event; omitted and restated both attribute the credential and write exactly one `DECISION_RECORDED` event for it; the transition chain's recorded actors are now complete (`ASSIGNED`, `INVESTIGATION_STARTED`, `DECISION_RECORDED`, `RESOLVED` — the first and second previously recorded none); forged decline actor → 403 then correct attribution; forged activity actor → 403 with no `Activity` row written; an API client gets 201 with `actor_id IS NULL` and is refused when it names a human. The pre-existing contract that *rewarded* forging was updated rather than deleted: `test_governance.py::test_authorization_isolation_across_projects` now raises project B's dispute as a second real human (`reviewer_b`) instead of posting a mismatched `initiator_id`, and asserts the derived attribution landed. No assertion was weakened to reach green. |

## 2. Evidence-to-decision lifecycle — CRITICAL

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 2.1 | Evidence is bound to the correct case/project from trusted server-side data | **FAIL** | `POST /integrations/evidence` takes a caller-supplied `project_id` with no scope or visibility check (`endpoints/integration.py:387,420-421`); the only gate is `require("external_data.write")`, which passes for a permission held in *any* scope. |
| 2.2 | Uploader identity is recorded in the audit trail | **FAIL** | The ingestion path appends `EVIDENCE_UPLOADED` with `actor_id=None` (`services/evidence_ingestion.py:118-129`); same for `evidence_graph.py:196-202,248-258` and `fusion.py:825-831`. The ledger row cannot answer "who put this here". |
| 2.3 | Quarantined evidence is never treated as verified | **FAIL** | Quarantine is a bucket location, not an enforced state: `Evidence.status` is written once at insert (`endpoints/evidence.py:53,72`) and never updated; no `VERIFIED` value exists in the domain; no read path filters on status (`vision.py:32-34`, `duplicate_intelligence.py:75-81`); quarantined bytes are presign-downloadable to any reader with `evidence.read` (`evidence.py:76-77`). Only `publication.py:423-426` consumes status. |
| 2.4 | Object / database / checksum / retrieval-permission agreement holds | **UNVERIFIED** | A checksum is computed at upload and stored, but there is no reconciliation that re-reads the object and compares, and nothing detects a record whose bytes were replaced or lost. Needs a verification probe before this can be called pass or fail. |
| 2.5 | Decisions persist with rationale, actor, timestamp, history | **PARTIAL** | Persistence and history are implemented and tested. Attribution was wrong by construction (1.4) — **closed in stage 02**, so decision and transition actors are now the authenticated credential and the transition chain records actors it previously left blank. Still PARTIAL because the *uploader* behind the evidence being decided on is absent (2.2). |
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
| 5.2 | `/metrics` is not anonymous | **FAIL → FIXED (verified 2026-10-16)** | Measured on the VM: unauthenticated `GET /metrics` returned 3 537 lines of Prometheus text (HTTP and GC counters). **FIXED → VERIFIED (stage 02, committed `6a430c74`):** `GET /metrics` is now guarded by `Depends(require("metrics.read"))` (`backend/app/main.py:107-112`), a permission deliberately held by no baseline role and grantable only to a scoped API client, while `/health`, `/ready` and `/healthz` stay anonymous so the load balancer needs no credential. Proven by `tests/integration/test_stage02_metrics_authz.py` (4 tests: anonymous `401` with no `# HELP` in the body, `403` for an authenticated human lacking the permission, `200` for a scoped scraper, and the no-baseline-role invariant) — passing in the 967-test run below. |
| 5.3 | Request and upload size limits at the transport | **PARTIAL** | Pagination is capped (`le=100` on list routes) and the upload limit is enforced in-handler (`config.py:83`, `evidence_ingestion.py:91` → `413`), but there is no body-size cap at the server/proxy layer, and some list-building queries are unbounded (`retention.py:163-171,207`, `evidence_request.py:178-184`; `auth.py:544-548` slices only for display). |
| 5.4 | Database timeouts and pool bounds | **FAIL** | `backend/db/session.py:42` creates the engine with no `statement_timeout`, no pool size ceiling and no pool recycle. |
| 5.5 | Workers: retries, failed/stale/duplicate jobs, dead-letter | **PARTIAL** | Analysis queue timeouts are configured and proven (`test_be037c_*`), webhook retry/auto-disable tested (BE-036); but a corrupt payload is silently dropped with no dead-letter record (`analysis_worker.py:307-309`), and the queue-depth gauges have no caller. |
| 5.6 | Structured logs contain no tokens, secrets, presigned URLs or raw evidence | **FAIL → FIXED (verified 2026-10-16)** | Original finding: redaction existed only for OpenTelemetry span attributes (`observability/tracing.py:204,245,270,293`), gated by `settings.observability_redact_sensitive` and reachable only inside `if settings.otel_enabled:` (`app/main.py:123-125`) — and the deployed `.env` sets no `OTEL_*` key (measured), so that path never ran on the VM. The ordinary log stream had no redaction: `core/logging.py` attached only a `RequestIdFilter`, and all four worker entrypoints called `logging.basicConfig` directly, bypassing even that. Anything a `logger.*` call interpolated reached stdout verbatim. **FIXED → VERIFIED (stage 02, committed `6a430c74`):** `backend/core/logging.py` now installs a `RedactingFormatter` on the shared root handler, scrubbing the *rendered* line so message, interpolated args and exception text are all covered (`scrub_secrets`, five shape-based scrubbers: key/value secrets using the telemetry catalogue's key names so the two paths cannot drift, `scheme://user:pass@host` connection strings, presigned/S3 query credentials, bare `Bearer …`, and bare `eyJ…` JWTs). `setup_logging()` is called by `app/main.py:22` and by all four worker entrypoints (`analysis_worker.py:409`, `notification_worker.py:86`, `retention_worker.py:43`, `webhook_worker.py:289`), replacing the `basicConfig` calls. Proven by `tests/unit/test_stage02_log_redaction.py` (4 test functions, **13 collected cases** — the credential-shape test is parametrized: credential shapes scrubbed, operational detail *not* scrubbed as collateral damage, args and exception text scrubbed at the formatter, and `setup_logging` installing the scrubber on the shared handler) — passing in the 967-test run below. Note this is defence-in-depth, not a claim that secrets should ever be logged: the scrubbers match text shapes, so a novel credential format can still pass through. |
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
| 7.2 | Reviewer request/response schemas defined | **PARTIAL** | Schemas exist per endpoint. A reviewer-facing subset document still does not exist — the original reason (no reviewer identity, 1.2) is gone, since stage 02 supplied a verifiable sign-in, so this is now a documentation task rather than a blocked one. |
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
   close and needs no design decision. **— CLOSED (stage 02, `6a430c74`; see row 1.1.)**
2. **1.2/1.3 — no human identity path.** A Reviewer website cannot be built honestly on top
   of the current backend without either adding a JWT/OIDC verifier in `resolve_principal` or
   putting an API-client secret in the browser, which is prohibited. **— CLOSED in code
   (stage 02, verifier + 39 tests, uncommitted at the time of writing); the remaining action
   is the owner's: set the `AUTH_OIDC_*` keys and provision the reviewer accounts, because
   until then the deployed API accepts no human credential.**
3. **1.4/2.2 — attribution is forgeable and often absent.** A tamper-evident ledger whose
   actor column is chosen by the caller records *a* story, not *the* story. **— 1.4 CLOSED
   (stage 02, uncommitted at the time of writing); 2.2 (uploader identity) still open.**
4. **2.3/2.6 — quarantine is cosmetic and retries duplicate.** Both are data-integrity
   defects that get worse with volume, not better.
5. **5.1/5.2/5.6 — no rate limiting, anonymous `/metrics`, and redaction that covers only
   OTel spans** (the plain log stream is unprotected). **— 5.2 and 5.6 CLOSED (stage 02,
   `6a430c74`); 5.1 rate limiting still open (stage 03).**

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

### Decisions taken (2026-10-16)

| Decision | Owner's call | Consequence |
|---|---|---|
| Reviewer identity | **Supabase Auth**, with trusted JWT/JWKS verification in `resolve_principal` | Adds an outbound JWKS fetch and a signature-verifying dependency; maps the verified subject onto a `users` row through `identity_provider`/`external_subject`. |
| Caller-supplied actor fields | **Always derive from the authenticated principal** — a conflicting `decided_by`/`actor_id` is refused, the fields are not removed | Shipped as `backend/security/attribution.py` (row 1.4): omit → credential, mismatch → `403`, unauthenticated-with-an-actor in enforcing mode → `401`. |
| `/metrics` | Permission **through the existing authorization layer** (`metrics.read` via `require(...)`) | No new mechanism; liveness/readiness stay anonymous (row 5.2). |
| Idempotency | **Enforce the documented keys** with deterministic replay and reject conflicting reuse | Starts with evidence ingestion, then decision submissions (row 2.6, open). |
| Quarantine | **Enforce a real lifecycle and authorization policy** | Needs a migration plus a read-path filter, and an owner call on backfilling existing rows (row 2.3, open). |
| Public ingress | **Keep it private** while security is being fixed; HTTPS only when a remotely hosted frontend exists | No port is opened and no domain claimed as secure yet. |
| VM reboot test | **Wait** until the recovery steps are documented and approved | Row 4.6 stays open by decision, not by omission. |
| Model weights | **Deferred** | Rows 6.x stay unverified; no outbound weight fetch happened. |

Still open: **the off-laptop backup destination** — the only owner call in that table with no
answer yet.

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

### Stage 02 remediation run (2026-10-16)

Command: `python armfull.py suite`, same armed disposable stack as above (`poa_disp_suite` /
`poa_disp_owner`, `poa_disp_redis`, `poa_disp_minio`, `poa_disp_pg` probe). No `pofa_dev` or
`pofa_test` read or written.

**967 passed, 1 skipped, 0 failed** — exit code 0, 447.80s (`suite214.log`), after the
principal-derived attribution tranche.

**1006 passed, 1 skipped, 0 failed** — exit code 0, 453.23s (`suite213.log`), after the
reviewer-identity tranche. This is the current figure.

Arithmetic, all four figures measured with `armfull.py suite --collect-only` rather than
inferred:

| Step | Collected | What moved |
|---|---|---|
| Stage-01 armed run (`1e8ecd16`) | 933 passed + 1 skipped | as recorded above. |
| After the route/`/metrics`/redaction tranche (`6a430c74`) | 955 passed + 1 skipped | **+22** = 5 `test_stage02_context_route_authz.py` + 4 `test_stage02_metrics_authz.py` + **13** `test_stage02_log_redaction.py` (4 test functions, one of them parametrized over credential shapes). |
| After principal-derived attribution | 967 passed + 1 skipped | **+12** = 6 `tests/unit/test_actor_attribution.py` + 6 `tests/integration/test_stage02_actor_attribution.py`. |
| After reviewer identity via the provider key set (this run, uncommitted) | 1006 passed + 1 skipped | **+39** = 27 `tests/unit/test_stage02_oidc_verification.py` (19 test functions: 18 plain + one startup-validation function parametrized over 9 refused configurations) + 12 `tests/integration/test_stage02_reviewer_identity.py`. `--collect-only` reports the two files at 27 and 12. |

The single skip is unchanged in both runs
(`tests/unit/test_preflight.py::test_ml_missing_never_becomes_available_without_importer` —
it skips *because* the interpreter genuinely imports the ML stack). Nothing was deselected and
no existing assertion was relaxed; the one existing test whose contract the attribution change
invalidated was rewritten to use two real callers instead of a forged actor (row 1.9).

**What this run does not prove.** Inbound token verification is no longer untested, but every
one of those 39 tests serves its **own locally generated key set** — so none of them proves
that the real provider's issuer string, JWKS URL or audience value is the one this backend
will accept. That check is owed against a live configured provider before row 1.2 can be
called closed *on the deployment* rather than closed in code (stage 02 step 5, task #217).
Also still untested or unfixed: request-rate limiting (5.1) and `statement_timeout` (5.4);
quarantine remains cosmetic (2.3); the evidence uploader is still recorded with `actor_id=None`
(2.2); and advertised `Idempotency-Key` behaviour is still not implemented (2.6). A green
suite over those rows is
silence, not evidence.

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

**Superseded on 2026-10-16 (stage 02, rows 1.4/1.9).** The claim that *no* test asserts a
mismatched or absent actor is rejected is no longer true — `tests/unit/test_actor_attribution.py`
and `tests/integration/test_stage02_actor_attribution.py` do exactly that, in the `enforcing`
posture. One honest caveat remains, and the two kinds differ:
`test_authorization.py:406-412` sends the supervisor's own token with `decided_by` set to that
same id, so it is a correct attribution test and would pass in either posture;
`test_review_case.py:372-378` and `test_audit_ledger.py:505-512` send **no `Authorization`
header at all** and post a bare `uuid4()` that names no user, so they pass today only because
`conftest.py` leaves them in the development posture where the anonymous bypass forwards the
supplied text — and `review_cases.decided_by` has no foreign key, so the row stores an actor id
that does not exist. That is a lead for the 1.7 suite-wide re-fixture, not evidence that
impersonation still works against a real credential.

## 8. Resource scope and ownership — addendum (2026-10-17)

Raised by the owner's review of stage 02, which required that authorization be checked as
*permission **and* scope*, not permission alone. Full adjudication, including the routes that
turned out to be already scoped, is in
[`Authorization Scope Classification — 2026-10-17.md`](Authorization%20Scope%20Classification%20—%202026-10-17.md).
Nothing in sections 1–7 is altered by this addendum.

The policy these rows are measured against (owner-approved 2026-10-17):

- **P1 Project resources** — access constrained to projects the principal is authorized to access.
- **P2 Organization resources** — access constrained to the principal's organization unless an
  explicitly granted platform-wide (GLOBAL) permission permits more.
- **P3 Global configuration** — globally readable only where the product deliberately defines it as
  global and the authorization contract says so.
- **P4 Creation and ownership** — a caller cannot grant ownership or access by supplying another
  user's id; ownership derives from the authenticated principal, delegation requires explicit
  authorization.

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 8.1 | Retention reads are restricted to the caller's scope | **FOUND 2026-10-17 — CRITICAL before real multi-project data** | Five GETs are guarded only by resource-less `require("retention.read")`, which passes for a grant held in *any* scope: `list_policies` (`retention.py:170-171`) is `db.query(RetentionPolicy).order_by(RetentionPolicy.created_at, RetentionPolicy.id).all()` with **no predicate at all**; `get_policy` (`:153`) and `get_hold` (`repositories/retention.py:118-119`) fetch by caller-supplied id with no ownership check; `policy_history` (`:216`) probes existence only, then lists every version of that policy; `list_holds` (`repositories/retention.py:126-132`) filters on `project_id` **only when the caller supplies it**, so omitting the parameter reads every project's holds. Decisive internal evidence: the write paths in the same file already do this correctly — `_enforce_policy_scope` (`retention.py:90-105`) and `_enforce_hold_row` (`:434-446`) load the row and enforce its `project_id`/`organization_id`, and neither is called from any read. Scope columns exist (`RetentionPolicy.organization_id:1675`/`project_id:1679` with `scope_type:1674`; `RetentionHold.project_id:1778`/`organization_id:1781`), except `RetentionPolicyVersion` (`:1702`), which must be scoped by joining its parent policy. **Resolution criteria:** apply the existing per-row scope enforcement to list, individual-resource and history endpoints; a `scope_type='GLOBAL'` row stays globally readable per P3; regression tests prove a project-A reviewer cannot read project B's policy, version history, hold list or hold detail, paired with a same-caller success on project A so no assertion passes vacuously. |
| 8.2 | Publication-policy configuration has one coherent scope boundary | **FOUND 2026-10-17 — HIGH, owner scope decision required** | The classification answers the "global or per-project?" question from the code: `PublicationPolicy` (`models.py:2753-2770`) has **no** project/organization column, and `services/authorization.py:1090-1093` declares *"policies are administrative configuration, not scoped domain objects … only GLOBAL assignments can manage them."* So they are **global configuration (P3)** — per-project policies are not expressible today. The defect is that three guards on the same rows disagree: `GET /publications/policies/{policy_id}` (`publication.py:351`) resolves to a bare `Resource` and therefore demands a **GLOBAL** grant, while `GET /publications/policies` (`:369-380`) does an inline any-scope `publication.read` check (`:374-377`) and returns the whole catalogue, and `POST /publications/policies` (`:303`) is resource-less `require("publication.policy.manage")`, so a caller holding that permission at *project* scope can create global configuration. A project-scoped reviewer can enumerate policies it is refused by id. **Resolution criteria:** owner picks Option B (recommended — GLOBAL enforcement on list and create, item read as the model) or Option A (reviewer-visible configuration — keep the list open and relax the item read to match). The create route needs GLOBAL under either option. Enforce and test the chosen boundary. |
| 8.3 | Ownership is derived from the principal and project creation is audited | **FOUND 2026-10-17 — HIGH (P4)** | `ProjectCreate` (`schemas/context.py:1-32`) makes `owner_id` **required and caller-chosen**; `POST /projects` (`context.py:55-63`) validates it with `_require_user` (`:50-53`), which is existence-only — `db.query(User).filter(User.id == str(user_id))` — and then commits `Project(name=..., owner_id=str(request.owner_id))`. Any holder of `project.create` can therefore park a project under another user's id, which is a *grant of ownership by supplied id*, not a forgeable audit actor (row 1.4). The route also appends **no audit event**, so the creation is unrecorded. `PATCH /projects/{id}` changes `name` only, so ownership has no legitimate mutation path today. **Resolution criteria (owner-approved):** owner derives from the authenticated principal by default; delegated ownership, if it is a real product requirement, goes through an explicitly authorized operation with validated target scope; the creation event is recorded. A decision is needed for API-client principals, which have no `users` row (the same constraint that makes `activities.actor_id` record NULL for clients — see 1.4). **Regression tests:** cross-project and cross-organization denial, object-level reads, authorized ownership assignment, and the project-creation audit event. |
| 8.4 | Integration reads are restricted to the caller's scope | **FOUND 2026-10-17 — HIGH (P1/P2), surfaced by the classification pass** | Five GETs are resource-less `require(...)` guards whose only filters are caller-supplied query parameters, i.e. the caller chooses which project to read: `list_clients` (`repositories/integration.py:77-80` — `db.query(ApiClient)` plus optional `status`), `list_systems` (`:47-51`, `organization_id` only when supplied at `integration.py:96`), `list_webhooks` (`:276-280`), `list_events` (`:423-431`, `project_id` only when supplied at `:716`), `list_references` (`:162-168`, all three filters caller-supplied). Two are **GAP-SCHEMA**: `ExternalReference:2103` has no project/org/client/creator column at all (scope must derive from its `ExternalSystem`), and `IntegrationEvent.project_id:2274` is a plain nullable UUID **with no foreign key**, so filtering it requires an integrity decision first. `ApiClient.project_id:1605` and `ExternalSystem.organization_id:2054` are usable today, and `resolve_resource_scope` already supports `"external_system"` (`:1031`), `"api_client"` (`:1037`) and `"webhook_subscription"` (`:1042`, org via join). The single-object routes show the intended pattern: `integration.py:230` `require("integration.read", "api_client", "client_id")`, `:658` `require("webhook.manage", "webhook_subscription", "subscription_id")`. `revoke_credential_endpoint` (`:276`) is resource-less and should be reviewed in the same pass. Related, already recorded: **2.1** (`POST /integrations/evidence` accepts caller-supplied `project_id` with `require("external_data.write")` only). |
| 8.5 | Notification delivery records are restricted to the caller's scope | **FOUND 2026-10-17 — MEDIUM (P2)** | `GET /notifications/{id}/deliveries` (`notification.py:222`) is resource-less `require("notification.admin")`; `repositories/notification.py:191` filters only `NotificationDelivery.notification_id == notification_id`, `_user_id()` is never called, and the parent notification is never checked to exist (unknown id → `200 []`). `NotificationDelivery:1937` has no scope column — only `notification_id:1942-1944` — so a predicate requires a join to `Notification`, which does carry `recipient_id:1907`, `organization_id:1908`, `project_id:1909`, and `"notification"` is already supported by `resolve_resource_scope` (`services/authorization.py:1026`). |
| 8.6 | Every resource-less guard is either scoped or justified | **PARTIAL → adjudicated 2026-10-17** | A scanner over the committed app (`scope_blind_lists.py`) reported **23** GET routes with a permission-only guard. Each was read individually and its final SQLAlchemy filter quoted, so the candidate list was not treated as a finding list. **The arithmetic: 11 of the 23 are already scoped, 1 (`/metrics`) is justified global telemetry, and 11 are gaps — rows 8.1 (5), 8.4 (5) and 8.5 (1).** The 11 already scoped: `/auth/organizations` (`auth.py:311,315` `Organization.id.in_(visible)`), `/auth/users/{user_id}/roles` (rows through `services/authorization.py:698`), the five field routes (`repositories/field_operations.py:128-129, 132-137, 307-310, 352-359` and `services/field_operations.py:373-376`), and four notification routes (`repositories/notification.py:74, 100-102, 250`; `notification.py:175-176`). `/retention/operations` never appeared in the 23 because its guard is `require_global`, a different name; it passes on the GLOBAL requirement rather than a row filter, which is justified because `RetentionOperation` (`models.py:1807-1836`) has no scope columns. `/metrics` is global by design: the `route` label is the template and never the raw path (`main.py:61`, `observability/metrics.py:47-49`) and the governance/publication metric modules both state "never user_id, project_id, evidence_id, claim_id, or dispute_id" — with one recorded constraint: the webhook counters declare an id-bearing `subscription_id` label (`observability/metrics.py:212-215, 218-221, 236-239, 243-246, 249-252`) that **no call site records today** (`record_http_request` at `main.py:63` is the only `get_metrics().record_*` caller in `backend/`), so nothing leaks now and the label must not be wired without a scope-aware surface. Two residual caveats on routes classified as scoped, logged and not yet fixed: `role.manage` in any scope can confirm that an arbitrary foreign user id exists (`auth.py:542`, repository unfiltered), and `notification.admin` in any scope escapes the recipient check on `/notifications/{id}` (`:174`) — correct shape, wrong scope granularity. |

### Reconciliation of the reported test counts

The owner asked that the extra 12 be reconciled before any "+51" figure is used. The two figures
describe the same work measured at different points; neither is wrong, and the earlier wording was
ambiguous:

| Tranche | Files | New tests |
|---|---|---|
| #214 principal-derived attribution | `tests/unit/test_actor_attribution.py` (6), `tests/integration/test_stage02_actor_attribution.py` (6) | **12** |
| #213 reviewer identity | `tests/unit/test_stage02_oidc_verification.py` (27), `tests/integration/test_stage02_reviewer_identity.py` (12) | **39** |
| Combined identity + attribution milestone | | **51** |

Measured ladder, each value re-read from its own log rather than recalled:
**933** (`armed_suite.log`) → **955** (`fullsuite_stage02_2.log`, +22) → **967** (`suite214.log`,
+12) → **1006 passed / 1 skipped / 0 failed** (`suite213.log`, +39). `1006 − 967 = 39` is the
identity tranche alone because 967 already contained the 12 attribution tests; `1006 − 933 = 73 =
22 + 51`. At `61762341`, `armfull.py suite --collect-only -q` collects **1007** = 1006 + the single
surviving skip (`tests/unit/test_preflight.py::test_ml_missing_never_becomes_available_without_importer`,
ML weights deferred by owner decision). Correct phrasing going forward: **"+39 since the 967-test
baseline, +51 for the combined identity and attribution milestone; latest reported result 1006
passed / 1 skipped / 0 failed."**

### Forward-only correction to sections 1 and 7

Rows **1.2** and **1.4** say the stage 02 identity and attribution work was *"uncommitted — staged at
the time of writing."* That remains true of the moment they described and is left intact per the
owner's instruction not to change existing findings retroactively. The forward-only fact: the owner
committed that staged set as **`61762341 "cleanup#4"`** (parent `6a430c74`) on 2026-10-17 — 28 files,
+1918/−113 — so the work is now in history and `git diff --cached` is empty. No commit was rewritten.
What row 1.3 already states about the VM is unchanged and still load-bearing: `AUTH_OIDC_*` is unset
on the deployment, so **it still accepts no human credential**, and enabling OIDC in production is
gated on verifying the real provider's issuer, audience, JWKS endpoint and access-token flow. All 39
identity tests serve locally generated key sets and therefore prove none of those four values.
