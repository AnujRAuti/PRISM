# BE-026 Stage D — Runtime Verification Results

Milestone: BE-026 Field Operations & Offline Evidence Capture Backend
Branch: `Backend` · Baseline commit: `29d12eb8` (BE-025 accepted)
Stage gate: task file §22 (Stage D — Runtime verification)

---

## 1. What this gate required, and how it was satisfied

§22 forbids substitutes: verification must run against real PostgreSQL, PostGIS,
pgvector, Redis, MinIO and Python 3.12, must use real HTTP, and must not claim
end-to-end success on the strength of unit tests. It names one path that has to
be walked as a single connected run:

```
Assigned Activity → Field Session → Offline Capture Representation
→ Synchronization → Evidence Ingestion → Evidence Association
→ Provenance → Audit
```

Four evidence tracks were run. All of them hit the same `pofa_test` database;
no track fell back to `pofa_dev`.

| Track | Method | Result |
|---|---|---|
| Environment preflight | Standalone script; measured server versions, extensions, Alembic head, BE-026 schema, permission grants, Redis ping, MinIO buckets, audit chain | PASS |
| Targeted + affected suites | `pytest` over real HTTP (`TestClient`) against `pofa_test`, three batches | 352 passed, 1 skipped, 1 pre-existing environment failure (§7) |
| Live-socket end-to-end probe | Standalone script driving a **running uvicorn** process over TCP (`requests`, no `TestClient`), 136 assertions across 14 sections | 136/136 PASS, 16.0 s |
| Enforcing-mode probe | Same script against a second server started with `AUTH_MODE=enforcing`, 18 assertions | 18/18 PASS, 8.4 s |

No production file, test or assertion was changed during Stage D. `git status`
at the end of this stage is byte-for-byte the Stage C change set (§10). Every
defect found here was in the Stage D harness itself, and each one is recorded
FOUND → FIXED in §8 rather than quietly re-rolled.

---

## 2. Environment (measured, not assumed)

```
$ DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test \
  PYTHONPATH=D:/CODING/Projects/Proof-Of-Action-Final \
  backend/.venv312_clean/Scripts/python.exe "$TEMP/poa_stageD_be026/preflight.py"

url_host       localhost:5432/pofa_test
current_db     pofa_test
postgres       PostgreSQL 15.13 (Debian 15.13-1.pgdg120+1)
postgis        POSTGIS="3.4.2 c19ce56" [EXTENSION] PGSQL="150" GEOS="3.11.1-CAPI-1.17.1"
               PROJ="9.1.1" LIBXML="2.9.14" LIBJSON="0.16" LIBPROTOBUF="1.4.1" WAGYU="0.5.0"
pgvector       0.7.4
alembic        ['p6q7r8s9t026']
field_tables   ['field_assignments', 'field_capture_operations', 'field_sessions']
  rows field_assignments            0
  rows field_capture_operations     0
  rows field_sessions               0
constraints    26 CHECK: 17
permissions    ['field_assignment.manage', 'field.sync']
granted_to     [('ADMINISTRATOR', 'field_assignment.manage'),
                ('FIELD_OFFICER', 'field.sync')]
auth_mode      development
db_in_settings localhost:5432/pofa_test
redis          True
buckets        ['pofa-evidence', 'pofa-quarantine']
exists         evidence: True quarantine: True
endpoints      http://localhost:9000 pofa-evidence pofa-quarantine
chain          {'checked_events': 22462, 'first_sequence': 1,
                'last_sequence': 22462, 'valid': True} failures: 0
```

```
$ backend/.venv312_clean/Scripts/python.exe -V
Python 3.12.0

$ docker ps
pofa_db     Up   (postgres-postgis-pgvector, :5432)
pofa_redis  Up   (:6379)
pofa_minio  Up   (:9000)
```

Two things in that block are load-bearing and were confirmed rather than
assumed:

* `current_db pofa_test` **and** `db_in_settings localhost:5432/pofa_test` —
  the process actually connected to the test database, and `settings` agrees,
  so the standalone tracks could not have been writing to `pofa_dev`.
* `alembic ['p6q7r8s9t026']` is a single head, and the three BE-026 tables exist
  with 26 constraints (17 `CHECK`), which is the schema Stage C shipped.

