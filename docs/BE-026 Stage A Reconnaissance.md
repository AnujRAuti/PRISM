# BE-026 Stage A Reconnaissance — Field Operations & Offline Evidence Capture Backend

Milestone: BE-026 · Branch: `Backend` · Baseline: `29d12eb8` (BE-025 accepted, pushed)
Task file: `docs/Production Task Files/BE-026 — Field Operations & Offline Evidence Capture Backend.md`
Gate: **Stage A — reconnaissance only. No production code was written, no migration created, no API added, nothing committed.**

## 1. Method and evidence classes

Every statement below is tagged:

* **[R]** — runtime-verified in this session against a live server
  (`uvicorn backend.app.main:app`, `AUTH_MODE=enforcing`, `AUTH_DEV_TOKENS_ENABLED=false`,
  `DATABASE_URL=…/pofa_test`, port 8077) or against live PostgreSQL by read-only SQL.
* **[C]** — read from source with a file:line citation.

No conclusion rests on OpenAPI-string matching, grep-only inference, or documentation.

Environment events during reconnaissance **[R]**: the Docker Desktop engine went down at
≈12:41 UTC (`docker info` → `failed to connect to the docker API at
npipe:////./pipe/dockerDesktopLinuxEngine`, host port 5432 refused), which blocked the
probe set and made a first anonymous `/evidence/nearby` call return `500`. The engine was
restarted, `pofa_db` / `pofa_redis` / `pofa_minio` came back `Up`, and every probe below
was re-run successfully after recovery. This is the same host-cycling condition already
recorded for BE-025 (MinIO `SIGTERM` every ~7–23 min), now escalated to the whole engine.

New observation to classify at Stage D **[R]**: uvicorn startup emits
`--- Logging error --- … ValueError: Formatting field not found in record: 'request_id'`
from `backend/app/main.py:125` (`std_log.info("application.starting")` under a formatter
that expects `request_id`). Noise only — the application started and served correctly —
but it is an observability defect in the BE-020 logging path and is recorded here as
**OBS-A-01** rather than silently ignored.

## 2. Existing field / activity architecture **[C]**

The word "activity" in this codebase does **not** mean assignable field work.

* `Activity` — `backend/db/models.py:81-91`: `project_id` NOT NULL FK, `actor_id`
  **nullable plain FK**, `verb` String(128), `details` JSONB, `created_at`. No assignee,
  no status, no scheduled/due time, no location, no expiry. It is an audit-feed row.
* `Project` — `:66-78`: `owner_id` NOT NULL FK; `organization_id` (`:74`) and
  `organizational_unit_id` (`:75`) **nullable**; no `status`, no `updated_at`.
* `Claim` — `:94-106`: `claimant_id` nullable, `temporal_start_at` / `temporal_end_at`
  nullable, `created_at`.
* `Evidence` — `:109-125`: `project_id` **nullable** (`:112`), `claim_id` nullable,
  `storage_key` NOT NULL default `legacy/unknown`, `status` NOT NULL default
  `uploaded_quarantine` **with no CHECK constraint** (unlike every other lifecycle column
  in the schema), `sha256` nullable indexed, `phash` nullable,
  `location Geometry(POINT, 4326)` nullable, `created_at` server-default — **the only
  timestamp the row carries**.
* The only foreign key into `activities` anywhere in the schema is
  `EvidenceRequest.activity_id` (`:836`).

Consequence: **there is no entity that a field officer is "assigned to".** The BE-026
pipeline's first link (`Assignment → Field Activity`) has no server-side representation.

## 3. Existing assignment architecture **[C]**

| Structure | What it is | Lifecycle | BE-026 usability |
|---|---|---|---|
| `UserRoleAssignment` `:1459-1510` | RBAC grant: role × scope (`GLOBAL`/`ORGANIZATION`/`ORGANIZATIONAL_UNIT`/`PROJECT`), `ck_assignment_scope` + `ck_assignment_scope_matrix`, `uq_user_role_scoped` (nulls-not-distinct) | **none** — no status, no `revoked_at`, no `expires_at`; revocation is a hard `DELETE` (`services/authorization.py:535-537` → `repositories/authorization.py:126-129`) | Answers "authorized *now*", never "was authorized *at capture time*" |
| `Project.owner_id` `:70` | single owner, transferred via `POST /auth/projects/{id}/ownership` | none | Not a team/field assignment |
| `ReviewCase.assigned_to` `:738-739` | review queue assignee, **plain UUID, no FK** | `ASSIGNED`/`ESCALATED` statuses `:761-765`, no expiry | Reviewer workflow, not field work |
| `EvidenceRequest` `:825-869` | request/respond flow, `recipient_id` plain UUID `:840`, `due_at` nullable `:842`, status incl. `EXPIRED` `:853-857` | yes | Closest existing "work item for a named person"; still request-shaped, not capture-shaped |
| `RetentionHold` `:1690-1724` | `status ACTIVE/RELEASED/EXPIRED/CANCELLED` `:1717-1720` + `expires_at` `:1708` + `created_by`/`released_by`/`released_at` | yes | **Lifecycle template to copy**, not to reuse |
| project team / membership | **does not exist** (confirmed in `docs/BE-025 Stage B Design.md:157`) | — | — |

