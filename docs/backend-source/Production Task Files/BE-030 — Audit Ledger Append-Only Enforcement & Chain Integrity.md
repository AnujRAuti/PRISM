# BE-030 — Audit Ledger Append-Only Enforcement & Chain Integrity

**Project:** Proof-Of-Action (PoA)
**Task ID:** BE-030
**Category:** Backend / Database / Audit Ledger / Data Integrity / Observability
**Priority:** High
**Status:** Not Started — blocked on decisions D-1 and D-2 (§4)
**Depends On:** BE-029 (results §14.6–§14.12), BE-028 (drift containment), BE-023 §4/§14 (append-only rules and the static guard)
**Blocks:** Any claim that the audit ledger is tamper-evident *by enforcement* rather than by convention

---

# 1. TASK OBJECTIVE

Make the audit ledger's append-only, tamper-evident property true **in the database**, and make the
application's own verification capable of detecting damage instead of only detecting it by accident.

BE-029 measured that today the property is an application convention plus a verifier that has to be
called by someone:

* PostgreSQL refuses neither `UPDATE` nor `DELETE` on `audit_ledger_events` — no trigger, rule,
  policy or privilege stands in the way.
* `append_event` links a new event onto whatever the current tail row *claims* its hash is, without
  recomputing it, so a single edited row silently re-bases every later event.
* Verification over a recent window reports `valid=True` on a database whose older history is
  damaged, which means the control that exists can be satisfied by a tampered ledger.
* One database in the estate (`pofa_dev`) already has 36 sequence numbers missing across 7 ranges.

BE-030 must not turn that into a green checkmark by weakening a test, deleting history, or inventing
identity or audit data. It must add enforcement that survives review, and it must state honestly what
cannot be enforced without a product decision.

---

# 2. MEASURED STARTING STATE

Every row below was measured during BE-029 and is reproducible with the scripts named in the results
document. **Do not re-derive these by reading the code and agreeing.** Re-measure on the current
database before writing any migration (§5).

| # | Fact | Measured value | Source |
| --- | --- | --- | --- |
| F-1 | Database objects to `UPDATE` on the ledger | **No** — row changed | results §14.6 |
| F-2 | Database objects to `DELETE` on the ledger | **No** — row gone | results §14.6 |
| F-3 | Rolled-back append burns a sequence number | **No** | results §14.6 |
| F-4 | Writer notices invalid history and stops | **No** — it kept appending onto a permanently invalid chain | results §14.6 |
| F-5 | Honest append after a rewritten tail | `previous_hash` **equals the stale stored hash** | results §14.11 |
| F-6 | `verify_chain(newest, newest)` on that damaged chain | **`valid=True`** | results §14.11 |
| F-7 | Symptom classes | `sequence gap before N (expected M)`, `missing predecessor for sequence N`, `event_hash mismatch at sequence N` | `backend/services/audit_ledger.py::verify_chain` |
| F-8 | `event_type` domain enforced in the database | **No** — Python only (`AUDIT_EVENT_TYPES`, `backend/db/models.py:982`, 94 members) | results §14.6 |
| F-9 | Out-of-domain `event_type` values in live data | **0** in `pofa_dev` (6,023 rows) and **0** in `pofa_test` (38,185 rows); no NULLs | results §14.9 |
| F-10 | `pofa_dev` chain | 6,023 rows, span 1..6,059, **36 missing numbers in 7 ranges** (5344-5349, 5374-5379, 5381-5384, 5386-5391, 5393-5396, 5671-5676, 5678-5681), **no hash mismatch anywhere** | results §14.6 |
| F-11 | `pofa_test` chain after a full 12-minute suite | 38,185 rows, span 1..38,185, 0 missing, no duplicate numbers | results §14.10 |
| F-12 | `payload` / `metadata` column type | **`json`, not `jsonb`** (`jsonb_set(json, …)` fails) | results §14.11 |
| F-13 | Ledger append serialisation | `pg_advisory_xact_lock(hashtext('poa_audit_ledger_append'))`, then `sequence = latest + 1` (`audit_ledger.py:220-241`) | code + measurement |
| F-14 | Enforcement objects visible to Alembic | **No** — the drift diff stayed at 3 operations, none ledger-related, under every variant | results §14.9 |

