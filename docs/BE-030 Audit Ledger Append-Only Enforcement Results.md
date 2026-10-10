# BE-030 — Audit Ledger Append-Only Enforcement & Chain Integrity: Results

**Project:** Proof-Of-Action (PoA)
**Task:** BE-030
**Date of measurements:** 2026-10-10
**Owner decisions this task executed against:** D-1 = **A** (refusing `BEFORE ROW` trigger + narrow,
audited `SET LOCAL` hatch; TRUNCATE consciously left open until a non-owner role exists);
D-2 = **A** (writer recomputes the immediate predecessor and refuses on damage) **+ §9 anchored
verification** as the durable read-path control; §15 = **2** (reviewed named autogenerate filter, no
model change, no dependency upgrade); §16 = **a** (keep bare lists, document `/auth/roles` and
`/auth/permissions` as report-only enumerations).

This document is written against the task file's §18 DEFINITION OF DONE. Every item below carries a
**command**, a **target database**, and a **measured number**. Items that are *not* fully done are
stated as such (§12), per §18.12: "Do not claim BE-030 is complete merely because this file exists."

---

## 0. Targets, provenance, and safety posture

| Database | Role in this task | Verified `current_database()` | Alembic revision (from server) | Ledger |
| --- | --- | --- | --- | --- |
| `pofa_test` | Shipped enforcement + full suite run | `pofa_test` | `t0u1v2w3x030` (head) | span `1..max`, contiguous, span−count = 0 |
| `pofa_be030_proof` | Disposable clone — enforcement round trip | `pofa_be030_proof` | driven `s9t0u1v2w029 → t0u1v2w3x030 → s9t0u1v2w029 → head` | clone of `pofa_test` |
| `pofa_dev` | **Untouched.** Read-only re-measurement only | `pofa_dev` | `s9t0u1v2w029` (BE-029 head, **unchanged**) | 6,023 rows, span 1..6,059, **36 missing in 7 ranges, 0 hash mismatch** |

Safety facts asserted by commands, not prose:
* `pofa_dev` was **never** migrated, downgraded, reset or cleanup-SQL'd. Its revision is still
  `s9t0u1v2w029` and it has **no** enforcement objects (`triggers=[]`, `rules=[]`, `policies=[]`).
* API, workers and schedulers were stopped for the duration; no external writer contended the ledger.
  (If this were not true, the contiguity numbers below would not hold.)
* No credential is printed in this document or its evidence files. Test URLs are read from
  `D:/CODING/Scratch/be030/_testurl.txt` into environment variables only.
* `backend/db/safety.py` armed contexts (`pytest` / `verification`) still refuse `pofa_dev`/`pofa_test`
  for ad-hoc probes; enforcement was applied to `pofa_test` via the ordinary un-armed `alembic`
  migration path, which is the sanctioned route, and pinned by `test_be029_database_safety_guard.py`.

---

## §18 Definition-of-Done — item by item

### DoD-1 — `UPDATE` and `DELETE` refused on the application's normal path (D-1 = A)

**Command:** disposable clone `p99_clone_proof.py` (alembic-driven), then shipped tests on `pofa_test`.
**Measured (clone `pofa_be030_proof`):**
* `UPDATE audit_ledger_events …` → **refused**, `ProgrammingError`, **SQLSTATE 42501**, message
  `append-only enforcement refuses UPDATE on the audit ledger`.
* `DELETE FROM audit_ledger_events …` → **refused**, `ProgrammingError`, **SQLSTATE 42501**, message
  `append-only enforcement refuses DELETE on the audit ledger`.
* Option named in evidence: **D-1-A** (trigger + `SET LOCAL` hatch). The refusing objects on
  `pofa_test` are present: trigger `trg_audit_ledger_append_only`, function
  `audit_ledger_refuse_mutation`, CHECK `ck_audit_ledger_event_type_domain` (all `True`).

**Shipped:** `test_update_without_hatch_is_refused` asserts the UPDATE refusal (class, SQLSTATE 42501,
message) on `pofa_test`. The DELETE refusal is proven on the clone, not shipped as an in-repo test —
rationale in §13 note below.

### DoD-2 — `append_event` cannot link onto a predecessor whose hash does not recompute

