# BE-026 Stage E — Hardening Results

Milestone: BE-026 Field Operations & Offline Evidence Capture Backend
Branch: `Backend` · Baseline commit: `29d12eb8` (BE-025 accepted)
Stage gate: task file §23 (Stage E — Hardening)

---

## 1. What §23 required, and where each item was proven

§23 names twenty things to test and adds two rules that shape how all of them
were tested:

> **Do not fake unavailable dependency tests.**
> **Restore infrastructure after fault injection.**

Both rules were honoured literally: every outage was produced by stopping a real
container or closing the real test database, each outage was confirmed live from
outside the application before a single assertion ran, every injection had a
guaranteed restore in a `finally` block, and the audit chain was re-verified
after each restore as well as at the end.

Three probe scripts, 535 assertions in total, all against a running uvicorn over
a TCP socket and the real `pofa_test` database:

| Part | Focus | Checks | Result | Log |
|---|---|---|---|---|
| A | duplicate / concurrent / timeout-retry / conflicting payload / revoked / expired / closure | 167 | **167 passed, 0 failed, GATE PASS** | `partA-seA7.log` |
| B | malformed ids / malformed payloads / oversized evidence / missing GPS / missing timestamps / authorization bypass / cross-organization / audit integrity | 286 | **286 passed, 0 failed, GATE PASS** | `partB-seB4.log` |
| C | MinIO outage / Redis outage / Postgres outage / partial ingestion failure / rollback / restoration | 82 | **82 passed, 0 failed, GATE PASS** | `partC-seC3.log` |

§23 coverage matrix — one row per required item:

| §23 item | Proven by | What the measurement showed |
|---|---|---|
| duplicate synchronization | A `S1`, A `S2b`, C `C15.13`, `C17.16`, `C18b.10`, `C19.10` | byte-identical replay answers 200 `already_synchronized`, exactly one operation row and one Evidence row, `sync_count` advances monotonically with no duplicate counter |
| concurrent synchronization | A `S2` (two server processes, one identity) | 8-way burst on a fresh identity: one 201, seven 200s, one row, one evidence, one `FIELD_SYNC_ACCEPTED` |
| timeout / retry | A `S3`, C `C15.11`, `C17.14`, `C18.9` | a client that never saw the answer recovers the stored outcome; an undecided identity stays retryable and lands exactly once after the dependency returns |
| conflicting client payload | A `S4` | same identity + different bytes → 409 `PAYLOAD_MISMATCH`, original digest and evidence untouched, `FIELD_SYNC_CONFLICT` audited (`S4.11`: `session_id` is inside `request_hash`, so the hash answers first) |
| revoked assignment | A `S5` | queued-then-revoked capture → durable `CONFLICT` / `ASSIGNMENT_REVOKED`, **no evidence row** |
| expired assignment | A `S6` | expiry after queueing → explicit conflict, lazy server-set expiry audited |
| activity closure | A `S7` | closed session / superseded context → explicit outcome, never a crash and never a silent accept |
| malformed IDs | B `S8` (all eleven field routes) | malformed and over-long identifiers are 422/404-shaped refusals with no row; a non-UUID `session_id` is 422 `SESSION_ID_MALFORMED` (was 500 — F-SE-03) |
| malformed payloads | B `S9` | unknown form fields refused as `UNEXPECTED_FIELD_*`, smuggled `project_id`/`role` never read, duplicate form keys resolved deterministically (`S9.13`), over-long parsed metadata 422 (`S9.12b`) |
| oversized evidence | B `S10` | 413 with no Evidence **and** no operation row; configured `max_upload_size=10485760` |
| missing GPS | B `S11` | accepted as unlocated: `location IS NULL`, lat/lon NULL as a pair, `location.reported: false` — never 0,0 and never invented |
| missing timestamp | B `S11` | absent client timestamps stay NULL (not derived); ordering anomalies flagged in `timestamp_flags`, values stored verbatim |
| database outage | C `C17` | real closed database (§3.3): no operation row, no evidence row, no field audit row, identity still retryable afterwards, servers recover without a restart |
| Redis outage **where applicable** | C `C16` | **NOT APPLICABLE, demonstrated not assumed** (§3.2) |
| MinIO outage | C `C15` | 503 `temporarily_unavailable` with no stack trace, no row, no evidence, no orphan object; retry after restore lands exactly once |
| partial evidence-ingestion failure | C `C18` | object landed, database refused → 503, no Evidence row, **audit twin rolled back with its row**, orphan object removed |
| rollback | C `C18`, `C18b`, B `S14.24` | every failure path asserts the absence of durable state; the ledger's own rollback-guarded tamper probe proves a rolled-back write leaves nothing |
| authorization bypass attempts | B `S12` (enforcing mode) | forged/anonymous/non-owner calls refused; a `field.sync` API client with no assignment is refused (`S12.22`: narrow 403, broad 403, gate `NO_ACTIVE_ASSIGNMENT`) and audited |
| cross-organization access | B `S13` | foreign reads 404 (no content, no count oracle); an org-A officer acting inside org-B refused at session open 404 (`S13.5-6`) — an assignment never confers authority |
| audit integrity | B `S14`, and chain re-verification after **every** outage | full `FIELD_*` event coverage with correct actor/resource linkage, secret-free payloads, append-only enforced by the shipped guard, chain valid after each restore |

