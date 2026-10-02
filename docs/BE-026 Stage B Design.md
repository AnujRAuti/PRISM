# BE-026 Stage B Design — Field Operations & Offline Evidence Capture Backend

Milestone: BE-026 · Branch: `Backend` · Baseline: `29d12eb8`
Inputs: `docs/BE-026 Stage A Reconnaissance.md` (approved), task file §4–§20
Gate: **design only. No production code written, no migration created, no endpoint added, nothing committed.**

Conventions cited below are read from the current tree, not assumed:
`[A]` = Stage A finding, `[V]` = verified by reading source in this session, `[D]` = design decision.

---

## 1. Design constraints carried into Stage B

1. Backend authorization stays authoritative; the BE-016 plane (`require` / `can` /
   `resolve_resource_scope` / `filter_by_project_scope`) is the only policy engine. **[V]**
2. No second anything: ingestion (`ingest_evidence`), storage (`StorageService`),
   SHA-256 (`backend/engines/hashing/sha256.py:sha256_digest` `[V]`), request hashing
   (`compute_request_hash` `[V]`), audit (`append_event` `[V]`), EXIF/capture-time
   (`temporal_intelligence` `[V]`).
3. No changes to any existing table. No new resource types in `resolve_resource_scope`
   (that would be an authorization redesign).
4. Idempotent sync, four timestamp families preserved separately, missing GPS/time stays
   missing, conflicts first-class and auditable, nothing silently overwritten.
5. Findings preserved, not absorbed: SR-01, DF-SD-02, DF-SE-01, DF-SE-02, P15,
   MinIO/Docker host cycling, OBS-A-01.

---

## 2. Design decisions

| ID | Decision | Choice |
|---|---|---|
| D1 | Field session representation | First-class **thin** table `field_sessions` (reverses Stage A §11.4, reason below) |
| D2 | Sync transport | `POST /api/v1/field/sync`, **multipart, one capture per request** (bytes + metadata form fields) |
| D3 | Idempotency | New operation ledger table; reuse `compute_request_hash` + a `NEW/REPLAY/CONFLICT` evaluator written against it (not against `idempotency_keys`) |
| D4 | Permissions | Two additive permissions: `field.sync` (FIELD_OFFICER only), `field_assignment.manage` (ADMINISTRATOR only) |
| D5 | Assignment authority model | `field_assignments` is an **operational** work assignment, never an authorization grant; both RBAC scope AND an active assignment must hold |
| D6 | Scope shapes | `field_assignments` is PROJECT-rooted only (org/unit derived, never supplied) → no BE-025-style scope/ID matrix needed |
| D7 | Activity/Claim usage | Read-only context references; BE-026 writes **no** `Activity` rows and adds no lifecycle to `activities`/`projects` |
| D8 | Batch semantics | No server-side batch; batch = client queue iteration, safe because replays are `already_synchronized` |
| D9 | Conflict resolution | Conflict rows are terminal records resolved by a human annotation; the capture itself must be re-submitted under a new `client_operation_id` |

### D1 — why a session table after all