**Command:** shipped `test_append_refused_after_tail_tampering`; clone `d2a_tail_refusal`.
**Measured:** after a sanctioned UPDATE damages the tail row, `append_event` raises
`PredecessorInvalid`; clone message: `refusing to append onto sequence 38264: event_hash mismatch at
sequence 38264`. Insert, contiguity, no-burned-number and concurrency behaviour remain proven by the
existing suite (`test_append_negative_control_with_enforcement_live`, `test_concurrent_appends_keep_valid_chain`,
the BE-029 rolled-back-append no-burn test) — see DoD-10 matrix.

### DoD-3 — an anchored verification path reports `invalid` on the tampered shape; F-6 blind spot pinned

**Command:** shipped `test_anchored_verification_catches_mid_chain_tampering`; clone
`anchored_full_chain` + `midchain_asymmetry`.
**Measured:** a window strictly after a tampered middle row reports `valid=True` (the F-6 shape), while
a walk that *includes* the tampered row reports `valid=False` with an `event_hash mismatch` failure.
Clone `midchain_asymmetry.covering_range_valid = False`, `downstream_window_valid = True`. The
anchored walk over the whole clone chain: `valid=True`, `checked_events=38265`, span `1..38265`.
F-6 is now pinned by a test that fails if anyone reintroduces a tail-only "it's valid" claim.

### DoD-4 — enforcement installed by one reviewed, guarded migration; symmetric downgrade proven; catalog-pinned

**Command:** `alembic upgrade t0u1v2w3x030` → `downgrade s9t0u1v2w029` → `upgrade head` on the clone;
`test_enforcement_objects_are_present_in_the_catalog` on `pofa_test`; `alembic current` on `pofa_test`.
**Measured (clone):** before-upgrade objects `{trigger:false, function:false, check:false}`;
after-upgrade `{true,true,true}` at `t0u1v2w3x030`; after-downgrade `{false,false,false}` back at
`s9t0u1v2w029`; after-re-upgrade `{true,true,true}`. Final full-chain `valid=True`.
**Migration guards (`upgrade()`):** aborts with `EnforcementPreconditionFailed` on out-of-domain rows,
on a pre-existing trigger/function/CHECK (refuses to guess a hand-fixed DB). **`downgrade()`** drops in
reverse order (CHECK → trigger → function). One revision, single linear `down_revision=s9t0u1v2w029`.
Catalog pin (`pg_trigger`/`pg_proc`/`pg_constraint`) is the *only* protection, because Alembic 1.11.2
`compare_metadata` cannot see a trigger or CHECK (feasibility §2a) — see DoD-7.

### DoD-5 — the `event_type` `CHECK` shipped with the Python/SQL equality test

**Command:** shipped `test_out_of_domain_insert_is_refused` (integration) and
`tests/unit/test_be030_ledger_contract.py` (enum↔constraint equality).
**Measured:** out-of-domain raw INSERT → **refused**, `IntegrityError`, **SQLSTATE 23514**, message
`... violates check constraint "ck_audit_ledger_event_type_domain"`. The constraint's `IN` list is
generated from `AUDIT_EVENT_TYPES` (94 members); the unit test fails if the model `CHECK` and the
migration list ever diverge. Both databases re-measured to **0** out-of-domain rows and **0** NULLs
before adding it (`p1_remeasure.py`: `pofa_dev` `out_of_domain_event_types=[]`, `null_event_type=0`).

### DoD-6 — `pofa_dev`'s 36 missing numbers reconciled **read-only**

**Command:** `p1_remeasure.py` (anti-join over `generate_series(min..max)`, read-only session).
**Measured:** the register (feasibility doc §6) lists **36 missing numbers in 7 ranges**
(5344–5349, 5374–5379, 5381–5384, 5386–5391, 5393–5396, 5671–5676, 5678–5681) and each range's
surviving-neighbour timestamps; a live re-query on `pofa_dev` today reproduces exactly those 7 ranges
and sum 36, `span_minus_count=36`, **zero hash mismatch**. No row was created, edited, renumbered or
deleted; §10's forbidden list was not touched. Alerting is anchored to this register so *known* damage
(these 7 ranges) is distinguished from *new* damage.

> **Honest partial (see §12):** the register-vs-live comparison is a read-only *script* run against
> `pofa_dev`, not a continuously-running `pytest`. §14 bars automated tests from reading live
> `pofa_dev`/`pofa_test`, so pinning `pofa_dev`'s specific baseline as a repo test would require
> shipping that DB's exact gaps as a constant and reading the live DB at test time — a shape §14
> forbids. It is therefore reported as a §13.15 partial, not a shipped green checkmark.

### DoD-7 — §15 tooling debt resolved; `alembic check` and the containment gate reported **separately**