## 4. Existing evidence pipeline — the reuse target **[C]**

`POST /api/v1/evidence` (`backend/api/v1/endpoints/evidence.py:23-40`) does a bounded read
at the caller (`file.read(settings.max_upload_size + 1)`, `:32`) and delegates everything
else to **`ingest_evidence(data, filename, declared_type, db)`**
(`backend/services/evidence_ingestion.py:74-150`), which is already the shared service for
BE-003 uploads *and* BE-014 requested evidence:

1. content-type allow-list, empty-body `400`, oversize `413` (`:87-92`);
2. magic-byte + Pillow verification and MIME/signature/declared cross-check → `415`
   (`match_image_content_type`, `:47-71`; `detect_signature_content_type`, `:37-44`);
3. server-minted `evidence_id` = `str(uuid4())` (`:96`) and
   `storage.quarantine_key(evidence_id)` (`:98`);
4. `storage.put_object(quarantine_bucket, …)` (`:101-106`);
5. `Evidence` row + `audit_service.append_event(EVIDENCE_UPLOADED)` **in the same
   transaction**, then `db.commit()` (`:107-130`);
6. on `StorageError` / `SQLAlchemyError`: `rollback()` + best-effort
   `delete_object()` of the orphaned object, and the error propagates (`:131-148`).

`StorageService` (`backend/services/storage.py`) exposes `put_object` `:124`,
`get_object_bytes` `:137`, `copy_object` `:193` (quarantine → trusted evidence bucket),
`create_presigned_upload_url` `:95`, `create_presigned_download_url` `:113`,
`quarantine_key` `:226`, `evidence_key` `:229`, with a typed `StorageError` hierarchy
`:14-30`. SHA-256 / pHash are computed downstream by the fingerprinting service
(`backend/services/fingerprinting.py`) as an **analysis job**, not inside ingest:
`AnalysisQueue` (`backend/services/analysis_queue.py:18-107`, Redis stream,
`enqueue/dequeue/acknowledge/retry/recover_abandoned`) + `backend/workers/analysis_worker.py`
+ `create_analysis_job` (`backend/services/analysis_jobs.py:13`).

**Two hard constraints this imposes on BE-026 [C]:**

* `ingest_evidence` accepts **bytes**, generates the identity itself, and sets neither
  `project_id` nor an actor (`actor_id=None`, `project_id=None`, `:118-129`). A client
  cannot pre-assign an Evidence identity, and sync-time attachment must happen in the
  sync transaction, not by re-calling an existing endpoint.
* An Evidence row with `project_id IS NULL` resolves to an unscoped resource
  (`resolve_resource_scope`, `services/authorization.py` — `holder_project` stays `None`)
  and `can()` then returns **`RESOURCE_UNSCOPEABLE`** (`services/authorization.py:1194-1200`),
  which `enforce()` maps to **404** (`security/authorization.py:163-165`). So today a
  non-GLOBAL FIELD_OFFICER cannot attach their own fresh upload through
  `PATCH /evidence/{id}/context` (`endpoints/context.py:185-219`). Offline sync must not
  inherit that dead end.

## 5. Existing provenance capabilities **[C]**

* `evidence` has **no** provenance column. `EvidenceMetadata` (`:128-135`) stores one JSONB
  blob (`metadata_json`, column name `metadata`) and has **no unique constraint on
  `evidence_id`** — writers upsert by query (`services/fingerprinting.py:62`,
  `services/correction.py:541-550`).
* Capture time is today **derived at read time from EXIF**, never persisted:
  `extract_capture_time` (`backend/services/temporal_intelligence.py:85-103`),
  `get_capture_time` (`:191-198`), `CaptureTime` model `:47` — "unknown" is expressible
  only in code (`value=None`, `tz_known=False`), not in the schema. Retention anchors
  `CAPTURED_AT` / `INGESTED_AT` (`models.py:1564-1573`) resolve to `Evidence.created_at`
  and the derived EXIF value respectively (`services/retention.py:343-359`).
