# BE-026 Stage C — Implementation Summary

Gate: Stage A reconnaissance and Stage B design are approved. This stage implements the
minimum backend changes only. No frontend, no browser storage, no native mobile, no ML, no
Evidence redesign, no Authorization redesign, no Audit redesign.

Everything below was verified by running the real application against real Postgres/PostGIS,
Redis and MinIO under `TEST_DATABASE_URL=…/pofa_test` (plus a clean scratch database for the
migration and regression evidence). Nothing is claimed from grep, imports, OpenAPI strings or
static reading.

---

## 1. What was built

| Layer | File | Lines | Change |
|---|---|---|---|
| models | `backend/db/models.py` | +371 / −0 | three tables, six vocabularies, thirteen audit event types, two permissions, one role grant |
| permissions | `backend/services/authorization.py` | +3 / −0 | `field.sync`, `field_assignment.manage` in `ACTION_PERMISSIONS` |
| routing | `backend/api/v1/router.py` | +4 / −1 | `field_router` included last |
| migration | `alembic/versions/p6q7r8s9t026_be026_field_operations.py` | 257 | one additive, reversible revision chained on `o5p6q7r8s025` |
| repository | `backend/repositories/field_operations.py` | 375 | 21 query/insert/lock helpers |
| schemas | `backend/schemas/field_operations.py` | 315 | 9 enums, 8 request models, 9 response models, all `extra="forbid"` |
| service | `backend/services/field_operations.py` | 1762 | assignments, sessions, work feed, synchronization, conflicts, resolution |
| endpoints | `backend/api/v1/endpoints/field.py` | 492 | 11 operations |
| unit tests | `tests/unit/test_field_operations.py` | 461 | 52 tests |
| integration tests | `tests/integration/test_be026_field_operations.py` | 1779 | 41 tests |
| contract | `openapi.json` | regenerated | field-additive only |

## 2. Data model

Three tables, exactly as Stage B §3 (Stage A's two-table sketch was rejected with reasons):

* **`field_assignments`** — the officer↔project binding. Organization/unit are **derived from
  the project**, never accepted from a caller. Two partial unique indexes govern ACTIVE work:
  `uq_field_assignments_active_general` (officer, project, claim-less) and
  `uq_field_assignments_active_claim` (officer, project, claim), so an officer can hold one
  general assignment plus claim-specific ones. Statuses `ACTIVE/RELEASED/REVOKED/EXPIRED`; a
  status leaving `ACTIVE` requires `closed_reason`.
* **`field_sessions`** — the server-minted execution context (`ACTIVE/CLOSED/EXPIRED`),
  unique per `(assignment_id, client_device_id)` while open.
* **`field_capture_operations`** — the idempotent synchronization ledger keyed on
  `(user_id, client_operation_id)` with `char_length(client_operation_id) >= 8`. Timestamps
  `captured_at / queued_at / uploaded_at / received_at / processed_at` are stored separately
  and never derived from one another; ordering violations are recorded as `timestamp_flags`,
  never corrected. GPS is a pair-or-nothing CHECK, `0,0` requires confirmation, accuracy
  requires a fix, a fix requires a location source.

`PENDING` is the one addition over the approved §6 vocabulary: it is a reservation made before
the reused ingestion pipeline commits its own transaction. It is a transient state, never
public — the public `sync_status` set is exactly the task §11 words.

**Removed after runtime evidence (DEF-C-03):** the planned
`ck_field_operations_accepted_has_evidence` CHECK. See §6 below.

## 3. Authorization integration (no redesign)

Synchronization requires **all three**, re-evaluated on every call, from server rows only:

1. the `field.sync` permission through the existing BE-016 `require()` plane;
2. a current scope grant covering the assignment's project (`visible_project_ids` /
   `_assert_project_authority`, i.e. `evidence.create` for the real target);
3. an ACTIVE, unexpired assignment belonging to the calling principal, plus an OPEN session
   when the capture names one.

Consequences that are now covered by tests:

* An assignment grants nothing. Role without assignment → 403; assignment without covering
  scope → 404 at the scope gate, **with no row written**.