The 7 gaps in F-10 are the **consequence**, not the cause: because the writer can never skip a number
(F-3, F-13), a discontinuity can only mean rows were removed after the fact. BE-023 §4 records that
two test cleanups did exactly that historically.

---

# 3. SCOPE AND NON-GOALS

## 3.1 In scope

1. Database-level enforcement of append-only on `audit_ledger_events`, installed by a reviewed
   migration.
2. Chain-aware writing: the writer must not link onto a predecessor it has not validated (§8).
3. Anchored verification that a operator or health surface can trust, i.e. a control that cannot
   report `valid=True` over a damaged history (F-6) (§9).
4. A **read-only** reconciliation register for already-missing sequence numbers (§10).
5. Database enforcement of the `event_type` domain, if §11's feasibility holds on re-measurement.
6. A catalog-pinned test proving the enforcement exists, because the drift machinery cannot see it
   (F-14).
7. The two tooling/contract debts in §15 and §16, as scoped, decided items — not silent fixes.

## 3.2 Explicit non-goals

* **Never repair, renumber, backfill, rewrite or delete a ledger row** in `pofa_dev`, `pofa_test`,
  staging or production to make verification pass. This is inherited from BE-029 §11.3 and is
  absolute.
* Never falsify history to close the §10 gaps. The register records damage; it does not hide it.
* No user-identity work: OQ-3 (`external_subject`) is a separate open decision (BE-029 results §14.3).
* No change to the hash algorithm, `hash_algorithm`, `ledger_version`, or the genesis constant. A
  re-hash would invalidate every stored event hash at once.
* No weakening, skipping, deleting or re-page-sizing of an existing test to accommodate enforcement.
  If an enforcement makes a shipped test impossible, that is decision D-1, surfaced to the owner —
  not a test edit.

---

# 4. REQUIRED PRODUCT DECISIONS

BE-030 cannot be completed without two owner decisions. Both have a measured reason behind them;
neither is a hypothetical.

## D-1 — Does the application role lose the ability to mutate the ledger?

**Why it matters.** Only a refusing mechanism actually enforces (§6). But three shipped tests create
tamper damage by rewriting one ledger row inside a transaction that is rolled back — the shape BE-023
§4 *sanctions*:

* `tests/integration/test_audit_ledger.py::test_tamper_detection_with_rollback` (line 238)
* `tests/integration/test_audit_ledger.py::test_broken_link_detection_with_rollback` (line 256)
* `tests/integration/test_be029_audit_ledger_history.py::test_rewriting_an_event_is_detected_by_hash_recomputation`

Measured: a blanket `BEFORE ROW … RAISE EXCEPTION` trigger refuses those UPDATEs, so tamper detection
becomes untestable in-repository (§14.9).

| Option | Shape | Consequence |
| --- | --- | --- |
| **A (recommended)** | Trigger that refuses unless a narrowly-scoped, audited exception is set — e.g. a session-level `SET LOCAL` flag or a dedicated non-application role, and the exception path itself appends a ledger event | Enforcement is real for the application's own connection; tamper tests keep working; the escape hatch is itself observable |
| B | Blanket trigger, no exception | Strongest guarantee; **breaks three shipped tests**; tamper detection can then only be proven on disposable clones by scratch scripts, which no future developer will re-run |
| C | Enforcement only for `DELETE`, `UPDATE` left free | Deletion is what opened `pofa_dev`'s 36 gaps (F-10) and is never legitimate; payload tampering stays undetectable by the database but is still detectable by `verify_chain` |
| D | No database enforcement; app-layer checks + scheduled verification only | Zero migration risk; the ledger remains editable by anyone with SQL access, which is precisely the property under audit |

**Recommendation: A, with C as the fallback if A's exception path cannot be made auditable.** Do not
choose B without the owner explicitly accepting the loss of in-repository tamper testing.

## D-2 — What must the writer do when history is already invalid?