* The one place the schema **does** separate source time from server time is the BE-019
  integration surface: `ExternalAssertion.source_timestamp` (nullable) + `ingested_at`
  (NOT NULL) (`:2055-2066`), plus `ExternalReference` (`:2023-2047`) which maps an
  external id onto a PoA resource under a unique constraint. **This is the closest living
  precedent for "client-generated identity + preserved source timestamp + link to canonical
  Evidence"**, and BE-026 should mirror its shape rather than invent a rival.
* `graph_relationships.dedupe_key` / `.provenance` JSONB (`:340-346`) are graph-edge
  concepts — different meaning, do not reuse.

## 6. Existing idempotency infrastructure **[C]**

* Table `IdempotencyKey` (`:2074-2092`): `client_id` **NOT NULL FK → api_clients, ON DELETE
  CASCADE**, `idempotency_key`, `request_hash`, `result_payload`, `expires_at`,
  unique `uq_idempotency_client_key`.
* Evaluator `check_idempotency(db, client_id, key, request_hash)` →
  `NEW` / `REPLAY` (+ stored `result_payload`) / `CONFLICT`
  (`backend/services/integration.py:252-269`), `compute_request_hash` `:240-249`
  (canonical sorted-key JSON SHA-256), `record_idempotency` `:272-294` with
  `IntegrityError` → rollback → re-read for the concurrent-insert race, and
  `update_idempotency_result` `:297-302`. TTL constant `IDEMPOTENCY_TTL_HOURS`.
* HTTP wiring: `Idempotency-Key` header
  (`endpoints/integration.py:392`), `_check_idempotency` → `409` on `CONFLICT`
  (`:58-76`), and `POST /api/v1/integrations/evidence` (`:380-460`) which is the existing
  worked example of **external capture → reuse `ingest_evidence` → record `ExternalAssertion`
  with a timezone-aware `source_timestamp` (400 if naive, `:411-415`) → `ExternalReference`
  upsert → single commit**.
* Other idempotency is index-shaped, not ledger-shaped: partial unique indexes on
  disputes (`:2344`), correction requests (`:2432`), reprocessing (`:2568` pending),
  graph dedupe (`:342`).

**Verdict [C]:** the *algorithm* is reusable and already correct (NEW/REPLAY/CONFLICT,
request-hash comparison, race handling), but the *table is not*: it is keyed to an
`api_clients` row with CASCADE, so a **User-authenticated field officer cannot use it at
all**, and its TTL expiry is unsuitable for a durable offline operation log.

## 7. Existing authorization mechanisms **[R][C]**

Guards are per-route dependencies; there is **no global auth dependency** —
`backend/api/v1/router.py:24-50` includes routers plainly, and `backend/app/main.py:28-41`
adds only CORS, `RequestIDMiddleware` and a metrics middleware. So a route without a
principal dependency is open in every mode.

* `require(action, resource_type=None, id_param=None)` (`security/authorization.py:50-91`);
  `require_global(action)` `:242-263`; `require_target(action)` `:217-239`;
  `enforce()` `:149-170` maps `NO_PERMISSION → 403`, `SCOPE_DENIED` /
  `RESOURCE_UNSCOPEABLE → 404` (out-of-scope ≡ absent, never a 403 oracle),
  `UNAUTHENTICATED → 401`; `reject_malformed_resource_id` `:34-47` (DF-SD-01) 422s
  malformed UUIDs before any DB touch; `visible_project_ids` `:94-141` and
  `filter_by_project_scope` `:266-284` do list filtering **before counting**.
* Role catalogue is code-owned: `AUTH_ROLES = CITIZEN, FIELD_OFFICER, REVIEWER,
  SUPERVISOR, ADMINISTRATOR, API_CLIENT` (`models.py:1098-1105`); `AUTH_PERMISSIONS`
  `:1109-1184`; `AUTH_ROLE_PERMISSIONS` from `:1188`, FIELD_OFFICER block `:1205-1230`
  (already includes `project.read`, `activity.read/create`, `claim.*`, `evidence.read/
  create/update_context`, `graph.read`, `review_case.read`, `evidence_request.*`,
  `notification.*`, `dispute/correction.create/read`, `intelligence.reprocess`,
  `publication.create/read`).

### 7.1 Runtime finding SR-01 — legacy BE-007 routes are open anonymously **[R]**

`backend/api/v1/endpoints/context.py` declares **no principal dependency** on
`create_activity` `:107-115`, `list_activities` `:118-122`, `get_activity` `:125-131`,
`create_claim` `:134-145`, `list_claims` `:148-152`, `get_claim` `:155-161`,
`update_claim` `:164-182`, `nearby_evidence` `:257-259`, `project_nearby_evidence`
`:262-265`. Anonymous probes against the enforcing-mode server (no `Authorization`
header at all, target `pofa_test`):