**Environment incident, recorded in order.** The first preflight attempt of this
session failed with `psycopg2.OperationalError: Connection refused`. Root cause
was not the code: the Docker Desktop daemon was down
(`com.docker.service` = Stopped), so `pofa_db` was unreachable. Starting Docker
Desktop restored `pofa_db`/`pofa_redis`/`pofa_minio`, and the identical command
then produced the block above. This is the reason §2 measures the environment
before anything else is trusted.

---

## 3. Commands executed (verbatim, reproducible)

```bash
REPO=D:/CODING/Projects/Proof-Of-Action-Final
PY=$REPO/backend/.venv312_clean/Scripts/python.exe
export PYTHONPATH=$REPO

# --- environment preflight (measured, §2) ---
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test \
  $PY "$TEMP/poa_stageD_be026/preflight.py"

# --- targeted + affected regression, three batches (TEST_DATABASE_URL) ---
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test \
  $PY -m pytest <batch files> -q -p no:randomly -p no:cacheprovider

# --- live-socket probe: development pass ---
DATABASE_URL=.../pofa_test $PY -m uvicorn backend.app.main:app \
  --host 127.0.0.1 --port 8018 --log-level info &
DATABASE_URL=.../pofa_test BASE_URL=http://127.0.0.1:8018 \
  AUTH_MODE_PASS=development LABEL=sdA8 \
  $PY "$TEMP/poa_stageD_be026/probe.py"

# --- live-socket probe: enforcing pass (second server, real AUTH_MODE) ---
AUTH_MODE=enforcing DATABASE_URL=.../pofa_test $PY -m uvicorn backend.app.main:app \
  --host 127.0.0.1 --port 8019 --log-level info &
DATABASE_URL=.../pofa_test BASE_URL=http://127.0.0.1:8019 \
  AUTH_MODE_PASS=enforcing LABEL=sdE1 \
  $PY "$TEMP/poa_stageD_be026/probe.py"
```

The probe talks to the server over a TCP socket with `requests`. Nothing in it
uses `TestClient`, imports an endpoint function, or monkeypatches authorization.
It reads the database back after each HTTP step, so a 200 response is never on
its own evidence that anything happened.

---

## 4. Targeted BE-026 suite (real HTTP, isolated test database)

```
tests/unit/test_field_operations.py               37 passed
tests/integration/test_be026_field_operations.py  41 passed
batch 2 (with the ingestion tracks it pulled in):
  125 passed, 7 warnings in 194.47s
```

Batch 2's files: `tests/unit/test_field_operations.py`,
`tests/integration/test_be026_field_operations.py`,
`tests/integration/test_evidence_upload.py`, `tests/integration/test_storage.py`,
`tests/integration/test_fingerprinting.py`,
`tests/integration/test_analysis_jobs.py` — 125 passed, 0 failed, 0 skipped.

Those six files are the point of the batch: BE-026 does not own ingestion,
storage, hashing, fingerprinting or the analysis queue, so its own green result
means nothing unless the tracks it *reuses* also stay green behind it.

---

## 5. Live-socket end-to-end probe — development pass, 136 checks, 0 failures

```
pass=development label=sdA8 base=http://127.0.0.1:8018 db=pofa_test
checks=136 passed=136 failed=0 duration=16.0s
teardown_remaining={"field_assignments": 0, "field_sessions": 0,
 "field_capture_operations": 0, "probe_evidence": 0, "probe_users": 0,
 "probe_orgs": 0, "probe_projects": 0}
GATE: PASS
```

The single run walks the §22 path in order, then attacks it. Each row below is
one section of one connected session — the capture in section D is the one whose
assignment came from section A, in the session opened in section C.