No shipped test or assertion was weakened anywhere in this stage. Two production
files were changed, for six real defects. Tests **added during Stage E**: the
unit form-bound section for F-SE-03/F-SE-04 (`test_over_wide_form_text_is_a_deterministic_422_not_a_driver_error`,
`test_a_malformed_sync_session_id_is_refused_before_it_reaches_a_query`,
`test_recovery_labels_are_bounded_by_the_same_column_width`),
`test_scope_denied_session_open_is_audited_as_a_security_failure` for F-SE-05,
and one unit + one integration test for F-SE-06. F-SE-01 and F-SE-02 are
concurrency properties already covered in the shipped suite by Stage C's
`test_concurrent_first_submissions_create_exactly_one_accepted_capture` and
`test_abandoned_reservation_is_adopted_and_lands_exactly_once`, which stayed
green across the fixes, plus this stage's 8-way measurements.

---

## 2. Environment (measured, not assumed)

```
current_database   pofa_test
postgres           PostgreSQL 15.13 (Debian 15.13-1.pgdg120+1)
postgis            POSTGIS="3.4.2 c19ce56" [EXTENSION] PGSQL="150" GEOS="3.11.1-CAPI-1.17.1"
alembic head       ['p6q7r8s9t026']            (single head, Stage C migration)
python (harness)   Python 3.12.0  backend/.venv312_repro
uvicorn            0.23.1, two processes, 127.0.0.1:8121 and :8122
AUTH_MODE          enforcing (real env var on the server process, not a flag pretending to be it)
DATABASE_URL       postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test  (per process)
containers         pofa_db (postgres+postgis+pgvector) · pofa_redis (:6379) · pofa_minio (:9000)
max_upload_size    10485760
```

Two uvicorn processes are required, not decorative: `POST /field/sync` is
`async def` doing blocking database work, so one process serializes concurrent
requests and a concurrency probe against it would prove nothing.

The uvicorn processes run **without** `--reload`, so every production fix below
required a deliberate restart before it could be measured. Each verification run
listed in §4 is against a server started after the corresponding edit — and
F-SE-06 nearly escaped that rule (§6, ENV-SE-02).

```bash
# servers (two processes, enforcing, against pofa_test)
REPO=D:/CODING/Projects/Proof-Of-Action-Final
PY=$REPO/backend/.venv312_repro/Scripts/python.exe
bash /d/CODING/Scratch/poa_stageE_be026/launch_servers.sh   # ports 8121/8122

# part A / B / C (each with a fresh LABEL; part C is the outage track)
PYTHONPATH=$REPO BASE_URL=http://127.0.0.1:8121 BASE_URL2=http://127.0.0.1:8122 \
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test \
LABEL=seC3 $PY /d/CODING/Scratch/poa_stageE_be026/hardening_c.py \
  > /d/CODING/Scratch/poa_stageE_be026/partC-seC3.log 2>&1

# shipped suites (TEST_DATABASE_URL, never a pofa_dev fallback)
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test \
  $PY -m pytest -q -p no:randomly -p no:cacheprovider --tb=line -W ignore \
  tests/unit/test_field_operations.py tests/integration/test_be026_field_operations.py

TEST_DATABASE_URL=... $PY -m pytest ... tests/unit/test_authorization.py \
  tests/integration/test_authorization.py tests/unit/test_audit_ledger.py \
  tests/integration/test_audit_ledger.py tests/unit/test_retention.py \
  tests/integration/test_retention.py tests/unit/test_migrations.py \
  tests/unit/test_audit_guard.py tests/unit/test_preflight.py \
  tests/unit/test_test_target.py tests/integration/test_evidence_upload.py \
  tests/integration/test_storage.py tests/integration/test_fingerprinting.py \
  tests/integration/test_analysis_jobs.py tests/integration/test_evidence_graph.py
```

The probe scripts, fixtures and harness live under
`D:/CODING/Scratch/poa_stageE_be026/`, outside the repository.