| Request | Status | Body observed |
|---|---|---|
| `GET /api/v1/projects?limit=1` | **401** | `{"detail":"Authentication required"}` — control: this route *does* have a guard |
| `GET /api/v1/audit/events?limit=1` | **401** | `{"detail":"Authentication required"}` |
| `GET /api/v1/auth/users?limit=1` | **401** | `{"detail":"Authentication required"}` |
| `GET /api/v1/projects/{pid}/claims?limit=2` | **200** | full claim payload: `id`, `project_id`, `claimant_id`, `title` |
| `GET /api/v1/projects/{pid}/claims/{cid}` | **200** | same, single row |
| `GET /api/v1/projects/{pid}/activities?limit=2` | **200** | `{"items":[],"limit":2,"offset":0,"total":0}` |
| `GET /api/v1/evidence/nearby?latitude=10.5&longitude=20.5&radius=1000&limit=2` | **200** | two rows with `evidence_id`, `latitude`, `longitude`, `distance_meters`, `project_id` |
| `GET /api/v1/evidence/nearby?…&radius=200000` | **422** | bounds are enforced (`le=100000`) |

**This is a pre-existing condition in the BE-007-era surface, not BE-026 damage, and it is
NOT being fixed here** (task §1 "no unrelated cleanup", §27). It matters to BE-026 for two
reasons: (a) an offline **assignment feed must not be built on, or routed through, these
handlers**; (b) `tests/integration/test_be007_contracts.py:63-99` asserts
`POST …/activities` → `201`, `POST …/claims` → `201`, `GET …/activities` → `200` **with no
headers**, and the suite never sets `AUTH_MODE` (`tests/conftest.py` has no auth-mode
assignment; `backend/core/config.py:48` defaults to `development`). So tightening those
routes is a deliberate, separately-scoped change that will regress a passing BE-007
contract suite — Stage A records it, Stage B does not silently "fix" it.

## 8. Existing audit mechanisms **[C]**

`append_event(db, *, event_type, action, resource_type, resource_id=None, actor_id=None,
project_id=None, payload=None, request_id=None, source=None, commit=False)`
(`backend/services/audit_ledger.py:187-260`): unknown `event_type` raises `ValueError`
against the `AUDIT_EVENT_TYPES` frozenset (`models.py:1033-1046`, extended by BE-025);
`scrub_sensitive(payload)` `:118`; `pg_advisory_xact_lock` on `APPEND_LOCK_KEY` `:220-222`
serialises sequence assignment; hash chain built from `previous_hash` of the latest event
(`GENESIS_HASH` for sequence 1) with `compute_event_hash` `:169`; flush-within-caller-
transaction so domain mutation + audit row commit or roll back together. Read-only
`verify_event` `:276` / `verify_chain` `:300`. The BE-023 append-only guard
(`tests/audit_guard.py`, exercised by `tests/integration/test_audit_ledger.py:287`) remains
in force: no UPDATE/DELETE path on the ledger, and new event types are additive registrations.

## 9. Existing offline / sync functionality: **none** **[R][C]**

A full-tree sweep (`backend/`, `alembic/versions/`, `tests/`, root scripts) found no
implementation of any kind. Every apparent hit is a docs mention or a word collision:

| Term | Status | Detail |
|---|---|---|
| `field_session`, `FieldSession`, `client_operation`, `capture_timestamp`, `operation_id`, `device` | **zero hits anywhere** | nothing to reuse, nothing to collide with |
| `offline` | collision | `alembic/env.py:30,57` — Alembic's `run_migrations_offline` / `is_offline_mode` SQL-script mode |
| `sync(hronize)` | collision | SQLAlchemy kwarg `synchronize_session=False` (`repositories/publication.py:91`, `repositories/governance.py:191-238`, `services/retention.py:1175`) and prose "synchronously" (`services/fusion.py:775`, `workers/webhook_worker.py:3`) |
| `conflict` | collision | fusion signal state `CONFLICTING` (`models.py:401,493`, `services/fusion.py:324-330,505`), retention `POLICY_CONFLICT` (`services/retention.py:120,128,577`), HTTP `409` wording |
| `client_id` | collision, and misleading | BE-019 **API-client** identity (`models.py:2008`, `:2079`; `security/authentication.py:51-89`), not a device key |
| `queue` / `pending` | adjacent only | server-side Redis analysis stream (`services/analysis_queue.py`) and the BE-018/BE-019 transactional **outbox** (`models.py:1910-1930`, `workers/notification_worker.py:19-33`) — keyed on committed rows, not a client pending queue |
| `dedup` | adjacent only | BE-006 duplicate-evidence intelligence (`services/duplicate_intelligence.py`) and graph `dedupe_key` |
| `idempot*` | **real, but per-HTTP-request for API clients** | §6 above — reusable precedent, not an offline operation log |
| `accuracy` | docs-only | `docs/backend-scope.md:398,427` (`LOW_GPS_ACCURACY`), `docs/Proof-of-Action Backend — TODO.md:1177` (`gps_accuracy_check()` aspiration). No `gps_accuracy` column exists |
| offline field behaviour spec | docs-only | `docs/Final Architecture.md:113,117,710-716,1076` — PWA offline-first, assignment sync, capture-vs-sync timestamps, idempotent deferred sync. **No code implements it** |

