# BE-031 — Post-BE-030 Operational Readiness & Deferred Debt Closure — Results

**Disposition: COMPLETE WITH DOCUMENTED BLOCKERS.**

BE-031 was scoped by `docs/Production Task Files/BE-031 — Post-BE-030 Operational Readiness &
Deferred Debt Closure.md` (an untracked proposal; no earlier canonical BE-031 specification existed,
so this proposal is authoritative for scope). It is an **evidence-backed operational-readiness
assessment**, not a migration or enforcement rollout. Per §10, "if no implementation change is safely
justified, a well-evidenced readiness assessment and an explicit list of gated decisions is a valid
result." That is the outcome: **no application code changed, no database was migrated, no service was
restarted, nothing was staged, committed, or pushed.** Every unresolved item is either a deliberate
completed-BE-030 design decision, a defect-free observation, or an owner-gated decision.

Convention used throughout: **[MEASURED]** = executed this session against a named target, output
quoted; **[PRIOR]** = reproduced from an earlier results document, not re-run here; **[DOC]** = read
from a spec/backlog.

---

## A. Baseline

| Item | Value | Source |
| --- | --- | --- |
| Repository root | `D:/CODING/Projects/Proof-Of-Action-Final` | [MEASURED] `git` |
| Branch | `Backend`, tracks `origin/Backend`, no `[ahead/behind]` marker | [MEASURED] `git status -sb` |
| HEAD before **and** after | `07cb59a44cdf43b459ed00915fcad5c263e789b6` — "BE-30 Complete" | [MEASURED] `git log -1` (unchanged; no commit made) |
| Initial working tree | Clean except one **untracked** file: the BE-031 task proposal. No staged, no modified, no deleted paths. | [MEASURED] `git status --short` |
| BE-029 / BE-030 commits present locally | Yes — `22ce7497` "finalize BE-029 and prepare BE-030" and `07cb59a4` "BE-30 Complete" | [MEASURED] `git log` |
| Alembic head (script graph) | **Single linear head** `t0u1v2w3x030`; 25 revision files; `s9t0u1v2w029` (BE-029) is its direct parent | [MEASURED] `alembic heads` / `alembic history` |
| `pofa_test` — server identity | `current_database() = pofa_test`, `alembic_version = t0u1v2w3x030` | [MEASURED] read-only recon + `alembic current` |
| `pofa_dev` — server identity | `current_database() = pofa_dev`, `alembic_version = s9t0u1v2w029` (BE-029 head, **not** BE-030) | [MEASURED] read-only recon |
| Working interpreter | `backend/.venv312_repro/Scripts/python.exe` | per [[env-verification-interpreters]] |

Database targets were resolved from the **connection**, not the URL text, and cross-checked against
`current_database()` before and after every query, per §2.1. The read-only baseline script
(`D:/CODING/Scratch/be031/recon_baseline.py`, output `recon.json`) opened a `SET SESSION READ ONLY`
psycopg2 connection, issued `SELECT`-only statements, never printed the URL, and reported
`target_matches_expectation: true` for both databases.

Source documents inspected: the BE-031 proposal; `BE-030 Audit Ledger Append-Only Enforcement Results.md`
(§2 Open/blocked items, DoD-6, DoD-7); `BE-030 Audit Ledger Feasibility Evidence And Migration
Design.md` (historical gap register §6); `BE-029 User Identity Constraint Remediation Results.md`
(§"Open questions — final state of the record" OQ-1..OQ-6 — the authoritative identity backlog) and its
corrected §2; project memory `project-be030-status`, `project-be029-g3-backup`.

---

## B. Findings

Each finding is classified **pre-existing?** and **resolved / deferred / blocked(owner-gated)**.

### F-01 — Enforcement exists on `pofa_test`, absent on `pofa_dev` (expected, not a defect)
[MEASURED] `pofa_test` catalog has all three BE-030 enforcement objects
(`trg_audit_ledger_append_only`, `audit_ledger_refuse_mutation`, `ck_audit_ledger_event_type_domain`);
`pofa_dev` has none (`trigger_present/function_present/check_present = false`). This is a **correct**
consequence of `pofa_dev` still sitting at `s9t0u1v2w029`. Pre-existing by design. **Deferred** — closing
it means migrating `pofa_dev` (Appendix B), which is owner-gated.