---

## 3. Part C in detail: the outages were real

§23's "do not fake unavailable dependency tests" is the reason part C exists as
its own script. Each outage has an independent proof, measured from outside the
application, before any behaviour assertion is allowed to run.

### 3.1 MinIO down (`C15`)

```
C15.0 storage-reachable-before-the-fault
C15.1 lifecycle-works-before-the-fault        (baseline 201)
C15.2 storage-confirmed-unreachable           poll until the endpoint refuses
C15.2b pofa_minio state during the fault: exited
```

Then, with the container proven down: 503 `temporarily_unavailable` (`C15.3`,
`C15.4`), no stack trace in the body (`C15.5`), no operation row (`C15.6`), no
Evidence row (`C15.7`), total operation count unchanged (`C15.8`), and the
read/session surfaces keep working because they never touch storage (`C15.9`).
After `docker start`: `C15.10` storage reachable, `C15.11` the same identity is
still retryable and lands 201, `C15.12` exactly one row, `C15.13` replay of the
now-decision is idempotent, `C15.14` the refused uploads left **no orphan
object**, `C15.15` chain valid.

This is BE-026's own `StorageError → 503` translation (Stage C) holding under a
live outage — it measured correctly in every run of this section, including the
failing seC2, so Stage E records it as **verified**, not as a defect. The
still-open sibling is DF-SE-02 on the plain upload route (§7).

### 3.2 Redis down (`C16`) — proven *not applicable*, on a live outage

```
C16.0 redis-healthy-before-the-fault      (/ready redis sub-check healthy)
C16.1 fault-is-live readiness sees redis down
C16.2 session-open during the outage      201/409
C16.3 capture-accepted-during-the-outage  201
C16.4 duplicate-replay-during-the-outage  200 already_synchronized
C16.5 read-and-close-surfaces-during-the-outage
C16.6 no-field-surface-degraded-because-of-redis
C16.8 redis-restored · C16.9 chain valid after redis fault and restore
```

`C16.7` states the reason rather than assuming it: Redis *is* a required
dependency of `/ready` and of the analysis worker
(`backend/observability/health.py`, `backend/services/analysis_queue.py`), but
the synchronization path never enqueues — the reused ingestion pipeline has no
Redis import. So "Redis outage where applicable" resolves to **not applicable to
BE-026**, demonstrated by running the whole field surface while the container is
actually stopped.

### 3.3 Postgres down (`C17`) — scoped to this test database only

The outage is produced with `ALTER DATABASE pofa_test WITH ALLOW_CONNECTIONS
false` on an **autocommit** maintenance connection, followed by
`pg_terminate_backend` of the database's surviving backends — an `ALTER
DATABASE` that is not autocommit silently rolls back, and already-open pooled
connections keep working regardless, so both steps are necessary
(this exact trap is what made the first version of this section fake; §6,
PD-SE-02). Measured:

```
close: datallowconn=False terminated=3 backends left=0
C17.1 fault-is-live datallowconn is False
C17.2 fault-is-live a brand-new connection is refused     (fresh engine, new process)
C17.3 no-surviving-backends on the closed database
C17.4 fault-is-scoped: pofa_dev still reachable           (shared server stays up)
C17.4b readiness postgres sub-check during the outage:
     {"status":"unhealthy","message":"PostgreSQL connection failed","required":true}
