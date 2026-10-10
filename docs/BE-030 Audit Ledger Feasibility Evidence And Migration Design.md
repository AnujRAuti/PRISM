# BE-030 — Audit Ledger Append-Only Enforcement & Chain Integrity: FEASIBILITY EVIDENCE, MIGRATION DESIGN, AND BLOCKED ITEMS

Task file: `docs/Production Task Files/BE-030 — Audit Ledger Append-Only Enforcement & Chain Integrity.md`

Status: **Phase 1 (§5) and the §6/§7/§8/§11 feasibility work are done and measured. No
enforcement has been installed in `pofa_test` or `pofa_dev`, and no migration has been
written.** §4.1 and §17.1 permit exactly this: feasibility evidence, migration *design*,
and a blocked-items report. Enforcement code and migrations wait on D-1 and D-2.

Dates: measurements taken 2026-10-10. Interpreter `backend/.venv312_repro`. Docker Desktop
had to be restarted at the start of this pass (its containers were down); no measurement
preceded that restart.

---

# 1. Phase 1 — §5 re-measurement, before any code

Both live databases were confirmed from the server (`SELECT current_database()`, not from
`.env`), then measured read-only under `set_session(readonly=True)`, with the shipped
`verify_chain()` used for every verdict. Scripts: `D:/CODING/Scratch/be030/p1_remeasure.py`;
outputs `p1_pofa_dev.json`, `p1_pofa_test.json`.

| Fact | §2 recorded | Measured 2026-10-10 | Agrees? |
| --- | --- | --- | --- |
| Head revision | `s9t0u1v2w029` | `s9t0u1v2w029` on both | yes |
| `pofa_test` ledger | 38,185 rows, span 1..38,185, 0 missing | **38,261 rows, span 1..38,261, 0 missing**, distinct = count | yes (grew by 76, as §5 predicts) |
| `pofa_dev` ledger | 6,023 rows, span 1..6,059, 36 missing in 7 ranges, no hash mismatch | **6,023 rows, span 1..6,059, 36 missing in the same 7 ranges, zero hash mismatch anywhere** | yes |
| F-6 (window reports valid on damaged history) | measured in §14.11 by scratch tamper | **reproduced on live `pofa_dev` with no tampering at all**: `verify_chain(from=6059)` → `valid=True`; `verify_chain()` full → `valid=False`, 7 failures | yes, and now on real data |
| F-7 symptom classes | 3 classes | `pofa_dev` full range produced **7 × `sequence gap`, 0 × `event_hash mismatch`, 0 × `missing predecessor`** | yes |
| F-8/F-9 `event_type` domain | Python only; 0 out-of-domain, 0 NULL | **0 out-of-domain and 0 NULL on both**; no CHECK in the catalog; distinct values in use: `pofa_dev` 50, `pofa_test` 71 of the 94 members | yes |
| F-12 column types | `json` not `jsonb` | `payload`/`metadata` = **json**; `sequence_number` = bigint; hashes varchar | yes |
| F-1/F-2 (no refusal) | proved by mutating a clone | established **from the catalog on the live databases** — 0 triggers, 0 rules, 0 policies, `relrowsecurity = false`, and `current_user = table owner = postgres` holding `UPDATE` and `DELETE` | yes, without touching a row |
| F-14 (drift machinery) | 3 operations on the BE-029 assumptions clone | **2 operations on both live databases** (the `uq_user_role_scoped` pair), `mentions_ledger = false` | shape agrees; the count differs and is explained in §2.1 |
| Ledger constraints present today | not listed | `audit_ledger_events_pkey`, **`uq_audit_ledger_sequence`** — i.e. the sequence is already unique, but nothing stops mutation | new detail |

Cost, measured (§9.3 asked for it to be stated): full-chain verification of 38,261 events takes
**9.503 s**; 6,023 events take **2.099 s**; a 500-event window takes 0.087–0.136 s; one event
0.007 s. So a request-path full verification is impossible, and an out-of-band job is the only
shape that fits.

**Phase 1 verdict: nothing contradicts §2.** No new gaps, no hash mismatch, no out-of-domain
values, no pre-existing enforcement. §17.2 does not fire, so the work could proceed.

### 2.1 The drift count difference is not a contradiction