### F-02 — `pofa_dev` historical chain gaps are unchanged (no new damage)
[MEASURED] `pofa_dev` ledger: 6,023 rows, `min_seq=1`, `max_seq=6059`, `distinct_seq=6023`,
**`span_minus_count = 36`, `gap_range_count = 7`**, `null_event_type = 0`. [PRIOR] BE-030 DoD-6 /
feasibility §6 recorded the *same* 36 missing numbers in the *same* 7 ranges
(5344–5349, 5374–5379, 5381–5384, 5386–5391, 5393–5396, 5671–5677, 5678–5681) with **0 hash mismatch**
on the survivors. The identical measured gap count on re-inspection means **no row was created, edited,
renumbered or deleted since BE-030** — the register is still accurate. BE-030's zero-hash-mismatch was
its own measurement; BE-031 re-measured span/gap only (a live `verify_chain()` hash walk of
`pofa_dev` was **not** re-run here — §2.4 forbids weakening/altering verification, and no write is
permitted to that ledger). Pre-existing. **Deferred** (repairing history is explicitly barred by §2.4;
the gaps are historical residue of two pre-BE-030 test cleanups, now closed by `test_no_test_deletes_audit_ledger_rows`).

### F-03 — The §9 durable read-path control is **not reachable over HTTP** (operational gap, by design)
[MEASURED] The only audit-verification endpoint, `GET /api/v1/audit/verify`
(`backend/api/v1/endpoints/audit_ledger.py:91-101`), calls `audit_service.verify_chain(db, from, to)`
and nothing else. `verify_chain_anchored()` and `ledger_checkpoint()`
(`backend/services/audit_ledger.py`) — the anchored whole-chain walk and the anti-`TRUNCATE` checkpoint
digest that BE-030 §9/D-2-A designated as the **durable** control — have **no endpoint, no scheduler
call, and no automatic caller**. The digest is emitted to the application log only *if something invokes
`verify_chain_anchored`*, and nothing in the running code does. Pre-existing (introduced deliberately
in BE-030 §9, which exported the digest to the log rather than the DB because a `TRUNCATE` erases an
in-DB digest). **Deferred / owner decision** — surfacing an admin-only anchored-verification endpoint is
new API surface and therefore barred by §10 without an owner call. Recorded as a readiness gap: today
the durable control is *proven by tests* but *unpolled by the application*.

### F-04 — No application-level distinction between *known* historical damage and *new* tampering
[MEASURED] `verify_chain()` classifies three symptoms distinctly ("sequence gap before N (expected M)",
"missing predecessor for sequence N", "event_hash mismatch at sequence N") but does **not** annotate
whether a reported gap is one of `pofa_dev`'s seven *known* ranges or a *fresh* integrity event.
[PRIOR] BE-030 DoD-6 states "alerting is anchored to this register so known damage is distinguished
from new damage" — but that anchoring is a **read-only script/registers in documentation**, not code:
there is no runtime component that consults the register, and §2.4/§14 bar a shipped test from reading
live `pofa_dev`. Pre-existing. **Deferred / owner decision** — implementing it needs a persisted-baseline
or signed-checkpoint design (a product/architecture choice), which BE-031 may document but not build.

### F-05 — `TRUNCATE` on the ledger is **not** mitigated by the shipped enforcement (needs a role change)
[MEASURED] On **both** `pofa_test` and `pofa_dev`: `table_owner = postgres`, `session_user = postgres`,
`has_truncate_priv = true`, `is_owner_of_table = true`, `role_memberships = []`. The BE-030 trigger is
`BEFORE UPDATE OR DELETE FOR EACH ROW`, which **does not fire on `TRUNCATE`**, and `REVOKE TRUNCATE` is
inert while the application connects as the table owner (owner privileges are implicit). So the current
effective role *can* truncate the ledger; only a fresh append-onto-a-rebuilt-chain would surface it,
which is exactly the silent-reset hole BE-030 §2f measured. Pre-existing and **accepted-open by owner in
BE-030 D-1-A**. **Blocked (owner + deployment)** — closing it requires a non-owner least-privilege
runtime role, i.e. a database-role architecture change, which §2.2 and §6.3 gate. Appendix D states the
precise prerequisite. Do **not** report `TRUNCATE` as protected: it is not, and no shipped test proves
the effective role is denied it.