```

Behaviour under that outage: BE-026's own service, driven **in-process against
the closed database**, answers `FieldOperationError(503,
temporarily_unavailable)` and nothing else (`C17.5`) — no raw ORM error escapes.
No stack trace on the sync path or the read path (`C17.6`, `C17.7`). After
reopen (`C17.8`), with `pofa_dev` proven untouched (`C17.9`): zero operation
rows (`C17.10`, `C17.11`), zero Evidence rows (`C17.12`) and zero field audit
rows (`C17.13`) written inside the outage window; the servers recovered **without
a restart** (`C17.14`); the identity tried during the outage stayed retryable and
landed exactly once (`C17.15`, `C17.16`); chain valid and ledger contiguous
(`C17.17`, `C17.18`).

`C17.19` records the honest boundary: over HTTP during a real outage the answer
is `401 {"detail": "Invalid credentials"}`, because `resolve_principal`
(`backend/security/authentication.py`, which predates BE-026) converts any
`SQLAlchemyError` into a credential failure **before** the field route runs.
BE-026's own obligations all hold in that window (no row, no evidence, no audit,
no leak, retryable identity) — it fails closed, it just misclassifies. That
401-during-outage behaviour is **not a new finding**: it is DF-SE-01, recorded in
`docs/BE-024 Final Acceptance Report.md` §8 as Low / non-blocking / intentionally
deferred, with the remediation already stated there ("distinguish transient DB
errors from credential errors → 503 with retry semantics"). Stage E re-measured
it against a genuinely closed database instead of reasoning about it, and that
measurement is what makes BE-026's own 503 claim defensible: the design-6
obligation holds inside BE-026 (`C17.5`), and the layer above it is the open
finding. It is carried forward (§7), not worked around and not asserted correct.

### 3.4 Partial ingestion and rollback (`C18`, `C18b`)

Two injections, both trigger-based, both keyed to a sentinel so no other traffic
in the shared server is disturbed:

* `C18` — a `BEFORE INSERT` trigger on `evidence` refuses **only** the upload
  whose filename is the probe sentinel. The object has already landed in
  quarantine when the database refuses: 503 (`C18.1`), declared vocabulary
  (`C18.2`), no stack trace (`C18.3`), no operation row (`C18.4`), no Evidence
  row (`C18.5`), and the **audit twin rolled back with its row** (`C18.6`) — the
  `EVIDENCE_UPLOADED` event never exists without its Evidence row. `C18.7` finds
  nothing dangling, `C18.8` proves the rollback deleted the object it had
  written, `C18.9` the identity lands exactly once once the fault is gone,
  `C18.10` chain valid.
* `C18b` — a `BEFORE UPDATE` trigger on `field_capture_operations` refuses the
  transition to `ACCEPTED` for this label's own identity, i.e. failure *after*
  the reused pipeline has already committed its own row. Result: 503, not 201 and
  not 500 (`C18b.1`, F-SE-06's verification), no stack trace (`C18b.2`), the
  reservation survives as `PENDING` and undecided (`C18b.3`), the immediate retry
  is protected by the in-flight window (`C18b.6`), protection does not
  double-create (`C18b.7`), and once the reservation goes stale it is adopted
  and lands (`C18b.8`), exactly one row in the end (`C18b.9`), replay idempotent
  (`C18b.10`), chain valid (`C18b.11`).

`C18b.4` states the seam rather than hiding it: `ingest_evidence` commits in its
own transaction (design 5) and BE-026 finalizes in a second one, so a failure
between the two leaves **one real, unlinked quarantine Evidence row** (measured
delta of exactly 1). BE-026 does not own or redesign that pipeline, so Stage E
documents it, tracks the row, and removes it in teardown.

### 3.5 Restoration (`C19`) — required by "restore infrastructure afterward"

```
C19.2 test-database accepts connections
C19.3 storage reachable
C19.4 no injection tracked as still installed
C19.5 injection triggers are gone            (by name, in pg_trigger)
C19.6 injection functions are gone           (by name, in pg_proc)
C19.7 redis reachable again
C19.8 readiness snapshot after restoration: status healthy, all three required checks healthy
C19.9 full-lifecycle-works-after-restoration  (201 accepted, end to end)
C19.10 idempotency still holds after restoration
C19.11 chain valid at the end
```

`restore_all()` runs in a `finally` block — reopen the database, start the
containers, then drop the injections in that order (dropping first was itself a
probe bug, §6 PD-SE-04) — and `C99` re-verifies the chain after all fault
injection, independent of the per-section checks.

---

## 4. Defects found by hardening: FOUND → FIXED → VERIFIED

Six production defects, all in BE-026-scoped files, all found by running the
probe against real infrastructure. The VERIFIED column names the retained run
that measured the fix; the shipped-test situation is stated under the table.

Log retention, stated so the evidence is readable as evidence: the three
**passing** runs above (`seA7`, `seB4`, `seC3`) and the two failing runs that
produced F-SE-06 and the PD-SE-02 finding (`seC2`, plus `seB3` for PD-SE-01) are
kept as files in `D:/CODING/Scratch/poa_stageE_be026/`. The earliest discovery
runs (`seA2`, `seA3`, `seB1`, `seB2`) were overwritten by later iterations of the
same scripts, so their FOUND measurements below are recorded from the working
notes taken at the time. Every FIXED claim was re-measured from scratch and is
backed by a retained passing log — which is why the fix rows cite
`seA7`/`seB4`/`seC3`, not the discovery run — and four of the six additionally
have a shipped test added in this stage.

| ID | Severity | FOUND (measured) | FIXED | VERIFIED |
|---|---|---|---|---|
| **F-SE-01** | High — idempotency accounting | Run seA2, `S2b`: 8 concurrent exact retries on an identity at `sync_count=8` moved it to **12**, not 16, with duplicate ledger counters `[2,3,4,5,6,7,8,9,9,10,10,11,11,12,12]`. Root cause: the replay path read the identity row **without a lock**, so concurrent retries lost each other's counter writes | `field_repo.lock_operation_by_client_id()` (`SELECT … FOR UPDATE` on `(user_id, client_operation_id)`); `sync_capture`'s first read and `_reserve`'s `IntegrityError` re-read both use it | seA4, seA5, seA7: `S2b codes=[200×8] sync_count 8 -> 16, duplicates=8`, counters strictly increasing; A `S2` one-row/one-evidence/one-event assertions |
| **F-SE-02** | High — 500 on a legal race | Run seA3, `S2c`: the stale-`PENDING` **adoption** race returned `[500, 503]` and the clone row vanished. Traceback: `InvalidRequestError: Could not refresh instance` at `field_operations.py:1688`, reached from `_settle_existing:1533 → _execute` | `_claim_stale_reservation()` — a compare-and-set on the reservation's own stale clock (`received_at`), because `ingest_evidence` commits and no row lock can span adoption; the loser gets 503 `temporarily_unavailable` | seA4, seA5, seA7: `S2c codes=[201, 503]`, exactly one Evidence row, one `FIELD_SYNC_ACCEPTED`, one `ACCEPTED` row; C `C18b.6–C18b.9` exercise the same window under an injected failure |
| **F-SE-03** | Medium — 500 on client input | Run seB1, `S8`: `POST /field/sync` with a non-UUID `session_id` answered **500** for all four malformed inputs. `_norm_id` deliberately passes unparseable text through, and psycopg then rejected it in the driver | `_session_identifier()` validates and canonicalizes the form value → 422 `validation_failed` + stable code `SESSION_ID_MALFORMED`, no row written | seB4 `S8` green; shipped `tests/unit/test_field_operations.py:325` |
| **F-SE-04** | Medium — 500 on client input | Run seB1: over-long multipart form text (`client_operation_id`, `client_capture_id`, `client_device_id`, `filename`, `declared_content_type`) overflowed the column width → **500** | `SYNC_FORM_WIDTHS` (the schema's own widths) + `_bounded_form_text()` → 422 + `<FIELD>_TOO_LONG`; the recovery route got the same ceiling, because comparing an over-wide literal against the column fails in the driver instead of here | seB4 `S8`/`S9` green; shipped `tests/unit/test_field_operations.py:313,347` |
| **F-SE-05** | Medium — missing denial audit | Run seB2: the `POST /sessions` scope-gate denial raised **without any audit event**, while `POST /field/sync` audited the identical gate. R2 requires a denial to be recorded even though it mutates nothing | The session-open denial now appends `FIELD_ASSIGNMENT_SECURITY_FAILURE` (committed on its own, since no domain state is written) | seB4 `S13.6b`/`S13.6c`; shipped `test_scope_denied_session_open_is_audited_as_a_security_failure` |
| **F-SE-06** | Medium — 500 where the design says 503 | Run seC2, `C18b.1`: a database failure raised while **finalizing** an accepted capture escaped as `500 {"detail": "internal server error"}`. Server log pinned the raise site: `_audit → audit_ledger.append_event → insert_event → db.flush()`, which emits the pending `ACCEPTED` update — only `db.commit()` had been guarded | Two guards: the whole association/finalization phase in `_execute` is inside one `try/except SQLAlchemyError → 503 temporarily_unavailable` (with rollback), and `sync_capture` became a thin wrapper around `_sync_capture` that translates the same failure class for the pre-reservation reads. Declared denials and the reused validator's 400/413/415 propagate unchanged | seC3: `C18b.1` 503 + `C18b.2` no leak, `C17.5` 503 measured **against the closed database in-process**, `C17.10–C17.13` nothing written; shipped `test_a_database_failure_while_finalizing_answers_temporarily_unavailable` + 2 unit tests |

Four of the six added shipped tests of their own (F-SE-03, F-SE-04, F-SE-05,
F-SE-06); the two concurrency defects (F-SE-01, F-SE-02) are covered by Stage C's
shipped concurrency tests, which stayed green through the fixes. BE-026's
targeted suite is now 67 unit + 43 integration tests, all passing (§9).

---

## 5. Deliberate non-claims

Four places where the result could have been inflated, and what was stated
instead:

* **Redis was not claimed to be covered — it was proven out of scope** (§3.2).
  The alternative reading of "where applicable" was to write a test that pretends
  the field path uses Redis; it does not, and the outage proves it.
* **The 401-during-Postgres-outage was not fixed here.** It belongs to
  pre-BE-026 authentication, is already recorded as a cross-cutting finding, and
  fails closed. Changing `resolve_principal` to reach a different status code is
  an authorization-behaviour change in another milestone's surface — out of scope
  for BE-026, and §23 does not require it. It is carried forward (§7).
* **`C18b`'s orphan Evidence row was documented, not redesigned away.** Making
  ingestion and finalization one transaction would mean changing the shared
  `ingest_evidence` contract that BE-013/BE-016 own. The delta is measured (
  exactly 1), tracked, and removed by teardown.
* **The audit-ledger section never destroyed a row** — after one run did. See
  PD-SE-01 below; the disclosure is part of the record.

---

## 6. Probe and environment history

Nothing in this table is a product defect, and nothing in it was hidden by
re-running until green: each row is a measurement that was wrong before it was
right.

### 6.1 Probe defects (scripts live outside the repository)

| ID | FOUND | FIXED | VERIFIED |
|---|---|---|---|
| **PD-SE-01** | Run seB3, `S14.23`: the "append-only" probe issued a **committed `DELETE FROM audit_ledger_events`** and destroyed one tip `FIELD_*` harness event — exactly what `tests/audit_guard.py` forbids. Disclosure: this happened, in `pofa_test`, during this stage. Recovery state verified: 23076 rows, no gaps, no duplicates, `verify_chain` valid; the deleted row was probe-written, never product | The destructive helper was deleted. The section now proves append-only three ways without destroying anything: a rollback-guarded `UPDATE` (applied then rolled back, `S14.24`), a collision-insert that must fail, and hash recomputation using the shipped chain code, plus `S14.23`/`S14.25` asserting the guard refuses and the row survives | seB4 `S14.23`/`S14.24`/`S14.25` green; ledger contiguous `1..26343` and chain valid at the end of the stage (§8) |
| **PD-SE-02** | Run seC2, `C17`: the Postgres outage was **never in effect**. The maintenance engine used `isolation_level=None`, which is *not* psycopg2 autocommit, so the `ALTER DATABASE` rolled back at connection close; `C17.1` "passed" only because the harness's own pooled connection was dead, while both servers kept serving. Five of that run's seven failures are the direct consequence | `isolation_level="AUTOCOMMIT"`, `pg_terminate_backend` of surviving backends, `datallowconn` read back, a brand-new-engine refusal proof, and `engine.dispose()` on every state change; the service check moved in-process against the closed DB | seC3: `datallowconn=False terminated=3 backends left=0`, fresh connection refused, `/ready` postgres sub-check **unhealthy** during the window — and zero rows written, which seC2 could not show |
| **PD-SE-03** | Run seC2, `C15.9`: the probe used a *colleague's* assignment as the officer, so the session open was a legitimate 404 and the check misread it as storage-dependence | Use `w["assignment"]` | seC3 `C15.9` green |
| **PD-SE-04** | Run seC2: `restore_all()` dropped the injection triggers **before** reopening the database, so the drop itself failed on a closed DB | Restore order corrected: reopen → start containers → drop injections | seC3 `C19.2–C19.7` green, 0 leftover functions/triggers (§8) |
| **PD-SE-05** | Several probe expectations were written against imagination: `S14.20` looked for a `resolution_note` inside the audit payload (design §10 restricts payloads to ids/hashes/statuses/reasons — the note is durable on the **row**, `S14.20b`); `S6.15`/`S6.17` expected `validation_errors` on administrative refusals (that envelope belongs to the synchronization path; the stable codes are carried by the service error and asserted in the shipped unit suite); `S4.11` expected a session-vs-payload ordering it had not derived; `S11`'s `CONTEXT_RESOURCE_MISSING` assumed an HTTP route that referential integrity makes unreachable | Each expectation retargeted at what the design actually promises, with the reasoning written into the section comment. No product rule was relaxed — in the `S14.20` case the stronger claim (durable note **and** visible conflict, design §9) is asserted, just in the right place | seA7 / seB4 NOTE lines record each correction in the run that verified it |
| **PD-SE-06** | Run seA6 crashed before any assertion: `json.loads` on an already-parsed dict in `s1_duplicate`; run seC1 crashed at import (wrong interpreter, ENV-SE-01) | Both fixed in the scripts | seA7, seC3 complete runs |

### 6.2 Environment incidents (classified ENVIRONMENT, not product)

| ID | FOUND | RESOLVED |
|---|---|---|
| **ENV-SE-01** | A regression batch run on `backend/.venv` (Python 3.14) reported `test_vision_relationship_from_real_be009_output :: assert 'retry' == 'completed'`. That interpreter has no `torch`/`ultralytics`, so BE-009 inference cannot run there — the failure is the interpreter, not BE-026. An earlier attempt on `backend/.venv312_clean` died even earlier: no `pytest`, `requests`, `boto3` | Re-run with `backend/.venv312_repro` (3.12, complete ML + HTTP + DB stack): that single test passes, and both Stage E batches are green (§9). **No shipped test was edited or skipped to achieve this** |
| **ENV-SE-02** | The restart after F-SE-06 appeared to succeed but every request hung: `.venv312_clean` has since lost `click`, so `python -m uvicorn` exited immediately with `ModuleNotFoundError: No module named 'click'`, and a stale readiness check reported 503 | `launch_servers.sh` now launches `.venv312_repro`, with a comment saying why. Verified: both `/ready` endpoints return 200 with all three required checks healthy, and part C's 82 assertions ran through those servers |

---

## 7. Carried forward

| Item | Status | Where it belongs |
|---|---|---|
| `resolve_principal` maps every `SQLAlchemyError` to `401 Invalid credentials`, so a Postgres outage misclassifies as a credential failure over HTTP (fails closed; BE-026's own obligations all hold) | Open — this is **DF-SE-01**, recorded in `docs/BE-024 Final Acceptance Report.md` §8 (Low, non-blocking, deferred). Stage E re-measured it live (`C17.19`). BE-026 Stage B design rule 5 lists it as "preserved, not absorbed", which is exactly why it is reported here rather than fixed | Not BE-026 scope — an authentication-behaviour change in another milestone's surface |
| `DF-SE-02`: a MinIO outage surfacing as a generic 500 on the plain evidence **upload** route | Still open, also "preserved, not absorbed". BE-026's own synchronization route was measured at 503 with no leak and no orphan object (`C15.3–C15.5`, `C15.14`); the upload route was not touched by this milestone and is not claimed here | BE-013/BE-024 storage-surface scope |
| The reused ingestion pipeline commits `Evidence` before BE-026 finalizes, so a failure between the two leaves one unlinked quarantine row | Documented and measured (`C18b.4`, delta 1); BE-026 neither causes nor worsens it | BE-013/BE-016 scope if single-transaction ingestion is ever required |
| 62 pre-existing unreferenced quarantine objects in the bucket, counted at `S10` | Not BE-026's; measured, untouched, deliberately not cleaned (deleting other people's objects to make a count look good is not verification) | Storage lifecycle policy |
| BE-025 `test_organization_lifecycle_noop_audit_and_isolation` first-page assertion vs 94 organizations | Still open, carried from Stage D §7 | BE-025's own scope |
| Structured-log formatter raises `KeyError: 'request_id'` outside a request context | Still open, pre-existing, startup completes | Not BE-026 scope |

---

## 8. Isolation, residue and repository state

Final state, measured by a standalone script after every restore and after both
regression batches:

```
current_db     pofa_test
datallowconn   {'pofa_dev': True, 'pofa_test': True}      # the closed DB was reopened
leftover_fns   0     (pg_proc, names like be026_stage_e%)
leftover_trg   0     (pg_trigger, names like be026_stage_e%)
field_rows     {'field_assignments': 0, 'field_sessions': 0, 'field_capture_operations': 0}
ledger         (26343, 1, 26343)                          # count, min, max — contiguous
chain          {"valid": true, "checked_events": 26343, "first_sequence": 1,
                "last_sequence": 26343, "failures": []}