**Command A:** `alembic check` (via `process_revision_directives` in `alembic/env.py`).
**Measured A (pofa_test):** the `remove_constraint`/`add_constraint` pair on
`user_role_assignments.uq_user_role_scoped` is DETECTED then SUPPRESSED by the reviewed named filter
in `backend/db/schema_drift_policy.py` (reason text + measurement pointer logged), and the command ends
`No new upgrade operations detected.` → **`alembic check` = CLEAN.**

**Command B:** `pytest tests/integration/test_schema_drift_gate.py` (custom containment gate over
`compare_metadata`, which does *not* run the revision directives).
**Measured B (pofa_test):** **6 passed.** The gate's baseline entry
(`tests/schema_drift_baseline.py`) **retains** the `uq_user_role_scoped` pair as an explicitly
*justified* Category-B tooling artifact — item 7's "either deleted or explicitly justified" resolved as
**justified**.

These two are reported separately and neither is inferred from the other. The schema is not declared
fully clean merely because the custom gate returns CLEAN: `alembic check` is now independently CLEAN
through the filter, and the enforcement objects remain invisible to both — which is exactly why DoD-4's
catalog test exists.

### DoD-8 — §16 envelope question carries an owner decision, not an incidental change

**Decision recorded:** §16 = **a** — keep bare lists; document. `GET /api/v1/auth/roles` and
`GET /api/v1/auth/permissions` are annotated (OpenAPI `description=`) as report-only enumerations;
their request/response contract is unchanged. **Command:** regenerated `openapi.json`.
**Measured:** the `openapi.json` diff is exactly **+2 lines** (the two descriptions) and nothing else —
no other endpoint shape moved. This is a decision, not a silent fix.

### DoD-9 — guard reports `violations: 0`; regression file still pins every DELETE/bulk-UPDATE spelling; no test deletes or bulk-updates ledger history

**Command:** `pytest tests/unit/test_audit_guard.py`.
**Measured (pofa_test, static over the whole tree):** **25 passed**, including
`test_current_test_tree_has_no_violations` (violations == 0). The regression file still pins
`orm_delete`, `core_delete` (bare + module-qualified), `raw_delete`, `truncate`, `bulk_update`, and
`test_core_delete_has_no_rollback_exception`. New enforcement tests were enrolled in
`_ALLOWED_UPDATE_TESTS` and every sanctioned UPDATE is inside a rolled-back function.

### DoD-10 — full matrix re-run on the named target: counts, durations, named skips, zero unexplained failures

**Command:** `pytest tests -p no:cacheprovider -q -rs -rf --durations=8` with `TEST_DATABASE_URL`
pointed at `pofa_test` (single, isolated run — no concurrent suite, no external writer). Skips are
reported as skips, not passes.

**Headline (single clean isolated run):**

| Bucket | Command filter | Collected | Result |
| --- | --- | --- | --- |
| **Full tree** | `pytest tests` | 793 | **792 passed, 1 skipped, 0 failed** — 515.30s (8:35) |
| Integration bucket | `pytest tests -m integration` | 33 | **33 passed, 0 failed** — 53.50s |
| Unit / non-integration bucket | `pytest tests -m "not integration"` | 760 | **759 passed, 1 skipped, 0 failed** |