| § | Section | Task ref | Checks | What was proven at runtime |
|---|---|---|---|---|
| F0 | Chain before | §22 | 1 | `verify_chain` valid at start, so the after-state is comparable |
| A | Assignment creation | §20 Assignment | 11 | Admin creates 201; organization/unit **derived server-side** from the project, never accepted from the client; claim + activity bound on the row; officer 403, supervisor 403, cross-project claim 422 |
| B | Work feed + permission-without-authority | §20 Assignment | 14 | Officer sees exactly own assignment with nested claim/activity/project; reviewer, supervisor, citizen all 403; `field.sync` API client with no assignment gets an **empty** feed (200, `total: 0`), a narrow client gets 403; anonymous denied; a *different* officer with `field.sync` and no assignment is refused 403 `authorization_denied`, writes **no operation row**, and the refusal is audited |
| C | Field session | §20 Offline capture | 4 | Open 201 `ACTIVE` with `server_time_at_open`; non-owner refused; one active session per device/assignment |
| D | Sync → ingestion → PostGIS → storage | §22 core | 20 | 201 `accepted`; response attributes `project_id`/`claim_id` server-side; Evidence row created with status `uploaded_quarantine` and a storage key; ledger `payload_sha256` **equals** `sha256(bytes fetched back out of MinIO)`; `file_size` equals the fetched length; client `captured_at`/`queued_at`/`uploaded_at` stored verbatim while `received_at`/`processed_at` are recorded separately and differently; an unreported `uploaded_at` stays NULL (never derived); `timestamp_flags` stored as a list; lat/lon stored as reported and readable through PostGIS (`ST_X`/`ST_Y`, `ST_SRID=4326`, `ST_AsEWKT` → `SRID=4326;POINT(...)`); operation inherits its Activity through the assignment (`field_assignments.activity_id`), never restated by the client |
| E | Existing analysis pipeline | §22 Evidence | 8 | `POST /analysis/jobs` 202 `queued`; the message is **dequeued from live Redis** (`brpoplpush`) with the matching `job_id`; the real `process_evidence` recomputes the same SHA-256 the ledger holds and writes `phash` + one `evidence_metadata` row; `acknowledge()` removes the message from the processing list; the job is still `queued` in the DB, stated deliberately (§6) |
| F | Provenance read-back | §22 Provenance | 5 | `GET /field/captures/{client_operation_id}` 200 carrying identity, all five timestamps, device id and location; no storage internals, no bytes, no tokens; a foreign officer's read is 404, not 403-with-content |
| G | Exact duplicate | §20 Synchronization | 7 | Byte-identical replay answers 200 `already_synchronized`; exactly one Evidence row and one operation row; `sync_count` ≥ 2; the storage key is unchanged |
| H | Same identity, different payload | §20 Conflict | 5 | 409 `conflict` / `PAYLOAD_MISMATCH`; the original digest is **not** overwritten; the original evidence survives with `resolution_status` untouched; `FIELD_SYNC_CONFLICT` audited with the reason |
| I | Missing GPS | §20 Offline capture | 4 | Capture accepted, `evidence.location IS NULL` (never 0,0), provenance reports `location.reported: false`, latitude/longitude NULL as a pair |
| J | Malformed captures | §20 Offline capture | 9 | PNG-under-JPEG-content-type 415; oversized 413 with no Evidence **and no operation row**; out-of-range coordinates 422; too-short `client_operation_id` 422 `validation_failed`; an unexpected `project_id` form field is refused as `UNEXPECTED_FIELD_PROJECT_ID` rather than ignored; missing file refused; unconfirmed zero-island refused |
| K | Assignment revoked while offline | §20 Conflict | 5 | Revoke 200 and audited; the queued-then-revoked capture yields a durable `CONFLICT` row with `conflict_reason=ASSIGNMENT_REVOKED` and **no evidence**; the revocation is visible on the very next request (feed no longer contains the assignment) |
| L | Session close | §20 Synchronization | 4 | Close 200, session `CLOSED`; syncing against the closed session is an explicit outcome, not a crash; double close 409 |
| M | Conflict surfacing and resolution | §20 Conflict/Audit | 17 | Admin `?status=CONFLICT` lists the durable conflict with client identity + server state; the payload-mismatch replay is deliberately **absent** from that feed and still `ACCEPTED` (a decided outcome, not a new row — §6); officer 403 and supervisor 403 on resolve; admin resolve 200; resolution recorded (`RESOLVED`/`DISMISSED`/`resolved_by`) **without erasing** `conflict_reason` or the `CONFLICT` status; second resolve 409; the accepted evidence is untouched; officer listing 403; `limit=0`/`limit=1001` 422; malformed ids on the four real routes 422 / fail-closed; unknown operation resolve 404 writing nothing |
| N | Audit | §20 Audit | 17 | All ten expected `FIELD_*` event types present for this run's own resources with the right `resource_type`; actor is the authenticated officer; `project_id` attributed on the event; `FIELD_ASSIGNMENT_SECURITY_FAILURE` recorded for cross-principal attempts; chain valid **after** the run; chain append-only (`first_sequence` unchanged, `last_sequence` grown); a regex sweep over every `FIELD%` payload this run appended found no bytes, tokens, credentials or storage internals |
| Z | Teardown | hygiene | 1 | Every quarantine object the run wrote was deleted from MinIO and verified absent |