containers     pofa_db Up · pofa_redis Up · pofa_minio Up
pofa_dev       dev_field_tables absent · dev_alembic ['n4o5p6q7r022'] · dev_evidence 324
```

* **No ledger row was ever deleted** by the finished probes (§6, PD-SE-01 for the
  one that did, and its disclosure). Each retained passing run grew the ledger by
  its own window: part B `seB4` `23097 → 23186`, part A `seA7` `23214 → 23341`
  (B's passing run came first, because the F-SE-01…04 fixes forced a replay of
  part A), part C `seC3` `25733 → 25790` (the gap before it is the regression
  batches, which also only append). The stage ends contiguous from sequence 1
  with a valid chain — append-only survived a MinIO stop/start, a Redis
  stop/start, a closed database, two injected triggers and one rolled-back
  tamper attempt.
* **Zero residue** from each part: `teardown_remaining` reports 0 for
  assignments, sessions, operations, evidence, users, orgs and projects, and
  every quarantine object the probes wrote was deleted from MinIO and listed back
  to confirm absence (`C15.14`, `C18.7`, `C18.8`).
* **No `pofa_dev` contamination** — stronger than "no new rows": `pofa_dev` has
  no BE-026 tables at all and its Alembic version is still `n4o5p6q7r022`, the
  pre-BE-026 head. Every track ran against `pofa_test`, and the Postgres outage
  was scoped to that one database with `pofa_dev` measured reachable throughout
  (`C17.4`, `C17.9`).

Repository state is the Stage C/D change set plus this stage's edits, nothing
staged, nothing committed, nothing pushed:

```
 M backend/api/v1/router.py
 M backend/db/models.py
 M backend/services/authorization.py
 M openapi.json
 M tests/unit/test_migrations.py