`-rf` printed no failure lines: **zero unexplained failures.** The suite run also grew `pofa_test`'s
ledger from 38,261 to **42,545 rows, span `1..42545`, span−count 0** under live enforcement — i.e.
4,284 real `append_event` writes happened with the trigger, CHECK and D-2-A guard installed and the
chain stayed contiguous (DoD-2's "no burned number / contiguity" proof, in the aggregate).

> A prior run of the non-integration bucket reported "3 failed" — that was **two suites overlapping on
> `pofa_test`** (concurrent `append_event` calls contending the same advisory-locked sequence space), not
> a real regression. The isolated clean run above is 0-failed. Concurrency is not a substitute for an
> isolated verification run.

**Slowest tests (all passing):** `test_tamper_detection_with_rollback` 29.65s,
`test_api_creates_job_and_worker_persists_real_fingerprint_result` 27.76s,
`test_concurrent_appends_keep_valid_chain` 10.01s, `test_api_verify_reports_valid_chain` 9.92s.

**Skip named (only one):** `tests/unit/test_preflight.py::…` — *SKIPPED: "ML stack genuinely installed
in this environment."* This is a deliberate inverted guard: the test skips *because* the optional heavy
dependency is present, so a green run is not mistaken for "ML verified." It is not a failure.

**Targeted counts captured this session (isolated, `pofa_test`):**

| Suite | Count | Result |
| --- | --- | --- |
| `tests/unit/test_migrations.py` | 8 | passed |
| `tests/unit/test_be030_ledger_contract.py` | 5 | passed |
| `tests/integration/test_be030_ledger_enforcement.py` | 7 | passed |
| `tests/unit/test_audit_guard.py` | 25 | passed |
| `tests/integration/test_schema_drift_gate.py` | 6 | passed |

### DoD-11 — documentation reconciled with dated corrections; exact working-tree state reported

**Corrections applied this task (all dated 2026-10-10, in the feasibility doc and this file):**
* §11.2's claim that the drift gate would "report real drift" if the model omitted the `CHECK` is
  **false** for Alembic 1.11.2 — corrected: `compare_metadata` does not inspect CHECKs, the count moves
  by 0, catalog test is the only guard.
* §7.4's `%`-hazard is located in SQLAlchemy's psycopg2 dialect, not PostgreSQL — corrected; the shipped
  function body is `%`-free.
* §6 adds the **TRUNCATE hole** (a `FOR EACH ROW` trigger does not fire on `TRUNCATE`) — the D-1-A choice
  does **not** close it; owner accepted it as open until a non-owner role exists.
* §4 D-2 gains the measured qualification that A is **one-shot**, not a standing guard.
* The **trigger `RETURN` bug** — see §3 below (FOUND→FIXED→VERIFIED).

**Working tree (exact):** see §4 "Working-tree state and commit proposal."

### DoD-12 — blocked items reported as blocked

See §2 "Open / blocked items." In particular the live-`pofa_dev` migration is **not** done and is
**gated**, and §13.15 is a read-only **partial**. This document does not claim BE-030 complete merely
because it exists; it claims the enforcement is **designed, shipped to `pofa_test`, and proven on a
disposable clone**, with the named open items surfaced.

---

## 2. Open / blocked items (reported as blocked, with the safe next step)

1. **Live `pofa_dev` has NOT been migrated.** It remains at `s9t0u1v2w029` with no enforcement. This is
   intentional and gated: applying `t0u1v2w3x030` to `pofa_dev` changes the runtime behaviour of every
   audited write on that database (D-2-A refusal, D-1 trigger). **Required before applying:** a fresh,
   verified `pg_dump` of `pofa_dev` **and** explicit per-step owner approval, with API/workers confirmed
   stopped. Options: (a) leave `pofa_dev` unenforced (dev only) and ship enforcement to staging/prod
   first; (b) migrate `pofa_dev` after a verified backup. **Safest next step:** (a) — do not touch live
   `pofa_dev` without a verified backup and explicit owner sign-off.

2. **§13.15 register test is a read-only partial** (see DoD-6 note). The register and its live
   re-query match exactly (36 in 7 ranges), but it is a manually run script, not a continuously
   enforced `pytest`, because §14 bars tests from reading live `pofa_dev`.

3. **TRUNCATE remains an open hole under D-1-A** (accepted). Closing it needs a dedicated non-owner
   application role (deployment/credential work outside a migration), after which `REVOKE` becomes
   effective and a `TRUNCATE` guard becomes meaningful.

4. **BE-029 carry-overs still open (not BE-030 scope, tracked here so they are not lost):** OQ-3
   (`external_subject`) remains an unanswered product decision; the API/worker restart after BE-029's
   live migration is still pending owner action.

5. **`test_migrations.py` module docstring** still names an older head in prose (`o5p6q7r8s025`); the
   authoritative `EXPECTED_HEAD` constant was bumped to `t0u1v2w3x030`. The docstring is non-load-bearing
   narrative and was already stale for three prior milestones; left as-is rather than silently rewritten.

---

## 3. Trigger bug — FOUND → FIXED → VERIFIED (this session)

**FOUND (on `pofa_be030_proof`, first clone run).** The D-1-A hatch branch in `audit_ledger_refuse_mutation`
bypassed with `RETURN OLD` for **every** operation. In a `BEFORE` row trigger the return value
*replaces* the row, so `RETURN OLD` on UPDATE silently reverted the sanctioned write to its pre-image.
Symptoms on that run: `d2a_tail_refusal = "NOT refused (BUG)"` and `midchain_asymmetry.covering_range_valid
= true` — i.e. a sanctioned UPDATE left the row untouched, so the tamper was never real, so D-2-A and the
anchored test could not fire.

**FIXED.** `FUNCTION_SQL` now returns `NEW` for UPDATE and `OLD` otherwise inside the hatch branch
(alembic `t0u1v2w3x030`, lines 75–79), with a comment recording the measured failure mode. The shipped
`test_hatch_permits_and_records_sanctioned_update` proves the sanctioned UPDATE now lands (`action`
becomes `sanctioned`) and the hatch is transaction-scoped (refused again after rollback).

**VERIFIED (post-fix clone artifact `p99_clone_proof.json`).**
`d2a_tail_refusal = PredecessorInvalid` (`refusing to append onto sequence 38264: event_hash mismatch at
sequence 38264`); `midchain_asymmetry.covering_range_valid = False`; sanctioned `in_domain_insert =
executed`; anchored `full_chain.valid = True` over 38,265 events. Note for the record: the **earlier
`p2a` feasibility measurement used the buggy `RETURN OLD`** — its "append refused / midchain" rows should
be read as pre-fix; this section supersedes them.

> **Evidence freshness (asserted, not assumed).** The authoritative clone artifact
> `D:/CODING/Scratch/be030/p99_clone_proof.json` has mtime **17:15:54**, which is *after* the trigger fix
> to the migration file (mtime **17:14:42**); reading the file back confirms the corrected values above
> (`d2a_tail_refusal` = `PredecessorInvalid`, `covering_range_valid` = `False`), not the stale pre-fix
> capture. A same-moment re-run was deliberately **not** performed: the clone currently sits at head with
> enforcement applied, so re-running would require first re-creating / downgrading the clone to
> `s9t0u1v2w029`, and the idle-clean `pofa_test` (the DoD-10 run had just finished against it) was not
> worth disturbing for a duplicate capture. The round trip (upgrade→downgrade→re-upgrade) and the
> D-2-A / anchored asymmetry are covered independently by the shipped catalog-pin and enforcement tests on
> `pofa_test`.

---

## 4. Working-tree state and commit proposal

_(Nothing has been staged or committed. Per §14/§4.1: do not stage, commit or push unless the owner
asks. This is a proposal only.)_

**Modified (tracked):** `alembic/env.py`, `backend/api/v1/endpoints/auth.py`, `backend/db/models.py`,
`backend/db/schema_drift_policy.py`, `backend/services/audit_ledger.py`, `openapi.json`,
`tests/audit_guard.py`, `tests/integration/test_audit_ledger.py`,
`tests/integration/test_be029_audit_ledger_history.py`, `tests/unit/test_migrations.py`, and the BE-030
task file itself.

**Untracked (new):** `alembic/versions/t0u1v2w3x030_be030_ledger_append_only.py`,
`tests/integration/test_be030_ledger_enforcement.py`, `tests/unit/test_be030_ledger_contract.py`,
`docs/BE-030 Audit Ledger Feasibility Evidence And Migration Design.md`, and this results doc.

**Not touched:** `pofa_dev` (revision unchanged), the `identity_retirement_archive` (BE-029 evidence),
any already-applied migration, any test weakened/skipped/deleted/re-paged.

**Proposed commit (owner approval required first):** a single `feat(backend): BE-030 audit-ledger
append-only enforcement + chain integrity` staging the BE-030 files enumerated above. Do not run
`git add -A`/`.`; stage the named paths explicitly.

---

## 5. Reproduction

```
# disposable clone: enforcement round trip (requires pofa_test to have no active connections)
backend/.venv312_repro/Scripts/python.exe D:/CODING/Scratch/be030/p99_clone_proof.py

# shipped enforcement + unit + drift on pofa_test (TEST_DATABASE_URL from _testurl.txt)
TEST_DATABASE_URL=$(cat D:/CODING/Scratch/be030/_testurl.txt) \
  backend/.venv312_repro/Scripts/python.exe -m pytest \
  tests/unit/test_migrations.py tests/unit/test_be030_ledger_contract.py \
  tests/integration/test_be030_ledger_enforcement.py tests/unit/test_audit_guard.py \
  tests/integration/test_schema_drift_gate.py -q -rs

# alembic check (reported separately from the containment gate above)
DATABASE_URL=$(cat D:/CODING/Scratch/be030/_testurl.txt) \
  backend/.venv312_repro/Scripts/python.exe -m alembic -c alembic.ini check

# read-only pofa_dev re-measurement / §10 register
backend/.venv312_repro/Scripts/python.exe D:/CODING/Scratch/be030/p1_remeasure.py
```