* A stored assignment snapshot confers nothing: authority is resolved at synchronization time.
* Denials map to the existing `enforce()` vocabulary (401/403/404) and never mutate domain
  state (design rule R2).
* Owner-scoped surfaces (`/work`, `/sync`, `/captures/{id}`, session close) refuse the
  anonymous development bypass with 401, because they bind rows to an identified officer.
* Role matrix verified in `AUTH_MODE=enforcing`: `FIELD_OFFICER` synchronizes;
  `REVIEWER`/`SUPERVISOR`/`CITIZEN` are 403 with zero rows; `ADMINISTRATOR` manages but cannot
  synchronize; `SUPERVISOR` gains no new management permission (Stage B recommendation,
  ratified); API clients need explicit scopes and still have no assignment, so they are
  refused; unauthenticated is 401.

No existing permission was weakened and no hidden bypass was added.

## 4. Reuse instead of new machinery

`POST /field/sync` calls the existing `ingest_evidence(data, filename, declared_type, db)`, so
the one validator, the quarantine bucket, the SHA-256 writer and the audit twin are shared:

* 400/413/415 propagate unchanged from that validator;
* a bounded read of `max_upload_size + 1` bytes happens at the endpoint, exactly like
  `POST /evidence`;
* BE-026 stores its own `payload_sha256` from the existing `sha256_digest`, and the integration
  test proves `Evidence.sha256 == process_evidence(...).sha256 == operation.payload_sha256`,
  i.e. no second SHA-256 implementation was introduced;
* project/claim association and the PostGIS `location` (SRID 4326, `POINT(-6.2603 53.3498)`
  verified through `ST_AsText`/`ST_SRID`) are written in the same transaction as finalization;
* conflict resolution ingests nothing and changes no Evidence row.

## 5. Idempotency and conflicts

Key = (officer, `client_operation_id`). `request_hash` = `compute_request_hash` over the
canonical metadata dict ∪ `payload_sha256`, with blank values normalized and UUIDs canonicalised
so an equivalent submission cannot hash differently.

* exact retry → replay of the stored outcome, `already_synchronized`, one Evidence row,
  `sync_count` incremented, `FIELD_SYNC_DUPLICATE` appended;
* same identity, different content → 409 `conflict`/`PAYLOAD_MISMATCH`, the stored row is
  **untouched** (proved by re-reading it byte-for-byte after the attempt) and the existing
  Evidence is not re-ingested;
* superseded context → durable `CONFLICT` row with one of the seven CHECK-constrained reasons
  (`ASSIGNMENT_REVOKED`, `ASSIGNMENT_EXPIRED`, `SESSION_CLOSED`, `OPERATION_SESSION_MISMATCH`,
  `CONTEXT_RESOURCE_MISSING`, `ASSIGNMENT_SUPERSEDED`, plus `PAYLOAD_MISMATCH` in the ledger);
* invalid client metadata → durable `VALIDATION_FAILED` row with the reject labels and
  `timestamp_flags`, replayed exactly;
* five concurrent first submissions of one identity → exactly one 201, one row, one Evidence;
* an abandoned `PENDING` reservation (older than `STALE_PENDING_SECONDS = 900`) is adopted by
  the retry and lands exactly once;
* a dependency failure or a structural validator rejection deletes the reservation, so the
  identity stays retryable.

Resolution (`POST /field/operations/{id}/resolve`) is a human annotation on a terminal record:
`RESOLVED`, actor, time, note — and the conflict fields are **not** cleared. A second
resolution is 409.

## 6. Defects found and fixed in Stage C

All four were found by running code, and all four are recorded in the order they appeared.