Stage A §11.4 excluded `field_sessions` as speculative. Task §4 requires the design to
answer "What is a field session?" and demands it stay associated with
`user · organization · project · activity · assignment`; §15 lists "field session" in the
provenance set; §16 requires "field session creation/activation" in the audit; §22's runtime
chain has "Field Session" as a step. A label column on the operation row cannot satisfy any
of those, because the server would then be trusting a **client-asserted** execution context
— the exact thing §8 forbids ("must not gain authority merely because it possesses an old
assignment snapshot"). A session row is the smallest structure that can hold a
*server-minted, server-validated* context binding. Rejected alternative: session-as-label
(fails §4/§15/§16/§22 and violates the never-trust-client-claims rule).

Three tables total (`field_assignments`, `field_sessions`, `field_capture_operations`) is
therefore the revised minimum. Disclosed as a Stage A → Stage B change, not rewritten out of
history.

### D2 — why one multipart request

`ingest_evidence(data, filename, declared_type, db)` takes **bytes already in memory**
and mints the Evidence id itself `[A] §4`. A two-phase "metadata then bytes" design would
need a server-side pending-blob area with expiry, which *is* a second ingestion system
(task §9 forbids). A JSON-only sync that references externally uploaded objects would need
the client to call `POST /evidence` first — and that path lands the row in
`project_id IS NULL`, which resolves to `RESOURCE_UNSCOPEABLE → 404` for any non-GLOBAL
officer `[A] §4`, i.e. the capture would be unreachable to its own author. So: one request,
bounded read at the caller exactly like `endpoints/evidence.py:32` `[V]`, ingest reused
in-process, association written in the same transaction as the established BE-014 pattern
(`endpoints/integration.py:422-425` sets `evidence.project_id` immediately after
`ingest_evidence` and commits once `[V]`).

---

## 3. Domain model

All new tables share the repo column conventions: `UUID(as_uuid=False)` PK with
`default=gen_uuid`, `DateTime(timezone=True)` + `server_default=func.now()`,
`updated_at` with `onupdate`, named `ck_*` CHECKs, `ix_*` indexes
(`[V]` from `models.py` and `alembic/versions/i9d0e1f2g016*`, `n4o5p6q7r022*`).

### 3.1 `field_assignments` — who is expected to do field work on which project

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | server-minted |
| `user_id` | UUID FK `users.id` ON DELETE RESTRICT, NOT NULL | the officer |
| `project_id` | UUID FK `projects.id` ON DELETE RESTRICT, NOT NULL | D6: always project-rooted |
| `organization_id` | UUID FK `organizations.id` nullable | **derived server-side from the project**, never accepted from a client |
| `organizational_unit_id` | UUID FK `organizational_units.id` nullable | same |
| `claim_id` | UUID FK `claims.id` nullable | optional work context |
| `activity_id` | UUID FK `activities.id` nullable | optional read-only context (D7) |
| `status` | String(32) NOT NULL default `ACTIVE`, CHECK `ACTIVE/RELEASED/REVOKED/EXPIRED` | mirrors `RetentionHold` lifecycle style `[A] §3` |
| `valid_from` | timestamptz nullable | "assignment active at capture time" test anchor |
| `expires_at` | timestamptz nullable | CHECK `expires_at > valid_from` when both present |
| `instructions` | Text nullable | free-text task note; no structure invented |
| `created_by` | UUID FK `users.id` nullable | manager who created it |
| `revoked_by` / `revoked_at` | UUID FK nullable / timestamptz nullable | **revocation never deletes the row** |
| `closed_reason` | String(255) nullable | required when status leaves ACTIVE (CHECK) |
| `created_at` / `updated_at` | timestamptz | |

Indexes and uniqueness:
* `uq_field_assignments_active_general` — UNIQUE `(user_id, project_id)`
  `WHERE status = 'ACTIVE' AND claim_id IS NULL` (`postgresql_where=sa.text(...)`, the
  convention `[V]` in `n4o5p6q7r022:82`).
* `uq_field_assignments_active_claim` — UNIQUE `(user_id, project_id, claim_id)`
  `WHERE status = 'ACTIVE' AND claim_id IS NOT NULL`.
  Two partial indexes avoid the nullable-column uniqueness problem entirely; no
  `postgresql_nulls_not_distinct` needed here (that idiom is only used where NULL is a
  meaningful value, as in `uq_user_role_scoped` `[V]`).
* `ix_field_assignments_user_status (user_id, status)`,
  `ix_field_assignments_project (project_id)`.

State machine: `ACTIVE → RELEASED | REVOKED | EXPIRED`, all terminal. No reactivation —
reissuing work creates a **new** assignment, so "superseded state" (§4) stays observable.
`EXPIRED` may be set by the server lazily when `expires_at` has passed (audited); a client
can never request it.

### 3.2 `field_sessions` — the server-minted execution context

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | returned to the client; the client cannot invent one |
| `assignment_id` | UUID FK `field_assignments.id` RESTRICT, NOT NULL | the binding |
| `user_id` | UUID FK `users.id` RESTRICT, NOT NULL | copied from the assignment server-side; CHECK-free consistency guaranteed by construction |
| `project_id` | UUID FK `projects.id` RESTRICT, NOT NULL | same |
| `organization_id` | UUID FK nullable | same |
| `status` | String(32) CHECK `ACTIVE/CLOSED/EXPIRED` | |
| `session_label` | String(128) nullable | client's human name for the outing |
| `client_device_id` | String(128) nullable | §5 device identifier; **not** BE-019 `client_id` `[A] §9` |
| `started_at` | timestamptz NOT NULL server-default | |
| `server_time_at_open` | timestamptz NOT NULL | lets the client report clock skew; never used to rewrite client timestamps |
| `closed_at` / `close_reason` | nullable | |
| `last_sync_at` | timestamptz nullable | updated by sync (counter, not state overwrite) |

`uq_field_sessions_active_device` — UNIQUE `(assignment_id, client_device_id)`
`WHERE status = 'ACTIVE' AND client_device_id IS NOT NULL` (multi-device allowed, one open
session per device per assignment); `ix_field_sessions_user_status (user_id, status)`.

### 3.3 `field_capture_operations` — the idempotent sync ledger and provenance record

| Group | Columns |
|---|---|
| identity | `id` UUID PK; `user_id` FK NOT NULL; `client_operation_id` String(128) NOT NULL CHECK `char_length ≥ 8`; `client_capture_id` String(128) nullable; `client_device_id` String(128) nullable; `session_id` FK `field_sessions.id` RESTRICT nullable (set on first execution); `assignment_id` FK nullable; `project_id` FK nullable; `claim_id` FK nullable; `evidence_id` FK `evidence.id` SET NULL nullable |
| integrity | `request_hash` String(64) NOT NULL; `payload_sha256` String(64) NOT NULL (from `sha256_digest(data)`); `declared_content_type` String(128); `filename` String(512); `file_size` bigint |
| outcome | `status` String(32) NOT NULL CHECK `ACCEPTED / VALIDATION_FAILED / CONFLICT` (see §6 for why REJECTED/503 never persist) |
| timestamps | `captured_at`, `queued_at`, `uploaded_at` (client, all nullable) · `received_at` (server, NOT NULL) · `processed_at` (server, nullable) — each `timestamptz`, independently nullable |
| GPS | `latitude` numeric CHECK −90…90; `longitude` numeric CHECK −180…180; `capture_accuracy_m` numeric CHECK `> 0 AND ≤ 100000`; `altitude_m` numeric CHECK `−1000…10000`; `location_source` String(32) CHECK `DEVICE_GPS/DEVICE_MANUAL/CLIENT_INFERRED/UNKNOWN`; `zero_island_confirmed` boolean NOT NULL default false |
| conflict | `conflict_reason` String(64) nullable; `conflict_detail` JSONB nullable; `timestamp_flags` JSONB NOT NULL default `[]`; `resolution_status` String(32) CHECK `UNRESOLVED/RESOLVED` default `UNRESOLVED`; `resolved_by` FK nullable; `resolved_at` nullable; `resolution_note` Text nullable; `sync_count` integer NOT NULL default 1; `last_synced_at` timestamptz nullable |

Constraints:
* `uq_field_operations_user_client_id` — UNIQUE `(user_id, client_operation_id)`; both NOT
  NULL so a plain unique constraint suffices `[D]`. This is what makes retry-after-timeout
  answerable and duplicate Evidence impossible.
* `ck_field_operations_coordinate_pair` — `NUM_NONNULLS(latitude, longitude) IN (0, 2)`
  → no half-populated fix.
* `ck_field_operations_zero_island` —
  `NOT (latitude = 0 AND longitude = 0 AND zero_island_confirmed IS NOT TRUE)`
  → missing GPS can never be silently recorded as `0,0` (§7), while a genuine reported fix
  at those coordinates is storable when explicitly confirmed.
* `ck_field_operations_source_when_located` — `latitude IS NULL OR location_source IS NOT NULL`.
* `ck_field_operations_accuracy_needs_fix` — `capture_accuracy_m IS NULL OR latitude IS NOT NULL`.
* `ck_field_operations_conflict_shape` — `status = 'CONFLICT'` ⟺ `conflict_reason IS NOT NULL`;
  `status <> 'CONFLICT'` ⟹ conflict columns NULL.
* `ck_field_operations_resolution_needs_conflict` — `resolution_status = 'RESOLVED'`
  only when `status = 'CONFLICT'`.
* `ck_field_operations_timestamp_order_free` — deliberately **no** cross-timestamp ordering
  CHECK; clock drift is real and must be preserved, so ordering violations are recorded as
  `timestamp_flags` (§7) instead of rejected.
* `ck_field_operations_accepted_has_evidence` — `status = 'ACCEPTED'` ⟹ `evidence_id IS NOT NULL`.
  **Stage C amendment (DEF-C-03): implemented, then removed.** The bullet above gives this FK
  `ON DELETE SET NULL`, and `retention.py:1175-1176` purges Evidence exactly through that key.
  Postgres evaluates CHECKs on the FK-driven nulling too, so the CHECK aborted the purge (and
  every later UPDATE of the row). The pairing is a service-level invariant instead: the
  executor writes `status` and `evidence_id` in one statement.
* Indexes: `ix_field_operations_user_status`, `ix_field_operations_session`,
  `ix_field_operations_evidence`, `ix_field_operations_conflict (resolution_status) WHERE status='CONFLICT'`.

`field_capture_operations` is the answer to "where is provenance?": it *is* the provenance
record for a field capture, joined to canonical Evidence by `evidence_id`. No new column is
added to `evidence`, and `EvidenceMetadata` is not written by BE-026 (its existing writers
query-then-insert and it has no unique `evidence_id` `[A] §5`; racing it would be a second
metadata store).

---

## 4. Authorization model

### 4.1 Containment statement (the load-bearing rule)

`field_assignments` **grants nothing**. Authority continues to come only from
`user_role_assignments` + `AUTH_ROLE_PERMISSIONS`, evaluated by `can()`. A sync or session
open succeeds only when **both** hold:

1. the permission gate (`field.sync`, checked by `require("field.sync")` — the verified
   no-resource form, which "must simply be present in any scope"
   (`security/authorization.py:67-79`) `[V]`), **and**
2. the scope gate: `can(principal, "evidence.create", resolve_resource_scope(db, "project", <assignment.project_id>))`
   is allowed for the **server-resolved** project, **and**
3. an operational gate: an `ACTIVE`, non-expired `field_assignments` row for
   `(principal.principal_id, that project)`.

Consequences, stated so Stage C cannot drift:
* A field assignment for a user with no matching role grant produces a durable
  `REJECTED`-equivalent denial, never access. Assignment ⇒ authority is impossible.
* Authority is re-evaluated **at every sync** against current DB rows (§8 of the task). A
  stale client snapshot is data, not a credential.
* Neither new permission is granted to CITIZEN, REVIEWER, SUPERVISOR, API_CLIENT or any
  other role, so §14's negative cases fall out of the catalogue; they are still tested
  explicitly.
* `is_development_bypass` may not be relied on by any BE-026 test; enforce-mode denials are
  mandatory (SR-10).

### 4.2 Ownership and cross-tenant rules

* Session/capture reads and `GET /field/work`: rows filtered by `user_id = principal.principal_id`
  **before counting** (the `filter_by_project_scope` idiom `[V]` `context.py:68-81`), so no
  cross-user count leakage.
* `GET /field/assignments`, `GET /field/operations`: managers only, filtered to projects the
  caller can manage (`visible_project_ids`-equivalent), out-of-scope ⇒ **404**, never 403
  (`SCOPE_DENIED` mapping `[V]` `security/authorization.py:163-165`).
* Malformed UUIDs in any path parameter hit `reject_malformed_resource_id` → 422 before a DB
  touch (DF-SD-01 precedent `[V]`).
* A non-GLOBAL principal may not name an organization/unit the project does not already
  carry: org/unit are derived from `Project` server-side (D6), so there is no client field to
  forge.

### 4.3 Explicitly not done

No new `resource_type` in `resolve_resource_scope` (that is an authorization redesign); no
parallel role table, no policy engine, no bearer-token side channel, no admin bypass.
Ownership is enforced by direct column comparison in the service, which is the existing
pattern for owner-scoped surfaces.

---

## 5. Sync algorithm

`POST /api/v1/field/sync` (multipart: `file`, `client_operation_id`, optional
`client_capture_id`, `client_device_id`, `session_id`, `captured_at`, `queued_at`,
`uploaded_at`, `latitude`, `longitude`, `capture_accuracy_m`, `altitude_m`,
`location_source`, `zero_island_confirmed`).

```
 1. require("field.sync")            → 401/403 by the existing gate
 2. load session (server rows only)  → 404 if foreign/absent
 3. canonical metadata dict          → request_hash = compute_request_hash(dict ∪ {payload_sha256})
    payload_sha256 = sha256_digest(data)   (data bounded-read at the caller, max_upload_size + 1)
 4. operation lookup by (user_id, client_operation_id)
      FOUND and hash equal   → REPLAY  (§6 table)   200 already_synchronized
      FOUND and hash differs → CONFLICT 409 (existing row untouched, audit appended)
      NOT FOUND              → continue
 5. re-evaluate authority NOW: §4.1 gates + assignment.status/expires_at + session.status
      permission/scope failure  → 403/404 + audit only, NO row (§6 rule R2)
      context superseded        → insert row status=CONFLICT + audit → 409
 6. metadata validation (timestamps tz-aware, GPS pair/zero-island/source rules)
      failure → insert row status=VALIDATION_FAILED (+timestamp_flags) + audit → 422
 7. ingest_evidence(data, filename, declared_type, db)      ← BE-003 reused, unmodified
      its own 400/413/415 propagate unchanged (§6 rule R3)
      Stage C note (DEF-C-04): step 6's VALIDATION_FAILED row covers metadata *BE-026*
      validates. A structural rejection here writes no row -- the §6 table says "none
      (rollback)" -- because the reused validator raises before it stores or commits,
      so the reservation is dropped and a retry answers with the same 400/413/415.
 8. associate on the fresh Evidence row, in the same transaction:
      evidence.project_id = assignment.project_id          (server-resolved)
      evidence.claim_id   = assignment.claim_id            (when set)
      evidence.location   = ST_SetSRID(ST_MakePoint(lng, lat), 4326)  (when a fix exists)
    set operation.evidence_id, status=ACCEPTED, processed_at
 9. append_event(FIELD_SYNC_ACCEPTED) + append_event(FIELD_EVIDENCE_ASSOCIATED)
10. db.commit()   — one transaction: operation row + Evidence + association + audit
    commit together or roll back together
```

Any `StorageError`/`SQLAlchemyError` propagates after `ingest_evidence`'s own
rollback + orphan-object cleanup `[A] §4`; the service adds nothing there and does not
swallow it.

### 5.1 Idempotency evaluator

Written against `field_capture_operations` (not `idempotency_keys`, which is bound to
`api_clients` with CASCADE `[A] §6`), but with the *same* three-way outcome contract so the
semantics stay familiar: `NEW | REPLAY | CONFLICT` via `compute_request_hash` over a
sorted-key canonical dict that includes `payload_sha256` — therefore "same client ID,
different payload" covers both different metadata **and** different bytes. Concurrent first
submissions are settled by the `uq_field_operations_user_client_id` violation:
`IntegrityError → rollback → re-read → REPLAY/CONFLICT`, mirroring
`record_idempotency` `[V]` `services/integration.py:280-294`.

Replay reconstructs its response **from the stored row** (`evidence_id`, statuses, the five
timestamps) rather than from a `result_payload` blob — no duplicate of
`idempotency_keys.result_payload` concept.

### 5.2 What is *not* a conflict

Same `client_operation_id`, same hash, already `ACCEPTED` → `already_synchronized` (200),
audit `FIELD_SYNC_DUPLICATE`, `sync_count += 1`, `last_synced_at` updated. Task §4:
"Do not classify ordinary duplicate requests as conflicts." Retries are therefore safe and
free, which is why batches are client-side iteration (D8).

---

## 6. Status vocabulary and persistence rules

Response `sync_status` is exactly the task §11 set; row `status` is the smaller persisted set.

| Condition | HTTP | `sync_status` | row status | audit events |
|---|---|---|---|---|
| first execution, authorized, valid, ingest ok | 201 | `accepted` | `ACCEPTED` | `FIELD_SYNC_ACCEPTED`, `FIELD_EVIDENCE_ASSOCIATED` |
| exact retry / replay | 200 | `already_synchronized` | `ACCEPTED` (unchanged; counters move) | `FIELD_SYNC_DUPLICATE` |
| same id, different hash | 409 | `conflict` (`PAYLOAD_MISMATCH`) | existing row **untouched** | `FIELD_SYNC_CONFLICT` |
| superseded context (assignment revoked/expired, session closed, id bound to another session, referenced claim/activity gone) | 409 | `conflict` | `CONFLICT` (new row) | `FIELD_SYNC_CONFLICT` |
| invalid client metadata (naive timestamp, half GPS pair, unconfirmed `0,0`, bad source enum) | 422 | `validation_failed` | `VALIDATION_FAILED` (new row) | `FIELD_SYNC_REJECTED` |
| permission/scope/ownership failure (no `field.sync`, RBAC scope not covering the project, wrong org, foreign session, project ≠ assignment project) | 403 / 404 | *(error envelope, no `sync_status`)* | **none** | `FIELD_SYNC_REJECTED` + `FIELD_ASSIGNMENT_SECURITY_FAILURE` |
| file structural rejection by the reused validator | 400/413/415 | *(propagated `detail`)* | none (rollback) | none — identical to today's `POST /evidence` contract |
| Postgres / Redis / MinIO unavailable | 503 | `temporarily_unavailable` | none (rollback) | none (request log + metrics) |

**R1 — row recorded ⟺ the server made a durable decision about that operation identity.**
**R2 — a denied request never mutates domain state.** Matches BE-016 (`SCOPE_DENIED → 404`
writes nothing) and stops untrusted input from writing rows; the security events are still
appended (append-only ledger, `commit=True`, because the surrounding transaction is rolled
back and the requirement in §16 is explicit).
**R3 — `ingest_evidence`'s 4xx are terminal client errors and roll the whole sync back**,
leaving no Evidence, no object, no operation row. Consequence for testing: nothing was
created, so a retry cannot double-create; the existing BE-003 behaviour is preserved rather
than reimplemented.

## 7. Timestamp semantics

| Field | Set by | Nullable | Notes |
|---|---|---|---|
| `captured_at` | client | yes | device clock; NEVER backfilled |
| `queued_at` | client | yes | offline queue insertion |
| `uploaded_at` | client | yes | the client can only know this after a response; the server **never** fills it |
| `received_at` | server | no | PoA ingestion time |
| `processed_at` | server | yes | set only when ingest completed in this execution |
| domain event time | audit ledger | — | `audit_events.created_at`; **no duplicate column** — the row does not fake it |

Rules: `timestamptz` columns only; naive ISO-8601 ⇒ `validation_failed` (the existing
timezone-aware precedent at `endpoints/integration.py:411-415` `[V]`); missing stays NULL and
is reported as `unknown` in responses; no column is derived from another; ordering
violations (`queued_at < captured_at`, `uploaded_at < received_at`, future `captured_at`)
are recorded in `timestamp_flags` as labels such as `QUEUE_BEFORE_CAPTURE`,
`FUTURE_CAPTURE`, `UPLOAD_AFTER_RECEIPT` — **observed, not rewritten, not rejected**.
EXIF-derived capture time stays exactly where it is (`temporal_intelligence` read-time
derivation `[A] §5`); BE-026's `captured_at` is a *client assertion* kept beside it, and
**retention anchors are not rewired**: `services/retention.py:343-359` continues to resolve
`CAPTURED_AT`/`INGESTED_AT` as before. Changing that would silently alter deletion
eligibility — out of scope, recorded as a non-goal.

## 8. GPS semantics

Coordinates on the operation row are the **client's reported fix**, stored as numeric
assertion data (accuracy, altitude, source, zero-island confirmation) — PostGIS remains the
only authoritative location, and it is written on `Evidence.location` through the existing
`ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)` path (`endpoints/context.py:232` `[V]`),
only for an accepted operation with a complete pair. DB CHECKs (§3.3) make "missing GPS" and
"GPS at 0,0" uncollapsible. Accuracy/altitude have no home on `evidence` today, which is
precisely why they live here instead of redesigning Evidence. GPS presence is provenance,
never an authenticity or truth claim (§7/§15 of the task), and absence of GPS alone never
rejects a capture.

## 9. Conflict taxonomy

`conflict_reason` vocabulary (CHECK-constrained), each with a deterministic rule:

| Reason | Trigger | Rule |
|---|---|---|
| `PAYLOAD_MISMATCH` | existing id, different hash | 409; existing row untouched; recover by submitting under a new `client_operation_id` |
| `ASSIGNMENT_REVOKED` | assignment status `REVOKED` at sync | 409 + `CONFLICT` row; server state wins, never silently re-authorized |
| `ASSIGNMENT_EXPIRED` | `expires_at < received_at` or lazily `EXPIRED` | 409 + `CONFLICT` row |
| `SESSION_CLOSED` | session not `ACTIVE` | 409 + `CONFLICT` row (synchronizing against superseded context) |
| `OPERATION_SESSION_MISMATCH` | id already bound to a different session of the same user | 409 + `CONFLICT` row |
| `CONTEXT_RESOURCE_MISSING` | assignment's referenced claim/activity no longer exists | 409 + `CONFLICT` row |
| `ASSIGNMENT_SUPERSEDED` | a newer ACTIVE assignment covers the same (user, project, claim) | 409 + `CONFLICT` row |

Nothing is auto-resolved in the client's favour (§12). `POST /api/v1/field/operations/{id}/resolve`
(`field_assignment.manage`) records a human decision — `DISMISSED` or
`RESUBMISSION_REQUIRED` — sets `resolution_status=RESOLVED`, `resolved_by`, `resolved_at`,
and appends `FIELD_SYNC_CONFLICT_RESOLVED`. Resolution **never** ingests evidence, never
mutates `Evidence`, and never clears the conflict fields: the annotated row stays as the
historical record (D9).

## 10. Audit events

Additive to `AUDIT_EVENT_TYPES` (`models.py:1036-1043` block style `[V]`):

`FIELD_ASSIGNMENT_CREATED`, `FIELD_ASSIGNMENT_STATUS_CHANGED`, `FIELD_ASSIGNMENT_EXPIRED`,
`FIELD_ASSIGNMENT_ACCESSED`, `FIELD_ASSIGNMENT_SECURITY_FAILURE`,
`FIELD_SESSION_OPENED`, `FIELD_SESSION_CLOSED`,
`FIELD_SYNC_ACCEPTED`, `FIELD_SYNC_DUPLICATE`, `FIELD_SYNC_REJECTED`, `FIELD_SYNC_CONFLICT`,
`FIELD_SYNC_CONFLICT_RESOLVED`, `FIELD_EVIDENCE_ASSOCIATED`.

Payloads carry **ids, hashes, statuses and reasons only** — never bytes, tokens,
credentials, presigned URLs or file contents (the ledger already `scrub_sensitive`s
payloads `[A] §8`; BE-026 does not rely on that as a licence to log secrets).
`resource_type` is `field_assignment` / `field_session` / `field_capture_operation` /
`evidence` as appropriate, `actor_id` is the officer, `project_id` the server-resolved
project. Chain validation is re-run after every BE-026 test group, and the BE-023
append-only guard (`tests/audit_guard.py`) must stay green — no UPDATE/DELETE path against
`audit_events` is added.

**One reasoned soft-deviation from §16** ("cover … assignment access"):
`FIELD_ASSIGNMENT_ACCESSED` is appended for the moments that turn access into authority —
session open against an assignment — and for administrative cross-user reads
(`GET /field/assignments`, `GET /field/operations`). An officer's own `GET /field/work` poll
is **not** a ledger event; it is covered by the structured request log and metrics. Rationale:
offline clients poll by design, and every poll would otherwise append a chained event,
unboundedly growing the append-only ledger and diluting its security signal. Rejected
alternative: log every poll. Flagged for explicit user ratification rather than assumed.

## 11. API surface (11 operations)

`backend/api/v1/endpoints/field.py`, `router = APIRouter(prefix="/field")` (prefix only, no
`tags=` — the convention `[V]` `endpoints/publication.py:16`), registered in
`backend/api/v1/router.py`; no route-order interaction with `context_router`/`evidence_router`
because every path is under `/field`. Error docs reuse the `_error_docs(...)` style `[V]`.

| # | Method + path | Guard | Purpose |
|---|---|---|---|
| 1 | `POST /api/v1/field/assignments` | `require("field_assignment.manage", "project", "project_id")` | create work assignment; org/unit derived server-side; audit |
| 2 | `GET /api/v1/field/assignments` | `require("field_assignment.manage")` + project-scope filter | manager listing, paginated, filters `user_id`/`project_id`/`status` |
| 3 | `GET /api/v1/field/assignments/{assignment_id}` | owner **or** manager, else 404 | detail |
| 4 | `PATCH /api/v1/field/assignments/{assignment_id}/status` | `field_assignment.manage` | `RELEASED`/`REVOKED` only; never deletes |
| 5 | `GET /api/v1/field/work` | `require("field.sync")` | the §13 assigned-work feed (own rows only, paginated) |
| 6 | `POST /api/v1/field/sessions` | `require("field.sync")` + §4.1 gates | open a session against own ACTIVE assignment |
| 7 | `POST /api/v1/field/sessions/{session_id}/close` | `require("field.sync")` (owner) or manager | close |
| 8 | `POST /api/v1/field/sync` | `require("field.sync")` + §4.1 gates | §5 algorithm, multipart, one capture |
| 9 | `GET /api/v1/field/captures/{client_operation_id}` | `require("field.sync")`, owner-only | retry-after-timeout recovery (§10 of the task) |
| 10 | `GET /api/v1/field/operations` | `field_assignment.manage` + scope filter | conflict/queue visibility for managers, paginated |
| 11 | `POST /api/v1/field/operations/{operation_id}/resolve` | `field_assignment.manage` | §9 terminal annotation |

Pagination everywhere: `limit: int = Query(50, ge=1, le=100)`, `offset: int = Query(0, ge=0)`,
envelope `{items, total, limit, offset}` (`*ListResponse` convention `[V]`), stable ordering
`created_at DESC, id DESC` (id tiebreak makes it deterministic), authorization filter applied
**before** `count()`.

Schemas: `backend/schemas/field_operations.py` — `str, Enum` vocabularies for status /
sync_status / conflict_reason / location_source, request models with
`ConfigDict(extra="forbid")` (so an unexpected `project_id` on sync is a 422, not a silently
ignored escalation attempt — see SR-12), response models with `ConfigDict(from_attributes=True)`.
Service: `backend/services/field_operations.py` (module-level functions, keyword-only args,
`FieldOperationError(status_code, detail)` mirroring `AdminOperationError`, commits inside the
service, `_lock_row`-style `with_for_update()` before any lifecycle transition). Repository:
`backend/repositories/field_operations.py` (`get_*/insert_*/list_*`, no `commit()`,
`list_*(db, *, limit, offset) -> (rows, total)` — all per the verified conventions).

### 11.1 Feed data minimization (§13)

`GET /field/work` returns, per ACTIVE assignment: `assignment_id`, `project{id,name}`,
`organization_id`, `expires_at`, `valid_from`, and **only** the context the assignment itself
names — `claim{id,title}` when `claim_id` is set, `activity{id,verb,created_at}` when
`activity_id` is set. It never returns: other projects or activities, claims not named by an
assignment, fusion/graph/intelligence values, review-case or dispute content, evidence owned
by other users, audit or administrative data, or counts of anything outside the caller's own
rows.

## 12. Error taxonomy

Existing conventions, no new machinery: 401 `Authentication required`, 403 `Forbidden`,
404 `Not found` (out-of-scope ≡ absent), 409 conflict with `sync_status:"conflict"` +
`conflict_reason` in the body, 422 validation (`VALIDATION_FAILED` row), 413/415/400 from the
reused validator, 503 `temporarily_unavailable` for dependency outage. No failure collapses to
500; no stack trace in any response body; `detail` strings stay consistent with the
`enforce()` mapping.

## 13. Migration plan

Exactly **one** new revision, additive, reversible, chained on the current head:

* file `alembic/versions/p6q7r8s9t026_be026_field_operations.py`,
  `revision: str = "p6q7r8s9t026"`, `down_revision: Union[str, Sequence[str], None] = "o5p6q7r8s025"`
  (typed form, next free slot in the verified linear chain `[V]`),
* `upgrade()`: three `op.create_table` calls + named `sa.CheckConstraint`s + `op.create_index`
  (two of them `unique=True, postgresql_where=sa.text("status = 'ACTIVE' …")`) + the
  `AUDIT_EVENT_TYPES` addition (Python-side constant; the ledger column is a string, so no DDL
  is needed for event types),
* `downgrade()`: drop indexes then tables in reverse dependency order — verified by
  downgrade/upgrade and a from-scratch run in Stage D/F,
* `tests/unit/test_migrations.py`: `EXPECTED_HEAD` → `p6q7r8s9t026`,
  `EXPECTED_REVISION_COUNT` 20 → 21, in the same change,
* no historical revision is touched; no `ALTER TABLE` against any existing table.

## 14. Permission catalogue changes (additive only)

`AUTH_PERMISSIONS += ("field.sync", "field_assignment.manage")`;
`AUTH_ROLE_PERMISSIONS["FIELD_OFFICER"] += "field.sync"`;
`AUTH_ROLE_PERMISSIONS["ADMINISTRATOR"] += "field_assignment.manage"`;
`ACTION_PERMISSIONS` identity entries for both (`services/authorization.py:48-114` `[V]`).
`ensure_default_catalogue` re-seeds idempotently `[V]` `:169-178`, so no data migration is
needed. Existing role lines are appended, never reordered or removed — **no permission is
weakened**, and reviewer/supervisor/citizen/API-client sets are byte-identical apart from the
two additions above. **D8-follow-up for the user**: conflict resolution is admin-only in this
design; granting `field_assignment.manage` to SUPERVISOR as well is a one-line additive change
if you want supervisors in the resolution loop (Stage C can take either).

## 15. Security considerations

SR-01 … SR-11 carry over from Stage A unchanged. Two additions from this design pass:

* **SR-12 (new, `[V]`, out of scope to fix)** — `POST /api/v1/integrations/evidence`
  (`endpoints/integration.py:386-425`) accepts a **client-supplied** `project_id` and applies
  only `require("external_data.write")` at permission level, with no scope re-check on the
  named project. Any principal holding that permission can therefore attach evidence to an
  arbitrary project. This is a pre-existing BE-019 finding, reported and preserved, **not**
  repaired here. BE-026 must not copy the pattern: sync has no `project_id` form field at all
  (the schema is `extra="forbid"`), and the project comes from the server-resolved assignment.
* **SR-13** — offline clients multiply the enumeration surface (device ids, operation ids).
  Owner-only lookups, 404-for-foreign, bounded pagination, and `char_length ≥ 8` opaque ids
  keep guesses useless; no endpoint accepts another user's identifiers to return their data.

Distributed-denial-of-ledger-growth is addressed by R2 (denials never write domain rows) and
by the §10 poll-logging decision.

## 16. Stage C work packages

1. models: three tables + 13 audit event type names (`db/models.py`).
2. repository `field_operations.py`: get/insert/list + partial-index-aware lookups, locking.
3. service `field_operations.py`: assignment create/transition, session open/close, work feed,
   the §5 sync evaluator, conflict resolution, audit appends, single-transaction commits.
4. schemas `field_operations.py`: vocab enums, `extra="forbid"` requests, response envelopes.
5. endpoints `field.py` (11 routes) + registration in `api/v1/router.py`.
6. permissions catalogue additions (§14).
7. migration `p6q7r8s9t026_be026_field_operations.py` + `test_migrations.py` constants.
8. tests: `tests/unit/test_field_operations.py` (hashing/idempotency/classification pure logic,
   conflict taxonomy, canonical dict stability) and
   `tests/integration/test_be026_field_operations.py` (§20 matrix below), plus
   `openapi.json` regenerated from the live app.
9. docs: Stage C implementation summary.

No frontend, no browser storage, no native code, no ML, no Evidence/Authorization/Audit
redesign.

## 17. Test design mapped to task §20

| Group | Cases (all against live Postgres/PostGIS/Redis/MinIO on `pofa_test`) |
|---|---|
| Assignment | authorized create; unauthorized create (403/404); cross-org denial; revoked; expired; pagination bounds + stable order + no foreign count |
| Offline capture | valid capture; malformed metadata; missing optional GPS (accepted, `unknown`); valid GPS; missing timestamp stays unknown; known timestamp preserved exactly; multiple timestamps preserved independently |
| Synchronization | first sync 201; exact duplicate 200 `already_synchronized` and **one** Evidence row; retry-after-timeout via endpoint 9 (same logical result); same id different payload → 409 `PAYLOAD_MISMATCH`; concurrent sync (N threads, one id) → exactly one ACCEPTED; partial failure (object written, row insert fails) → rollback + no orphan + retry lands; retry after failure |
| Evidence | `ingest_evidence` reused (no second validator: 415 on signature mismatch, 413 oversize propagate); `payload_sha256` equals the `Evidence.sha256` the analysis job later computes; storage state `uploaded_quarantine`; association `project_id`/`claim_id`/`location` correct; zero duplicate Evidence under any retry |
| Authorization | FIELD_OFFICER / REVIEWER / SUPERVISOR / ADMINISTRATOR / CITIZEN / API_CLIENT / unauthenticated matrix, **enforce mode** (`AUTH_MODE=enforcing`, dev tokens off), including "ACTIVE field assignment + no role grant ⇒ denied" and "role grant + no assignment ⇒ denied" |
| Conflict | assignment revoked while offline; assignment expired; session closed; id bound to another session; missing context resource; explicit `sync_status:"conflict"` + row + audit; duplicate-identity case |
| Audit | expected events per §6 table; correct actor/resource/project; chain valid after the run; no bytes/tokens/credentials in payloads; BE-023 append-only guard green |
| Regression | BE-025 §26 list: organization administration, role assignment, project ownership, API client authorization, audit, publication/dispute authorization, retention governance, evidence ingestion, existing idempotency; full unit + full integration in Stage F |

## 18. Stage A → Stage B deltas (disclosed, not rewritten)

1. Stage A §11.4 excluded a `field_sessions` table; Stage B introduces it (D1, with reasons).
   Net schema: **three** new tables instead of two; still zero changes to existing tables.
2. Stage A §12 listed `GET /api/v1/field/conflicts`; Stage B drops it — conflicts are visible
   on the owner's own operation rows (endpoint 9) and to managers (endpoint 10), so a separate
   endpoint would duplicate state without adding information.
3. Stage A §12 proposed `POST /api/v1/field/captures`; Stage B uses `POST /api/v1/field/sync`
   (task §17's own example, and it names the operation rather than implying a stored capture
   resource is created by the client).
4. SR-12 is new.
5. §10's audit-access soft-deviation is new and needs your ratification.

## 19. Explicitly out of scope for BE-026

Frontend/PWA, IndexedDB or any browser storage, offline UI, native mobile, push/SMS/chat,
new ML, fraud/authenticity/deepfake, OCR, face recognition, Evidence Graph/Fusion/Review
Case/Publication/Organization-RBAC redesign, OIDC, cloud/Kubernetes, unrelated
BE-024/BE-025 cleanup. Preserved findings, untouched: SR-01 unguarded legacy routes,
SR-12 integration scope gap, `evidence.status` missing CHECK, `evidence_metadata` missing
uniqueness, DF-SD-02, DF-SE-01, DF-SE-02, P15 fixture leak, MinIO/Docker host cycling,
OBS-A-01 startup logging error.

---

## Gate

**Stage B: complete.** Design only — no production code, no migration, no endpoint, no
permission granted, nothing committed. Baseline remains `29d12eb8`; the working tree holds
only the two untracked BE-026 documents.

Open items for you before Stage C: (a) ratify the §10 "assignment access" audit deviation;
(b) ratify or widen D8-follow-up (conflict resolution admin-only vs. also SUPERVISOR);
(c) confirm the three-table schema in place of Stage A's two, per §18.1.

**Awaiting approval to proceed to Stage C (implementation).**