The §2 figure came from `pofa_be029_assumptions`, a clone taken mid-BE-029. Both live
databases now report 2 operations, not 3, and the two are the `remove_constraint` /
`add_constraint` pair on `user_role_assignments.uq_user_role_scoped` — which is precisely
what `tests/schema_drift_baseline.py` still carries as its only accepted entries. The
containment gate therefore says CLEAN (2 observed, 2 accepted) while `alembic check` fails
by construction. Reported separately, as §18.7 requires.

---

# 2. Corrections to the task file, each from a measurement

These are findings against BE-030's own text. They must be settled before the migration is
written, because two of them change what protects what.

**(a) §11.2 is wrong about the `CHECK`, and it matters.**
§11.2 says a named `CHECK` on a mapped table is visible to the drift machinery, so omitting
it from the model "would make the gate report real drift". Measured on the enforced clone
(`p2b_check_visibility_and_latency.py`):

| State of the clone | drift operations | mentions the constraint |
| --- | --- | --- |
| `ck_audit_ledger_event_type_domain` present (94-member IN list) | **2** | **no** |
| constraint dropped again | **2** | no |

Alembic 1.11.2 does not compare `CheckConstraint` at all. Consequences: the gate cannot
protect the domain constraint in either direction; declaring it in the model is still
correct (documentation, and future Alembic versions will start seeing it) but it buys no
containment today; and §13.6's catalog test is not a belt-and-braces extra, it is the
**only** protection for the trigger, the function and the `CHECK`.

**(b) §7.4's `%` hazard is sharper than "a syntax hazard".**
A `RAISE EXCEPTION '... % ...', TG_OP` body sent through SQLAlchemy `text()` reached the
server as `'... %% ...'` and the function failed to compile. Control: the identical plpgsql
body sent straight through psycopg2 with no bound parameters **compiled fine**. So the
doubling is SQLAlchemy's psycopg2 dialect, not plpgsql, and since a migration runs through
exactly that dialect the rule for BE-030 is: **no `%` in the trigger's messages at all.**
The shipped design uses one branch per operation (`TG_OP` tested in PL/pgSQL, a literal
message each), which also gives tests a stable string (§7.3).

**(c) D-1-A's escape hatch must be `SET LOCAL`, never `SET` — measured, not assumed.**
On the enforced clone, `SET poa.ledger_mutation_exception = 'true'` (session scope) let the
next statement rewrite a ledger row and **stayed effective for that connection until
`RESET`**. With a pooled connection that is a permanently open hatch handed to whoever
borrows it next. `SET LOCAL` inside the transaction worked, and the very next transaction
was refused again. §7.5 said "session-scoped (`SET LOCAL`)"; the measurement is what makes
it a hard requirement, and a test must pin the leak.

**(d) A refusal arrives as SQLSTATE 42501 wrapped in `ProgrammingError`.**
`psycopg2.errors.InsufficientPrivilege` is what the trigger's `ERRCODE` produces, but
SQLAlchemy re-raises it as `sqlalchemy.exc.ProgrammingError`. Application code that wants to
map "policy refusal" must read `orig.diag.sqlstate`, never the wrapper class — the same
discipline BE-029's `identity_conflict()` uses (`orig.diag.constraint_name`, never
SQLSTATE). Tests assert on 42501 plus the message.

**(e) D-2-A is a one-shot control. This is the most consequential finding.**
The re-basing attack (F-5) can be refused — measured — but only for the *first* honest write
after the damage. Sequence on the enforced clone (`p2f_writer_ordering.py`):

| Step | Result |
| --- | --- |
| 1. tail event 38384 rewritten and committed (trigger dropped for the damage, reinstated after) | damage is pre-enforcement history, exactly `pofa_dev`'s shape |
| 2. predecessor-checking writer appends | **refused** — `refusing to append: predecessor sequence 38384 does not verify (event_hash mismatch at sequence 38384)` |
| 3. shipped `append_event` appends instead | succeeds as 38385 with `previous_hash` **equal to the tampered row's stale stored hash** |
| 4. predecessor-checking writer appends again | **succeeds** (38386) — the new tail is locally self-consistent |
| 5. `verify_chain(from=38385)` | `valid=True, checked=2` on a chain with a damaged row one below it |
| 5. `verify_chain(from=38383)` (last known-good anchor) | `valid=False`, `event_hash mismatch at sequence 38384` |

So §8's step 3 is necessary and it is not sufficient. The refusal window is a single write,
and any writer that gets there first — the current shipped writer, a worker, a retry —
closes it permanently. The durable controls are the anchored check (§9) and, if the owner
wants the write path itself to be durable, the checkpoint of D-2-C.