?? alembic/versions/p6q7r8s9t026_be026_field_operations.py
?? backend/api/v1/endpoints/field.py
?? backend/repositories/field_operations.py     (F-SE-01)
?? backend/schemas/field_operations.py
?? backend/services/field_operations.py         (F-SE-02/03/04/05/06)
?? tests/integration/test_be026_field_operations.py
?? tests/unit/test_field_operations.py
?? docs/BE-026 Stage A/B/C/D + this document + the BE-026 task file
```

Stage E touched exactly two production files (`backend/services/field_operations.py`,
`backend/repositories/field_operations.py`) and two test files. No unrelated
production code, no migration history, no Evidence/Authorization/Audit redesign,
no second ingestion validator.

---

## 9. Shipped suites after the fixes

```
targeted   tests/unit/test_field_operations.py
           tests/integration/test_be026_field_operations.py
           → 110 passed in 73.91s

affected   authorization (unit+integration) · audit ledger (unit+integration) ·
           retention (unit+integration) · migrations · audit guard · preflight ·
           test_target · evidence upload · storage · fingerprinting ·
           analysis jobs · evidence graph
           → 176 passed, 1 skipped in 215.57s

           SKIPPED tests/unit/test_preflight.py:117 — "ML stack genuinely
           installed in this environment": the opt-out test skips *because* the
           ML stack is present. Reported as a skip, not counted as a pass.