Notable runtime facts, established by measurement rather than by reading source:

* **The digest is the same value three different ways.** The ledger's
  `payload_sha256`, the SHA-256 of the bytes pulled back out of MinIO, and the
  digest the independent `process_evidence` fingerprinter computes from those
  bytes all match — so BE-026 is genuinely feeding the existing pipeline rather
  than writing a parallel one.
* **Authorization is decided per request.** `K4` needed no cache invalidation,
  no restart and no delay: revoking the assignment changed the next request's
  answer.
* **Permission is not authority.** `B5` and `B8` are the same fact from two
  sides — a `field.sync` API client is served an empty feed, and an officer who
  holds `field.sync` with no assignment is refused, audited, and leaves no row
  behind.
* **A refused capture writes nothing.** Every rejection path in section J
  asserts the absence of an operation row as well as the status code, which is
  the Stage C DEF-C-04 contract measured end to end.

---

## 6. Deliberate non-claims

Two places where a Stage D report could have inflated the result, and what was
stated instead:

* **The analysis job is not completed.** `pofa_test` runs no analysis worker, so
  the job created in section E is still `queued` at the end. An earlier draft of
  the probe wrote `status='completed'` and inserted an `analysis_results` row by
  hand. That was removed and replaced by `E3b`, which asserts the job is *still*
  queued. BE-026's §22 path ends at ingestion and association; inventing worker
  output would have been a fabricated result, and the hand-written `UPDATE` could
  not have worked anyway (`analysis_jobs` has `completed_at`, not `finished_at`).
* **A payload mismatch is not a conflict row.** The design replays the decided
  outcome against the original `ACCEPTED` operation and records the conflict in
  the ledger. The probe now pins that in both directions: `H2`/`H2b` show the
  original row is intact, and `M2c` shows the mismatch is absent from
  `?status=CONFLICT` while the revoked-assignment capture *is* there.

---

## 7. Regression tracks and the one failure

```
batch 1  1 failed, 93 passed, 8 warnings in 418.37s
batch 2  125 passed, 7 warnings in 194.47s
batch 3  134 passed, 1 skipped, 6 warnings in 96.68s
```

Batch 3 covers the planes BE-026 touches without editing: `test_authorization`
(unit + integration), `test_audit_ledger` (unit + integration), `test_retention`
(unit + integration), `test_migrations`, `test_audit_guard`, `test_preflight`,
`test_test_target`. Its one skip is `tests/unit/test_preflight.py:117`, the
expected "ML stack genuinely installed" skip.

**The single failure: classified pre-existing, not a BE-026 regression.**

```
FAILED tests/integration/test_be025_admin_control_plane.py::
       test_organization_lifecycle_noop_audit_and_isolation
tests\integration\test_be025_admin_control_plane.py:535
  listed = client.get("/api/v1/auth/organizations", headers=admin_headers)
  ids = [item["id"] for item in listed.json()["items"]]
> assert str(org.id) in ids
E  AssertionError: assert '8a917fbd-…' in ['2fa6e572-…', …]
```

Every BE-026-relevant and BE-025-relevant step inside that test passed — audit
event counts, before/after payloads, actor attribution, suspension making a
scoped grant inert, no-op suppression, reactivation. The failing line is BE-025's
own last assertion, and it fails for a measurable data reason:

```
organizations in pofa_test                     94
/api/v1/auth/organizations default limit       50   (auth.py:301)
ordering                                       name, id  (auth.py:306)
organizations sorting before "Renamed life"    94
```

The list is alphabetical, not newest-first, so with 94 rows present a newly
created organization named "Renamed life" cannot appear on the default 50-row
page. The assertion presumes a nearly-empty database. It was true when BE-025
passed its own gate; it became false as `pofa_test` accumulated organizations
across suites.