**(f) `TRUNCATE` is not covered, and cannot be covered by the means §7 allows.**
On a purpose-built throwaway (`pofa_be030_trunc`, `p2g_truncate_hole.py`):

```
enforcement present (1 trigger) + 38,385 events
TRUNCATE TABLE audit_ledger_events  -> executed. rows now 0. trigger survived.
3 new appends                        -> sequence restarts at 1
verify_chain() full                  -> valid=True, checked_events=3
```

A `BEFORE ROW` trigger never fires for TRUNCATE; §7.7 forbids a TRUNCATE trigger; and
`REVOKE` cannot help while the application connects as the table **owner** (measured
`has_table_privilege(current_user,'TRUNCATE') = true`, owner = `postgres`). Total-loss tamper
followed by a rebuilt chain is therefore invisible to every link-based verifier, including an
anchored one whose checkpoint lives in the same database and is equally truncatable. §9.4's
"the checkpoint table must be covered by the same enforcement" is true but insufficient: a
checkpoint needs something *outside* the database to be worth anything (a published digest
in application logs or an external store), otherwise D-1 protects UPDATE/DELETE and leaves
the destruction case open. That belongs in the D-1 decision, not in a footnote.

**(g) The enforcement costs nothing measurable; the writer check costs 0.568 ms.**
20 appends through the enforced table: 20.65 ms each with the trigger, 54.69 ms without (the
"without" run was the first after a reinstall, so the ordering means this is a warm-cache
observation, not a speed-up: the defensible claim is **no measurable penalty**). One
`verify_event()` recompute of the predecessor: **0.568 ms** against a 22.83 ms append —
about 2.5%. Cost is not an argument against any option here.

---

# 3. D-1 as measured, so the decision is about the hatch

Blanket trigger (option B) was run against the shipped tests on the enforced clone:

```
TEST_DATABASE_URL=...pofa_be030_scratch  pytest tests/integration/test_audit_ledger.py
                                                    tests/integration/test_be029_audit_ledger_history.py
3 failed, 11 passed in 69.23s
FAILED test_audit_ledger.py::test_tamper_detection_with_rollback
FAILED test_audit_ledger.py::test_broken_link_detection_with_rollback
FAILED test_be029_audit_ledger_history.py::test_rewriting_an_event_is_detected_by_hash_recomputation
```

Exactly the three tests D-1 predicted, and nothing else: the refusal does not disturb
inserts, the API audit trails, or the other eleven ledger tests. Option A's mechanism works
(`SET LOCAL` → rowcount 1, refused again next transaction), so choosing A means **those
three shipped tests each gain one statement** (`SET LOCAL poa.ledger_mutation_exception =
'true'` before the sanctioned rewrite) plus an assertion that the hatch is transaction-bounded
and observable. That is not a weakening: it moves the tamper simulation from "silently
allowed by an unguarded table" to "explicitly permitted, per transaction, and recorded", and
§13.1.4/5 make both halves testable. Option C (DELETE-only refusal) keeps all three tests
unchanged — the sanctioned shape is an `UPDATE` — but leaves payload tampering, the F-5
attack, entirely to the application, and §10's gaps are the deletion case, so C protects the
damage that actually happened and not the damage that is easiest to hide.

Recommended remains **A**, now with the hatch's two measured constraints (§2c leak, §2f
TRUNCATE hole) stated in the same breath.

---

# 4. Migration design (design only — nothing executed)

One revision, linear down_revision from the head verified at execution time (currently
`s9t0u1v2w029`). Objects, named deterministically, created in this order and dropped in
reverse:

1. function `public.audit_ledger_refuse_mutation()` — `CREATE OR REPLACE`, no `%`, `TG_OP`
   branches, `ERRCODE 'insufficient_privilege'`, `HINT` naming the GUC.
2. trigger `trg_audit_ledger_append_only` — `BEFORE UPDATE OR DELETE ... FOR EACH ROW`.
   (If D-1-C is chosen: `BEFORE DELETE` only.)
3. `CHECK (event_type IN (...))` named `ck_audit_ledger_event_type_domain`, the 94 values
   **generated from `AUDIT_EVENT_TYPES`** at migration time by importing the enum, never
   hand-copied, ordered for a stable diff. Declared in the model too, with the §2a note that
   the gate cannot see either side today.