```

Both runs used `TEST_DATABASE_URL=…/pofa_test` and
`backend/.venv312_repro/Scripts/python.exe` (§6.2). The BE-009/BE-025 vision and
admin-plane files are inside the affected set, and the previously failing
`test_vision_relationship_from_real_be009_output` passes under the correct
interpreter.

---

## 10. Stage E gate decision

**Stage E: PASS.**

* All twenty §23 items are covered, 535 assertions across three probe parts, all
  passing in their final runs: **167/167**, **286/286**, **82/82**.
* No dependency test was faked: MinIO and Redis outages are real container
  stops confirmed by polling and by `/ready`; the Postgres outage is a real
  closed database confirmed by `datallowconn`, a fresh-connection refusal and
  zero surviving backends. Redis is reported **not applicable** on evidence, and
  the one place the HTTP answer differs from design 6 (401 from pre-BE-026
  authentication) is measured, named and carried rather than smoothed over.
* Infrastructure was restored after every injection and re-verified: containers
  up, database accepting connections, **0** leftover functions and **0** leftover
  triggers, full lifecycle working again, idempotency still holding.
* The audit chain was re-verified after each restore and at the end: valid,
  contiguous `1..26343`, append-only, `pofa_test` only.
* Six production defects (F-SE-01 … F-SE-06) are recorded **FOUND → FIXED →
  VERIFIED** with the before/after measurements, four of them with shipped tests
  added in this stage (§4); no shipped assertion was weakened, and no existing
  test was edited to make a gate pass.
* Targeted 110 passed; affected 176 passed with one honestly-reported skip.

Ready to proceed to **Stage F — full verification** (§24: BE-026 targeted tests,
affected integration tests, full unit suite, full integration suite, migration
verification, from-scratch migration, BE-023 preflight, authorization regression,
audit-chain verification, repeated/idempotency verification), pending approval.

The BE-026 commit remains **un-staged and un-pushed**; the proposal from Stage C
still stands and now also covers the Stage E files:

```
git add backend/api/v1/router.py backend/db/models.py backend/services/authorization.py \
        openapi.json tests/unit/test_migrations.py \
        alembic/versions/p6q7r8s9t026_be026_field_operations.py \
        backend/api/v1/endpoints/field.py backend/repositories/field_operations.py \
        backend/schemas/field_operations.py backend/services/field_operations.py \
        tests/integration/test_be026_field_operations.py tests/unit/test_field_operations.py \
        "docs/BE-026 Stage A Reconnaissance.md" "docs/BE-026 Stage B Design.md" \
        "docs/BE-026 Stage C Implementation Summary.md" "docs/BE-026 Stage D Runtime Results.md" \
        "docs/BE-026 Stage E Hardening Results.md" \
        "docs/Production Task Files/BE-026 — Field Operations & Offline Evidence Capture Backend.md"
git commit -m "BE-026: implement field operations and offline evidence capture backend"
```