Classification: **pre-existing test-data sensitivity in BE-025's suite, exposed
by database state.** BE-026 creates no organizations, no `auth/organizations`
code path was touched (`backend/services/authorization.py` gained three lines of
permission vocabulary only), and the same file passed 16/16 during Stage C. The
BE-025 test was deliberately **not** edited: weakening another milestone's
assertion to clear a gate is not a fix, and the correct fix — paginating to find
the row, or ordering deterministically — belongs to BE-025's own scope. It is
carried forward as a Stage F item.

---

## 8. Harness defects found and fixed in Stage D

All were found by running the probe, all lived in the Stage D script outside the
repository, and **none of them changed production code**. They are listed in the
order they appeared because several were discovered by the previous one's crash.

| ID | FOUND | FIXED | VERIFIED |
|---|---|---|---|
| SD-01 | Probe created the fixture project as the ADMINISTRATOR → 403. Not a defect: `project.create` belongs to SUPERVISOR, and ADMINISTRATOR is deliberately not a superuser | Fixture created by a supervisor principal, still owned by the admin | 136/136 |
| SD-02 | Probe inserted `api_clients` with `client_id`/`is_active` columns that do not exist | Client created through `POST /api/v1/auth/clients` as the admin (holder of `api_client.manage`) with explicit scopes | 136/136 |
| SD-03 | Probe projected `activity_id` from `field_capture_operations`, which has no such column — activity binding lives on the assignment | Read `assignment_id` from the operation and `activity_id` from the assignment, and made `D6b` assert that inheritance explicitly | `D6b` passes |
| SD-04 | `op[19]` index shifted after SD-03, and `ev[7]` was `location` not `file_size` (`int()` blew up on EWKB hex) | Indices recomputed against the shipped projections | `D6`/`D11` pass |
| SD-05 | `D8b` expected `SRID=4326;POINT` from `ST_AsText`, which returns bare WKT in PostGIS 3 — the check could never pass even though the column was correct | Projected `ST_AsEWKT` and asserted against it, keeping `ST_SRID` in `D8` | `D8`+`D8b` pass |
| SD-06 | `E1`/`E7` read the job id from `id`; `AnalysisJobResponse` exposes `job_id`, so `job_id` was `None` and the Redis comparison could not match | Read `job_id` | `E3` matches the dequeued id |
| SD-07 | `E` section fabricated a completed analysis job and an `analysis_results` row (§6) | Fabrication deleted; replaced by `E3b` (still `queued`) and `E3c` (LREM really removed the message from the live processing list) | both pass |
| SD-08 | UUID-vs-string comparisons: the driver returns `UUID` objects for `activity_id`/`evidence_id`, so two visually identical ids compared unequal (`D6b`, `H2b`) | Compare stringified values, as the rest of the probe already did | both pass |
| SD-09 | `J3b` read `sync_status` at the top level; a structurally rejected sync is an HTTPException envelope, so it lives under `detail`, while a *decided outcome* is the response body itself | Read whichever shape arrived | `J3b` passes |
| SD-10 | `M2` expected the payload mismatch in the `status=CONFLICT` feed and `M2b` read a `payload_sha256` key the response model does not expose | Retargeted section M at the durable `ASSIGNMENT_REVOKED` conflict, added `M2c` for the non-claim, read the digest from the database | `M2`/`M2b`/`M2c` pass |
| SD-11 | `M12`/`M13` probed `GET /field/operations/{id}`, a route that does not exist, so both only measured the router's catch-all 404 | Replaced with malformed-id checks on the four routes that exist, measured live first: assignment GET, assignment-status PATCH, operation resolve POST (all 422) and session close (fails closed) | `M12a–d`, `M13` pass |
| SD-12 | `N1` looked up `FIELD_EVIDENCE_ASSOCIATED` under the operation id; the event is emitted against `resource_type='evidence'` with the evidence id | Keyed on the evidence id | all ten event types found |
| SD-13 | Leaked fixture rows and quarantine objects from crashed runs (teardown never reached) | Added a label-scoped, FK-safe cleaner that also deletes exactly the run's MinIO keys and verifies absence; probe teardown now removes storage too (`Z`) | final `teardown_remaining` all zero |
| SD-14 | `A5` expected 401/403 for an anonymous assignment create under `AUTH_MODE=development`, where the documented BE-016 bypass answers instead | Made mode-aware: development asserts the request clears authorization and hits the duplicate guard (409), enforcing asserts 401 (`P4b`) and that nothing was written (`P4c`) | both passes green |