**Conclusion [R][C]: BE-026 is greenfield.** The correct reuse set is `ingest_evidence`,
`StorageService`, `AnalysisQueue`/worker, `append_event`, `require()`/`enforce()`/
`filter_by_project_scope`, and the `NEW|REPLAY|CONFLICT` + `ExternalAssertion`
`source_timestamp`/`ingested_at` **precedents** — plus the outbox pattern as the shape for
a durable, server-side record of a client-submitted operation.

## 10. Missing backend capabilities

| # | Capability | Today |
|---|---|---|
| G1 | An assignable field-work entity (activity/task with assignee + lifecycle) | absent (§2, §3) |
| G2 | Assignment authority that survives offline: `ACTIVE` / `REVOKED` / `EXPIRED` + `expires_at` on the assignment itself | absent; `user_role_assignments` has no lifecycle and revocation deletes the row |
| G3 | Stable client-generated identity for a capture/operation, unique per owner | absent; Evidence ids are server-minted inside ingest |
| G4 | Idempotent operation ledger usable by **User** principals (not `api_clients`), durable rather than TTL-expired | absent (§6) |
| G5 | Deterministic same-key-different-payload conflict outcome for User sync | exists only on the API-client surface (`endpoints/integration.py:58-76`) |
| G6 | Persisted capture / queue / upload / server-received / processing timestamps, each independently nullable so "unknown" survives | absent; one `Evidence.created_at`, capture time EXIF-derived at read time (§5) |
| G7 | GPS accuracy / altitude / fix source columns with a "missing ≠ 0,0" representation | absent; lat/lng only, no CHECK, no spatial index (§2, §9) |
| G8 | First-class conflict record with resource, server state, reason, actor/client, resolution status | absent (fusion `CONFLICTING` is unrelated) |
| G9 | Sync result vocabulary beyond 2xx/4xx (`accepted` / `already_synchronized` / `rejected` / `conflict` / `authorization_denied` / `validation_failed` / `temporarily_unavailable`) | absent; error convention is `detail` strings + structured 401/403/404/409/422 (§7) |
| G10 | Provenance that a piece of evidence came from a field capture workflow | absent (§5); nearest analogue is `ExternalAssertion` for external systems |
| G11 | Audit coverage for sync accepted / duplicate / rejected / conflict / assignment access | absent — no such events exist to emit; type set is additive |
| G12 | Sync-time re-evaluation of current authorization against a still-active assignment | impossible without G1/G2 |
| G13 | A paginated, authorization-filtered "assigned work" feed | absent; the existing project-scoped list idiom (`filter_by_project_scope`) is the pattern to follow |
| G14 | Retry-after-timeout recovery: fetch the outcome of a previously submitted client operation | absent |

## 11. Required schema changes and the migration verdict

**Is a migration actually required? YES — and it can be confined to two new tables plus
zero changes to existing tables.** [C]

*Why new tables are unavoidable:* G1/G2/G3/G4/G6/G7/G8 have no home in the current schema,
and the alternatives all violate locked architecture — adding capture/queue/upload/GPS
columns to `evidence` would redesign Evidence (task §21 forbids); reusing
`user_role_assignments` as the assignment would give no lifecycle (task §8 requires
"not revoked / not expired"), and its hard-delete revocation destroys the very fact sync
must test; reusing `idempotency_keys` requires an `api_clients` FK with CASCADE, which a
field officer does not have.

*Proposed minimal shape (final decision belongs to Stage B):*