**Why it matters.** A "verify before append" writer is the direct fix for F-5/F-6. But `pofa_dev` is
already invalid (F-10), so a strict policy denies every audit write on the live development database
the moment it ships — measured: the writer currently appends into invalid history without complaint
(F-4).

| Option | Behaviour | Cost |
| --- | --- | --- |
| **A (recommended)** | Validate only the **immediate predecessor** (recompute its hash and compare); refuse the append if *that* row is damaged. Pre-existing gaps elsewhere in the chain are surfaced by metrics/alerting, not by refusing writes | Catches the re-basing attack at the first honest write after damage; keeps a gapped database writable |
| B | Full-chain check before every append | Strongest, and unusable: permanently refuses all writes on any database that has ever lost a row |
| C | Chain-wide checkpoint table: refuse only when the tail does not match the last published checkpoint | Detects rewriting a *tail* and re-basing; needs checkpoint publishing and its own integrity story |
| D | Keep the writer as-is; only add scheduled anchored verification + alerting | No write-path latency or refusal risk; damage is found on a schedule rather than at the next write |

**Recommendation: A for the write path plus §9's anchored verification for the read path.** B is
rejected on measurement, not on taste. Any option other than D changes runtime behaviour of every
audited write and needs the API/workers stopped during rollout.

> **Measured qualification, 2026-10-10 (feasibility doc §2e).** A is a **one-shot** control, not a
> standing guard. It refuses only the first append whose *immediate predecessor* is damaged; after
> that refusal, a later honest write re-bases onto a valid row and everything downstream becomes
> locally valid, so A never fires again for the original damage. A therefore catches the re-basing
> attack only if someone is appending; its durability against a tampered middle rests entirely on §9's
> anchored verification (and, for tail rewrites, D-2-C's checkpoint). The owner should read A as
> "refuse the next bad write," not "detect that history was broken."

## 4.1 Do not guess these policies

Do not infer D-1 or D-2 from the code, from a comment, from a prior task document, or from what
"most systems do". Do not pick the option that makes the test suite green. If neither decision has
been given, produce the feasibility evidence, the migration *design*, and the blocked-items report,
and stop. Installing an enforcement that silently breaks three tests, or that stops `pofa_dev` from
accepting audit writes, is a worse outcome than an unfinished task.

---

# 5. PHASE 1 — RE-MEASURE BEFORE ANY CODE

BE-029's numbers are a snapshot; `pofa_test` grew by 347 ledger rows during one integration run alone.
Before touching a migration:

1. Confirm the target: `SELECT current_database()`, `SELECT version_num FROM alembic_version`, row
   count, `min`/`max(sequence_number)`, `count(DISTINCT sequence_number)`, and span-minus-count.
   Do not trust `.env`, a shell variable or a displayed connection URL.
2. Re-run `verify_chain()` from the shipped module over the full range and over a recent window, and
   record both. If the window says valid and the full range does not, F-6 still holds.
3. Re-check F-8/F-9: distinct `event_type` values outside `AUDIT_EVENT_TYPES`, and NULLs.
4. Re-check F-12 column types.
5. Re-check that the enforcement objects are still invisible to the drift comparison (F-14).

Expected starting verdicts, all measured in BE-029: `pofa_test` is contiguous, `pofa_dev` has exactly
the 7 ranges in F-10 and no hash mismatch. Anything else is a new finding: stop and investigate
before proceeding.

---

# 6. ENFORCEMENT OPTIONS: WHAT WAS MEASURED, WHAT WAS REJECTED

Five variants were installed, used and dropped against a disposable clone (results §14.9). Outcome
vocabulary is the point: **refused** = the statement raises and the writer learns immediately;
**swallowed** = the statement reports success and nothing changes — the writer *believes it wrote*;
**changed/gone** = nothing enforced.

| Variant | `UPDATE` | `DELETE` | `append_event` | sanctioned tamper `UPDATE` | Verdict |
| --- | --- | --- | --- | --- | --- |
| none (current schema) | changed | gone | works | works | the hole |
| `BEFORE ROW` trigger, `RAISE EXCEPTION` | **refused** | **refused** | works | **refused** | the only enforcer; needs D-1 |
| rules spelled `DO NOTHING` | changed | gone | works | works | **rejected — a trap** |
| rules spelled `DO INSTEAD NOTHING` | **swallowed** | **swallowed** | works | **swallowed** | **rejected — silent no-op** |
| `REVOKE UPDATE, DELETE` from the connected role | changed | gone | works | works | **ineffective as deployed** |

Two rejections must be written down so nobody re-proposes them from a blog post:

* `DO NOTHING` **is not** a suppression. The default action still runs. A reviewer reading the
  catalog sees a rule named `…_refuse_delete` and believes the ledger is protected while it is fully
  mutable. `DO INSTEAD NOTHING` does suppress — and suppression is silent, which for an audit writer
  is worse than an exception: callers keep receiving success they did not earn.
* `REVOKE` cannot work until the application stops connecting as the table owner. Measured: both
  statements were allowed unchanged after the revoke, because owner privileges are implicit. Making
  this real requires a dedicated non-owner application role — deployment and credential work far
  outside a migration. Treat it as a separate task if the owner wants defence in depth on top of D-1.

> **New hole, measured 2026-10-10 (feasibility doc §2f).** Even with the `BEFORE ROW` trigger
> installed, `TRUNCATE audit_ledger_events` succeeds: a `FOR EACH ROW` trigger does not fire on
> `TRUNCATE`, §7.7 bars a `TRUNCATE` trigger as a fix, and `REVOKE` is inert while the application
> connects as the table owner. Measured on a disposable clone: truncating the full ledger left the
> trigger live, and the next three `append_event` calls rebuilt a chain that `verify_chain()` reports
> `valid=True` with `sequence_number` restarting at 1 — a silently reset ledger is *locally* valid.
> Choosing D-1-A therefore does **not** close TRUNCATE; the owner must accept it as an open hole until
> a non-owner role exists, or D-1-C/other is reconsidered with this fact in view.

---

# 7. TRIGGER DESIGN CONSTRAINTS

If D-1 selects A or B, the trigger must satisfy all of these; each is a measured failure mode, not a
style preference.

1. **`BEFORE ROW` on `UPDATE OR DELETE`**, `FOR EACH ROW`. Insert must remain untouched — measured:
   `append_event` continued to work with the trigger installed.
2. **Use `TG_OP`, never `TG_TAG`.** `TG_TAG` exists only in *event* trigger functions; a row trigger
   referencing it compiles and then fails every mutation with
   `column "tg_tag" does not exist` — a refusal for the wrong reason, and a confusing error for
   whoever hits it in production.
3. **Set `ERRCODE` explicitly** (e.g. `insufficient_privilege`) so the application can distinguish a
   policy refusal from an ordinary SQL error, and so the message is stable for tests to assert on.
4. **A bare `%` in a `RAISE` format string is a syntax hazard.** One placeholder per argument, and no
   unescaped `%` elsewhere in the literal.
   > **Corrected 2026-10-10 (feasibility doc §2b).** Measurement located this hazard in
   > SQLAlchemy's psycopg2 dialect, not in PostgreSQL: the identical function body compiled and
   > ran fine when sent through raw psycopg2, and only the ORM/`op.execute` connection path
   > doubled a bare `%` into `%%` and broke it. The reliable fix is a `%`-free `RAISE` body (branch
   > per `TG_OP`, no placeholders), which removes the dialect entirely as a variable.
5. **The D-1-A exception path must be narrow and self-documenting**: session-scoped (`SET LOCAL`),
   never role-broad, and its use must itself be recorded (a ledger event or an application log line
   with the same `source` discipline the writer already uses).
6. **Deterministic, index-free object names**, dropped in `downgrade()` in reverse order
   (trigger before function), and `CREATE OR REPLACE FUNCTION` so re-running is safe.
7. **Never** add `INSTEAD OF` rules, `TRUNCATE` handling by trigger, or any statement that mutates
   rows as a side effect of refusing to mutate them.

---

# 8. CHAIN-AWARE WRITING

The re-basing defect (F-5) is the one an attacker actually gets: edit one row's contents, leave its
stored `event_hash` alone, and every subsequent honest event chains onto the stale value while the
newest events continue to verify (F-6).

Required behaviour under D-2-A, inside the existing advisory lock (`audit_ledger.py:220`), so the
check and the link are atomic:

1. Read the predecessor exactly as `append_event` does now.
2. **Recompute** the predecessor's `event_hash` from its persisted fields using the same
   `compute_event_hash` path the verifier uses — do not copy the stored column.
3. If the recomputed hash differs from the stored one, refuse the append with a typed error naming
   the predecessor's sequence number. Do not silently re-anchor, and do not "repair" the row.
4. Keep every existing invariant: sequence = predecessor + 1, genesis handling for the first row,
   `scrub_sensitive` on the payload, and `commit=False` default so domain mutation and audit row
   still commit or roll back together.
5. Preserve rolled-back-append behaviour (F-3): a refused or aborted append must not burn a number.
   Re-run the existing test for this after the change (§13).
6. Do not add a second writer path. `append_event` stays the only place a ledger row is created;
   domain services must not gain a "force append" bypass.

Note the interaction with §7: a trigger that refuses `UPDATE` makes step 3 unreachable for *future*
damage but does not make it unnecessary — a `DELETE` from the middle of the chain (D-1-C allows it to
be the only refusal) produces `missing predecessor for sequence N`, which step 3 must also detect.

---

# 9. ANCHORED VERIFICATION AND CHECKPOINTS

A bounded, recent-window check is not a control (F-6). BE-030 must make "the ledger is intact" an
answer that cannot be obtained by looking only at the tail.

Required:

1. A verification entry point that **anchors from sequence 1** (or from the last published checkpoint
   plus the full range since it) and reports, separately: hash/link failures, gap ranges as
   `from..to` pairs with counts, and the span-minus-count arithmetic.
2. Expose the three symptom classes distinctly, because they mean different incidents:
   `event_hash mismatch` = rewritten contents; `missing predecessor` = the row a specific event
   chained onto is gone; `sequence gap` = rows removed from the middle.
3. Cost must be explicit. `pofa_test` holds 38k events and `pofa_dev` 6k today; full-chain
   verification recomputes every hash in Python. So: run it out-of-band (scheduled job / admin
   endpoint), never on a request path, and record duration in the acceptance report.
4. If D-2-C or D-1-A involves checkpoints, the checkpoint table itself is append-only and must be
   covered by the same enforcement, or the control is only as strong as its weakest table.
5. Alerting on a *newly detected* failure, not on a known-false baseline: with F-10 present in
   `pofa_dev`, an alert that fires on "chain invalid" is noise from day one. Anchor the comparison to
   the §10 register.

---

# 10. HISTORICAL GAP RECONCILIATION — READ-ONLY

`pofa_dev`'s 36 missing numbers currently make six named audit-chain tests fail on any database
inheriting that data (BE-029 results §7.2), and make full-chain verification permanently false.

Permitted:

* A read-only query listing every missing range with counts and the surviving neighbours' timestamps,
  so the gaps can be correlated with the BE-023-recorded test cleanups that produced them.
* Recording that register in the repository (e.g. a documented table under `docs/`) as the baseline
  of *known* damage, so §9.5 can alert on new damage only.
* Appending an event through the normal writer that records the reconciliation itself, if the owner
  wants the act of reconciling in the ledger.

Forbidden, absolutely: creating rows to fill the ranges, editing `sequence_number`, deleting
surviving rows to shorten the span, re-hashing to make `verify_chain` agree, or truncating and
replaying. If the owner later chooses a repair, that is a new task with its own evidence package,
backup and approval — not a BE-030 sub-step.

---

# 11. EVENT TYPE DOMAIN ENFORCEMENT

F-8/F-9: the domain lives only in Python, and raw SQL inserted an out-of-domain type successfully —
while **0** of 6,023 `pofa_dev` rows, **0** of 38,185 `pofa_test` rows, and 0 scratch rows are outside
the 94-member set, and no row has NULL `event_type`. So a `CHECK` is addable to current data on both
databases with no cleanup.

Requirements:

1. Re-measure F-9 per §5 on every target database *first*. If any database has out-of-domain values,
   stop: adding the constraint would fail there, and "clean the data so the constraint fits" is the
   kind of move this task exists to refuse.
2. Declare it in **both** the model and the migration. F-14 shows the drift machinery does not see
   triggers or rules; a named `CHECK` on a mapped table is visible, and omitting it from the model
   would make the gate report real drift.
   > **Corrected 2026-10-10 (feasibility doc §2a).** Measurement falsified the second half of this
   > sentence: Alembic 1.11.2's `compare_metadata` does not inspect `CHECK` constraints at all, so
   > installing the event-type `CHECK` moves the drift count by **0** operations and the gate reports
   > CLEAN with or without it. Declaring it in the model is still correct hygiene, but do **not**
   > rely on the drift gate to catch an absent `CHECK` — §13.6's catalog-pinned test is the only
   > protection, exactly as it is for triggers and rules.
3. A 94-value `IN` list is a maintenance coupling: the Python enum is the source of truth, so the
   migration must be generated from `AUDIT_EVENT_TYPES` and a test must fail if the two diverge
   (§13). Do not hand-copy the list into SQL.
4. Note the lock cost: `ADD CONSTRAINT … CHECK` requires a brief exclusive lock and validates every
   existing row. Order it after the enforcement trigger in the migration and measure it (§13).
5. A `CHECK` prevents an out-of-domain *insert*; it does nothing about `UPDATE`/`DELETE`. It is not a
   substitute for D-1.

---

# 12. MIGRATION REQUIREMENTS

1. One new revision with a single linear down_revision from the current head. Verify the head from
   `alembic heads` at execution time; BE-029's pair (`r8s9t0u1v028`, `s9t0u1v2w029`) is the *current*
   head only until this task adds to it.
2. **Guarded upgrade** in the BE-029 §6 check-12 style: the migration must refuse to run when its
   assumptions are violated — out-of-domain `event_type` values present, NULLs, a non-contiguous span
   where the migration claims otherwise, or a target database whose `current_database()` is not the
   authorised one. Fail with a message that says *which* assumption failed.
3. **Symmetric downgrade**: drop trigger before function, drop the `CHECK`, and prove the round trip
   on a disposable clone of *each* shaped database (`pofa_test`-shaped and `pofa_dev`-shaped, which
   differ by exactly the F-10 gaps).
4. **Never** rewrite an already-applied migration, never bypass the armed-context guards, never add
   destructive SQL outside a reviewed migration, and never run a downgrade against a live database.
5. Test every migration change on a disposable clone first; keep the original record values in the
   `identity_retirement_archive` untouched — it is BE-029's evidence and this task has no authority
   over it.
6. Because enforcement objects are invisible to autogenerate (F-14), add a **catalog test** (§13) as
   the only real protection against someone dropping the trigger and the gate reporting CLEAN.

---

# 13. TEST REQUIREMENTS

No requirement below may be met by a mock, and skips do not count as passes. Enrol all new ledger
tests in the existing markers so they are selectable and counted.

## 13.1 Enforcement (integration, disposable target)

1. The database **refuses** an `UPDATE` of a ledger row: assert the raised error class and message.
2. The database **refuses** a `DELETE` of a ledger row: same shape.
3. Negative control: `INSERT` through `append_event` still succeeds while both refusals are active.
4. D-1-A path: with the exception set, the sanctioned rollback-guarded `UPDATE` still works; without
   it, it is refused. Both halves, because the exception is the risky part.
5. The exception path is itself observable (a logged or appended record of its use).
6. Catalog pin: `pg_trigger` / `pg_rewrite` / `pg_constraint` state asserted by name, so a silently
   dropped enforcement fails a test even though the drift gate cannot see it (F-14).
7. Alembic round trip on a disposable clone: upgrade → enforcement present → downgrade → absent →
   upgrade → present again, with the ledger's span and row count unchanged throughout.

## 13.2 Chain-aware writing (integration)

8. Rewriting the tail row's payload and then appending: the append is **refused**, and the damaged
   row is left untouched (results §14.11, as a permanent test rather than a scratch probe).
9. A `verify_chain` range that starts after a rewrite reports valid for its own window *before* the
   fix and is caught by the anchored check afterwards — pin F-6 so nobody reintroduces it.
10. The three symptom classes are each produced and each reported distinctly.
11. Predecessor recompute does not break: genesis row, first append after a rolled-back append
    (no burned number — re-run BE-029's existing test), and concurrent appends under the existing
    thread test.
12. D-2 policy test: on a database whose history is already invalid (gap in the middle), document the
    chosen behaviour as a test, not as a comment. If D-2-A was chosen, appends beyond the gap must
    still succeed while the gap is reported.

## 13.3 Event-type domain

13. An out-of-domain `event_type` inserted by raw SQL is **refused by the database**.
14. Every member of `AUDIT_EVENT_TYPES` is present in the constraint, and nothing extra — generated
    comparison, so the Python/SQL coupling in §11.3 cannot rot.

## 13.4 Reconciliation and hygiene

15. The §10 register matches the live missing-range query exactly (a test that fails if new damage
    appears, and passes only against a disposable or read-only target).
16. `tests/audit_guard.py` still reports `violations: 0` over the whole tree, and its own regression
    file still pins the `delete(Model)` / `update(Model)` construct spellings — BE-029 §14.8 closed
    that blind spot; a narrower guard is a defect, not a simplification.
17. Any new test touching the ledger may only add rows, or mutate inside a rolled-back transaction.
    No `DELETE`, `TRUNCATE`, or bulk `update()` in the test tree, with or without rollback.

---

# 14. DATABASE SAFETY RULES

Inherited verbatim from BE-029 and applicable without exception:

* Never downgrade, reset, recreate or cleanup-SQL live `pofa_dev`.
* Never use live `pofa_dev` or `pofa_test` for automated integration tests, probes, seed data or
  `TestClient` scripts; those must run against an explicitly named disposable target and be refused
  otherwise by `backend/db/safety.py`'s armed contexts (`pytest` / `verification`).
* Do not run a migration against a database until its `current_database()` **and** Alembic revision
  have both been verified from the server, not from `.env` or a printed URL.
* Keep the API, workers, schedulers and other writers stopped during any approved database-changing
  operation, and say so in the evidence.
* Do not print credentials in logs or in this task's evidence.
* Nothing in this task may mutate a live row without a verified mapping on a disposable clone plus
  explicit owner approval.
* Git discipline: inspect status and diffs first; preserve other people's and earlier work; never
  `git add .` / `-A`, `git clean`, `git reset --hard`; do not revert unfamiliar files; do not stage,
  commit or push unless the owner asks.

---

# 15. TOOLING DEBT — THE ALEMBIC NULLS-NOT-DISTINCT ARTIFACT

BE-029 §14.7 measured and corrected the attribution: SQLAlchemy 2.0.52 **does** reflect
`postgresql_nulls_not_distinct=True`; Alembic 1.11.2's
`autogenerate/compare.py::_make_unique_constraint()` rebuilds the reflected constraint from column
names and name alone and discards `params["dialect_options"]`. The result is a permanent
`remove_constraint` / `add_constraint` pair on `user_role_assignments.uq_user_role_scoped`, so the
repository's drift gate says CLEAN while `alembic check` fails by construction.

BE-030 owns the tooling fix, and only these two shapes are acceptable:

1. Upgrade Alembic to a version that carries dialect options through the comparison, then re-measure
   the diff and, if the pair disappears, **delete the baseline entry** in
   `tests/schema_drift_baseline.py` so the gate shrinks rather than accumulates exceptions; or
2. Add a reviewed, named autogenerate filter for this specific pair, with the reason text and the
   pointer to the measurement.

Forbidden: deleting `postgresql_nulls_not_distinct=True` from the model
(`models.py:1567`) to make `alembic check` go quiet. That would change the constraint's semantics —
NULL scopes would stop comparing as equal, which the BE-025 assignment matrix depends on — and §14.7
measured that no current row would notice, so the weakening would be invisible.

---

# 16. CONTRACT DEBT — PAGINATION ENVELOPE (DECIDE, DO NOT SILENTLY FIX)

BE-029 §14.5 found the same endpoint family inconsistent: `/users`, `/organizations`, `/units` and
`/users/{id}/roles` return `{items, limit, offset, total}`, while `GET /api/v1/auth/roles`
(`auth.py:445-458`) and `GET /api/v1/auth/permissions` (`auth.py:461-474`) accept `limit`/`offset`
and return a **bare list with no total** — a client cannot tell a truncated list from a complete one.

This is an owner decision, because it changes the published OpenAPI contract and every existing
consumer. BE-030 must either (a) record the decision to keep bare lists and document that these two
endpoints are report-only enumerations, or (b) implement the envelope with a documented breaking
change and updated contract tests. It must not be "fixed" incidentally while touching other files.

---

# 17. STOP CONDITIONS

Stop and report rather than pushing through if any of these occur:

1. Either D-1 or D-2 is unanswered. Feasibility evidence and design may proceed; enforcement code and
   migrations that install refusals may not.
2. Re-measurement contradicts §2 (new gaps, a hash mismatch, out-of-domain `event_type` values, or a
   database where the enforcement already exists). New damage is an incident, not a starting point.
3. The chosen enforcement breaks a shipped test. Report which test, which assertion, and what the
   enforcement prevents. Do not edit the test.
4. `current_database()` or the Alembic revision is not the authorised one.
5. The migration proposes anything beyond: adding enforcement, adding the domain `CHECK`, and (if
   D-2-A/C) new checkpoint objects. Unexpected `drop_*` operations mean the target is not the schema
   assumed.
6. A writer-side validation makes an existing database refuse all audit writes — that is D-2-B in
   disguise; stop and surface it.
7. The full suite shows a regression attributable to this task, or a failure this task cannot explain.
   An unidentified failure is not a pass.
8. Evidence would require touching live rows with no verified mapping, or any repair/backfill of
   ledger history.

---

# 18. DEFINITION OF DONE

BE-030 is complete only when all of the following are true and each is backed by a command, a target
database, and a measured number — not by a claim in a document:

1. The database refuses an `UPDATE` and a `DELETE` of a ledger row for the application's normal
   connection path, asserted by tests 1 and 2 (§13.1), with the chosen D-1 option named in the
   evidence.
2. `append_event` can no longer link onto a predecessor whose stored hash does not recompute (test
   8), while inserts, contiguity, no-burned-number and concurrency behaviour are all still proven.
3. An anchored verification path exists that reports `invalid` on the tampered-database shape that
   §14.11 measured, and the recent-window blind spot (F-6) is pinned by a test so it cannot return.
4. Enforcement is installed by one reviewed, guarded migration with a proven symmetric downgrade on
   both `pofa_test`-shaped and `pofa_dev`-shaped disposable clones, and is pinned by a catalog test
   that fails if the object is dropped.
5. Either the `event_type` `CHECK` is shipped with the Python/SQL equality test (14), or the reason
   it was not is recorded as a decision.
6. `pofa_dev`'s 36 missing numbers are reconciled **read-only**: a register exists, its contents match
   a live query, no row was created, edited, renumbered or deleted, and alerting distinguishes known
   damage from new damage.
7. §15's tooling debt is resolved in one of its two allowed shapes, with the drift baseline entry
   either deleted or explicitly justified, and `alembic check` and the containment gate reported
   **separately** — the schema is not declared fully clean merely because the custom gate returns
   CLEAN.
8. §16's envelope question carries an owner decision, not an incidental change.
9. `tests/audit_guard.py` reports `violations: 0`, its regression file still pins every DELETE and
   bulk-UPDATE spelling, and no test in the tree deletes or bulk-updates ledger history.
10. Full matrix re-run on the explicitly named disposable target: unit and integration counts,
    durations, every skip named with its reason, and zero unexplained failures. Skips are not passes.
11. Documentation is reconciled with dated corrections wherever this task's measurements contradicted
    earlier text, and the exact modified/untracked working-tree state is reported.
12. Blocked items are reported as blocked: the missing decision, why it matters, the options, and the
    safest recommended next step. **Do not claim BE-030 is complete merely because this file exists**
    or because enforcement was designed but not installed.