No shipped assertion was weakened at any point, and no existing test file was
edited. After the first five crashes the probe's SQL was validated statically
against `information_schema` — 70 SQL literals, 0 unknown tables or qualified
columns — which is why the last six defects were findings rather than crashes.

---

## 9. Enforcing-mode pass — 18 checks, 0 failures

The second server was started with `AUTH_MODE=enforcing`, not with a flag
pretending to be it.

```
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8019/api/v1/field/work
401                                  # anonymous: served in development, refused here

pass=enforcing label=sdE1 base=http://127.0.0.1:8019 db=pofa_test
enforcing pass: health=200
checks=18 passed=18 failed=0 duration=8.4s
GATE: PASS
```

| Check | Task ref | Outcome |
|---|---|---|
| P1 anonymous `/work` and `/operations` | §20 unauthenticated | 401 ×2 |
| P2 anonymous sync | §20 unauthenticated | 401 |
| P3 forged `dev-user-<random uuid>` token | §14 / no bypass | 401 |
| P4 forged token cannot create an assignment | §14 | 401 |
| P4b/P4c anonymous assignment create | §14 | 401 **and** zero rows written |
| P5 real officer still reads the feed | §20 field officer | 200 |
| P6 real reviewer | §20 reviewer | 403 |
| P7/P8 real admin creates, non-admin denied | §20 administrator | 201 / 403 |
| P9–P10 enforced session + sync | §22 | 201 / 201 accepted |
| P11–P13 non-officer sync, citizen sync, officer listing | §20 | 403 / 403 / 403 |
| P14 audit chain after the enforcing pass | §20 Audit | `valid=True`, 0 failures |
| Z teardown quarantine objects | hygiene | removed and verified absent |

This is the track that shows the development-mode bypass in §5 is the documented
BE-016 contract and not a BE-026 backdoor: with the mode actually enforced, every
anonymous and forged call on the field surface is a 401, while the real
principals keep working and the chain stays valid.

---

## 10. Isolation, residue and repository state

Audit ledger rows from this stage were **never** deleted — they are the record of
the run. Everything disposable was removed:

* final `teardown_remaining` after each pass: field assignments 0, sessions 0,
  operations 0, probe evidence 0, probe users 0, probe orgs 0, probe projects 0;
* preflight at the end of the stage re-confirms `rows field_assignments 0`,
  `rows field_capture_operations 0`, `rows field_sessions 0` on `pofa_test`;
* chain after all Stage D work: `checked_events 22462`,
  `first_sequence 1`, `last_sequence 22462`, `valid True`, 0 failures —
  contiguous and append-only across the 1 178 events this stage appended
  (21 284 at Stage C close → 22 462);
* MinIO: each run's quarantine objects deleted by teardown `Z` and listed back to
  confirm absence; the two orphaned objects from the crashed early attempts were
  deleted explicitly and re-listed to 0.