1. **`field_assignments`** — server-side "officer X works on project P (optionally claim /
   area / activity reference) until T". Columns: `id`, `user_id` FK RESTRICT, `project_id`
   FK RESTRICT NOT NULL, `organization_id` FK nullable, `status` CHECK
   `ACTIVE/RELEASED/REVOKED/EXPIRED` (mirroring `RetentionHold` `models.py:1708,1717-1720`),
   `valid_from`/`expires_at` nullable, `created_by`, `revoked_by`/`revoked_at`,
   `created_at`/`updated_at`, partial-unique "one ACTIVE per (user, project)" in the style
   of `uq_disputes_active_target_initiator` `:2345-2352`, plus a **scope/identifier CHECK
   matrix** in the style of BE-025's `ck_assignment_scope_matrix` if any nullable scope is
   introduced. This is what makes "assignment revoked while device was offline" a testable,
   recorded state instead of a deleted row.
2. **`field_capture_operations`** — the offline sync log and provenance record:
   `id`, `user_id` FK, `client_operation_id` (String, unique per `(user_id,
   client_operation_id)` with `postgresql_nulls_not_distinct`, i.e. the
   `uq_user_role_scoped` idiom), `request_hash` (canonical-payload SHA-256 via
   `compute_request_hash`), `assignment_id` FK, `project_id`/`claim_id` FKs nullable,
   `evidence_id` FK nullable (set only when ingest succeeded), `status` CHECK
   `PENDING/ACCEPTED/ALREADY_SYNCHRONIZED/REJECTED/CONFLICT/AUTHORIZATION_DENIED/VALIDATION_FAILED/TEMPORARILY_UNAVAILABLE`
   (the §11 response vocabulary, persisted so "retry after timeout" can be answered from
   the row), the §6 timestamps as **separately nullable** columns (`captured_at`,
   `queued_at`, `uploaded_at`, `received_at` NOT NULL, `processed_at` nullable, each
   `timestamptz`), the §7 GPS fields (`latitude`/`longitude` numeric nullable,
   `capture_accuracy_m` nullable, `altitude` nullable, `location_source`, a CHECK forbidding
   a coordinate pair half-populated **and** a CHECK forbidding `0,0` unless explicitly
   flagged), `device_label`/`session_label` nullable, `conflict_reason`/`conflict_detail`
   JSONB nullable, `resolution_status`, `created_at`/`updated_at`.
   PostGIS semantics stay authoritative for canonical evidence location — the operation row
   records the *client's* reported fix, and any Evidence `location` write continues through
   the existing `ST_SetSRID(ST_MakePoint(lng, lat), 4326)` path (`endpoints/context.py:232`).
3. **New `AUDIT_EVENT_TYPES` entries** (additive, `models.py:1033-1046`): field sync
   accepted / duplicate / rejected / conflict / assignment accessed / assignment security
   failure / evidence association.
4. **Not** required, and deliberately excluded: any change to `evidence`,
   `evidence_metadata`, `user_role_assignments`, `idempotency_keys`, the audit ledger, or
   a `field_sessions` table (a session is a label on the operation row; inventing a third
   table now would be speculative). Fixing `evidence_metadata.evidence_id` uniqueness,
   `evidence.status`'s missing CHECK, and the §7.1 unguarded routes are **separate,
   documented findings**, not BE-026 work.

Migration mechanics **[C]**: chain is 20 linear revisions with a single head
`o5p6q7r8s025` (`alembic/versions/o5p6q7r8s025_be025_assignment_scope_check.py:15-16`);
BE-026 would add exactly one revision with `down_revision = "o5p6q7r8s025"`, filename
convention `<revision>_be026_<slug>.py`, additive-only, reversible, and
`tests/unit/test_migrations.py` `EXPECTED_HEAD` + `EXPECTED_REVISION_COUNT` (currently
`o5p6q7r8s025` / `20`) updated in the same change — no historical revision is touched.

## 12. Required APIs

Subject to Stage B, but reconnaissance says these fit existing conventions [C]:

| Purpose | Shape | Guard | Notes |
|---|---|---|---|
| G13 assigned-work feed | `GET /api/v1/field/assignments` (page) | authenticated principal, own work | reuse `filter_by_project_scope`-style filtering **before counting**; envelope `{items, limit, offset, total}`, `limit ge=1 le=100`, `offset ge=0`, stable ordering — the `context.py:68-81` idiom |
| Sync one capture | `POST /api/v1/field/captures` (multipart file + metadata, or JSON metadata + deferred bytes — Stage B decides) | `require("evidence.create")` **plus** server-side assignment re-check | must re-evaluate authority at sync time (task §8), then call `ingest_evidence` in-process; **never** route through §7.1's open handlers |
| G14 outcome recovery | `GET /api/v1/field/captures/by-client-id/{client_operation_id}` | owner-only | answers "did my retry land?" with the persisted status |
| Assignment administration | `POST /api/v1/field/assignments`, `PATCH …/{id}/status`, `GET …/{id}` | BE-025 containment (`require()` + admin scope) | reuses `AdminOperationError → status`, `404` out-of-scope ≡ absent |
| Conflicts | `GET /api/v1/field/conflicts` | reviewer/supervisor/admin semantics only | must not leak cross-org detail (task §13) |
| Field sessions | **do not build yet** | — | §11.4; revisit only if Stage B finds a real server-side lifecycle need |