### DEF-C-01 — production crash on a foreign-assignment denial — FIXED, VERIFIED
**FOUND:** `_resolve_sync_context` called `_deny(..., session_id=req.session_id)`, a keyword
`_deny` does not accept, so the `FOREIGN_ASSIGNMENT` path would have raised `TypeError`
(→ 500) instead of answering 404. **FIXED:** removed the unsupported keyword; `_deny`'s payload
already carries the session id. Verified with an AST check across the whole service (0
signature mismatches).
**VERIFIED — and this claim was corrected, not inflated.** The first VERIFIED note pointed at
`test_retry_after_timeout_recovers_the_stored_outcome`, but that test only exercises the normal
foreign-owner lookup, so it did **not** reach the crashing branch; the branch is not reachable
through the public API at all. The verification was therefore strengthened with
`test_sync_against_a_mismatched_session_is_denied_not_crashed`: a session row owned by the caller
but pointing at a colleague's assignment is written with a raw `INSERT INTO field_sessions`, the
caller syncs against it, and the runtime answer is 404 `authorization_denied` / `"Not found"` with
zero operation rows and zero Evidence, plus `FIELD_SYNC_REJECTED.payload.failure ==
"FOREIGN_ASSIGNMENT"` recording `session_id` **and** `assignment_id`, and a
`FIELD_ASSIGNMENT_SECURITY_FAILURE` against the victim's assignment. The denial path itself was
also widened to record `assignment_id`/`project_id` so the security event is forensically useful.

### DEF-C-02 — every field endpoint was broken — FIXED, VERIFIED
**FOUND:** `_call(db, action, *args, **kwargs)` invoked `action(*args, **kwargs)`, dropping the
session: `TypeError: work_feed() missing 1 required positional argument: 'db'`. All 39
integration tests failed at once — a single production defect, not 39 defects (diagnosed with
`--tb=line` on one test rather than by assumption). **FIXED:** `_call` now passes `db` through. **VERIFIED:** 39/39 at 60.55 s, then 40/40, and the
current file passes **41/41 in 65.17 s** — every later test in this stage ran on the fixed path, so
the verification has kept re-passing rather than being quoted once.

### DEF-C-03 — CHECK constraint blocked the existing retention purge — FIXED, VERIFIED
**FOUND:** during test teardown, `DELETE FROM evidence …` raised
`psycopg2.errors.CheckViolation: … ck_field_operations_accepted_has_evidence` with the
context `UPDATE ONLY "public"."field_capture_operations" SET evidence_id = NULL`. The cause is
in my own new schema: Stage B §3.3 specified both `evidence_id … ON DELETE SET NULL` and that
CHECK. `backend/services/retention.py:1175-1176` purges Evidence exactly through that FK, so
**production retention would fail for every field-synced capture**, and any later UPDATE of the
operation row (a replay bumping `sync_count`) would fail too.
**CLASSIFICATION:** production defect introduced by BE-026, latent against BE-024 retention.
**FIXED:** the CHECK was removed from `models.py` and from the (unmerged) BE-026 revision. It
cannot be repaired in place: a CHECK cannot express "the evidence existed when I accepted it",
and `DEFERRABLE` does not help because the violation is permanent, not transient. The invariant
is service-level: `_execute` writes `status='ACCEPTED'` and `evidence_id` in one statement.
Both `models.py` and the revision now carry the reason as a comment, and Stage B §3.3 carries a
non-destructive amendment note rather than a rewritten history.
**VERIFIED:** `test_retention_purge_of_a_field_capture_leaves_the_operation_readable` replays
retention's exact two deletes against real Postgres, then proves the operation row survives
(`ACCEPTED`, `evidence_id IS NULL`, identity intact) and is still updatable. Migration
round-trip re-run clean.