### F-06 — `external_subject` is still a write-only declared key with no consumer (re-confirmed)
[MEASURED] `grep` over `backend/` (authoritative, current code) finds only the **write** path and the
model declaration for `external_subject`/`identity_provider`:
`db/models.py:50-51` (nullable `String(512)`, `identity_provider NOT NULL default "local"`),
`models.py:60` (`UniqueConstraint("identity_provider","external_subject")`),
`schemas/authorization.py:64-65`, `endpoints/auth.py:160-161`, `services/authorization.py:327,340-341`
(a missing subject defaults to `uuid4()`), `repositories/authorization.py:52-59` (plain insert).
**No query anywhere filters/joins/looks up on either column** — principal resolution keys on `User.id`
(`dev-user-<uuid>` → id). [MEASURED data] `pofa_test`: 2,710/2,710 rows `external_subject IS NULL`
(the API write path that always sets it clearly was **not** how those rows were created — they are
seeded). `pofa_dev`: 1,004/1,054 NULL (50 non-NULL, i.e. the only rows created through the service).
`identity_provider` distinct = `{local}` in both. The constraint `UNIQUE (identity_provider,
external_subject)` is byte-identical in both DBs and **inert for NULL** (PostgreSQL default NULLS
DISTINCT). Pre-existing. **Deferred / owner decision (BE-029 OQ-3)** — no NOT NULL, no backfill, no
policy invented. Full brief in Appendix A.

### F-07 — The §5 required write/read-path behaviors are shipped-tested (assessment, not a gap)
[MEASURED] Every §5-required behavior that is *testable without touching live `pofa_dev`* has a named
green test (targeted matrix, Appendix on results §G): valid append
(`test_append_negative_control_with_enforcement_live`, `test_append_chain_and_verify`); invalid
predecessor rejected (`test_append_refused_after_tail_tampering` → `PredecessorInvalid`); new corruption
not reported valid (`test_anchored_verification_catches_mid_chain_tampering` covering-range `valid=False`);
refused append/UPDATE creates no partial landing (`test_update_without_hatch_is_refused` re-verifies the
row; `test_failed_domain_operation_leaves_no_audit_row` count-unchanged); concurrent writers do not
bypass validation (`test_concurrent_appends_keep_valid_chain`, 10 threads → 10 distinct sequences, chain
valid); rollback preserves consistency (`test_tamper_detection_with_rollback`,
`test_hatch_permits_and_records_sanctioned_update` re-refused after rollback); out-of-domain INSERT
refused (`test_out_of_domain_insert_is_refused`, SQLSTATE 23514); enforcement visible in catalog
(`test_enforcement_objects_are_present_in_the_catalog`). Pre-existing + passing. **Resolved (assessed).**

### F-08 — Alembic reflection blind spots persist; catalog pins remain the mitigation
[MEASURED] `alembic check` on `pofa_test` detected a **changed unique constraint** on
`user_role_assignments.uq_user_role_scoped` purely as a `nulls_not_distinct` reflection artifact, then
**suppressed** it via the reviewed named filter in `backend/db/schema_drift_policy.py` (reason +
measurement pointer logged), ending `No new upgrade operations detected.` This is a live confirmation
that `compare_metadata` mishandles `NULLS NOT DISTINCT` and, per BE-030 feasibility §2a, reflects
neither CHECK constraints nor triggers. Pre-existing tooling limitation, already mitigated. **Resolved
(assessed as contained)** — the enforcement objects stay invisible to autogenerate by design, which is
why the catalog-pin tests (F-07) and the custom `test_schema_drift_gate.py` are the real guards.

---

## C. Changes made

**Repository code/test/schema changes: none.** No in-scope, reproducible, owner-approval-free defect was
found (§10 gate). Each finding in §B is either a completed design decision (F-03, F-08), a correctly-behaving
but unpolled control (F-03/F-04), historical data whose repair is barred (§2.4, F-02), an identity-policy
question that is not BE-031's to answer (F-06), or a role change requiring owner authorization (F-05).
Adding an anchored-verification endpoint, a known-vs-new alerting mechanism, or a NOT NULL/backfill would
each be new product/schema surface or an unauthorized live change, so §10 directs that they be documented
and gated rather than built.

Files **created** (outside the repo, scratch only, not tracked): `D:/CODING/Scratch/be031/`
— `recon_baseline.py`, `recon.json`, `run_targeted.sh`, `run_alembic.sh`, `full_clean.txt`. These are
diagnostics, deliberately not placed under `docs/` or `backend/`, and contain no secrets.

One **documentation** deliverable is created: this results file, `docs/BE-031 Post-BE-030 Operational
Readiness Results.md`. See §H for the one surgical backlog correction applied to the BE-029 record.

---

## D. Database safety

- `pofa_dev`: **read-only only.** All access was `SET SESSION READ ONLY` / `SELECT`. No INSERT, UPDATE,
  DELETE, TRUNCATE, DDL, cleanup, migration, restore, or integration test touched it. It remains at
  `s9t0u1v2w029`, ledger byte-for-byte consistent with BE-030's register (F-02: same 36/7).