OpenAPI must document 401/403/404/409/413/415/422/503 accurately, including the idempotency
requirement and the conflict response; `openapi.json` is a tracked artifact and must be
regenerated from the live app (BE-025 DF-D-03 precedent, verified in that report's §12).

## 13. Security risks

| ID | Risk | Control reconnaissance implies |
|---|---|---|
| SR-01 | Legacy activity/claim/nearby handlers serve tenant data anonymously **[R]** (§7.1) | BE-026 surface must carry its own `require()`/ownership checks and must not proxy through those handlers; report, do not silently fix (task §27) |
| SR-02 | Offline client presents a stale assignment snapshot and is trusted | sync re-evaluates `field_assignments.status/expires_at` + `can()` against **current** DB state; old snapshot ⇒ explicit recorded `CONFLICT`, never silent acceptance (task §8) |
| SR-03 | Same `client_operation_id`, different payload | `request_hash` comparison ⇒ deterministic `CONFLICT` (409) + audit row; reuse `compute_request_hash` semantics, never accept silently |
| SR-04 | Retry creates duplicate Evidence | unique `(user_id, client_operation_id)` + persisted outcome ⇒ replay returns the stored result, no second ingest |
| SR-05 | Client-supplied timestamps/GPS treated as truth, or missing values fabricated | each timestamp stored in its own nullable column; no cross-filling; missing GPS stays NULL, never `0,0`; GPS presence is provenance, not authenticity (task §6/§7) |
| SR-06 | Unscoped-evidence dead end (§4) lets an officer's upload become unreachable to everyone but GLOBAL | attachment happens inside the sync transaction from the server-resolved assignment, not post-hoc by the client |
| SR-07 | Audit rows carrying file bytes, tokens or credentials | `append_event` already `scrub_sensitive`s payloads (`audit_ledger.py:118`); sync payloads carry ids/hashes only |
| SR-08 | Enumeration/leakage through list counts and errors | authorization filtering before counting; out-of-scope ≡ `404`; no cross-org totals |
| SR-09 | Unbounded or oversized sync batches (memory, storage) | bounded read at the caller exactly as `evidence.py:32`; per-request `max_upload_size`; batch size capped at Stage B |
| SR-10 | New permission weakening or hidden admin bypass | only additive permissions/grants, containment via existing `require()`; development-mode bypass (`is_development_bypass`) must not be relied on by any BE-026 test — enforce-mode-denial tests are mandatory |
| SR-11 | Citizen / API-client gaining sync authority | explicit role matrix tests (§15) |

## 14. Testing gaps **[C][R]**

Baseline suite is green (BE-025 §8: 348 unit + 216 integration) but covers **none** of:
assignment lifecycle transitions (no such entity), revoked/expired-while-offline sync,
client-operation identity, replay-after-timeout, same-key-different-payload, capture vs
upload vs server timestamp preservation, unknown-timestamp persistence, GPS accuracy/
altitude and missing-fix handling, no-duplicate-evidence-under-retry, batch/partial-failure
and rollback of sync, and sync-path audit events + chain validity. Adjacent coverage that
exists and can be leaned on: `test_be007_contracts.py:144-190` (PostGIS radius, bounded
`le=100000`), `test_be008_temporal.py:118-221,426` (capture present/absent, TZ-equivalence,
EXIF priority and no fabrication), `test_authorization.py:239-283` (project/org/unit
isolation), `test_be025_admin_control_plane.py:288-409,778` (scoped assignment, duplicate
concurrency, last-admin guard, CHECK enforcement), `test_audit_ledger.py:190-351` +
`tests/audit_guard.py`. Notable hole to respect: **the `Idempotency-Key` header is not
tested anywhere** despite `tests/unit/test_integration.py:5` claiming NEW/REPLAY/CONFLICT
coverage. Fault injection currently lives in root-level standalone scripts
(`stage_d_runtime_checks.py`, `stage_e_runtime_checks.py`) and `tests/preflight.py`
(`probe_postgres/redis/storage`, `require()`), not in pytest. No CI workflow exists
(no `.github/`), so every gate is manual.

## 15. Proposed BE-026 implementation plan

1. **Stage B (design)** — settle the §11 two-table shape and the §12 surface; decide (a)
   whether sync is multipart-with-bytes or metadata-then-bytes, (b) whether to introduce a
   `field.sync` permission or rely on existing `evidence.create` + ownership, (c) the batch
   contract and per-request limits, (d) the deterministic conflict taxonomy vs. ordinary
   duplicates, (e) whether `field_assignments` is admin-created only. State explicitly that
   no `Evidence` column changes.
2. **Stage C (implementation)** — models + one additive migration (head `o5p6q7r8s025` →
   new head) + `backend/services/field_operations.py` (sync: authorize → re-check
   assignment → idempotency NEW/REPLAY/CONFLICT → validate metadata → `ingest_evidence` →
   link → audit → single commit, with rollback + orphan-object cleanup on failure) +
   schemas + `backend/api/v1/endpoints/field.py` registered in `router.py` + additive audit
   event types + targeted test suite. No frontend, no browser storage, no ML.
3. **Stage D (runtime)** — live Postgres/PostGIS/pgvector/Redis/MinIO on `pofa_test`; full
   chain Assigned Activity → Field Session(represented) → Offline Capture → Sync →
   Evidence Ingestion → Association → Provenance → Audit; OpenAPI regenerated and diffed.
4. **Stage E (hardening)** — duplicate/concurrent sync (N threads on one
   `client_operation_id`), timeout-retry recovery, payload mismatch, revoked/expired
   assignment, activity/project state change, malformed UUID/payload (`422`, DF-SD-01
   precedent), oversized evidence (`413`), missing GPS/timestamp, Postgres/Redis/MinIO
   outage with infrastructure restored afterwards, partial-ingest rollback, cross-org
   access, audit-chain re-verification after every fault.
5. **Stage F (full verification)** — task §24's ten tracks, plus BE-025 regression (§26)
   and repeated-idempotency verification; `pofa_dev` isolation snapshot before/after.
6. **Deliverables** — the six `docs/BE-026 …` documents, findings preserved
   FOUND → FIXED → VERIFIED.

## 16. Explicit out-of-scope confirmation

Not built, not designed here, per task §28 and §1: PWA/frontend, IndexedDB or any browser
storage, offline UI, native Android/iOS, push notifications, SMS, chat, new ML models,
fraud/authenticity/deepfake detection, OCR, face recognition, Evidence Graph / Fusion /
Review Case / Publication / Organization-RBAC redesign, OIDC, cloud migration, Kubernetes,
and unrelated BE-024/BE-025 cleanup — **including** the §7.1 unguarded legacy routes,
`evidence.status`'s missing CHECK, `evidence_metadata`'s missing uniqueness, and the
known prior findings, which are preserved, not silently fixed: **DF-SD-02**,
**DF-SE-01**, **DF-SE-02**, **P15** (`tests/integration/test_publication.py:81` `be022-*`
fixture leak — ~66 GLOBAL assignments left per full integration run; re-observed in this
session's post-push verification: `pofa_test` GLOBAL rows 67 → 133 → 203 across two runs),
and the **MinIO host-restart environmental issue** (now escalated to full Docker engine
outage, §1). If BE-026 turns out to genuinely depend on one of them, Stage B will document
the dependency instead of editing unrelated code.

## 17. Decisions needed before Stage B

1. Sync payload shape: metadata-with-multipart-bytes in one request, or metadata-then-bytes
   two-phase (the latter keeps single-request batches small but needs a pending-blob
   strategy — note the existing pipeline only ever holds bytes in memory from a request).
2. Permission model: reuse `evidence.create` + server-side ownership checks, or add
   `field.sync` / `field_assignment.manage` to `AUTH_PERMISSIONS` (additive; BE-025's
   containment rules then decide who may create assignments).
3. Whether `field_assignments` needs ORGANIZATIONAL_UNIT scope or PROJECT-only (a CHECK
   matrix is only worth writing if more than one scope shape is legal).
4. Batch semantics: does one sync request carry one capture (simplest, §10 deterministic)
   or a batch with per-item outcomes (task §20 "partial failure" implies per-item results).
5. Is BE-026 allowed to *read* `Activity` rows (audit feed) for context, given it must not
   treat them as assignable work?

---

## Gate

**Stage A: complete.** Reconnaissance only — no production code modified, no migration
created, no endpoint added, nothing committed. Baseline remains `29d12eb8` with a clean
tree apart from this document.

**Awaiting approval to proceed to Stage B (domain and synchronization design).**