### DEF-C-04 — validator rejections wrote a row the design forbids — FIXED, VERIFIED
**FOUND:** `_execute` turned a `400/413/415` from the reused validator into a durable
`VALIDATION_FAILED` row labelled `FILE_REJECTED_BY_INGESTION_VALIDATOR`. The design's own §6
table says that case is "none (rollback)", and reading `ingest_evidence` shows the validator
raises *before* it stores or commits, so the comment justifying the row ("ingestion commits its
own work") was false. The divergence was observable: the first attempt answered 413 and the
replay answered the stored 422.
**FIXED:** the reservation is dropped instead (the same path as `temporarily_unavailable`), the
invented label is gone, and `_finalize_rejected` was deleted rather than left dead.
**VERIFIED:** `test_existing_ingestion_validator_decides_rejections` asserts 415 and 413
propagate, no Evidence and **no operation row** remain, the retry answers 413 again, and the
same `client_operation_id` can later land 201 once the file is valid.

### Test-authoring defects (same discipline, no production impact)
* five unit failures came from a helper that recomputed `datetime.now()` per call, so two
  "identical" submissions were not identical → fixed with a module-level `BASE`;
* `.isoformat()` vs `strftime(…Z)` microsecond mismatch;
* integration teardown deleted projects before claims/activities (RESTRICT FKs) → FK-safe
  order restored;
* `new_assignment` relied on the anonymous bypass inside an `AUTH_MODE=enforcing` block → now
  authenticates as the manager;
* a global `count(Evidence)` / unfiltered admin `total` assumed a pristine database → scoped to
  the scenario's project;
* a PAYLOAD_MISMATCH test read `json()["detail"]` although decided outcomes return the
  `FieldSyncResponse` body itself;
* one test asserted a state the API cannot produce (opening a session on an already-expired
  assignment 409s) → split into `ASSIGNMENT_EXPIRED` (expire after opening) and `SESSION_CLOSED`.

No assertion was weakened to make a test pass, and no existing test was edited (BE-026 changes
no BE-025 assertion; the only historical finding this stage touches is listed in §8).

## 7. Audit obligations

Thirteen additive event types (`FIELD_ASSIGNMENT_*`, `FIELD_SESSION_*`, `FIELD_SYNC_*`,
`FIELD_EVIDENCE_ASSOCIATED`). Payloads carry ids, hashes, statuses and reasons only. The
integration suite serializes every field event produced by a full scenario and fails on
`JFIF`, `data:image`, `Bearer`, `dev-user-`, `dev-client-`, `presigned`, `password`, `secret`
or a storage key, then re-runs `verify_chain()` and requires `valid is True`.

Runtime state on `pofa_test` after these runs: **chain valid**, all thirteen event types
present. The BE-023 append-only guard (`tests/audit_guard.py`, exercised by
`tests/unit/test_audit_guard.py` over the live test tree) stays green: no UPDATE, DELETE or
TRUNCATE path against `audit_ledger_events` was added, including in the new teardown code.

**Ratified deviation (Stage B §10, flagged for your approval and now implemented as proposed):**
`FIELD_ASSIGNMENT_ACCESSED` is appended when access turns into authority (session open) and on
administrative cross-user reads, **not** for an officer's own `GET /field/work` poll. Offline
clients poll by design; logging each poll would grow the append-only ledger unboundedly and
dilute its security signal. Polls remain covered by the structured request log and metrics.

## 8. Carried findings and observations

* **OBS-C-01** — `ingest_evidence` commits the Evidence row before BE-026 associates
  project/claim/location. A crash in that window can leave an unassociated Evidence row while
  the operation stays `PENDING`; the adopted-retry path re-ingests rather than repairing the
  orphan. Same non-atomicity already recorded for `POST /evidence`; no new mitigation added.
* **SR-01 / SR-12** remain findings from Stage A, untouched by this stage. SR-12 is the reason
  `POST /field/sync` refuses any multipart field outside its declared vocabulary with 422
  `UNEXPECTED_FIELD_*` — an unexpected scope-bearing field is a refusal, never an ignore.
* **Ambiguous ACTIVE assignments** with no session → 422 `AMBIGUOUS_ACTIVE_ASSIGNMENT` and no
  row (a denial must not write), per Stage B.
* **`CONTEXT_RESOURCE_MISSING`** is defensive: with no claim/activity delete endpoints and
  RESTRICT FKs it is unreachable through the API, so the test stubs only the existence lookup
  while the durable CONFLICT row, the audit event and the vocabulary still run against real
  Postgres. Recorded rather than papered over.
* **Known environment issue preserved, not fixed:** the shared long-lived `pofa_test` database
  has accumulated 94 organizations and 912 projects from historical runs. `test_be025_admin_
  control_plane.py` asserts that a newly created organization appears in the *first page* of
  `GET /api/v1/auth/organizations` (default `limit=50`), so it fails on that polluted database
  regardless of BE-026. Classified **pre-existing test-data sensitivity (environment)**: BE-026
  does not touch organizations or that endpoint, and the same file passes 16/16 on a clean
  schema with BE-026 code present. The test was **not** edited. See §9.
* Physical dependency-fault injection (Redis/MinIO/Postgres outage) and the `503` replay path
  are Stage E work; nothing here fakes an unavailable dependency.
* **OBS-C-02** — `alembic downgrade base` fails on a *populated* database inside the historical
  BE-003 revision (`c6e8a9d4b001_be003_evidence_upload_fields.py:42`, `SET NOT NULL` on
  `evidence.project_id`) whenever other suites have left NULL-project Evidence rows behind.
  Classified **pre-existing / not BE-026**, with the runtime isolation recorded in §9 step (4); the
  revision was **not** modified, because task §19 forbids historical migration modification.

## 9. Verification evidence (exact commands)

```
# targeted unit + integration for BE-026
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test PYTHONPATH=$PWD \
  backend/.venv312_clean/Scripts/python.exe -m pytest \
  tests/unit/test_field_operations.py tests/integration/test_be026_field_operations.py -q -p no:cacheprovider
```

* `tests/unit/test_field_operations.py` → **52 passed** in 5.49 s.
* Both files in the single command above → **93 passed** in 69.76 s (52 unit + 41 integration).
* `tests/integration/test_be026_field_operations.py` → **39 passed** in 60.55 s (before the
  DEF-C-03 regression test was added), **40 tests** collected after it.
* Same file after the DEF-C-01 runtime-proof test and the strengthened `FOREIGN_ASSIGNMENT`
  denial were added → **41 passed** in 65.17 s on `pofa_test` (the last number is the current
  count; the earlier runs are kept as history).
* Full `tests/unit` → **400 passed, 1 skipped** in 18.13 s (skip = ML stack present).
* Regression batch 1 on `pofa_test` (`test_be026_field_operations`, `test_be025_admin_control_plane`,
  `test_authorization`, `test_evidence_upload`, `test_audit_ledger`) → 92 passed, 1 failed; the
  failure is the environment finding in §8 (94 orgs > the 50-item page), reproduced only on the
  polluted database.
* Same batch on a **clean from-scratch schema**: `test_be025_admin_control_plane.py` → **16
  passed** in 25.81 s, proving no BE-025 regression.
* Audit chain on `pofa_test`, in its **final Stage C state** after every run above →
  `verify_chain()` = `{checked_events: 21284, failures: 0, first_sequence: 1,
  last_sequence: 21284, valid: True}`; sequences are contiguous with no gap, so nothing was
  appended out of order and nothing was removed. All 13 field event types are present
  (`FIELD_ASSIGNMENT_ACCESSED` 370, `FIELD_ASSIGNMENT_CREATED` 419, `FIELD_ASSIGNMENT_EXPIRED` 18,
  `FIELD_ASSIGNMENT_SECURITY_FAILURE` 47, `FIELD_ASSIGNMENT_STATUS_CHANGED` 57,
  `FIELD_EVIDENCE_ASSOCIATED` 146, `FIELD_SESSION_CLOSED` 27, `FIELD_SESSION_OPENED` 290,
  `FIELD_SYNC_ACCEPTED` 146, `FIELD_SYNC_CONFLICT` 90, `FIELD_SYNC_CONFLICT_RESOLVED` 9,
  `FIELD_SYNC_DUPLICATE` 51, `FIELD_SYNC_REJECTED` 74). An intermediate reading after the 41-test
  run alone was 20 934 events, also valid and contiguous.
* BE-023 safety suite on `pofa_test` → `tests/unit/test_audit_guard.py` +
  `tests/unit/test_preflight.py` = **43 passed, 1 skipped** in 1.11 s.
* Full-suite run (`tests/integration` + `tests/unit`): see §10.

Migration evidence, with `DATABASE_URL` published for the standalone CLI (per project memory,
`TEST_DATABASE_URL` alone would have written to `pofa_dev`):

```
# existing database already at head: reversible round-trip
DATABASE_URL=…pofa_test      alembic current            → p6q7r8s9t026 (head)
DATABASE_URL=…pofa_test      alembic downgrade -1       → o5p6q7r8s025
DATABASE_URL=…pofa_test      alembic upgrade +1         → p6q7r8s9t026

# (1) from-scratch upgrade on an empty database
DATABASE_URL=…pofa_be026_scratch  alembic upgrade head  → p6q7r8s9t026 in 5.03 s, single head

# (2) BE-026 revision round-trip against a POPULATED database
#     (the database holding the full-suite data: 2 261 audit events, 50 evidence rows)
DATABASE_URL=…pofa_be026_scratch  alembic downgrade -1  → o5p6q7r8s025
DATABASE_URL=…pofa_be026_scratch  alembic upgrade +1    → p6q7r8s9t026 (head)

# (3) entire linear chain down to base on an empty database
DATABASE_URL=…pofa_be026_scratch2 alembic upgrade head  → head in 5.60 s
DATABASE_URL=…pofa_be026_scratch2 alembic downgrade base → base in 3.12 s;
      public tables left: ['alembic_version', 'spatial_ref_sys']
      (spatial_ref_sys belongs to the postgis extension, which no revision drops)

# (4) same downgrade base against a populated database → FAILS inside a historical revision
DATABASE_URL=…pofa_be026_scratch  alembic downgrade base
  psycopg2.errors.NotNullViolation: column "project_id" of relation "evidence"
  contains null values — [SQL: ALTER TABLE evidence ALTER COLUMN project_id SET NOT NULL]
  raised by c6e8a9d4b001_be003_evidence_upload_fields.py:42; alembic stayed at
  p6q7r8s9t026 (transactional DDL rolled the whole chain back, no partial schema).
```

Finding **OBS-C-02** from step (4), classified **pre-existing, not BE-026**: the BE-003-era
revision relaxes `evidence.project_id` to nullable on upgrade and restores `NOT NULL` on
downgrade, so `downgrade base` is only executable against a database whose Evidence rows all carry
a project. The 32 NULL-project rows on that database belong to other suites (`be021-*` retention /
dispute fixtures, `citizen-fix.jpg`, `renamed.jpg`); **0** of them are referenced by
`field_capture_operations`, and BE-026 never writes a NULL `evidence.project_id`. §19 forbids
historical migration modification, so the revision was left exactly as found — verified with `git
diff --stat -- alembic/` → empty, and `git ls-files --others alembic/` listing only the new BE-026
file. Task §19 asks for "downgrade verified **where applicable**": the BE-026 revision itself
reverses cleanly both empty and populated (steps 1–3), and full-chain reversal is proven on an
empty database (step 3).

`field_capture_operations` on `pofa_test`, read from `pg_constraint` after the round-trip rather
than inferred from the model file, holds 26 constraints — 17 `ck_*`, 7 foreign keys, the primary
key and the composite unique key — and **no** `accepted_has_evidence` CHECK (the DEF-C-03 fix is
live in the schema, not only in the Python model).

OpenAPI: re-checked after every Stage C fix — `app.openapi() == json.load(open("openapi.json"))`
→ **True**, with exactly 10 `/api/v1/field` paths carrying 11 operations
(`GET|POST /assignments`, `PATCH /assignments/{id}/status`, `GET /assignments/{id}`,
`GET /captures/{client_operation_id}`, `GET /operations`, `POST /operations/{id}/resolve`,
`POST /sessions`, `POST /sessions/{id}/close`, `POST /sync`, `GET /work`), no removed path and no
non-field schema change anywhere in the document.

The regeneration was also diffed **structurally** against `HEAD:openapi.json` rather than trusted
on line counts (`git diff --numstat` shows 4 403 / 2 181 only because new paths and schemas shift
the emission order): paths removed → none; 10 paths added; per-path method sets and every existing
operation object byte-equal to before; `components.schemas` removed → none; existing schemas
changed → none; 25 field schemas added; `openapi`, `info` and `tags` identical. The change is
additive, which is what §1 claims.

## 10. Full-suite run on a clean database

```
# pofa_be026_scratch = empty database, alembic upgrade head, then the whole suite
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_be026_scratch \
  PYTHONPATH=$PWD backend/.venv312_clean/Scripts/python.exe -m pytest \
  tests/integration tests/unit -q -p no:cacheprovider
```

→ **657 passed, 1 skipped, 9 warnings in 335.11 s (0:05:35)**, `EXIT=0`.
The single skip is `tests/unit/test_preflight.py:117` ("ML stack genuinely installed in this
environment"), which is the expected BE-023 preflight outcome, not a failure. Zero failures, zero
errors, zero unexplained skips.

Count history for this file, kept rather than overwritten: the first full clean-database run was
**656 passed, 1 skipped in 330.58 s** (40 BE-026 integration tests); the +1 is the DEF-C-01
runtime-proof test added afterwards, hence 657.

Post-run state of that database (read, not assumed): `verify_chain()` → `valid=True`,
`checked_events=2261`, `failures=[]`, sequences `1..2261` contiguous, 13 `FIELD_*` event types.
No `503`/`temporarily_unavailable` replay path and no physical dependency fault was injected in
Stage C — that is Stage E scope (§8), so nothing here fakes an unavailable dependency.

**Scratch-database cleanup:** `pofa_be026_scratch` and `pofa_be026_scratch2` (both created by me
for this stage) were dropped after the evidence above was captured. Remaining databases on the
local cluster: `pofa_dev`, `pofa_test`, `pofa_audit_verify` (the last belongs to earlier-stage
work and was not touched).

**`pofa_dev` contamination check (task §24):** `pofa_dev` is still at
`version_num = n4o5p6q7r022` and `pg_tables` contains **no** `field%` tables at all, so neither the
BE-026 migration nor any BE-026 row ever landed there. Every manual CLI invocation in this stage
exported `DATABASE_URL` explicitly for exactly that reason.

## 11. Git state

Nothing has been committed. `git status --porcelain` reads exactly:

```
 M backend/api/v1/router.py
 M backend/db/models.py
 M backend/services/authorization.py
 M openapi.json
 M tests/unit/test_migrations.py
?? alembic/versions/p6q7r8s9t026_be026_field_operations.py
?? backend/api/v1/endpoints/field.py
?? backend/repositories/field_operations.py
?? backend/schemas/field_operations.py
?? backend/services/field_operations.py
?? docs/BE-026 Stage A Reconnaissance.md
?? docs/BE-026 Stage B Design.md
?? docs/BE-026 Stage C Implementation Summary.md
?? docs/Production Task Files/BE-026 — Field Operations & Offline Evidence Capture Backend.md
?? tests/integration/test_be026_field_operations.py
?? tests/unit/test_field_operations.py
```

No venv, cache, log, scratch database dump or temporary script is in scope; `git diff --stat --
alembic/` is empty, proving the migration chain gained a revision rather than being edited.
`backend/db/models.py` is **+371 / −0** (purely additive: three models, six vocabularies, thirteen
audit event types, one permission grant set).

The proposed commit stages all sixteen reported paths by name (never `git add .` / `git add -A`).
The BE-026 task file is included because every earlier task file is tracked in this repository —
`git ls-files docs/Production Task Files/` lists BE-020 … BE-025, and `git ls-files docs/` shows
BE-025 carrying all six stage documents, which is the §25 precedent BE-026 is following.

No push and no destructive Git operation has been performed; nothing has been committed.

## 12. Stage C gate

**PASS with recorded findings.** Every Stage C obligation is implemented and runtime-verified:
four production defects found and fixed with FOUND → FIXED → VERIFIED history, two pre-existing
findings classified (§8 polluted-database test sensitivity, OBS-C-02 historical downgrade limit)
without weakening any test or touching any historical revision, and the BE-023 append-only guard
still green.

Gate-by-gate against task §24: no unexplained failures (657 passed / 1 explained skip, §10); no
authorization regression (BE-025 16/16 clean, §9); no duplicate evidence (idempotency + conflict
tests, §5); no audit corruption (`verify_chain()` valid on both databases, §9/§10); no migration
drift (single head, round-trips, from-scratch, §9); no `pofa_dev` contamination (§10).

**STOP.** Stage D (runtime verification against the task §22 matrix) waits for your approval, as
does the commit described in §11 — nothing has been staged, committed or pushed.