- `pofa_test`: **writes occurred only through the sanctioned pytest armed context** (`TEST_DATABASE_URL`
  republished as `DATABASE_URL` before import by `tests/conftest.py`; `arm_pytest` + `confirm_server_database`
  proved `current_database() == pofa_test` before any write). This is a permitted test-database operation,
  explicitly distinct from a live operation. The two suites (full, targeted) were run **sequentially, never
  concurrently** (§11); an accidental third-party concurrent run was stopped before it could interleave.
- No operation bypassed `backend/db/safety.py`. The armed `verification` context refuses
  `pofa_dev`/`pofa_test` by design; read-only diagnostics were done over a raw read-only psycopg2 session,
  which is not a write path and does not require arming.
- **No audit-ledger row was created, edited, renumbered, or deleted on any database.** The only ledger
  growth is ordinary, honest appends emitted by the `pofa_test` suite itself (contiguous, chain-valid).

---

## E. Audit integrity

Measured chain state (read-only recon):

| Database | rows | min_seq | max_seq | distinct_seq | span−count | gap ranges | null event_type | enforcement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pofa_test` | 42,545 | 1 | 42,545 | 42,545 | **0** | **0** | 0 | trigger+fn+CHECK present |
| `pofa_dev` | 6,023 | 1 | 6,059 | 6,023 | **36** | **7** | 0 | none (pre-BE-030) |

`pofa_test`'s ledger is fully contiguous at BE-030 head. `pofa_dev`'s 36-missing-in-7-ranges matches the
BE-030 register exactly — no new damage (F-02). Enforcement objects verified present in `pofa_test`
catalog (F-01) and pinned by `test_enforcement_objects_are_present_in_the_catalog`. Integrity test
results: F-07 suite green. The `verify_chain` / `PredecessorInvalid` / hatch / anchored-asymmetry
contracts were exercised only against `pofa_test`; historical `pofa_dev` records were **not** rewritten.

---

## F. Migration readiness

- Observed heads: script graph single head **`t0u1v2w3x030`**; `alembic current` on `pofa_test` reports
  `t0u1v2w3x030`; `pofa_dev` reports `s9t0u1v2w029`. `alembic check` on `pofa_test` = **CLEAN**
  (F-08). The migration chain has not drifted.
- **BE-031 did NOT migrate `pofa_dev`.** No upgrade, downgrade, or re-upgrade was executed against it.
  The live-migration plan (Appendix B) is prepared, evidence-based, and **not executed**, and it
  requires a fresh `pofa_dev` backup plus per-step owner approval before any GO.
- Supporting evidence for the plan's key premise: D-2-A validates only the **immediate predecessor**, so
  `pofa_dev`'s *historical* mid-chain gaps do **not** block future appends onto its locally-valid tail —
  an operator migrating `pofa_dev` to enforcement should expect new writes to succeed while `verify_chain`
  still reports the 7 known gaps (the append-only trigger then blocks UPDATE/DELETE going forward).

---

## G. Test results

**Newly executed this session, target `pofa_test`:**

| Run | Command | Result | Duration |
| --- | --- | --- | --- |
| Full suite (isolated) | `pytest` (via `TEST_DATABASE_URL`, `.venv312_repro`) | **792 passed, 1 skipped, 0 failed** | 522.95s (0:08:42) |
| Targeted matrix (11 files) | `pytest -q -rs` on the BE-030 enforcement/contract, BE-029 identity/history/safety, audit, guard, drift, revision-graph files | **123 passed, 0 failed** | 78.83s (0:01:18) |
| Alembic | `alembic heads` / `current` / `check` (read-only, `pofa_test`) | head `t0u1v2w3x030`; current `t0u1v2w3x030`; check `No new upgrade operations detected.` | — |

Targeted-matrix files: `unit/test_be030_ledger_contract.py`, `integration/test_be030_ledger_enforcement.py`,
`integration/test_be029_audit_ledger_history.py`, `integration/test_audit_ledger.py`,
`unit/test_audit_ledger.py`, `unit/test_audit_guard.py`, `integration/test_be029_identity_contract.py`,
`integration/test_be029_identity_conflict_api.py`, `integration/test_be029_database_safety_guard.py`,
`integration/test_schema_drift_gate.py`, `unit/test_migrations.py` (revision-graph invariants: exactly one
head, single root, no merges, full reachability).

**Skip (both runs):** exactly **1** — `tests/unit/test_preflight.py:117`
`test_ml_missing_never_becomes_available_without_importer`, reason *"ML stack genuinely installed in this
environment."* This is a deterministic environmental skip and is **identical** to the single skip BE-030
recorded — not a regression.

**Baseline parity:** the full-suite 792/1/0 reproduces BE-030's recorded matrix exactly → BE-031
introduced no regression. The 9 pytest warnings are Starlette/FastAPI/Pydantic deprecation notices
(`on_event`, `HTTP_422_UNPROCESSABLE_ENTITY`, class-based config) — pre-existing, non-fatal, not
suppressed.

**Not re-run (documented, not claimed):** the BE-030 disposable-clone proof (`d2a_tail_refusal =
PredecessorInvalid`, anchored `full_chain.valid=True` over 38,265, midchain `covering_range_valid=False`)
and the `pofa_dev` hash-walk are **[PRIOR]**; no new clone or `pofa_dev` migration was performed in BE-031.

---

## H. Backlog reconciliation (no competing backlog created)

The authoritative registers are BE-029 Results OQ-1..OQ-6 and BE-030 Results §2 "Open / blocked items."
BE-031 updates their status against current evidence and does **not** delete unresolved debt.

| Register item | BE-031 status | Evidence | Action |
| --- | --- | --- | --- |
| BE-030 §2.1 live `pofa_dev` migration (gated) | **Still open / blocked** | [MEASURED] `pofa_dev` = `s9t0u1v2w029` | Retained; plan in Appendix B, owner-gated |
| BE-030 §2.2 `pofa_dev` gap baseline is read-only script, not a repo test | **Still open (by §14)** | [MEASURED] 36/7 reproduced; §14 bars live-reading test | Retained; explained, not force-closed |
| BE-030 §2.3 `TRUNCATE` open hole (owner-accepted) | **Still open / blocked** | [MEASURED] both DBs connect as owner w/ TRUNCATE | Retained; Appendix D follow-up |
| BE-030 §2.4 OQ-3 `external_subject` product decision | **Still open** | [MEASURED] write-only, no consumer, inert for NULL | Retained; Appendix A brief |
| BE-030 §2.4 API/worker restart after BE-029 | **Still open (owner action)** | [MEASURED] startup does not auto-migrate; 4 workers emit audit rows | Retained; Appendix C checklist |
| BE-029 OQ-6 "Commit?" | **Resolved — was stale** | [MEASURED] HEAD `07cb59a4`, BE-029 work in `22ce7497`, tree clean | Surgical dated note added to the BE-029 OQ row |
| NEW: §9 anchored control not exposed over HTTP (F-03) | Open, deferred (design/owner) | [MEASURED] only `verify_chain` wired to endpoint | Added to §I outstanding approvals |
| NEW: no runtime known-vs-new gap discrimination (F-04) | Open, deferred (owner) | [MEASURED] register is procedural | Added to §I |
| Legacy `audit_events` table | Not re-examined in depth this session | — | Left as-is; **not** closed without evidence |

A single dated edit was applied to the BE-029 Results OQ-6 row (see that file) because its "no commit"
claim is now factually superseded; the OQ table remains the identity backlog and is otherwise unchanged.

---

## I. Outstanding approvals (owner decisions / actions still required)

1. **Migrate live `pofa_dev` to `t0u1v2w3x030`** — needs fresh verified `pg_dump` + restore-to-disposable
   proof + explicit per-step sign-off, with API/workers stopped (Appendix B). Not done here.
2. **`external_subject` identity policy (OQ-3)** — keep nullable & inert, backfill under an approved
   mapping, or introduce NOT NULL (Appendix A). Not decided here.
3. **`TRUNCATE` hardening** — adopt a non-owner least-privilege runtime role (deployment/architecture
   change) before a `TRUNCATE` guard is meaningful (Appendix D).
4. **API/worker restart** after BE-029's live migration — owner action (Appendix C).
5. **Expose the §9 anchored control over an admin endpoint, and/or implement known-vs-new alerting**
   (F-03/F-04) — new product surface; needs a product decision before any code is written.

---

## J. Git status (as reported, not performed)

- Modified: **none**. Untracked: the BE-031 task proposal (pre-existing) and, after this session, this
  results document (`docs/BE-031 Post-BE-030 Operational Readiness Results.md`) — both intentionally left
  unstaged.
- Staged: **none**. Commit created: **none** (HEAD unchanged at `07cb59a4`). Push: **none**.
- `git diff --check`: **clean** (trailing-whitespace/conflict-marker check).
- No secrets, `.env`, dumps, database files, caches, or scratch artifacts are staged or under the repo
  (all BE-031 diagnostics live in `D:/CODING/Scratch/be031/`, outside version control).

Expected-and-achieved for this task: **nothing staged, nothing committed, nothing pushed.**

---

## K. Final disposition

**COMPLETE WITH DOCUMENTED BLOCKERS.** All approval-free, safe BE-031 reconnaissance and assessment work
is finished and evidenced: baseline recorded from the server (A), every investigated finding classified
(B), database safety asserted and separated (D), audit integrity measured (E), migration heads verified
with `pofa_dev` explicitly unmigrated (F), the test matrix re-executed to parity (G), and the existing
backlog reconciled without deleting debt (H). No code change was justified under §10, and the gated
items (live `pofa_dev` migration, `external_subject` policy, `TRUNCATE` role hardening, service restart,
anchored-control exposure, known-vs-new alerting) remain as explicit owner decisions (I). This matches
the definition of a valid result stated in §10 and every DoD checkbox in §15.

---

## Appendix A — `external_subject` decision brief (BE-031 §4 / BE-029 OQ-3)

**Exact unresolved question.** `users.external_subject` is a nullable `VARCHAR(512)` participating in
`UNIQUE (identity_provider, external_subject)` (`identity_provider` is `NOT NULL default 'local'`). The
decision is what this column is *for* and whether its uniqueness should ever bite. BE-031 does not make
this product call.

**What the code actually does (measured, current).** It is a **write-only, consumer-less key.** Only the
create-user path writes it (`schemas/authorization.py:64-65` → `endpoints/auth.py:160-161` →
`services/authorization.py:340-341`, defaulting a missing value to `uuid4()` → `repositories` plain
insert). **No read path** filters/joins/resolves on it; authentication resolves `dev-user-<uuid>` to
`User.id` and every consumer keys on `User.id`. Data: `pofa_test` 2,710/2,710 NULL (seeded, not
service-created); `pofa_dev` 1,004/1,054 NULL, 50 non-NULL (the service-created rows); provider distinct
= `{local}` throughout.

**Schema/API impact.** The UNIQUE constraint is inert for NULL rows (PostgreSQL NULLS DISTINCT), so it
has never prevented a duplicate federated subject — a real one can exist, and in fact the only rows with
a value are those the service created. The API request accepts optional `external_subject`/
`identity_provider`; `POST /auth/users` already returns **409** only for the three identity objects
(BE-029 follow-up), so duplicate-subject submissions on the *populated* subset already conflict cleanly.

**Options supported by the current implementation (none executed).**
- **A — Keep as-is (nullable, inert).** Zero migration, zero risk. Cost: a declared key with no enforced
  meaning and no reader; a latent trap if a real federated flow is ever added and assumes uniqueness.
- **B — Backfill + NOT NULL.** Gives the pair teeth, but requires (i) an approved subject-derivation
  mapping for the 2,710/1,004 NULL rows (there is **no** external IdP to source them from — inventing one
  is exactly what §4 forbids), and (ii) a data migration + contract change. Blocked on policy, not code.
- **C — NULLS NOT DISTINCT / functional unique on the populated subset only.** Enforces uniqueness among
  real values without touching NULLs. Smallest schema change with real effect, but still an identity
  *policy* choice and a drift-visible ALTER.
- **D — Retire the column.** It has no consumer today; removal is tempting but forecloses the federated
  anchor the BE-029 §2 analysis says it was reserved for.

**Required migration/test changes per option.** B/C/D are Alembic revisions against both DBs (so they
interact with the still-open live-`pofa_dev` migration); C is visible to the drift gate, B is not
(NOT-NULL default reflection). Existing tests already pin the current behaviour
(`test_null_external_subject_rows_are_permitted_and_do_not_collide`,
`test_identity_key_constraint_definition_is_unchanged`) and would be updated with whichever option is
chosen.

**Risks of deferring.** Low *operational* risk (no consumer depends on it). The real risk is drift:
future code assuming the pair is a working identity key when it is not enforced. **Recommendation for
the owner:** treat as a policy backlog item; if no federated login is planned near-term, Option A with an
explicit code comment marking the column "declared, not enforced, no consumer" is the cheapest honest
state. BE-031 keeps it open and does **not** backfill or add NOT NULL.

---

## Appendix B — `pofa_dev` → `t0u1v2w3x030` migration-readiness plan (BE-031 §7; **NOT executed**)

> **This plan was prepared, not performed. No live migration was executed by BE-031.** It is gated on
> fresh backup proof + explicit per-step owner approval.

1. **Confirm target & revision.** Connect, assert `current_database() = 'pofa_dev'` (server-side, never
   trust the URL), record `alembic_version` (= `s9t0u1v2w029` today) and the ledger baseline (rows/span/
   gap-ranges = 6,023 / 1..6059 / 36-in-7 today).
2. **Fresh backup, stored outside the repo.** `pg_dump -Fc` of `pofa_dev` **from inside container
   `pofa_db`** (`docker exec pofa_db pg_dump …` — host has no `pg_dump`/`psql`), write to `/tmp`, then
   `docker cp` out so a shell redirect cannot mangle bytes. The BE-029 G3 dump is a *pre-BE-029* snapshot
   and is **not** a valid restore point for a BE-030 upgrade — a NEW dump is mandatory.
3. **Integrity + SHA-256.** Record size and SHA-256 on both sides of the `docker cp`; keep a MANIFEST
   (follow `project-be029-g3-backup` format). Note: `archive_mode = off` (`wal_level=replica`, zero
   archived WAL) means **no true PITR** — the dump is one transactionally-consistent snapshot; writes
   after the dump instant cannot be replayed.
4. **Restore into a separately-named disposable DB** (e.g. `pofa_be031_proof`), never over
   `pofa_dev`/`pofa_test`. `pg_restore`, capture exit code + duration.
5. **Clone-vs-source comparison.** Table count, catalog (constraints/indexes), data counts, and the
   audit-ledger measurements (rows/span/36-in-7) must match the pre-migration snapshot. Beware the known
   `ALTER TABLE ADD CONSTRAINT` deparse / `nulls_not_distinct` reflection artifacts — prove equivalence
   by evaluating both forms, not by eye (per `project-be029-g3-backup`).
6. **Run the migration against the clone.** `alembic upgrade t0u1v2w3x030` with `DATABASE_URL` pointed at
   the clone; verify `trg_audit_ledger_append_only`, `audit_ledger_refuse_mutation`,
   `ck_audit_ledger_event_type_domain` appear.
7. **Verify enforcement + behavior on the clone.** UPDATE/DELETE on the ledger refused (SQLSTATE 42501);
   out-of-domain INSERT refused (23514); an honest append onto the clone's tail **succeeds** despite the
   7 historical gaps (F: D-2-A checks only the immediate predecessor); `verify_chain` still reports the
   known gaps (they are history, not repairable by the migration).
8. **Rollback / recovery compatible with append-only.** Prove `alembic downgrade s9t0u1v2w029` drops the
   three objects symmetrically and re-upgrade restores them; confirm downgrade never needs to rewrite
   ledger rows. A restore-from-dump is the recovery of last resort but loses post-dump writes (no PITR).
9. **Service & worker shutdown procedure.** Drain/stop `analysis_worker`, `notification_worker`,
   `webhook_worker` (they emit audit rows via `append_event`) and `retention_worker` (dry-run default);
   stop the API; confirm `pg_stat_activity` shows **0 backends on `pofa_dev`** before migrating.
10. **Pre/post checklist.** Pre: target confirmed, revision recorded, fresh dump hashed+restored+compared,
    0 backends, owner approvals logged. Post: `alembic current = t0u1v2w3x030`, enforcement catalog
    present, `alembic check` CLEAN, one honest append succeeds, `verify_chain` gap report unchanged (36/7
    — history not "fixed"), audit guard unviolated.
11. **Explicit owner approvals** at each gate: (a) authorize a fresh dump, (b) authorize a disposable
    restore+proof, (c) authorize the live `pofa_dev` upgrade itself, (d) authorize service downtime.
12. **Stop/GO with objective criteria.** GO only if the clone proof in 6–8 is fully green and the fresh
    dump is restored+verified. STOP if: identity `current_database()` ≠ `pofa_dev`; any write to
    `pofa_dev` is attempted outside the armed plan; the fresh dump cannot be restored and compared; or a
    post-migration `verify_chain` shows *new* (non-register) damage. **Reaffirm: BE-031 executed none of
    the above.**

---

## Appendix C — API / worker restart readiness checklist (BE-031 §8; **no service restarted**)

**Processes present (measured from the repo):**
- API: `backend/app/run.py` (`uvicorn.run("backend.app.main:app", …, reload=True)`, default
  `127.0.0.1:8000`). Startup hook `main.py:121` runs **only** OpenTelemetry init + a log line — it does
  **NOT** auto-run migrations and does **NOT** call `Base.metadata.create_all`. Starting the API alone
  neither changes schema nor emits audit rows (writes happen only while serving requests).
- Workers (each a standalone `if __name__ == "__main__"` process, `backend/workers/`):
  `analysis_worker.run_worker()` (continuous `while True` job loop, writes DB, may emit audit via the
  reprocessing hook), `notification_worker` (`run_worker_once`, outbox + retries), `webhook_worker`
  (`run_worker_once`, explicitly calls `audit_service.append_event`), `retention_worker`
  (`run_sweep_once(auto_delete=False)` — **dry-run by default**).
- `backend/db/init_db.py` uses `create_all` — a **manual**, migration-bypassing entrypoint; must not be
  used in place of `alembic upgrade`.

**Ambiguity to control (§2.1):** every process resolves the single `DATABASE_URL`, whose `.env` default is
`pofa_dev`, and the armed safety context is **unset in normal runtime** (no guard). "The env-var name
looks right" is not proof of the target. A readiness check must read `current_database()`.

**Restart prerequisites / safe order:**
1. Decide the intended target explicitly and confirm it via `SELECT current_database()` in a read-only
   session; if the plan requires `pofa_test` or a disposable DB, arm the verification context (which
   refuses the long-lived DBs) — otherwise you are on `pofa_dev`.
2. Preconditions: DB schema revision matches what the code expects. Today `pofa_dev` is at `s9t0u1v2w029`
   while the code's head is `t0u1v2w3x030`; a worker that appends audit events will run the D-2-A
   predecessor path only once the enforcement migration is applied — pre-migration restarts are the
   *current* dev behavior and do not crash, but post-migration behavior differs (UPDATE/DELETE now
   refused). Do not restart mid-migration.
3. Shutdown order before maintenance: workers first (`analysis`, `webhook`, `notification`, then
   `retention`), let in-flight `run_worker_once` passes finish so Redis queue items and outbox rows are
   not stranded, then the API. `analysis_worker`'s `while True` loop needs a signal-driven stop; a hard
   kill can leave a job "running" (recovery is the separate deferred FIX-002 in the cleanup backlog).
4. Startup order: API last, workers after, only once `alembic current` is at the intended head.
5. Health checks after start: HTTP `/health`/readiness, a bounded `GET /api/v1/audit/verify`, and — until
   F-03 is decided — a **manual/log** invocation of `verify_chain_anchored` (it has no HTTP surface; its
   checkpoint digest is log-only).
6. Rollback/stop conditions: if a worker emits `PredecessorInvalid` or the audit guard fires, stop the
   workers, preserve the ledger, and report — do not hatch-edit to clear it.
7. Required owner approvals: starting/stopping services is itself an owner-gated action (§2.2). **BE-031
   performed no restart.** (For accuracy: BE-031 started Docker Desktop only to restore the *database
   dependency* `pofa_db` after an unrelated outage per [[env-docker-desktop-outage]]; it launched no API
   or worker process.)

---

## Appendix D — Proposed follow-up: `TRUNCATE` / least-privilege runtime role (BE-031 §6)

**Verified today:** enforcement mitigates UPDATE/DELETE (row trigger) and out-of-domain INSERT (CHECK),
but **not** `TRUNCATE`; both DBs connect as the table owner (`postgres`, `has_truncate_priv=true`), so a
`REVOKE`-based guard would be inert and the silent-reset hole (BE-030 §2f) stays open.

**Mitigation tiers (per §6's required distinction):**
1. *Mitigated in current code:* UPDATE/DELETE refusal, out-of-domain INSERT refusal, anchored verification
   + checkpoint digest (proven by tests, but see F-03: unpolled at runtime).
2. *Works only with a restricted role:* a `TRUNCATE` guard becomes meaningful **only** once the application
   connects as a non-owner runtime role that lacks `TRUNCATE`/`DROP` on `audit_ledger_events`, with the
   table owned by a separate migration role.
3. *Remaining gap requiring owner/deployment change:* the role split itself.

**Proposed BE-032 follow-up (gated, not started):** introduce `poa_runtime` (DML only, no TRUNCATE) as the
connection role and `poa_migrate`/owner for DDL; grant sequence/append rights; prove with a dedicated test
that `poa_runtime` is denied `TRUNCATE audit_ledger_events` while `poa_migrate` may still perform the
append-only migration; keep the trigger+hatch as the UPDATE/DELETE layer. This changes DB roles/ownership,
so §2.2 gates it on explicit owner authorization and it must be proven on a disposable DB first.

---

## Limitations of the evidence

- `pofa_dev` chain was re-measured for **span/gap counts only** read-only; a full hash `verify_chain`
  walk of `pofa_dev` was not re-run (no write/hatch permitted there; hash-integrity is [PRIOR] from
  BE-030). Honest partial.
- No disposable clone was rebuilt for BE-031; the clone proof is [PRIOR] BE-030. Append-onto-gap
  behavior on a to-be-migrated `pofa_dev` is reasoned from the D-2-A immediate-predecessor contract,
  which is itself shipped-tested on `pofa_test`/clone, not newly demonstrated against a migrated
  `pofa_dev` clone in this session.
- Restart and role-architecture appendices are plans/analyses; none was executed.