Upgrade guards (§12.2), each failing with the assumption named:
`current_database()` equals the authorised name; the enum is non-empty and every stored
`event_type` is in-domain and non-NULL; the table exists with the expected columns; and the
refusal objects are absent before creation (so a re-run is a no-op, not an error).
`alembic/env.py` already logs the target and enforces the armed context, so the guard is
consistent with what BE-029 shipped.

Downgrade (§12.3): drop trigger → drop function → drop `CHECK`; proven symmetric on
**two** disposable clones shaped differently — `pofa_test`-shaped (contiguous) and
`pofa_dev`-shaped (the 7 §6 ranges) — with the ledger's row count, span and every surviving
`event_hash` unchanged across the round trip. Nothing in this migration reads or writes
ledger rows, so the downgrade cannot damage history.

Post-install expectations that the design commits to now, because they were measured:
the drift operation count stays at 2 and mentions neither the trigger nor the `CHECK` (§2a,
F-14); the write path adds no measurable latency (§2g); and `pg_trigger`, `pg_proc`,
`pg_constraint` become the authoritative pin for tests (§13.6).

---

# 5. Writer and verifier design, pending D-2

**Writer (§8, D-2-A).** Inside the existing advisory lock: read the predecessor, recompute
its hash with the shipped `verify_event`, and on mismatch raise a typed
`LedgerPredecessorInvalid` naming the predecessor's sequence — refuse, never re-anchor, never
repair. `append_event` stays the only writer. Measured behaviour to preserve: inserts keep
working under the trigger; a rolled-back or refused append burns no sequence number; a
mid-chain gap does **not** block writes (measured: prototype appended 38384 across a deleted
38356 while `verify_chain` reported `sequence gap before 38357` plus the pre-existing hash
mismatch). Stated plainly in the design so nobody later mistakes the one-shot property for
durable protection (§2e).

**Verifier (§9).** A full-history `verify_chain(db)` from sequence 1 (or from the last
published checkpoint) that reports separately: link/content failures, gap ranges as
`from..to` with counts, and the span-minus-count arithmetic. Out-of-band only — 9.5 s at
38k events today. Alerting compares against the §6 register, so `pofa_dev`'s known damage is
a recorded baseline rather than a permanently-false alarm (§9.5).

---

# 6. §10 reconciliation register — read-only, and the only permitted answer to the gaps