Repository state at the end of Stage D is the Stage C change set, untouched:

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
?? tests/integration/test_be026_field_operations.py
?? tests/unit/test_field_operations.py
?? docs/BE-026 Stage A/B/C + task file (and this document)
```

The Stage D probe, preflight and cleaner live under
`%TEMP%/poa_stageD_be026/`, outside the repository, and nothing is staged,
committed or pushed.

---

## 11. §20 test-requirement coverage, at runtime

| Task §20 requirement | Runtime evidence |
|---|---|
| Assignment: authorized / unauthorized / cross-org / revoked / expired / pagination | I: `work_feed_exposes_only_the_callers_active_assignments`, `cross_organization_assignment_denial`, `assignment_release_and_revocation_are_terminal`, `assignment_expiration_is_lazy_server_set_and_audited`, `assignment_pagination_is_bounded_and_scoped` · probe A, B, K1–K4, P5–P8 |
| Offline capture: valid / malformed / missing GPS / valid GPS / missing timestamp / known timestamp preserved / multiple timestamps preserved | I: `first_sync_accepts_and_associates_through_the_existing_pipeline`, `missing_gps_is_captured_as_unlocated_not_as_zero_island`, `confirmed_zero_island_and_anomalous_ordering_are_stored_not_rewritten` · probe C, D1–D11a, I1–I4, J1–J6 |
| Synchronization: first / exact duplicate / retry after timeout / same id different payload / concurrent / partial failure / retry after failure | I: `exact_duplicate_sync_is_already_synchronized_with_one_evidence_row`, `retry_after_timeout_recovers_the_stored_outcome`, `concurrent_first_submissions_create_exactly_one_accepted_capture`, `abandoned_reservation_is_adopted_and_lands_exactly_once`, `same_operation_identity_with_different_payload_conflicts` · probe G1–G5, D1, L1–L3 |
| Evidence: existing pipeline reused / SHA-256 preserved / storage state / relationship / no duplicate | I: `existing_ingestion_validator_decides_rejections`, `operation_digest_equals_the_fingerprint_the_analysis_job_computes`, `retention_purge_of_a_field_capture_leaves_the_operation_readable` · probe D2–D11, E1–E7, M8 |
| Authorization: field officer / reviewer / supervisor / administrator / citizen / API client / unauthenticated | I: `role_matrix_in_enforcing_mode`, `api_client_requires_explicit_scopes_and_still_needs_an_assignment`, `assignment_is_not_authority_in_two_directions`, `suspended_officer_cannot_sync`, `owner_surfaces_refuse_the_development_bypass` · probe A3–A5, B4–B8, M3/M4/M9, §9 in full |
| Conflict: assignment revoked offline / activity state changed offline / duplicate client identity / payload mismatch / explicit conflict result | I: `assignment_revoked_while_offline_conflicts_explicitly`, `superseded_assignment_conflicts`, `missing_context_resource_is_explicit_never_silent`, `expired_assignment_conflicts_after_the_device_queued`, `closed_session_conflicts_for_captures_queued_before_closure`, `operation_identity_bound_to_another_session_conflicts`, `ambiguous_active_assignments_require_a_session_and_leave_no_row` · probe H1–H4, K2–K3, L2, M1–M8 |
| Audit: expected events / correct actor / correct resource / chain valid / no sensitive leakage | I: `field_audit_trail_is_complete_chained_and_secret_free`, `audit_ledger_records_denied_synchronizations_without_a_row` · probe N1–N7, P14 |

---

## 12. Carried forward

| Item | Status | Handled in |
|---|---|---|
| BE-025 `test_organization_lifecycle_noop_audit_and_isolation` first-page assertion vs 94 organizations | Open, pre-existing, classified §7 — not edited here | Stage F: fix in BE-025's own scope (paginate to the row or order deterministically) |
| Structured-log formatter raises `KeyError: 'request_id'` for log lines emitted outside a request context (visible on uvicorn startup, `backend/app/main.py:125`) | Open, pre-existing — `main.py` is not in the BE-026 change set; startup completes and the app serves | Not BE-026 scope; report-only observation |
| No analysis worker exists in this deployment, so `analysis_jobs` rows created over HTTP remain `queued` | By design for §22; stated as a non-claim in §6 | Stage E if worker behaviour is to be exercised |

---

## 13. Stage D gate decision

**Stage D: PASS with one pre-existing failure recorded and carried forward.**

* Environment measured, not assumed: PostgreSQL 15.13, PostGIS 3.4.2,
  pgvector 0.7.4, Redis, MinIO with both buckets, Python 3.12.0, single Alembic
  head `p6q7r8s9t026`, on `pofa_test`.
* The §22 path was walked as one connected live-HTTP run — assignment → session
  → offline capture → synchronization → existing ingestion → evidence association
  → PostGIS + MinIO + digest read-back → provenance → audit — 136/136 checks,
  0 failures, in 16.0 s, and it was **not** inferred from unit tests.
* The enforcing-mode pass (18/18) closes the authorization claim over a real
  socket with a real `AUTH_MODE`.
* Targeted and affected suites: 352 passed, 1 expected skip across three batches.
* The one failure is a pre-existing BE-025 test-data sensitivity, proven by
  measurement (§7) rather than asserted, with BE-025's assertion left intact.
* Audit chain stayed valid, contiguous and append-only throughout; no
  authorization regression; no duplicate evidence; no `pofa_dev` contact; no
  production file changed by this stage.

Ready to proceed to Stage E (hardening: fault injection against real
PostgreSQL/Redis/MinIO, concurrency, timeout/retry, oversized and malformed
input, rollback, and audit-chain re-verification after infrastructure is
restored), pending approval. The BE-026 commit remains un-staged and unpushed;
the proposal from Stage C still stands.