Re-derived live on 2026-10-10 from `pofa_dev` by `p1_remeasure.py` (anti-join over
`generate_series(min..max)` collapsed into contiguous ranges, plus each range's surviving
neighbours' `created_at`). `pofa_test` has **no** missing ranges: 38,261 rows, span
1..38,261, `span_minus_count = 0`.

`pofa_dev`: 6,023 rows, span 1..6,059, **36 missing numbers in 7 ranges, zero hash mismatch**

| # | Missing range | Count | Last survivor before (`created_at`) | First survivor after |
| --- | --- | --- | --- | --- |
| 1 | 5344–5349 | 6 | 5343 @ 2026-09-25 10:23:58.872112+00 | 5350 @ 2026-09-25 10:35:54.433672+00 |
| 2 | 5374–5379 | 6 | 5373 @ 2026-09-25 10:36:05.348290+00 | 5380 @ 2026-09-25 10:46:01.670131+00 |
| 3 | 5381–5384 | 4 | 5380 @ 2026-09-25 10:46:01.670131+00 | 5385 @ 2026-09-25 10:46:12.554569+00 |
| 4 | 5386–5391 | 6 | 5385 @ 2026-09-25 10:46:12.554569+00 | 5392 @ 2026-09-25 10:56:24.029439+00 |
| 5 | 5393–5396 | 4 | 5392 @ 2026-09-25 10:56:24.029439+00 | 5397 @ 2026-09-25 10:56:32.796019+00 |
| 6 | 5671–5676 | 6 | 5670 @ 2026-09-25 11:00:03.180854+00 | 5677 @ 2026-09-25 11:00:09.503430+00 |
| 7 | 5678–5681 | 4 | 5677 @ 2026-09-25 11:00:09.503430+00 | 5682 @ 2026-09-25 11:00:15.749669+00 |

Reading of the timestamps: every range is bracketed inside a single minute-to-twelve-minute
window on **2026-09-25**, in runs of 4 and 6 — which matches BE-023 §4's record of two test
cleanups that deleted ledger rows, not an ongoing deletion. Nothing here suggests an actor
outside the repository's own history, and the ledger names none of them.

Forbidden and not done: filling ranges, editing `sequence_number`, deleting survivors to
shorten the span, re-hashing to make `verify_chain` agree, truncating and replaying. If the
owner later wants a repair, §10 makes that a new task with its own evidence package.

For §13.15 the register is mirrored as a constant in the test module (the test recomputes
the live query and compares; it runs against a disposable or read-only target, and the
`pofa_dev` baseline is what makes "new damage" distinguishable from "known damage").

---

# 7. What is already proven against §13

| §13 requirement | Status today |
| --- | --- |
| 1, 2 UPDATE/DELETE refused | **proven** on the clone (42501, message per operation); needs to become a shipped test |
| 3 negative control: appends still work | **proven** (20 appends under live enforcement) |
| 4 hatch both halves | **proven** (`SET LOCAL` allowed / refused after) |
| 5 hatch observable | **not yet designed to a test** — must be application-side, since §7.7 bars the trigger from writing |
| 6 catalog pin | **proven necessary** (§2a: drift cannot see it) |
| 7 Alembic round trip | design in §4; **not executed** |
| 8 append after tail rewrite is refused | **proven** as a prototype |
| 9 window-valid-before/anchored-caught | **proven** (`verify_chain(from=38385)` valid, anchor at 38383 invalid) |
| 10 three symptom classes distinct | gap + hash mismatch **proven**; `missing predecessor` proven in BE-029 §14.11 and reproduced in p2e |
| 12 D-2 policy on a gapped database | **proven** appendable across a mid-chain gap |
| 13 out-of-domain raw SQL insert refused | **proven** (23514 after the `CHECK`) |
| 14 enum/constraint equality | mechanism proven (94 generated members, 0 out-of-domain in data); the shipped test is still to be written |
| 15 register matches live query | register rebuilt from a live query today (§6); shipped test still to be written |
| 16, 17 guard hygiene | `tests/audit_guard.py` unchanged by this pass; must be re-run before any commit |

---

# 8. Blocked items

**D-1 — enforcement shape.** Options A/B/C/D and their measured costs are in §3. What is
missing is the owner's choice. Why it cannot be guessed: B breaks three shipped tests today;
A requires editing those three tests to use an audited hatch; C leaves the payload-tampering
attack (the one that actually re-bases a chain) entirely to the application. Safest next
step: **A**, plus a recorded acceptance that TRUNCATE stays open until a non-owner role
exists (§2f).

**D-2 — writer policy.** §2e is the new fact: A is one-shot. If the owner wants the write
path itself to be durable, that is C (checkpoints), and C is only meaningful with a
checkpoint digest that survives a truncate — i.e. published outside the database. Safest next
step: **A for the write path, §9's anchored verification as the durable control, and the
checkpoint digest exported to the application log** so a rebuilt chain cannot be made to look
continuous.

**OQ-3 (`external_subject`)** — not BE-030's, unchanged, still open.

**§15 tooling debt** and **§16 envelope contract** — both need an owner choice
(upgrade Alembic vs a reviewed named filter; keep bare lists vs documented breaking
envelope). Neither is decided by anything in this repository.

---

# 9. Evidence artifacts

`D:/CODING/Scratch/be030/`: `p1_remeasure.py` (+ `p1_pofa_dev.json`, `p1_pofa_test.json`),
`p2a_install_and_probe.py` (+ `p2a.json`), `p2b_check_visibility_and_latency.py` (+
`p2b.json`), `p2e_writer_prototype.py` (+ `p2e.json`), `p2f_writer_ordering.py` (+
`p2f.json`), `p2g_truncate_hole.py` (+ `p2g.json`).

Databases touched: `pofa_test` and `pofa_dev` **read-only** (no statement in this pass
mutated either); `pofa_be030_scratch` (`TEMPLATE pofa_test`, holds the enforcement plus probe
appends and two deliberate pre-enforcement damage shapes) and `pofa_be030_trunc` (created to
be truncated). Both were reached only through `safety.arm_verification`, which refuses
`pofa_dev`/`pofa_test` outright. The API and workers remained stopped.

Post-cleanup inventory (2026-10-10): `pofa_be030_trunc` was dropped after the TRUNCATE probe —
its measurement is preserved in `p2g_truncate_hole.json`, so the DB itself is not needed to
re-read the finding. `pofa_be030_scratch` is **retained**: it is the only place the installed
enforcement objects and both damage shapes still exist, for re-verification once D-1/D-2 land.
