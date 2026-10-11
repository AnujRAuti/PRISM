# BE-029 — User Identity Constraint Remediation: Results

Task: `docs/Production Task Files/BE-029 — User Identity Constraint Remediation.md`
Plan: `docs/BE-029 User Identity Constraint Remediation Plan.md`
Executed: 2026-10-08 → 2026-10-09 (scratch proof, then the approved live `pofa_dev` run — §12,
then the approved follow-up: auth conflict handling + rollback/re-upgrade reversibility proof — §13)
Branch: `Backend` — **not committed, not pushed** (OQ-6 remains undecided)

> **Corrected by BE-031 (2026-10-10).** The line above records the state *when this results document was
> first written*. Since then the BE-029 identity work was committed on `Backend` (`22ce7497`), BE-030
> finalized at HEAD `07cb59a4`, and BE-031 re-verified a clean tree at `07cb59a4`. OQ-6 is therefore
> **committed**; **it has still not been pushed**, and BE-031 ran no `git fetch`, so the local-vs-remote
> relationship is not re-established (project memory records the branch as unpushed). OQ-3 remains an
> open product decision. See the OQ table §1 and `BE-031 Post-BE-030 Operational Readiness Results.md`.

---

## 1. Product Decision

**Option A — username/email are identity attributes.** Ruled by the product owner on
2026-10-08 (OQ-1), with the consequence that database-level uniqueness on
`users.username` and `users.email` must eventually be enforced.

The decision was made *against* part of the available evidence, and the evidence is
recorded here so nobody mistakes the decision for a code-derived necessity:

| Evidence | Reading |
| --- | --- |
| `uq_user_identity_subject UNIQUE (identity_provider, external_subject)` exists and is enforced | the *de-facto* identity key is provider + external subject, not username/email |
| No query anywhere in `backend/` filters on `User.username` or `User.email` (`grep` over the package returns zero hits) | username/email are not used to resolve a user, so nothing in the current code breaks if two users share one |
| `create_user()` normalises with `username.strip()` / `email.strip().lower()` (`backend/services/authorization.py:307`) | the service already treats them as identity-shaped values, and it enforces non-blankness with `ValueError` |
| `create_user()` defaults `external_subject` to a generated `uuid4` when none is supplied | the service never *intentionally* creates a NULL-subject row; NULLs are historical/backfill residue |

Under Option A the pair is treated as an identity attribute and the schema is brought in
line with what the ORM already declared. The pre-existing BE-028 finding (B-1) was that
`models.py` declared `unique=True` on both columns while no revision ever created a UNIQUE
index, and duplicate rows existed in both real databases. That gap is now closed.

### Open questions — final state of the record

| # | Question | State | What was done |
| --- | --- | --- | --- |
| OQ-1 | Option A or B? | **Answered: A** | Unique indexes created by `s9t0u1v2w029`. |
| OQ-2 | Merge, keep a survivor, or retire the whole duplicate set? | **Answered: retire all** | 19 triples in `pofa_test`, 40 in `pofa_dev` archived and deleted; no survivor was designated, because the owner classified the entire set as synthetic fixture garbage rather than accounts. |
| OQ-3 | Repair `external_subject` / make it NOT NULL? | **Undecided — not done (still open per BE-031)** | Column left nullable; `uq_user_identity_subject` therefore stays inert for NULL rows (PostgreSQL defaults to NULLS DISTINCT). Covered instead by a test that pins the behaviour: `test_null_external_subject_rows_are_permitted_and_do_not_collide`. *BE-031 re-verification (2026-10-10): still open.* Re-confirmed in current code that `external_subject` is a **write-only key with no read consumer** (auth resolves on `User.id`); measured `pofa_test` 2,710/2,710 NULL, `pofa_dev` 1,004/1,054 NULL, `identity_provider` distinct = `{local}`. No backfill / NOT NULL done. Four-option decision brief in `BE-031 Post-BE-030 Operational Readiness Results.md` Appendix A. |
| OQ-4 | Is `pofa_dev` in scope? | **Answered: yes, but last** | `pofa_dev` was verified **untouched** at `n4o5p6q7r022` throughout. All proof work ran on clones. |
| OQ-5 | Application-level `IntegrityError` handling? | **Answered and done by the follow-up (2026-10-09)** | Was "not done" at the time of the run recorded in §12; it was then established that a *blanket* handler had existed since BE-016 (§13.1). `POST /api/v1/auth/users` now answers 409 only for the three identity objects and lets every other integrity failure stay a 500. |
| OQ-6 | Commit? | **Committed on `Backend`; not pushed (BE-031 dated reconciliation, 2026-10-10)** | "Not done" was accurate for the run recorded here, but the BE-029 identity work was later committed on `Backend` (`22ce7497` "finalize BE-029 and prepare BE-030"), and BE-030 finalized at HEAD `07cb59a4` "BE-30 Complete". BE-031 verified HEAD `07cb59a4` with a clean tree. **BE-031 performed no `git add`, commit, or push, and ran no `git fetch`, so the local-vs-`origin/Backend` relationship is not re-verified (memory records the branch as unpushed).** Original-run note retained: at that time the working tree held the change uncommitted. |

---

## 2. Existing Identity Model

Two columns, one constraint:

```
users.identity_provider   VARCHAR   NOT NULL       ('local' for every managed account today)
users.external_subject    VARCHAR(512) NULL
CONSTRAINT uq_user_identity_subject UNIQUE (identity_provider, external_subject)
```

**Corrected 2026-10-09 (final-closure Phase D).** This section originally read: "`(identity_provider,
external_subject)` is the key the application actually resolves against … no code queries by username
or email, and BE-016 left `external_subject` as the federated-identity anchor." The first half is
wrong; the second half is right for the wrong reason. Tracing **every** read and write of the two
columns across `backend/` (schemas → endpoints → services → repositories → migrations) gives:

| Path | Reality |
| --- | --- |
| Writes | `schemas/authorization.py:64-65` (request fields) → `api/v1/endpoints/auth.py:160-161` → `services/authorization.py:327,340-341` (defaults a missing subject to `uuid4()`) → `repositories/authorization.py:52-59` (plain insert). |
| Reads | **None.** No query anywhere filters, joins or looks up on `external_subject` or `identity_provider`; `grep` over `backend/` for either name returns only the write path above and the model declaration. |
| Principal resolution | `security/authentication.py:72-74` parses `dev-user-<uuid>` into a user **id**, and `repositories/authorization.py:46-47` resolves it with `User.id == user_id`. Every other consumer (`services/notification.py:310,538,678`, `api/v1/endpoints/context.py:50`, `services/authorization.py:787`) also keys on `User.id`. |
| Provider variety | One value only, `'local'`, in every surviving row of both databases (`SELECT DISTINCT identity_provider` → 1 row). |

So the pair is a **declared, write-only key with no consumer** — an anchor for a federated login flow
that does not exist yet, not the mechanism the running system uses to decide who you are. That is why
OQ-3 cannot be resolved from the code alone (§14.3), and why no NOT NULL constraint was added.
What the constraint *does* still do is enforce uniqueness on the one shape the service writes
distinctly, and it is a real database constraint rather than an ORM promise.

Two properties of that constraint matter to this task and are pinned by tests rather than
asserted in prose:

1. **It is inert for NULL.** PostgreSQL's default is NULLS DISTINCT, so any number of
   rows with `external_subject IS NULL` satisfy it. In `pofa_test` that was *all 2,098
   rows*; in `pofa_dev`, 1,009 of 1,094. The constraint has therefore never prevented a
   duplicate account in either database, and could not, without OQ-3 being decided.
2. **It is a real constraint, not an index-only guarantee**, so it survived the whole task
   untouched: `test_identity_key_constraint_definition_is_unchanged` compares
   `pg_get_constraintdef()` against the literal string
   `UNIQUE (identity_provider, external_subject)`.

username/email are the *human-facing* identity half of the model. Before BE-029 they were
declared unique in the ORM and unenforced in the schema. They are now both declared and
enforced the same way:

```
CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username)
CREATE UNIQUE INDEX ix_users_email    ON public.users USING btree (email)
```

Normalisation stays where it always was — in `create_user()` (strip username,
strip+lowercase email, reject blank with `ValueError`). No `citext`, no generated column,
no functional index was introduced, so uniqueness is byte-exact: `Test@example.com` and
`test@example.com` are distinct rows to the database, and the service is the only writer
in the normal path. §10 records the exposure that leaves open.

---

## 3. Duplicate Analysis

Measured on 2026-10-09 with `D:\CODING\Scratch\be029\p0_state.py` (read-only,
`current_database()` verified in every capture).

### 3.1 Before, per database

| Fact | `pofa_test` | `pofa_dev` |
| --- | --- | --- |
| Revision | `q7r8s9t0u027` | `n4o5p6q7r022` |
| users / projects / evidence | 2,098 / 1,053 / 784 | 1,094 / 584 / 324 |
| Duplicate username groups | **1** (`testuser` × 19) | **1** (`testuser` × 40) |
| Duplicate email groups | **1** (`test@example.com` × 19) | **1** (`test@example.com` × 40) |
| Residue triples | 19 | 40 |
| Rows in the retirement set | 57 (19 + 19 + 19) | 120 (40 + 40 + 40) |
| `external_subject` NULL | 2,098 / 2,098 | 1,009 / 1,094 |
| …NULL among the residue rows | 19 / 19 | 5 / 40 |
| `ix_users_username` | `CREATE INDEX` (non-unique) | `CREATE INDEX` (non-unique) |
| `ix_users_email` | `CREATE INDEX` (non-unique) | `CREATE INDEX` (non-unique) |
| `audit_ledger_events` | 30,862 rows, chain **valid** | 6,017 rows, chain **invalid — 7 sequence gaps** |

Every duplicate group had exactly the same shape:
`username='testuser'` + `email='test@example.com'`, owning exactly one project named
`testproj`, holding exactly one evidence row named `foo.jpg`. The origin is recorded in the
migration docstring: the pre-BE-027 `test_basic_crud` fixture re-inserted the same triple
on every run and could only "pass" because the schema did not enforce what the model
claimed. There is no case-insensitive or plus-tag variant hiding behind the visible group:
`lower()`-grouped and `split_part(email,'+',1)`-grouped counts are both 1 in each database.

### 3.2 Foreign-key impact

Enumerated from the catalog (`pg_constraint` → referencing columns), not from a hand-written
list, so a FK added later would be covered automatically:

* **Inside** the retirement set, self-references only: `projects.owner_id` → the archived
  users (19 / 40 rows) and `evidence.project_id` → the archived projects (19 / 40 rows).
  That is exactly the archive's own triple linkage, verified closed by `archive_audit.py`
  (`projects_owned_by_non_archived_user: []`, `evidence_in_non_archived_project: []`).
* **Outside** the set: none. Every other FK referencing `users`, `projects` or `evidence`
  was probed with `count(*) … WHERE col IN (SELECT id FROM <candidate CTE>)` and returned 0
  across `activities`, `audit_events`, `claims`, `field_assignments`, `field_sessions`,
  `notifications`, `notification_preferences`, `review_decisions`,
  `user_role_assignments` and the rest.
* **Composite FKs: none.** The predicate aborts rather than silently evaluating a composite
  key column-by-column; it never fired.
* **No `ON DELETE CASCADE` was used or relied on** (§15). Retirement order
  `evidence → projects → users` satisfies the real dependency direction.

### 3.3 Audit-ledger exposure

The append-only ledger has no foreign keys by design, so a missing principal is normal:
`pofa_test` already held 8,627 ledger rows whose `actor_id` no longer resolves to a user,
and all 281 of its `USER_CREATED` events were dangling for the same reason — that is
ordinary test cleanup, not damage. What BE-029 needed was the narrower fact, and it is
measured directly: **0 `audit_ledger_events` rows name any archived id** as actor, project
or resource, in `pofa_test` and in the `pofa_dev` rehearsal clone
(`ledger_rows_referencing_archived_ids: 0`). The migration also refuses to run if any such
row exists, and compares the ledger row count before and after.

---

## 4. Remediation

Two migrations, one model addition, one new test file, three test-infrastructure edits.
No application behaviour changed.

**What changed in the data** (this is the destructive part, and it is the only one):

* `pofa_test`: 57 rows retired — 19 `users`, 19 `projects`, 19 `evidence`.
* `pofa_be029_rehearsal` (exact copy of `pofa_dev`): 120 rows retired — 40 + 40 + 40.
* `pofa_dev`: **nothing. Not touched.** See §8.

Every retired row was archived first, as a `to_jsonb(row)` image with its original primary
key, into `identity_retirement_archive`. Nothing was merged, no FK was reassigned, no
username or email was rewritten, no survivor was promoted.

**Why archiving was the design, not a convenience**: the owner's ruling makes these rows
garbage, but "garbage" is a judgement that has to survive being wrong. Archiving means a
mistake is reversible by `downgrade()` without a restore-from-backup, and it makes the
target set auditable after the fact — the archive *is* the list of everything the migration
touched.

**Deliberately not done**: `external_subject` backfill / NOT NULL (OQ-3), `IntegrityError`
→ 409 mapping in the API (OQ-5), any change to login, registration, admin user creation or
the drift gate's policy.

*(The OQ-5 exclusion was lifted by a separately approved follow-up on 2026-10-09; the schema
work above was not reopened. See §13.1.)*

---

## 5. Database Changes

### 5.1 Revisions

| Revision | File | Parent | Effect |
| --- | --- | --- | --- |
| `r8s9t0u1v028` | `alembic/versions/r8s9t0u1v028_be029_retire_identity_residue.py` (373 lines) | `q7r8s9t0u027` | create `identity_retirement_archive`; run the residue predicate; archive; re-run the predicate; delete in FK-safe order |
| `s9t0u1v2w029` | `alembic/versions/s9t0u1v2w029_be029_user_identity_unique.py` (113 lines) | `r8s9t0u1v028` | require zero duplicate groups, then replace the two non-unique indexes with UNIQUE ones |

Chain: `… → q7r8s9t0u027 → r8s9t0u1v028 → s9t0u1v2w029`. Linear, single head, 24 revisions
(pinned by `tests/unit/test_migrations.py`).

### 5.2 New table

```sql
CREATE TABLE identity_retirement_archive (
    source_table  VARCHAR(32)  NOT NULL,
    source_id     UUID         NOT NULL,
    row_json      JSONB        NOT NULL,
    retired_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (source_table, source_id),
    CONSTRAINT ck_retirement_archive_source_table
        CHECK (source_table IN ('users','projects','evidence'))
);
```

`row_json` is a full-row image, so restore is literal
(`jsonb_populate_record(NULL::<table>, row_json)`) and is immune to the geometry/pgvector
column-mirroring problem that a hand-written column list would have hit. The recorded
limitation: if a *later* revision adds a NOT NULL column to `users`/`projects`/`evidence`,
this `downgrade()` would fail on restore — at which point the correct action is a forward
repair, not a silent NULL.

### 5.3 Constraints and indexes

| Object | Before | After |
| --- | --- | --- |
| `ix_users_username` | non-unique btree | **UNIQUE** btree on `(username)` |
| `ix_users_email` | non-unique btree | **UNIQUE** btree on `(email)` |
| `uq_user_identity_subject` | `UNIQUE (identity_provider, external_subject)` | unchanged, byte-identical `pg_get_constraintdef()` |
| `ck_user_status`, `users_pkey` | unchanged | unchanged |

`CREATE INDEX CONCURRENTLY` was considered and rejected (§20 measure-first): `users` holds
1,094 / 2,098 rows, and CONCURRENTLY cannot run inside Alembic's per-revision transaction.
A plain rebuild of a four-figure btree is sub-second and the exclusive lock is cheaper than
the complexity of a two-phase out-of-transaction build.

### 5.4 Guards, in execution order

`r8s9t0u1v028` aborts (`RetirementAborted`, whole revision rolls back) unless **all** of:

1. candidate `users` count == candidate `projects` count;
2. if candidates own projects, `foo.jpg` evidence exists;
3. every one of the five shape checks passes: each candidate owns exactly one project, that
   project is named `testproj`, every candidate project holds evidence, every child is named
   `foo.jpg`, and no `audit_ledger_events` row names a candidate as actor/project/resource;
4. no FK reference from *outside* the retirement set points into it — column-by-column over
   the catalog's FK list, with composite keys aborting as unsupported;
5. archived row counts equal counted row counts for all three tables;
6. each `DELETE`'s rowcount equals that table's archived count;
7. after the deletes: residue == 0, duplicate groups == 0, ledger row count unchanged.

The predicate is evaluated **twice** — once before anything is written to the archive, and
once immediately before the `DELETE`s — so a candidate that changed shape mid-migration is
caught, per the owner's step 5.

`s9t0u1v2w029` aborts (`UniquenessPreconditionFailed`) unless the duplicate-group count is
zero for both columns, and refuses to run if an index is already UNIQUE (so a re-run is a
clean no-op instead of a double rebuild). Its `downgrade()` refuses to touch an index that
is *not* UNIQUE, on the same principle: never silently rewrite an object whose state you
did not create.

---

## 6. Application Changes

**One addition, zero edits.** `backend/db/models.py` gains `IdentityRetirementArchive`
(+36 lines), which exists for exactly one reason: the BE-028 drift gate compares the live
database against this metadata, and a real table no model describes is reported as
`remove_table` drift. Declaring it keeps the gate honest instead of inviting an exception to
the baseline.

| Surface | Change |
| --- | --- |
| Models | `IdentityRetirementArchive` added (migration-owned table; not read by any repository, service or endpoint). |
| Validation | None. `create_user()` already strips usernames, lowercases emails and raises `ValueError` on blank — behaviour pinned by `test_blank_username_or_email_is_refused_before_insert` and `test_stored_email_is_lowercased_and_username_keeps_its_case`. |
| Authentication | None. `external_subject` is still defaulted to a `uuid4` by the service (`test_service_never_creates_a_null_subject`), and OQ-3/OQ-5 were both left undecided. |
| API / schemas / repositories / services | None. No endpoint, schema, repository or service file was modified. |
| Migration test infrastructure | `tests/unit/test_migrations.py`: `EXPECTED_HEAD` → `s9t0u1v2w029`, `EXPECTED_REVISION_COUNT` → 24. `tests/schema_drift_baseline.py`: the four category-E entries (`add/remove_index` on `ix_users_username`/`ix_users_email`) deleted, replaced by a comment naming the two revisions that resolved them; only the two category-B `uq_user_role_scoped` NULLS-NOT-DISTINCT tooling artifacts remain. `tests/integration/test_schema_drift_gate.py`: the stale-baseline test no longer hardcodes `"add_index|users|ix_users_email"` as its example — that entry legitimately stopped existing — and now derives its example from `ACCEPTED_SIGNATURES`. This *preserves* the two-directional mechanism; it does not soften it. |

---

## 7. Tests

Every command below was run with `backend/.venv312_repro` and an explicit
`TEST_DATABASE_URL` (the suite refuses to fall back to `pofa_dev`). Scratch clones use
`pofa_be029_*` names, which `backend/db/test_target.py` permits because only `pofa_dev` is
blocked.

### 7.1 The §25 identity-contract suite

`tests/integration/test_be029_identity_contract.py` — 15 tests, all passing on `pofa_test`
at head, on `pofa_be029_rehearsal` and on `pofa_be029_scratch`:

| Test | What it pins |
| --- | --- |
| `test_same_provider_and_subject_cannot_create_two_users` | `uq_user_identity_subject` fires, by name, on the second insert |
| `test_same_subject_under_different_providers_is_allowed` | the key is the *pair*, not the subject |
| `test_different_subject_under_same_provider_is_allowed` | …and not the provider alone |
| `test_duplicate_username_is_rejected_by_the_database` | new `ix_users_username` uniqueness, named in the `IntegrityError` |
| `test_duplicate_email_is_rejected_by_the_database` | new `ix_users_email` uniqueness, named in the `IntegrityError` |
| `test_email_normalisation_makes_case_and_padding_variants_collide` | `Test@Example.com ` → `test@example.com`, so the unique index catches the normalised form |
| `test_stored_email_is_lowercased_and_username_keeps_its_case` | what is actually written to the column |
| `test_blank_username_or_email_is_refused_before_insert` | `ValueError` from the service, no row attempted |
| `test_null_external_subject_rows_are_permitted_and_do_not_collide` | OQ-3 left undone, and NULLS DISTINCT means two NULL subjects coexist — documented, not hidden |
| `test_service_never_creates_a_null_subject` | the only NULLs in the tables are historical |
| `test_no_duplicate_username_groups_remain` / `test_no_duplicate_email_groups_remain` | §19's zero-duplicate precondition, re-checked on live data |
| `test_no_synthetic_identity_residue_remains` | the fixture triple is gone |
| `test_username_and_email_indexes_are_unique_in_the_catalog` | `pg_index.indisunique` is true for both |
| `test_identity_key_constraint_definition_is_unchanged` | `pg_get_constraintdef()` still reads `UNIQUE (identity_provider, external_subject)` |

### 7.2 Exact commands and exact results

| Database | Command | Result |
| --- | --- | --- |
| `pofa_test` (head) | `pytest -q tests/unit` | **420 passed, 1 skipped** in 33.53 s — baseline §30 match |
| `pofa_test` (head) | `pytest -q --tb=line -p no:randomly tests/integration` | **296 passed, 1 failed** in 687.66 s |
| `pofa_test` (head) | `pytest -q -m "not integration" tests` | **710 passed, 1 failed, 1 skipped, 6 deselected** in 490.29 s |
| `pofa_test` (head) | `alembic check` | 2 operations, both the accepted category-B artifact (was 6 before BE-029) |
| `pofa_test` (head) | drift gate `tests/integration/test_schema_drift_gate.py` | **6 passed** (inside the run above) |
| `pofa_be029_rehearsal` | `pytest -q --tb=line -p no:randomly tests/integration` | **291 passed, 6 failed** in 405.77 s |
| `pofa_be029_scratch` | `pytest -q tests/integration` | **290 passed, 7 failed** in 482.29 s (1 of the 7 was the MinIO-restart test; Docker had died mid-run and that test passes on its own — `1 passed in 3.80 s`) |
| `pofa_be029_control` (pre-BE-029) | the same 7 tests | **6 failed, 1 passed** in 43.84 s |
| `pofa_be029_fresh` (base → head) | guard probe, 4 scenarios | **GUARD PROBE: PASS** |
| either | `pytest -q tests/unit/test_migrations.py` | **8 passed** |

### 7.3 Every delta from the §30 baselines, explained

* **282 → 297 integration tests.** The 15 added tests are
  `test_be029_identity_contract.py`. No existing test was deleted or deselected.
* **The single `pofa_test` failure is the documented baseline failure**:
  `test_be025_admin_control_plane.py::test_organization_lifecycle_noop_audit_and_isolation`,
  asserting at line 535 that a newly created organisation appears in the default page of
  `/api/v1/auth/organizations`. It is volume-sensitive and pre-existing. Per §30 it was not
  weakened, skipped, deleted or modified — the only change to that file in this task is zero.
* **The `not integration` track's single failure is that same test.** It is re-confirmed by a
  dedicated run at head (`1 failed, 710 passed, 1 skipped, 6 deselected` in 977.33 s, log
  `D:/CODING/Scratch/be029/notintegration_pofa_test.log`), whose short summary names
  `test_organization_lifecycle_noop_audit_and_isolation` and nothing else. No failure in this
  task's evidence is unidentified.
* **The 6 failures on the `pofa_dev`-shaped clones are not BE-029 regressions, and that was
  measured rather than assumed.** All six are audit-chain tests
  (`test_audit_ledger.py::test_api_verify_reports_valid_chain`,
  `::test_tamper_detection_with_rollback`, `::test_concurrent_appends_keep_valid_chain`,
  `test_be025_admin_control_plane.py::test_admin_audit_chain_remains_valid`,
  `test_be026_field_operations.py::test_field_audit_trail_is_complete_chained_and_secret_free`,
  `test_retention.py::test_fusion_history_preserved_and_audit_chain_intact`).
  `verify_chain()` returns `valid=False, failures=7` on `pofa_dev`'s ledger — 7 sequence gaps
  in 6,017 rows, span 1..6,053 — which is pre-existing BE-028-recorded damage in the
  development database. **Control:** a fresh `pofa_dev` clone taken *back to* `q7r8s9t0u027`
  (every revision except BE-029's two) fails the identical six tests. **Therefore** the
  failures travel with `pofa_dev`'s data, not with this task's migrations. On `pofa_test`,
  whose chain is valid, all six pass. Fixing the gaps is out of scope here and is listed in
  §11.
* **The org-list baseline failure did not reproduce on the clones** (fewer organisations than
  the page size). Reported as observed; the test was not touched.

### 7.4 Performance and lock footprint (§34)

Measured on `pofa_be029_control` — `pofa_dev`'s data, 40 triples, 1,094 users — by traversing
each revision separately (`time`, warm PostgreSQL, cold Python client; interpreter and
Alembic startup is ~2 s of each figure, so the database work itself is ~1 s per revision):

| Traversal | Wall clock |
| --- | --- |
| `q7r8s9t0u027 → head` (predicate ×2, archive 120 rows, 120 DELETEs, 2 index rebuilds) | 3.54 s |
| `r8s9t0u1v028 → s9t0u1v2w029` (drop + create 2 UNIQUE indexes on 1,094 rows) | 2.82 s |
| `s9t0u1v2w029 → r8s9t0u1v028` (indexes back to non-unique) | 2.93 s |
| `r8s9t0u1v028 → q7r8s9t0u027` (restore 120 rows, drop archive) | 2.71 s |
| `n4o5p6q7r022 → head` on the pristine rehearsal clone (5 revisions) | succeeded, 40 triples retired |

Locks: both revisions take `ACCESS EXCLUSIVE` on `users` for the index drop/create, held for
roughly a second. At this table size no `CONCURRENTLY` path is warranted, and `pofa_dev` is a
single-developer database with no running application during the migration.

---

## 8. Data Safety

| Question | Answer |
| --- | --- |
| Was `pofa_dev` modified? | **Yes — on 2026-10-09, under explicit owner approval, and only by the reviewed migrations.** See §12 for the full evidence trail (backup → preflight → upgrade → 13 verification checks). Everything before that run was read-only: verified at the end of the scratch phase still at `n4o5p6q7r022`, 1,094 / 584 / 324 rows, 6,017 ledger rows, residue 40/40/40, one duplicate username group and one duplicate email group, both indexes non-unique, no archive table (`D:\CODING\Scratch\be029\p0_pofa_dev_untouched.json`). Every pre-approval destructive run happened on `CREATE DATABASE … TEMPLATE pofa_dev` clones; `clone_db.py` refuses to clone while anything is connected to the template. |
| Were users deleted? | **Yes, in three databases and never in a production one**: 19 in `pofa_test`, 40 in each `pofa_dev` clone (`pofa_be029_scratch`, `pofa_be029_rehearsal`, `pofa_be029_control`), and 40 in live `pofa_dev` during the approved §12 run. In every case the full original rows were archived first and every archived row matched `username='testuser'` / `email='test@example.com'` (`users_off_signature: []`). |
| Were users merged? | **No.** No canonical account was selected, no password/credential was moved, no `owner_id` was rewritten. The owner's OQ-2 ruling replaced merging with retiring the whole group. |
| Were foreign keys reassigned? | **No.** §15's reassignment design was not needed: the catalog sweep found no reference from outside the retirement set, so nothing had to be repointed. Same result on live `pofa_dev`. |
| Did audit records change? | **No.** `pofa_test`: 30,862 rows before and after, chain `valid=True, failures=0` before and after. Rehearsal clone: 6,017 rows before and after with the identical `valid=False, failures=7` set (same 7 gaps, same sequence numbers). Live `pofa_dev` (§12): 6,017 before and after, same 7 gaps, and the whole-table fingerprint of `audit_ledger_events` identical to the pre-migration backup copy. 0 ledger rows referenced any archived id, and the migration aborts if any do. |
| Anything else that touched data? | **Yes, and it is disclosed.** While debugging the *first* broken draft of the identity test file, 17 users leaked into `pofa_test` (2,098 → 2,115). They were checked for foreign-key references across all ten referencing tables (0 found), then deleted by id. Their `USER_CREATED` audit events (15 rows) remain, because the ledger is append-only and has no FK to the principal — the same ordinary state as the 281 already-dangling `USER_CREATED` rows that routine suite runs leave behind. No production database was involved, and no BE-029 migration wrote those rows. |

---

## 9. Rollback

`downgrade()` was executed, not inspected (§29).

**Retirement revision `r8s9t0u1v028`** restores every archived row literally with
`jsonb_populate_record(NULL::<table>, row_json)` in `users → projects → evidence` order
(the reverse of the delete order), asserts restored count == archived count, deletes the
archive rows, refuses to proceed unless the archive is then empty, and drops the table.

Proven twice on real `pofa_dev` data:

1. `pofa_be029_scratch`: 120 rows archived, restored, re-upgraded.
2. `pofa_be029_rehearsal` (pristine clone): upgrade → `compare.py … archive` reported
   **IDENTICAL: every column value matches the pre-upgrade snapshot** for all 120 rows;
   `downgrade q7r8s9t0u027` → `compare.py … restored` reported the same line for the live
   rows; the post-downgrade catalog showed `users` 1,094, `projects` 584, `evidence` 324,
   residue 40, duplicate groups 1 and 1, both indexes non-unique again, archive table gone,
   `uq_user_identity_subject` untouched, `external_subject` NULLs back to 1,009/1,094;
   re-upgrade → **every measured metric identical to the first upgrade** and the archive
   again byte-identical to the snapshot.

`Uniqueness revision s9t0u1v2w029` downgrades by recreating the two indexes as non-unique. It
refuses to drop an index that is not UNIQUE, so it cannot silently destroy an index someone
else rebuilt.

Two honest limits:

* Restore depends on the archive still matching the target table's shape. A later revision
  adding a NOT NULL column makes `downgrade()` fail loudly rather than half-restore.
* Rollback does not try to reconcile the database with what happened *after* the migration.
  A full `downgrade` reaches `q7r8s9t0u027` by first relaxing the two UNIQUE indexes, so a
  new row that reused a retired username or email does **not** block the restore — the
  duplicate simply reappears, which is the correct meaning of "undo". What *can* block it is
  `uq_user_identity_subject`, which this task never touched: 35 of the 40 residue rows in
  `pofa_dev` carry a non-NULL `external_subject`, so if a post-retirement row took the same
  provider+subject pair, the restore aborts on a unique violation and the whole downgrade
  rolls back. Same for a primary-key clash. Both are loud, neither is guessed at.

---

## 10. Remaining Risks

1. **The live run is done; its *rollback* is not exercised.** `pofa_dev` was upgraded through
   all five pending revisions to `s9t0u1v2w029` on 2026-10-09 (§12). What remains unproven on
   that specific database is a live `downgrade`: it was executed twice on pristine `pofa_dev`
   clones (§9), never against `pofa_dev` itself, because rolling back the real database was
   not approved and would discard the retirement. Recovery of the retired 40 triples on
   `pofa_dev` therefore rests on the archive table or on the verified pre-migration dump, not
   on an as-yet-unrun downgrade.
2. **`uq_user_identity_subject` is still inert** for NULL `external_subject`. After retirement
   that is *every* row in `pofa_test` (2,079 of 2,079) and 1,004 of 1,054 rows in
   `pofa_dev`-shaped data. Option A's identity guarantee is therefore only half-enforced until
   OQ-3 (backfill / NOT NULL) is decided. The behaviour is pinned by a test so a future change
   is a deliberate act.
3. **Duplicate-key errors were mis-mapped, not unhandled (OQ-5).** This entry originally
   claimed the API "has no handler" for the `IntegrityError` the new unique indexes make
   reachable. The follow-up audit disproved that: `POST /api/v1/auth/users` had carried a
   blanket `except IntegrityError -> 409` since BE-016. The real exposure was therefore the
   *opposite* of a 500 leak — every integrity failure, including primary-key, NOT NULL and
   foreign-key faults that are server defects, was being reported to the caller as "username,
   email, or identity already exists". Corrected on 2026-10-09 by keying the mapping on the
   violated object name; see §13.1.
4. **Uniqueness is byte-exact, not semantic.** `Alice@Example.com` and `alice@example.com`
   are two accounts, because only the service normalises. If Option A is meant to prevent
   look-alike identities, a generated/stored-normalised column or `citext` is a separate
   decision.
5. **`pofa_dev`'s audit chain is broken independently of this task** (7 gaps / 6,017 events),
   and it makes six audit-chain integration tests fail on every database that inherits that
   history. Those tests pass on `pofa_test` and on fresh databases.
6. **The archive table is a new permanent object** with one writer and one reader (the
   migration). Nothing in the application queries it, and the drift gate now knows about it
   through `IdentityRetirementArchive`.
7. **Case-variant collisions in the *existing* data**: measured as none — the case-folded and
   plus-tag grouped duplicate counts are both 1 (the fixture group) in each database, so
   retiring the fixture set genuinely emptied the duplicate space rather than hiding variants
   behind exact-match luck.

---

## 11. Next Task

**BE-030 is not started and is not recommended by default.** The one follow-up that follows
directly from measured results is the smallest:

1. **Decide OQ-3 (`external_subject`).** Either backfill it — 1,004 rows in `pofa_dev`-shaped
   data, 2,079 in `pofa_test`, i.e. every surviving row there — and make the column NOT NULL,
   or record formally that `(identity_provider, external_subject)` is a partial key. Today
   BE-029 leaves Option A's identity guarantee half-enforced, and that is a decision waiting,
   not an oversight.
2. ~~Then **OQ-5**: map the now-reachable `IntegrityError` on duplicate username/email to a 409
   with a field-level message~~ — **done by the follow-up on 2026-10-09** (§13.1). The mapping is
   keyed on the violated database object, so an unrelated integrity failure is no longer reported
   as a duplicate identity.
3. Separately, and outside BE-029's scope: **`pofa_dev`'s 7 audit-chain gaps**. A read-only
   reconciliation of the missing sequence ranges would let the six audit-chain tests be
   meaningful on a `pofa_dev`-shaped database again.
4. ~~**Run the live `pofa_dev` migration** once the evidence package is approved~~ — **done on
   2026-10-09** after owner approval; the rehearsal was reproducible and the live run matched
   it exactly (§12).

> **Dated pointer (2026-10-10), after the closure pass in §14.** The list above is kept verbatim as
> the record of what this task believed at the time. Current status:
>
> * **Item 1 (OQ-3) is still open.** No decision was taken and no value was invented (§14.3).
> * **Item 3 moved into BE-030**, together with the enforcement and chain-awareness gaps §14.6–§14.11
>   measured. The named six tests are unchanged and still fail on `pofa_dev`-shaped data for the same
>   reason.
> * **Two claims in the older sections were superseded by measurement** and carry dated corrections
>   where they appear, not silent edits: §7.2's "the only change to that file in this task is zero"
>   was true when written, but Phase F subsequently changed
>   `tests/integration/test_be025_admin_control_plane.py` — it strengthened, rather than weakened,
>   the volume-sensitive assertion after fixing the underlying `total` defect (§14.5); and §12.7's
>   attribution of the Alembic artifact to reflection was corrected to the comparison layer (§14.7).
> * **BE-030 now has a task file** — `docs/Production Task Files/BE-030 — Audit Ledger Append-Only
>   Enforcement & Chain Integrity.md`. Writing it was Phase K; **executing it is not authorised by
>   this document**, because its two design decisions are open (§14.12).

---

## 12. Live execution on `pofa_dev` (2026-10-09)

### 12.1 Approval and its boundaries

Owner approval (G3) authorised exactly: retire the 40 verified synthetic
user/project/evidence triples (120 rows), archive the full original rows before deleting
them, add UNIQUE indexes on `users.username` and `users.email`, and apply the pending
Alembic revisions through `s9t0u1v2w029`. It explicitly excluded unrelated data cleanup,
`external_subject` repair, authentication changes, commit and push. OQ-3, OQ-5 and OQ-6
therefore remain open after this run, and nothing in §12 pre-empts them.

### 12.2 Quiesce (Phase 1)

`pg_stat_activity` showed no application connection to `pofa_dev` — the only backend on that
database was the probe's own session. No process was listening on the API ports and no
`python` / `uvicorn` / `celery` / `node` process existed on the host. Re-checked at the end of
Phase 5, after every write and verification step, with the same result: zero connections to
`pofa_dev` apart from the probe sessions. `current_database()` was confirmed as `pofa_dev`
rather than trusting the connection string (§27).

### 12.3 Fresh, verified, recoverable backup (Phase 2)

Taken immediately before the migration, at a unique timestamped path, without touching the
earlier verified backup:

| Item | Value |
| --- | --- |
| Path | `D:\CODING\Scratch\be029\backups\pofa_dev_20261009T152259Z_pre-migration.dump` |
| Size | 1,728,985 bytes |
| SHA-256 | `5e6f926d6d757e8539181b537d4671095282af2f22526032ac13fd214f1746d4` (computed twice, in-container and after `docker cp`) |
| `pg_dump -Fc` | exit 0 |
| `pg_restore --list` | exit 0, 484 TOC entries |
| Restore test | restored into a **new** scratch database `pofa_be029_premig_verify` (exit 0, empty stderr log, 4.93 s) |
| Content proof | 69 / 69 tables matched the source on row count *and* on `md5(string_agg(t::text, E'\n' ORDER BY t::text))`, including the 40/40/40 candidate set and the 6,017-row ledger; 66 catalog objects differed only in deparsed text and were each proven predicate-equivalent by evaluating both forms over stored values, a bogus value and `NULL` (`restore_verify_premig.json`, `check_equiv.py`) |

A restored copy — not `pofa_dev` — is what the post-migration diff was computed against, so
the comparison had a pre-migration ground truth.

### 12.4 Preflight gates (Phases 1 and 3)

`preflight_live.py` (read-only, 9 gates: database name, revision, the 120 reviewed candidate
ids, the five shape checks, catalog-driven FK closure with composite-FK abort, ledger count
and span, the two duplicate groups, the fixture literals outside the candidate set, archive
absence, and every table's count + fingerprint) exited **0 at Phase 1 and again at Phase 3**,
immediately before the upgrade. The reviewed target set
(`live_dev_target_set.json`) matched the candidate ids in both gates, and the migration then
removed exactly those rows.

The gate was also validated *negatively*: pointed at `pofa_test` it exited 1 with 9 findings,
so a wrong target cannot pass it. Pre-migration state, recorded twice (`p0_pofa_dev_predump.json`):
`n4o5p6q7r022`, 1,094 / 584 / 324 rows, residue 40/40/40, one duplicate username group
(`testuser`, n=40) and one duplicate email group (`test@example.com`, n=40), both indexes
plain `CREATE INDEX`, ledger 6,017, no archive table.

### 12.5 The upgrade (Phase 4)

`alembic upgrade head` against the explicit `pofa_dev` connection, run from the repository
root with the project interpreter. No guard was bypassed, no constraint disabled, no
retirement SQL executed outside the reviewed revisions.

Exit 0 in 4.608 s, applying five revisions — this is the deviation §10 used to carry as a
risk, now resolved:

```
n4o5p6q7r022 → o5p6q7r8s025 (BE-025) → p6q7r8s9t026 (BE-026) → q7r8s9t0u027 (BE-028)
             → r8s9t0u1v028 (BE-029 1/2) → s9t0u1v2w029 (BE-029 2/2)
```

### 12.6 Post-migration checks (Phase 5)

| # | Check | Measured result |
| --- | --- | --- |
| 1 | Revision | `current()` = `s9t0u1v2w029`, one head, linear history |
| 2 | Archive | `identity_retirement_archive` present with **120 rows = 40 users / 40 projects / 40 evidence** |
| 3 | Archive integrity | Each archived `row_json` compared column-by-column against the pre-migration snapshot: **"IDENTICAL: every column value matches the pre-upgrade snapshot"**; `triple_linkage_ok: true` |
| 4 | Counts | 1,054 / 544 / 284 — exactly 40 off each pre-migration figure |
| 5 | Residue predicate | 0 candidate users, 0 projects, 0 evidence |
| 6 | Duplicates | 0 duplicate username groups, 0 duplicate email groups (`dup_username_values` / `dup_email_values` both empty) |
| 7 | Indexes | `CREATE UNIQUE INDEX ix_users_username`, `CREATE UNIQUE INDEX ix_users_email`; catalog `pg_index.indisunique` true for both |
| 8 | Unrelated constraints | `uq_user_identity_subject UNIQUE (identity_provider, external_subject)`, `ck_user_status` and `users_pkey` byte-identical to pre-migration; 0 constraints dropped |
| 9 | Protected rows | `post_verify_diff.py` vs the restored backup: **65 other pre-existing tables byte-identical**; row-level image subtraction gives removed = 120 (the reviewed ids), added = 0, surviving rows modified = 0; claims, review cases, organizations and role assignments unchanged |
| 10 | Ledger | 6,017 rows before and after, whole-table fingerprint identical, 0 rows referencing an archived id |
| 11 | Chain | `chain_probe.py` (read-only `verify_chain()`) at head: span 1..6,053, `valid=False`, **the same 7 pre-existing gaps** (before 5350, 5380, 5385, 5392, 5397, 5677, 5682) — no new discrepancy |
| 12 | Tests | `tests/unit/test_migrations.py` **8 passed**; `test_be029_identity_contract.py` + `test_schema_drift_gate.py` **21 passed** (both against `pofa_test`, so no test wrote to `pofa_dev`) |
| 13 | Still quiescent | Re-checked after every verification step: no application connection, no listener, no app process |

**Verdict of the blast-radius check:** `VERDICT: MIGRATION TOUCHED ONLY THE REVIEWED 120 ROWS`
(19 indexes added / 0 dropped, 48 constraints added / 0 dropped — the additions are BE-025,
BE-026 and BE-028 objects that `pofa_dev` had never received, not BE-029 ones).

### 12.7 `alembic check` on `pofa_dev`: reported, and attributed rather than asserted

`alembic check` against the migrated `pofa_dev` still prints `FAILED` with exactly two
operations: `remove_constraint` / `add_constraint` on `user_role_assignments.uq_user_role_scoped`.
That is the pair already documented as category B (an Alembic 1.11.2 reflection artifact —
it does not carry `NULLS NOT DISTINCT`), created by revision `i9d0e1f2g016` in BE-016 and
therefore untouched by this task. Verified three ways instead of asserted: the signatures
were recomputed with the gate's own `include_object` hook and `compare()`
(`drift_signatures_pofa_dev_postmig.txt`: *"operations reported: 2 … gate verdict: CLEAN"*);
`uq_user_role_scoped` is defined by a BE-016 revision, not a BE-029 one; and the BE-028
category-E pair that BE-029 was meant to close (`remove_index`/`add_index` on
`ix_users_username` / `ix_users_email`) is **absent** from the diff, which is the positive
proof that the model and the live schema now agree on identity uniqueness.

> **Corrected 2026-10-10:** the mechanism behind that pair is not reflection — SQLAlchemy 2.0.52 does
> hand Alembic `postgresql_nulls_not_distinct=True`, measured. The loss is in Alembic's own
> `_make_unique_constraint()`. See §14.7; the classification (category B, artifact not drift) and this
> section's verdict both stand unchanged.

### 12.8 Behaviour of the new constraint on real migrated data

Proving the constraint on fixtures is weak; proving it on 1,054 production-shaped rows is not.
`pofa_dev` was cloned read-only into `pofa_be029_devpost` (nothing was connected to the
template, so the clone could not disturb it) and probed there:

* duplicate an existing real `username` → **rejected (`UniqueViolation`)**
* duplicate an existing real `email` → **rejected (`UniqueViolation`)**
* brand-new username + email → **accepted**
* every insert ran in a savepoint that was rolled back; users count 1,054 before and after

The same suite passes on that clone: **29 passed** (15 identity-contract + 6 drift-gate +
8 migration), so BE-029's contract holds against the real migrated dev dataset, not only
against `pofa_test`. `pofa_dev` itself was never a test target.

### 12.9 Deviations, limits and what was *not* done

1. **Five revisions, not two.** `pofa_dev` was 5 behind, so BE-025, BE-026 and BE-028 were
   applied in the same run. This was known and approved, and check 9 attributes every added
   object to those revisions.
2. **`alembic upgrade head -v`** was rejected by Alembic (`unrecognized arguments: -v`,
   exit 2) and nothing executed; the run was re-issued without the flag. No state change.
3. **No `downgrade` was executed against live `pofa_dev`.** Rollback remains proven on clones
   only (§9, §10.1).
4. **No commit, no push, no working-tree cleanup.** `backend/db/models.py`,
   `tests/schema_drift_baseline.py`, `tests/integration/test_schema_drift_gate.py`,
   `tests/unit/test_migrations.py` and the five new BE-029 files remain uncommitted pending
   OQ-6. Scratch databases (`pofa_be029_scratch`, `_control`, `_rehearsal`, `_fresh`,
   `_bkpverify`, `_premig_verify`, `_devpost`, `pofa_audit_verify`) are retained as evidence.
5. **The API and workers were left stopped**, as instructed; restarting them is not part of
   this approval.
6. Credentials appear nowhere in this document; connection targets are named by database.

---

## 13. Follow-up (2026-10-09): auth conflict handling and reversibility proof

Two deliverables, kept independently testable: (1) duplicate-identity violations in the
user-creation flow must produce the API's conflict response without swallowing unrelated
database faults; (2) BE-029's reversibility must be proven against a *copy of the migrated
`pofa_dev`*, not against a fixture-shaped scratch database. Nothing in §12's schema work was
reopened, rolled back or re-applied on live `pofa_dev`.

### 13.1 Auth `IntegrityError` handling — what the audit actually found

The premise handed to this task was "a raw HTTP 500 reaches the client on duplicate
username/email". The audit disproved it:

| Fact | Evidence |
| --- | --- |
| `POST /api/v1/auth/users` already mapped `IntegrityError` → **409**, since BE-016 | `git blame` on the handler: commit `332b10f6` |
| That mapping was keyed on the **exception type**, so *every* integrity failure became "Username, email, or identity already exists" | same handler, one `except` clause, no discrimination |
| SQLSTATE `23505` is shared by unique-index **and** primary-key violations, so the type/state cannot distinguish them | measured: `diag.sqlstate == '23505'` for both `ix_users_username` and `users_pkey` |
| The violated object name is available and stable | `error.orig.diag.constraint_name`, with a message-regex fallback for drivers that do not populate `diag` |
| Where the violation surfaces | `auth_repo.insert_user()` flushes, so it raises before `_audit_admin()` / `db.commit()`; the request session is closed by `get_db()`'s `finally` |
| Blank username/email never reaches the database | `create_user()` raises `ValueError` → 422 first |
| A genuine server fault is 500 `{"detail": "internal server error"}` | the app's single catch-all handler; confirmed with `TestClient(app, raise_server_exceptions=False)` (`probe_500.txt`) |

So the defect was the **opposite** of a 500 leak: unrelated integrity failures were being
dressed up as caller errors. The fix narrows the mapping rather than adding one.

`backend/services/authorization.py` gained `IDENTITY_UNIQUE_OBJECTS`
(`ix_users_username`, `ix_users_email`, `uq_user_identity_subject`) and
`identity_conflict(error)`, which returns the violated object name only when it is one of
those three. `backend/api/v1/endpoints/auth.py` now does
`db.rollback()` → if `identity_conflict()` is `None` **re-raise** (catch-all answers 500) →
otherwise 409 with the existing, unchanged, non-sensitive message.

| Request | Before | After |
| --- | --- | --- |
| duplicate `username` | 409 | 409 (same body) |
| duplicate `email`, including a case/padding variant that normalises onto an existing one | 409 | 409 |
| duplicate `(identity_provider, external_subject)` | 409 | 409 |
| valid unique pair | 201 | 201 |
| `users_pkey` clash | **409, blamed on the caller** | **500 `internal server error`** |
| NOT NULL violation on `users.username` | **409** | **500** |
| FK violation on `projects.owner_id` | **409** | **500** |
| session reuse after any of the above | rollback ran | rollback still runs first; the next request on the pool succeeds |

No pre-check-then-insert was added — the database indexes remain the source of truth under a
race. `external_subject`, identity resolution, login and authentication rules were not touched,
and `POST /api/v1/auth/clients` (which has its own blanket handler for a different table) was
left alone as out of scope.

Tests: `tests/integration/test_be029_identity_conflict_api.py`, **12 tests** — the three
conflict shapes, session usability immediately after a conflict, the success path, the three
non-identity violations asserted at the service boundary *and* over HTTP, a test that pins the
shared-`23505` fact (so a future "just check the SQLSTATE" refactor cannot pass silently), and
the `diag`-less fallback path. They are self-cleaning (every created row is purged by id and by
identity value) and assert that no response body contains SQL text, constraint names, or
traceback markers. **Negative proof**: with the handler reverted to the old blanket form the file
reports `1 failed, 11 passed` — the failure being exactly the pkey-clash-over-HTTP test.

### 13.2 Reversibility on a disposable clone of the migrated `pofa_dev`

`pofa_be029_rollback` was created with `CREATE DATABASE … WITH TEMPLATE pofa_dev`, after the
tool confirmed the name was absent from `pg_database` (it refuses to overwrite or drop an
existing target) and that **0 sessions** were connected to the template. The downgrade and the
re-upgrade ran against this clone only; `pofa_dev` stayed at `s9t0u1v2w029` and `pofa_test`
was never rolled back.

Verification method, per snapshot (`rb_state.py`): every table's row count plus
`md5(string_agg(t::text, E'\n' ORDER BY t::text))`; complete PK-keyed row images for
`users`/`projects`/`evidence`; the whole archive with verbatim `row_json`; catalog index and
constraint definitions; duplicate groups; the residue predicate; ledger count/span. Diffs are
computed row-by-row (`rb_diff.py`), with a separate column-level archive-vs-live comparison
(`rb_restore_check.py`) and an all-foreign-key orphan sweep (`rb_fk_check.py`).

| Stage | Measured |
| --- | --- |
| Clone baseline | revision `s9t0u1v2w029`; 73 tables; 1,054 / 544 / 284; archive **120 = 40/40/40**; residue 0; 0 duplicate groups; `ix_users_username` and `ix_users_email` both `CREATE UNIQUE INDEX`; `uq_user_identity_subject` = `UNIQUE (identity_provider, external_subject)`; ledger 6,023, span 1..6,059; chain `valid=False` with the same 7 pre-existing gaps as `pofa_dev` — **matches the §12.6 baseline** (ledger count differs only because of §13.4) |
| `alembic downgrade q7r8s9t0u027` | exit 0, two steps in the correct order: `s9t0u1v2w029 → r8s9t0u1v028 → q7r8s9t0u027` |
| Post-downgrade | 1,094 / 584 / 324 (+40 each); residue 40; duplicate groups restored: `testuser` n=40 and `test@example.com` n=40; both indexes back to plain `CREATE INDEX`; `identity_retirement_archive` gone; **120/120 archived rows restored with their original primary keys and identical column values — 1,120 column comparisons, 0 mismatches, 0 extra restored rows**; `uq_user_identity_subject`, `users_pkey` and `ck_user_status` byte-identical; 113 foreign keys, 0 orphan rows; 68 of 72 shared tables byte-identical, the only other difference being `alembic_version`; **ledger 6,023, span 1..6,059, whole-table fingerprint IDENTICAL** |
| `alembic upgrade head` (same clone) | exit 0, `q7r8s9t0u027 → r8s9t0u1v028 → s9t0u1v2w029` |
| Post-re-upgrade | back to 1,054 / 544 / 284; residue 0; 0 duplicate groups; both unique indexes present and UNIQUE; `identity_retirement_archive` recreated with **exactly 120 rows = 40/40/40**; surviving rows modified **0**; ledger fingerprint still IDENTICAL |
| Round trip (baseline vs post-re-upgrade) | **72 of 73 tables byte-identical**, including `users`, `projects`, `evidence` and `alembic_version`; the only difference is `identity_retirement_archive`, and comparing it payload-for-payload shows the identical `(source_table, source_id)` set with **identical `row_json` on all 120 rows** — only `retired_at` moved, which the migration writes as a new wall-clock value |
| Schema signature | `alembic check` on the re-upgraded clone reports the **same two operations** as live `pofa_dev` (`remove_constraint`/`add_constraint` on `user_role_assignments.uq_user_role_scoped`, the BE-016 `NULLS NOT DISTINCT` reflection artifact of §12.7) and **no users-related operation** — i.e. rollback+replay lands on exactly the baseline schema state |
| Contract on the clone | `test_be029_identity_contract.py` + `test_be029_identity_conflict_api.py` → **27 passed** against `pofa_be029_rollback`, so the re-upgraded dev-shaped database enforces the same identity contract as the live one |

No row was ever deleted by hand, no constraint was disabled, and no manual repair was needed:
both directions passed first time, so the "preserve for diagnosis" branch was not triggered.

### 13.3 Suites (all against `pofa_test`, none against live data)

| Run | Result |
| --- | --- |
| `test_migrations.py`, `unit/test_authorization.py`, `integration/test_authorization.py`, `test_be025_admin_control_plane.py`, `test_be029_identity_contract.py`, `test_be029_identity_conflict_api.py`, `test_schema_drift_gate.py` | **90 passed, 1 failed** |
| `tests/unit` (whole) + `test_migration_and_crud.py` + `test_be027_foundation_contract.py` | **439 passed, 1 skipped** (skip is the ML-stack preflight case) |

The single failure is `test_organization_lifecycle_noop_audit_and_isolation`, at
`assert str(org.id) in ids` on the default-page organisation list — the documented
volume-sensitive BE-025 assertion (`pofa_test` now holds far more organisations than the
endpoint's default page). It predates this follow-up, is unrelated to identity or to the
handler change, and was **not** weakened, skipped or deleted.

### 13.4 Deviation: a scratch probe wrote 6 audit-ledger events into live `pofa_dev`

Reported rather than buried. To decide whether the server-fault test should assert 500 or an
propagated exception, a scratch script exercised the app's `TestClient` **outside pytest**, so
it did not inherit `TEST_DATABASE_URL`; `settings.database_url` therefore pointed at
`pofa_dev`. It created three ADMINISTRATOR users (`probe-admin-*`) plus three role
assignments — 6 events, `USER_CREATED` and `ROLE_ASSIGNED`, sequences 6,054–6,059, timestamps
2026-10-09 15:57:40–15:58:15 UTC — and then deleted the rows it had made.

Verified current state of live `pofa_dev` (read-only): `users` 1,054, `projects` 544,
`evidence` 284, archive 120, residue 0, **0** users matching `probe-admin-%`, **0** role
assignments for the three ids in those payloads — so no live row from the probe remains. What
remains is the ledger itself, which is append-only: 6,017 → 6,023 events, span 1..6,053 →
1..6,059, chain verdict unchanged (`valid=False`, the same 7 pre-existing gaps). Deleting those
rows would break the hash chain and was not attempted; correcting them is an owner decision
beside §11.3, not a cleanup this task may perform. The migration and the reversibility proof
added, removed and modified **no** ledger rows (§13.2).

Lesson carried forward: any script that constructs the app must set `DATABASE_URL` explicitly
rather than relying on the repository default.

### 13.5 Still not done

1. **No commit, no push** (OQ-6). The follow-up adds two modified files
   (`backend/services/authorization.py`, `backend/api/v1/endpoints/auth.py`) and one new test
   file to the working tree alongside the BE-029 schema changes; no unrelated modification was
   touched, staged or cleaned.
2. **OQ-3** (`external_subject` nullability / backfill) and **OQ-6** remain undecided.
3. **API and workers were left stopped**, as instructed; no restart, and no request traffic was
   sent to the deployed service.
4. **Scratch databases retained as evidence**, including `pofa_be029_rollback` (now at head,
   carrying the probe rows written by the §13.2 suite run) — nothing was dropped.
5. `pofa_be029_rollback` proves reversibility of *this* dev-shaped dataset. A `pofa_dev` with
   data that has diverged from the archived 120 rows would still downgrade cleanly, but that is
   asserted by the migration's own restore-from-JSONB mechanism, not measured here.

---

## 14. Final closure (2026-10-09 → 2026-10-10): Phases A–I, BE-030 feasibility, and the blocked list

Master document: `# BE-029 FINAL CLOSURE + BE-030 EXECUTION`. This section records what was
**measured and executed** in that pass, phase by phase, with the historical observations of §7 and
§13 left intact. Where this pass contradicts an earlier statement here, the contradiction is written
as a dated correction rather than an edit of history.

Nothing in this pass was committed (§14.12). No downgrade ran against any live database.

### 14.1 Phase A — the measured baseline

Baseline run, `pofa_test` at head, taken as the first action of this pass:

```
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test
backend/.venv312_repro/Scripts/python.exe -m pytest -q --tb=line -p no:randomly tests/integration
→ 2 failed, 320 passed, 9 warnings in 568.40 s
```

The two failures, with their later-confirmed causes:

| # | Failure | Cause established in this pass |
| --- | --- | --- |
| 1 | `test_be025_admin_control_plane.py::test_organization_lifecycle_noop_audit_and_isolation` | The §13.3 volume-sensitive assertion — re-measured and re-attributed in Phase F (§14.5), **not** accepted on prior attribution. |
| 2 | `test_be027_foundation_contract.py::test_readiness_reports_the_database_as_unavailable_when_it_really_is` | **Caused by this pass, not pre-existing.** A Phase C edit routed readiness through the cached application engine, which made it blind to `settings.database_url`. Order-dependent: it passed in isolation and failed in the full run. Fixed and pinned (§14.2). |

Historical baselines preserved unchanged in §7.2 and §13.3 (unit `439 passed, 1 skipped`; the
`pofa_test` integration run `296 passed, 1 failed`). Archived raw outputs for this pass, all under
`D:\CODING\Scratch\be029\`: `concurrency_failure.txt` (the Phase B concurrency test failing on
`NameError: threading` before it was completed), `assumption_run.log` + `assumption_results.json`
(Phase E), `ledger_remeasure.json` + `ledger_append_only.json` (Phase G), `phase_h_drift.json`
(Phase H), `phase_i_matrix.log` (Phase I).

### 14.2 Phase C — database test isolation is now enforced, not documented

**The defect this closes is §13.4**: a scratch script that built `TestClient(app)` outside pytest
inherited `.env`, resolved to `pofa_dev`, and wrote permanent append-only ledger events there. A
documented rule had failed to prevent it, so this phase added an enforcement point instead of
another rule.

Resolution chain, in order, with the check each link performs:

| Link | File | What it proves |
| --- | --- | --- |
| 1. URL resolution | `backend/db/test_target.py` | `TEST_DATABASE_URL` is the only supported source. Absent → hard collection error, never a fallback to `DATABASE_URL`. `pofa_dev` is blocked outright. |
| 2. Arm the context | `backend/db/safety.py` (new) | `arm_pytest(name)` publishes `POA_DATABASE_CONTEXT=pytest` + `POA_AUTHORIZED_DATABASE_NAME=<name>` before any engine exists. |
| 3. Guard the only engine factory | `backend/db/session.py` | `build_guarded_engine(url)` → `guard_url()` rejects a URL naming the wrong database **before connecting**; `confirm_server_database()` then asks the server `SELECT current_database()` and refuses any other name. `get_engine()` is the only other caller; verified: `build_guarded_engine` is the sole `create_engine(` site in `backend/`. |
| 4. Guard migrations too | `alembic/env.py` | `declare_target` runs on every Alembic invocation and logs `Alembic target database: <name>`; offline mode falls back to URL text, which is all it can reach. |
| 5. Guard the probe path | `backend/observability/health.py` | `PostgresHealthCheck` now builds a per-call engine through `build_guarded_engine(settings.database_url)` and disposes it, instead of reusing the application's cached engine. |

Contexts: **unset** = normal application/worker/Alembic runtime, guard inert, no behaviour change
(so production startup is not broken by this); **`pytest`** = server name must equal the armed name;
**`verification`** = ad-hoc probes, target must be passed explicitly to `arm_verification(url)` and
may not be `pofa_dev` **or** `pofa_test`.

Regression introduced and then pinned: replacing the cached engine in readiness initially made
`test_be027_foundation_contract.py` fail in full runs (§14.1 #2) because the mocked seam and the
real cached-engine path diverged. Both unit tests in `tests/unit/observability/test_health.py` were
repointed at the real seam (`patch("backend.db.session.build_guarded_engine")`), and three tests
were added to the guard suite so the property that broke is asserted directly:

| New guard test | What it refuses to let regress |
| --- | --- |
| `test_readiness_probes_the_configured_dsn_not_the_cached_engine` | Readiness must follow `settings.database_url` even after the application engine is already cached — the outage case §13.4-style, where the pool was opened before the database moved. |
| `test_armed_readiness_refuses_a_foreign_database_before_connecting` | A verification-context readiness probe against a protected name raises `ProtectedDatabaseError` rather than reporting on it. |
| `test_unarmed_readiness_reaches_a_real_connection_refusal` | Unarmed (normal runtime) still produces a genuine `OperationalError` from a real socket, and health reports UNHEALTHY — i.e. the guard did not become a stub that swallows faults. |

Suite: `tests/integration/test_be029_database_safety_guard.py` — **16 tests**, plus
`tests/unit/test_database_safety.py` for the pure URL/context logic. Combined with the BE-027
foundation file: **33 passed**.

**How to run the integration suite (the documented, supported way):**

```bash
export TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"
backend/.venv312_repro/Scripts/python.exe -m pytest -q tests/integration
```

The header pytest prints (`tests/conftest.py::pytest_report_header`) states the target explicitly —
`PoA test database: pofa_test` / `PoA test database source: TEST_DATABASE_URL` — so a run's target is
part of its output, not an assumption. Omitting `TEST_DATABASE_URL` is a loud refusal
(`TEST DATABASE NOT CONFIGURED`), never a switch to `.env`.

**Standalone scripts** (outside pytest — the class of thing that caused §13.4) must set
`DATABASE_URL` for the process *and* declare the target: `safety.arm_verification(url)` then
`build_guarded_engine(url)`. `arm_verification` takes the URL as a required argument and raises on an
empty one; there is no default to fall back to. Both Phase E and Phase G probes are written that way.

### 14.3 Phase D — `external_subject`, decided from behaviour only

§2 carries the dated correction and the full read/write trace. The conclusion in one line: the
`(identity_provider, external_subject)` pair is a **declared, write-only key with no consumer** —
nothing in `backend/` queries it, principal resolution keys entirely on `User.id`
(`security/authentication.py:72-74` → `repositories/authorization.py:46-47`), and every surviving
row in both databases uses `identity_provider = 'local'`.

Because no behaviour depends on the column being non-NULL, **no product rule was invented for it**.
No NOT NULL was added, no value backfilled, no identity manufactured, no user merged, no historical
key reinterpreted. `uq_user_identity_subject` is untouched (`contype='u'`, definition still exactly
`UNIQUE (identity_provider, external_subject)`), and the NULL-coexistence behaviour stays pinned by
`test_null_external_subject_rows_are_permitted_and_do_not_collide`.

**OQ-3, presented for the owner rather than answered here:**

| Option | What it means | Evidence-based reading |
| --- | --- | --- |
| (a) Leave nullable, as today | The constraint stays inert for NULL rows (1,009 of 1,094 pre-retirement in `pofa_dev`; all 2,098 in `pofa_test`). | Correct *for the current system*: there is no federated login to protect. Cost: the pair cannot be relied on as an identity key by a future flow without re-deciding this. |
| (b) Backfill NULLs with generated `uuid4()` and add NOT NULL | Every row gets a subject, and the constraint becomes live. | **Rejected by evidence, not preference.** It manufactures identities for rows whose real subject is unknown, and `create_user()` already generates a `uuid4` for *new* rows only — so a backfill would silently extend a convention the service never applied to those rows. Not executed. |
| (c) Add NOT NULL without backfill | — | Fails on existing data in both databases; it is option (b) with a broken migration. |
| (d) Decide when the federated flow is specified | Carry OQ-3 as an open, named decision attached to the login-flow work. | The only option consistent with "insufficient evidence ⇒ do not invent a rule". |

**Recommendation: (a) now, (d) as the trigger.** The nullable column costs nothing today and every
alternative needs product input on what an external subject *is* for a local account. It stays an open
owner decision and is **explicitly out of BE-030's scope** — BE-030 is the ledger task, and BE-030 §3.2
names OQ-3 as a non-goal so a future reader cannot assume the identity question rode along with it.

### 14.4 Phase E — §6 check 12: the migration refuses to run on violated assumptions

Check 12 asks whether downgrade and upgrade **fail safely when their assumptions are violated**,
which §9 and §13.2 had not proven: they showed the happy path only. Six scenarios were driven
against a disposable database, `pofa_be029_assumptions`, created and destroyed by the harness itself
(`assumption_violations.py`; `--reset` drops and recreates it, which S6 makes necessary because that
scenario removes the archive the shipped downgrade requires). **No live database was a target**; the
harness arms the `verification` context, so pointing it at `pofa_dev` or `pofa_test` raises before it
connects.

| # | Violation injected | Expected | Measured |
| --- | --- | --- | --- |
| S1 | none — valid residue at `q7r8s9t0u027` | upgrade succeeds | exit **0**; `s9t0u1v2w029`; users 3 → 1, `identity_retirement_archive` 0 → 6 rows. |
| S2 | a candidate owns two projects (shape violation) | upgrade refuses | exit **1**, predicate line `- owns exactly one project: 1 violating row(s)` (its companion `- every candidate project holds evidence: 1 violating row(s)` also fires); revision **stays** `q7r8s9t0u027`; users 2, projects 3, evidence 1 unchanged; archive absent. |
| S3 | a candidate appears in the ledger as actor/project/resource | upgrade refuses | exit **1**, `- no audit ledger involvement (actor, project or resource): 1 violating row(s)`; **ledger md5 identical before/after** (`f95f052d20f37c5255f41bf1b482c2fa`, span 1-1); revision unchanged; no archive. |
| S4 | a non-candidate row references a candidate | upgrade refuses | exit **1**, `- non-retirement reference into the set: users: activities.actor_id = 1`; every count unchanged; revision unchanged. |
| S5 | downgrade with a corrupted archive key (archived id does not match) | downgrade aborts, archive intact | exit **1**, `RetirementAborted: BE-029 downgrade restored 0 of 1 archived users rows; keeping the archive intact so no snapshot is lost`; archive still 3 rows; **nothing restored**; still at `s9t0u1v2w029`. |
| S6 | downgrade with the archive table missing | downgrade aborts, no partial restore | exit **1** (`UndefinedTable: relation "identity_retirement_archive" does not exist`); **no partial restore**; still at `s9t0u1v2w029`. |

Every scenario matched its expectation (`refused_as_expected: true` in all six), and in all four
refusal cases the database was left exactly where it started — the guards run before any DELETE, so
no half-applied state was produced and no repair was needed. §6's twelve checks are now all covered;
checks 1–11 as recorded in §9/§12/§13.2, check 12 here.

### 14.5 Phase F — the BE-025 regression, investigated rather than inherited

Prior attribution (§13.3) said "volume-sensitive assertion, pre-existing, unrelated". **Re-measured
from scratch before accepting it**, because the same symptom had two candidate causes — a test that
assumed page 1 contains everything, or an endpoint that paginates wrongly.

Measurement on `pofa_test`: `GET /api/v1/auth/organizations` → `total = 94`, page length `50`
(default `limit`), and the newly created organisation's rank under the endpoint's own
`ORDER BY name, id` = `94`. So the row was real and visible; the test's `assert str(org.id) in ids`
was checking a 50-row page for the 94th item. The endpoint's contract was **verified correct**:
`auth.py:305-321` computes `total = query.count()` *before* slicing, orders by `(name, id)`, and
bounds `limit` at 1..100. Cause established as the test, not the endpoint — and established by
measurement, not by inheriting §13.3.

Fix, with the constraint "never weaken, skip, delete or re-page-size a test" in force: the
assertion was **replaced by a stronger one**, not relaxed. A `walk_organizations(headers, limit)`
helper paginates to exhaustion and asserts (i) every page is 200, (ii) `total` equals the number of
rows enumerable, and (iii) the created organisation appears **exactly once across all pages** — a
property the old single-page check never proved. Two more pagination properties were added while
there: enumerate-exactly-once at two different page sizes (`limit=100` snapshot vs `limit=7` walk)
in `test_pagination_bounds_and_enumeration`.

While measuring the pagination contract, a **different, genuine endpoint defect** was found:
`list_user_roles` (`auth.py`) sorted the caller-visible assignments, sliced them, and then reported
`total=len(rows)` *after* slicing — so `total` was the page length, and any client paging on it
would stop after page 1 and silently miss every remaining role assignment.

| | Before | After |
| --- | --- | --- |
| 2 assignments, `?limit=1` | `items` 1, **`total` 1** | `items` 1, **`total` 2** |
| `?offset=0/1` | second assignment unreachable via `total` | each assignment returned exactly once across the pages |

FIXED at `auth.py:523-537` (`total` now counts the full visible list, `items` is the slice) and
VERIFIED by a new test,
`test_be025_admin_control_plane.py::test_role_assignment_list_reports_the_visible_total_not_the_page_length`;
the whole file is **17 passed**. Classification: FOUND → FIXED → VERIFIED, in a different function
than the one that failed — reported as such rather than filed under "BE-025 fix".

**Reported only, deliberately not changed:** the same endpoint family is inconsistent in envelope
shape. `/users`, `/organizations`, `/units` and `/users/{id}/roles` return `{items, limit, offset,
total}`; `GET /api/v1/auth/roles` (`auth.py:445-458`) and `GET /api/v1/auth/permissions`
(`auth.py:461-474`) accept `limit`/`offset` but return a **bare list with no total**, so a client
cannot tell a truncated list from a complete one. Changing them alters the published OpenAPI schema
and every existing consumer — an owner decision, not this task's. Carried to BE-030 as a candidate.

### 14.6 Phase G — audit-ledger integrity and history

Two questions, both answered by measurement rather than reading the code and agreeing.

**1. What is the real state of `pofa_dev`'s ledger?** (`ledger_remeasure.py`, read-only session,
the shipped `verify_chain()` — never a re-implementation.)

| Measurement | Value |
| --- | --- |
| Revision / count / span | `s9t0u1v2w029`, 6,023 events, span 1..6,059 |
| `missing_by_span` vs span | **36** |
| Distinct sequence numbers | 6,023 — equal to the row count, so **no duplicate numbers** |
| Gaps | **7 ranges**: 5344-5349 (6), 5374-5379 (6), 5381-5384 (4), 5386-5391 (6), 5393-5396 (4), 5671-5676 (6), 5678-5681 (4) = 36 rows |
| `verify_chain(1, 6059)` | `valid=False`, failures = exactly those 7 `"sequence gap before N (expected M)"` lines, **no `event_hash mismatch` anywhere** |
| `verify_chain(6039, 6059)` (this session's tail) | `valid=True`, 21 events |

Conclusion: the chain is broken by **removal**, not by tampering — every surviving event's hash
still recomputes correctly, and the only failures are gaps. That distinction matters: a hash
mismatch would mean a rewrite; gaps mean rows are gone. No renumbering, backfill, deletion or other
correction was performed: the append-only rule and §11.3 make repair an owner decision, and this
phase's job was to state the facts.

**2. Can the writer itself produce a gap, and does the database protect the table?**
(`ledger_append_only_probe.py`, run against the disposable `pofa_be029_assumptions` through
`safety.arm_verification()` + `build_guarded_engine()`.)

| Question | Measured answer |
| --- | --- |
| Do appends stay contiguous? | Yes — sequences 1,2,3, `valid=True`. |
| Does a **rolled-back** append burn a number? | **No.** The rolled-back event took 4, the next committed append was 4, count went 3 → 4. The writer cannot skip a number, not even on abort — which is precisely why a gap in `pofa_dev` is evidence of deletion and nothing else. |
| Does the **database** refuse `UPDATE` on `audit_ledger_events`? | **No.** `refused_by_database: false`. |
| Does the **database** refuse `DELETE`? | **No.** `refused_by_database: false`. |
| What detects it then? | Only `verify_chain()`: deleting sequence 2 from 1..3 yields `"sequence gap before 3 (expected 2)"`, and a payload rewrite yields `"event_hash mismatch at sequence N"`. |
| Does the writer notice and stop? | **No.** After a committed deletion it kept appending (next sequence 5) against a permanently invalid chain. |
| Is `event_type` constrained in the database? | **No.** The domain lives only in Python (`AUDIT_EVENT_TYPES`, `models.py:982`); raw SQL inserted an out-of-domain type (`PROJECT_CREATED`) successfully. |

So "append-only" is currently an application convention plus a verifier, enforced nowhere the
database will object. That is the highest-value gap this phase found and it is carried to BE-030 as
a candidate obligation (trigger or `REVOKE`/rule + a test that the database itself refuses).

**The six §13.4 probe events, identified** (`events_since` in `ledger_remeasure.json`): sequences
6054–6059, three `USER_CREATED` + three `ROLE_ASSIGNED` pairs at 2026-10-09 15:57:40 → 15:58:15 UTC,
resource ids `fc1f4f91…dc9a`, `9da417e1…d64`, `d295a665…f30`, `65f045cd…e8a`, `1ce16913…d50`,
`c35d67fe…976d`. Every referenced resource row is **already absent** (`events_since_resource_rows_still_present: []`),
so the payloads are the only remaining trace. Their own segment verifies, which is the positive
statement that no history was falsified to make the numbers look better.

**Appended regression tests** (shipped, `tests/integration/test_be029_audit_ledger_history.py`,
**4 passed**) — each one deliberately *adds* events and then asserts the detection, with docstrings
saying so, because deleting them would itself be the violation under test:

| Test | Property |
| --- | --- |
| `test_appends_are_contiguous_and_keep_the_chain_valid` | each number is the previous maximum plus one, checked on the live chain and anchored to event N-1 even when N-1 is outside the requested range |
| `test_a_rolled_back_append_does_not_burn_a_sequence_number` | the rolled-back-append measurement above, as a permanent test: failure cannot open a hole |
| `test_rewriting_an_event_is_detected_by_hash_recomputation` | tampering ⇒ `event_hash mismatch`, then proven reverted (needs `db.expire_all()` — the ORM caches an instance across a raw `UPDATE`, which is itself a measurement trap worth knowing) |
| `test_probe_events_from_this_file_are_findable_and_stay` | every event this file writes is findable by its `payload->>'probe'` marker and none is cleaned up, so "the suite deleted audit history" stays answerable by query |

**Dated correction (2026-10-10) to this table.** It originally listed five tests under names that do
not exist in the shipped file, including `test_deleting_an_event_is_detected_as_a_sequence_gap`.
There is no such shipped test. It was drafted, it worked, and it was **withdrawn** — see §14.8, which
records why: BE-023 §4 bans `DELETE` against the ledger in the test tree *unconditionally*, with no
rollback exception, and a test that deletes a ledger row inside a rolled-back transaction is still
that forbidden operation.

So the removal half of the property is proven where it can be: on a disposable clone, measured in
the table above (committed deletion ⇒ `verify_chain` reports the gap, and the writer keeps appending
anyway), plus `tests/unit/test_audit_guard.py`, which pins the guard that keeps any future test from
doing it in the repository's own databases. `test_be029_audit_ledger_history.py`'s module docstring
states this omission deliberately rather than hiding it.

### 14.7 Phase H — schema drift: two verdicts, reported separately

The instruction is explicit: a CLEAN custom gate is not a clean schema. Both answers were produced
against the same database and are reported side by side.

| Tool | Command | Verdict |
| --- | --- | --- |
| Repository drift gate | `pytest -q tests/integration/test_schema_drift_gate.py` (`pofa_test`) | **6 passed — CLEAN** |
| Upstream Alembic | `DATABASE_URL=…pofa_test python -m alembic check` | **FAILED: New upgrade operations detected** — exactly the pair `remove_constraint` / `add_constraint` on `user_role_assignments.uq_user_role_scoped`; header confirms `Alembic target database: pofa_test` |

The divergence is entirely accounted for, and the accounting was **re-measured rather than
inherited**: `phase_h_drift.py` (read-only, targets `pofa_test` and the disposable post-migration
clone `pofa_be029_devpost`) compared four layers in one session:

| Layer | `pofa_test` (923 rows) | `pofa_be029_devpost` (872 rows) |
| --- | --- | --- |
| `pg_get_constraintdef` | `UNIQUE NULLS NOT DISTINCT (user_id, role_id, scope_type, organization_id, organizational_unit_id, project_id)`, `indnullsnotdistinct = true` | identical |
| `sa.inspect().get_unique_constraints()` | `dialect_options.postgresql_nulls_not_distinct = **True**` | identical |
| `Base.metadata` declaration | `postgresql_nulls_not_distinct=True` (`models.py:1567`) | identical |
| `alembic check` / `compare_metadata` | remove+add pair, gate signatures both in the accepted baseline | identical |
| Duplicate groups that depend on NULL treatment | **0** | **0** |

So the database, the migrations (`i9d0e1f2g016` created it with the flag) and the model **agree**;
only Alembic's autogenerate comparison disagrees, and `alembic check` is loud about it.

**Dated correction (2026-10-10) to §12.7 and to the baseline entry's reason:** both attributed the
pair to *"Alembic 1.11.2 reflects a UNIQUE constraint without carrying NULLS NOT DISTINCT"*. That
attribution is wrong about the mechanism, and the wrong mechanism matters because it changes what a
future fixer would touch. Measured: SQLAlchemy 2.0.52 **does** hand Alembic the flag
(`get_unique_constraints()` returned `postgresql_nulls_not_distinct=True`). The loss is inside
Alembic: `autogenerate/compare.py::_make_unique_constraint()` (line 316 in 1.11.2) rebuilds the
reflected constraint from `column_names` and `name` alone and drops `params["dialect_options"]`, so
the live side of `_uq_constraint_sig` lacks `("nulls_not_distinct", True)` while the metadata side
has it. The conclusion in BE-028 was right — category B, a tooling artifact, not drift — but it is
right for a different reason, and the permanent pair is explained by that.
`tests/schema_drift_baseline.py`'s reason text now carries the corrected mechanism with a pointer
back to this section.

**Decision: report-only; do not "fix" it.** The tempting fix is to delete
`postgresql_nulls_not_distinct=True` from the model so `alembic check` goes green. That would make
the gate and upstream agree by **weakening the constraint's semantics** — BE-025's scope matrix
depends on NULL scopes comparing as equal, which is exactly what `test_the_assignment_constraint_is_still_nulls_not_distinct`
guards from the catalog. The current data carries no rows that would notice (0 dependent duplicate
groups in both databases), so a silent weakening would be invisible *and* wrong. The legitimate
fixes are tooling-level and belong to BE-030, not here: upgrade Alembic to a version that carries
dialect options through `_make_unique_constraint`, or add a reviewed autogenerate filter for this
named pair so `alembic check` stops proposing a destructive no-op rebuild.

The schema may therefore **not** be declared fully clean. The accurate statement is: no unexplained
drift exists; the model, the migrations and the database agree on every object; and one documented
comparison artifact makes upstream `alembic check` fail by construction.

### 14.8 Phase G (continued) — the append-only guard had a spelling-dependent blind spot

**FOUND.** `tests/audit_guard.py` is BE-023 §14's standing protection against a future test
deleting ledger history. Phase G drafted `test_deleting_an_event_is_detected_and_never_committed`,
which removed a ledger row with the SQLAlchemy **Core construct** spelling:

```python
delete(AuditLedgerEvent).where(AuditLedgerEvent.id == …)
```

The guard reported the tree clean. Its rules were `.delete()` / `.update()` **method calls** on an
expression mentioning the ledger, plus raw-SQL string patterns — so `delete(Model)` was invisible to
it. A guard whose coverage depends on which spelling a test author happened to use is not a guard:
the operation it exists to forbid was executed and unreported.

**FIXED — by narrowing, not by relaxing.** Three changes, in this order:

1. `scan_source()` gained `_construct_name()` / `_is_ledger_entity()` / `_core_construct()` and two
   violation kinds, `core_delete` and `core_update`, for the construct spellings.
2. `_core_construct()` deliberately matches **only** construct spellings (callee is a bare `Name` or
   `module.Name`, first positional argument *is* the entity). The first attempt matched any call
   named `update` whose arguments mentioned the ledger, which reclassified
   `session.query(AuditLedgerEvent).update({...})` from `bulk_update` to `core_update` and broke
   `test_detects_bulk_update_as_destructive`. Both kinds are kept distinct on purpose: the report has
   to say which shape was found.
3. `_ALLOWED_UPDATE_TESTS` gained `test_rewriting_an_event_is_detected_by_hash_recomputation` — the
   BE-029 Phase G file's rollback-guarded single-row UPDATE. This is the guard's *designed*
   extension path (the allowlist is keyed on "enclosing test is named here **and** the function
   actually calls `rollback()`", not on the name alone), not an exception granted to a new file.

**The deletion test was withdrawn rather than allowed.** BE-023 §4 bans `DELETE` against the ledger
in the test tree *unconditionally* — "there is no legitimate reason for a test to remove a ledger
row" — and gives the rollback exception to `UPDATE` only. Relaxing that is a policy change to another
task's rule, which this task has no authority to make. So `core_delete` gets **no** allowlist entry
(`test_core_delete_has_no_rollback_exception` pins that a `delete()` inside an allowlisted
rollback-guarded test is *still* a violation), and the removal half of the detection property is
proven on a disposable clone instead (§14.6) — recorded as a blocked decision in §14.12.

**VERIFIED.**

| Check | Result |
| --- | --- |
| `pytest -q tests/unit/test_audit_guard.py` | **25 passed** in 1.71s (20 before, 5 new: construct `delete`, module-qualified `delete`, delete-inside-a-guarded-test still flagged, construct `update` outside a guarded test, and the negative `delete(Project)` not flagged) |
| Whole-tree scan (`scan_test_tree(tests)`) | **`violations: 0`** |
| `tests/integration/test_be029_audit_ledger_history.py` | 4 tests, no `DELETE` anywhere, module docstring states the omission and points to §14.6 |

Both consumers of the guard also failed while the blind spot was being closed, and both failures were
**my own new code** being caught: the unit tree check and
`test_audit_ledger.py::test_no_test_deletes_audit_ledger_rows`. That is the guard working.

### 14.9 BE-030 feasibility — what actually enforces append-only in this database

§14.6 established the hole: the database objects to neither `UPDATE` nor `DELETE` on
`audit_ledger_events`. BE-030's candidate fix was "add enforcement", which is only plannable once the
candidate mechanisms are measured — including the two that look correct in a design document and are
not. Run as `ledger_enforcement_options.py` against the disposable `pofa_be029_assumptions` (revision
`s9t0u1v2w029`) through `safety.arm_verification()` + `build_guarded_engine()`; the armed
`verification` context refuses `pofa_dev` and `pofa_test` before connecting, every mutation attempt
is rolled back, and the run ends with `appends_only_growth: true` (10 new rows, 10 new maximum
sequence numbers — nothing removed, no number burned).

Outcome vocabulary matters more than the mechanism names: **refused** = statement raises, the writer
learns immediately; **swallowed** = statement reports success and nothing changes, the writer
*believes it wrote*; **changed/gone** = no enforcement.

| Variant (installed, used, dropped) | `UPDATE` | `DELETE` | `append_event` still works | BE-023 §4 rollback-guarded tamper `UPDATE` still works | Drift gate sees the object |
| --- | --- | --- | --- | --- | --- |
| none — current shipped schema | **changed** | **gone** | yes | yes | 3 ops, none ledger-related |
| `BEFORE ROW … RAISE EXCEPTION` trigger | **refused** | **refused** | yes | **no — refused** | 3 ops, none ledger-related |
| rules spelled `DO NOTHING` | changed | gone | yes | yes | 3 ops, none ledger-related |
| rules spelled `DO INSTEAD NOTHING` | **swallowed** | **swallowed** | yes | **swallowed** | 3 ops, none ledger-related |
| `REVOKE UPDATE, DELETE` from the connected role | changed | gone | yes | yes | 3 ops, none ledger-related |

Four findings that change BE-030's design, not just its wording:

1. **Only the trigger actually stops mutation — and it breaks the sanctioned tamper tests.** Three
   shipped tests depend on rewriting one ledger row inside a rolled-back transaction
   (`test_tamper_detection_with_rollback`, `test_broken_link_detection_with_rollback`,
   `test_rewriting_an_event_is_detected_by_hash_recomputation`). A blanket `BEFORE ROW` trigger makes
   tamper detection untestable. The enforcing migration therefore has to be conditional (a
   role- or GUC-gated exception) or the owner has to accept losing those tests. This is the blocked
   decision, not an implementation detail.
2. **`DO NOTHING` is a trap** (measured, not reasoned): the default action still runs, so the ledger
   stays fully mutable while a reviewer believes a rule protects it. Only `DO INSTEAD NOTHING`
   suppresses — and it **swallows**, which is the worst of the three outcomes for an audit writer:
   `append_event`'s callers would keep receiving a success they did not earn. Rules are therefore
   rejected on measurement, on the strength of the `swallowed` row above.
3. **`REVOKE` does nothing as currently deployed.** The application connects as the table owner
   (`postgres`), and owner privileges are implicit: both statements were allowed unchanged after the
   revoke. Privilege-based enforcement would first require a dedicated, non-owner application role —
   a deployment/credentials change far outside a migration.
4. **Enforcement added this way is invisible to the drift machinery**: the operation count stayed at
   3 across every variant and never mentioned the ledger. Whatever BE-030 installs must be created by
   a reviewed migration and pinned by a catalog test, because neither `alembic check` nor the
   containment gate will notice if it is later dropped.

Two supporting measurements, both read-only against the live databases (no application probe):

| Question | `pofa_dev` | `pofa_test` |
| --- | --- | --- |
| Ledger rows | 6,023 | 37,838 |
| `event_type IS NULL` | 0 | 0 |
| `event_type` values outside the 94-member Python domain | **0** | **0** |

So a database `CHECK` on `event_type` is addable to *current* data on both databases without any
cleanup — feasible, with the caveats that `ADD CONSTRAINT … CHECK` takes a brief exclusive lock, must
be written into the model as well as the migration or the drift gate will report it, and would not
retroactively make the historical `PROJECT_CREATED` insertion (§14.6) impossible if the domain list
drifts again. The scratch database reports the same 0 out-of-domain values.

### 14.10 Phase I — the reproducible test matrix

Interpreter `backend/.venv312_repro` (Python 3.12), PostgreSQL in container `pofa_db`, API/workers
stopped, target **`pofa_test`** in every row — set explicitly, because §14.2's guard makes a
mis-set target a refusal rather than a silent write to `pofa_dev`:

```bash
export TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"
```

| # | Command | Target | Result | Duration | Log |
| --- | --- | --- | --- | --- | --- |
| I-1 | `pytest -q tests/unit` | `pofa_test` | **445 passed, 1 skipped, 6 warnings** | 40.41s | `phase_i_matrix_final.log` |
| I-2 | `pytest -q tests/integration` | `pofa_test` | **335 passed, 9 warnings, 0 failures** | 745.71s (12:25) | same |
| I-3 | `pytest -q tests/unit/test_audit_guard.py tests/unit/test_database_safety.py tests/unit/test_migrations.py` | `pofa_test` | **53 passed** | 1.58s | — |
| I-4 | `pytest -q tests/integration/test_be029_audit_ledger_history.py …database_safety_guard.py …identity_conflict_api.py …identity_contract.py tests/integration/test_schema_drift_gate.py tests/integration/test_audit_ledger.py` | `pofa_test` | **68 passed, 6 warnings** | 87.70s | — |
| I-5 | `pytest -q tests/integration/test_schema_drift_gate.py` | `pofa_test` | **6 passed — gate CLEAN** | (subset of I-4) | §14.7 |
| I-6 | `DATABASE_URL=…pofa_test python -m alembic check` | `pofa_test` | **FAILED** — the documented `remove_constraint`/`add_constraint` artifact | — | §14.7 |

**The skip is named and is not a pass.** `tests/unit/test_preflight.py:117` skips with "ML stack
genuinely installed in this environment" — it is the *inverse* assertion (that a missing torch is
reported), which cannot hold on this machine. It was not converted into a pass, and I-1 is therefore
reported as 445 + 1 skip, not 446.

**Superseded run, kept for the record.** The first pass of this matrix, before §14.8's fix, produced
`1 failed, 439 passed, 1 skipped` (I-1) and `1 failed, 335 passed, 9 warnings in 718.86s` (I-2). Both
failures were the append-only guard rejecting **the test file this task had just added** — the unit
tree check and `test_audit_ledger.py::test_no_test_deletes_audit_ledger_rows`. Nothing pre-existing
failed, and the correct response was to withdraw the offending test, not to relax the guard's DELETE
rule (§14.8). Counts moved 439 → 445 because of the five new guard tests.

**Contiguity held across a 12-minute write-heavy suite.** Measured on `pofa_test` before and after:
38,185 rows, span 1..38,185, `missing_in_span = 0`, `count(DISTINCT sequence_number) = 38,185`. So
38k appends under concurrency, retries and rolled-back transactions produced no gap and no duplicate
number — which is the positive control for §14.6's inference that `pofa_dev`'s 36 missing numbers can
only be removal.

### 14.11 BE-030 feasibility, part 2 — a damaged tail is invisible to a tail-window check

The strongest finding of this phase, and the one that changes BE-030's shape. `append_event` copies
`predecessor.event_hash` into the new row's `previous_hash` (`audit_ledger.py:223-229`); it does not
recompute it. Whether that matters was answered by `ledger_tail_rewrite.py`, run against the
throwaway clone `pofa_be029_scratch` and **committing** its damage — because the question is what a
database with committed damage does, which cannot be observed inside a rolled-back transaction.

| Step | Measured result |
| --- | --- |
| Append victim event (7301), rewrite its `payload` in place, leave `event_hash` untouched | committed; `verify_chain(7301, 7301)` → `"event_hash mismatch at sequence 7301"` |
| Next **honest** append (7302) | `previous_hash` **equals the stale stored hash** (`equals_the_stale_stored_hash: true`) — the chain silently re-bases on the tampered value |
| `verify_chain(7302, 7302)` — the newest event alone | **`valid: true`** |
| `verify_chain(7301, 7302)` | one failure, at 7301; 7302 is not itself flagged |
| Delete the victim row (7301) and append again (7303) | writer succeeds; `verify_chain(7302, 7303)` → `"missing predecessor for sequence 7302"` — a second symptom class, distinct from `"sequence gap before N"` |
| Span vs row arithmetic | span grew by 3 while rows grew by 2 → `span_gap_now: 1`, the arithmetic signature of a deletion |

Three consequences BE-030 has to be written around:

1. **A health check over a recent window can report a healthy ledger on a tampered database.** The
   events after a rewrite are internally consistent — they chain onto whatever the tampered row
   *claims*. So "verify the last N events" is not a control; verification must be anchored
   (full-chain from 1, or a periodically published checkpoint). This is the single most actionable
   gap in the current observability story, and §14.6's `verify_chain(6039, 6059) → valid=True` on
   `pofa_dev` is the same fact seen from the other side: that tail verified *while 36 rows were gone
   behind it*.
2. **Chain-aware writing means recomputing the predecessor, not copying it.** If the writer verified
   its predecessor's hash before linking, a tampered tail would be caught at the next write instead
   of at the next audit.
3. **A strict refuse-on-invalid writer would deny service on live `pofa_dev` today** — it already has
   7 gaps. Measured here: the writer appended happily into invalid history (3 appends, 1 of them onto
   a stale hash). So BE-030's policy question D-2 is unavoidable and is a product decision, not an
   implementation detail.

State left behind, recorded rather than hidden: `pofa_be029_scratch` now holds 7,266 rows with maximum
sequence 7,303 — one rewritten-then-deleted event (7301), one event (7302) linked to its stale hash,
plus the 36 gaps it inherited from being a `pofa_dev` clone. It is a throwaway clone and must not be
used as evidence of anything except tamper behaviour.

### 14.12 Deviations, blocked decisions, and what was *not* done

**Not done, and why:**

| Item | Status | Reason |
| --- | --- | --- |
| Database enforcement of append-only | **not implemented** | Only the trigger enforces, and it refuses the UPDATE that BE-023 §4 sanctions for tamper testing (§14.9). Installing it would break three shipped tests. Owner decision D-1. |
| Chain-aware writing (predecessor recompute / anchor checkpoint) | **not implemented** | Behaviour against already-invalid history is undefined and would deny service on `pofa_dev` (§14.11). Owner decision D-2. |
| Reconciliation of `pofa_dev`'s 36 missing sequence numbers | **not performed** | §11.3 and the live-database rules forbid repair, renumbering or backfill here. A read-only reconciliation register is BE-030 work. |
| Shipped test for deletion detection | **withdrawn** | BE-023 §4 bans `DELETE` in the test tree unconditionally (§14.8). Proven on a disposable clone instead. |
| A `CHECK` on `event_type` | **not added** | Feasible (§14.9) but it is a schema change belonging to BE-030's migration, and adding it silently here would create unreviewed drift against the model. |
| `external_subject` NOT NULL / backfill | **not done** | OQ-3 remains a product decision (§14.3). |
| Envelope change for `/auth/roles`, `/auth/permissions` | **not done** | Changes the published OpenAPI contract and every consumer. Owner decision (§14.5). |
| Alembic dialect-options artifact | **not fixed** | Report-only; fixing it by deleting `postgresql_nulls_not_distinct` from the model would weaken the constraint (§14.7). Tooling-level fix belongs to BE-030. |
| Committing anything | **not done** | §1.2 — nothing staged, committed or pushed; the full working-tree state is in the final report. |

**Deviations from how this phase went:** two shipped-code defects were introduced and then closed
inside the same phase, and both are recorded where they happened rather than quietly amended away —
the guard's Core-DML blind spot (§14.8) and the two probe bugs in §14.9 (`TG_TAG` is an
event-trigger-only variable; `DO NOTHING` does not suppress the default action). The results doc's
§14.6 test table also carried five fictional test names until this pass corrected it, with the
correction dated.

---

## 15. Acceptance checklist (Phase L)

Verdicts are only **DONE** when a command or query produced the number cited. Nothing in this table
is asserted from reading code.

| Phase | Mandate | Evidence | Verdict |
| --- | --- | --- | --- |
| A | Measured baseline, history preserved | `2 failed, 320 passed, 9 warnings in 568.40 s`; both failures named, one attributed to this pass's own Phase C edit (§14.1) | **DONE** |
| B | Auth conflict handling, real concurrency, negative control, classifier robustness | Duplicate-identity 409 keyed on the violated database object; unrelated `IntegrityError` no longer reported as a duplicate (§13.1, shipped `test_be029_identity_conflict_api.py`) | **DONE** |
| C | Isolation enforced, not documented | Armed-context chain (5 links), `PROTECTED_DATABASE_NAMES` refusal, `test_target.py` refusal, `Alembic target database:` line; 3 guard tests + `test_database_safety.py`; readiness regression found and pinned (§14.2) | **DONE** |
| D | `external_subject` resolved from behaviour only | No value invented, no backfill, no merge; four options measured (§14.3) | **BLOCKED — OQ-3 (below)** |
| E | §6 check 12: migrations fail safely on violated assumptions | Six scenarios S1–S6 driven on disposable clones (§14.4); no live downgrade ever run | **DONE** |
| F | BE-025 regression investigated, not inherited | `total=94` vs page 50 vs rank 94; `list_user_roles` `total` defect fixed at `auth.py:523-537`; assertion strengthened, never weakened; bare-list envelope reported only (§14.5) | **DONE** |
| G | Ledger remeasured, probe events identified, tests appended, history never falsified | 36 missing numbers in 7 ranges, no hash mismatch; rolled-back append burns nothing; DB refuses neither `UPDATE` nor `DELETE`; events 6054–6059 identified with resource ids and orphan status; 4 tests shipped; guard blind spot closed (§14.6, §14.8) | **DONE (deletion test withdrawn)** |
| H | Drift gate vs `alembic check`, reported separately | Gate 6 passed CLEAN; `alembic check` FAILED on the named pair; four-layer measurement corrected the mechanism to Alembic's comparison layer; schema **not** declared clean (§14.7) | **DONE-WITH-CORRECTION** |
| I | Reproducible matrix | 445 passed + 1 named skip / 335 passed, target `pofa_test`, durations logged, superseded run retained (§14.10) | **DONE** |
| J | Documentation reconciliation with dated corrections | §11 pointer, §12.7 pointer, §14.3/§14.6 corrections, plan-doc status pointer, cross-references re-pointed | **DONE** |
| K | BE-030 selected and defined from evidence | `BE-030 — Audit Ledger Append-Only Enforcement & Chain Integrity.md`, 18 sections, every starting fact traceable to a measurement (§2 F-1…F-14) | **DONE** |
| K2 | Execute BE-030 if safe and unblocked | Feasibility probes run; implementation **not** started | **BLOCKED — D-1, D-2 (below)** |
| L | Acceptance checklist and blocked analysis | This section | **DONE** |

## 15.1 Blocked items

**D-1 — does the application role lose the ability to mutate the ledger?**
*Why it matters:* only a refusing mechanism enforces; measured, a blanket `BEFORE ROW` trigger also
refuses the rollback-guarded `UPDATE` that BE-023 §4 sanctions, so installing it unasked would break
three shipped tamper-detection tests.
*Options:* A trigger with a narrow audited exception (recommended) · blanket trigger and lose
in-repository tamper testing · refuse `DELETE` only (the operation that actually produced `pofa_dev`'s
36 missing numbers) · application-layer only.
*Safest next step:* the owner picks A or C; then BE-030 §5's re-measurement and §13.1's tests 1–5 can
be authored against that choice on a disposable clone before any live database sees a migration.

**D-2 — what must the writer do when history is already invalid?**
*Why it matters:* the fix for the re-basing defect (F-5/F-6) is a predecessor check in the write path,
and `pofa_dev` is already invalid, so a strict policy stops every audit write on it the moment it
ships.
*Options:* validate the immediate predecessor only, alert on the rest (recommended) · full-chain check
per append (rejected on measurement) · published checkpoint at the tail · no write-path change,
scheduled anchored verification instead.
*Safest next step:* choose A together with BE-030 §9's anchored verification and §10's read-only
register, so the gapped database stays writable while a *new* failure is still distinguishable from
the known 36.

**OQ-3 — is `external_subject` part of the identity key, and may it be NULL?**
*Why it matters:* BE-029 chose Option A and enforced it on username/email; the identity guarantee's
other half is still only a nullable column, so Option A is half-enforced by design.
*Options:* (a) declare local accounts exempt and document a partial key · (b) backfill generated
subjects (rejected: manufactures identity) · (c) NOT NULL without backfill (fails on data) · (d) decide
with the federated login-flow specification.
*Safest next step:* (a) recorded now as a decision, revisited at (d). Explicitly **not** folded into
BE-030, which is the ledger task.

**Envelope question — `/auth/roles` and `/auth/permissions` return bare lists with `limit`/`offset`.**
*Why it matters:* a client cannot distinguish a truncated list from a complete one, and the rest of the
family returns `{items, limit, offset, total}`.
*Options:* make them documented report-only enumerations · move them to the envelope as a breaking
OpenAPI change · leave them undocumented (not acceptable).
*Safest next step:* the owner chooses; BE-030 §16 forbids an incidental fix either way.

## 15.2 Working tree at the end of this pass

Measured with `git status --porcelain=v1` on branch `Backend` at the end of the verification work;
**nothing staged, nothing committed, nothing pushed** (`git diff --cached --stat` is empty). The
list below is that pre-commit inventory; the commit that closed it is recorded at the end of
this section.

Modified (14): `alembic/env.py`, `backend/api/v1/endpoints/auth.py`, `backend/db/models.py`,
`backend/db/session.py`, `backend/db/test_target.py`, `backend/observability/health.py`,
`backend/services/authorization.py`, `tests/audit_guard.py`,
`tests/integration/test_be025_admin_control_plane.py`, `tests/integration/test_schema_drift_gate.py`,
`tests/schema_drift_baseline.py`, `tests/unit/observability/test_health.py`,
`tests/unit/test_audit_guard.py`, `tests/unit/test_migrations.py` — 447 insertions, 64 deletions.

Untracked (12): `alembic/versions/r8s9t0u1v028_be029_retire_identity_residue.py`,
`alembic/versions/s9t0u1v2w029_be029_user_identity_unique.py`, `backend/db/safety.py`,
`docs/BE-029 User Identity Constraint Remediation Plan.md`,
`docs/BE-029 User Identity Constraint Remediation Results.md`,
`docs/Production Task Files/BE-029 — User Identity Constraint Remediation.md`,
`docs/Production Task Files/BE-030 — Audit Ledger Append-Only Enforcement & Chain Integrity.md`,
`tests/integration/test_be029_audit_ledger_history.py`,
`tests/integration/test_be029_database_safety_guard.py`,
`tests/integration/test_be029_identity_conflict_api.py`,
`tests/integration/test_be029_identity_contract.py`, `tests/unit/test_database_safety.py`.

**Closure (2026-10-10).** Those 26 files were then staged **explicitly by name** — no `git add .`,
no `git add -A` — and reviewed with `git diff --cached --check` / `--stat` / `--name-status`:
12 additions + 14 modifications, nothing else unstaged and nothing left untracked. The only
`--check` findings were the two-space markdown hard breaks in the task-file header block, which
are the committed house style (identical in BE-028's task file). The commit is a single commit on
branch `Backend` with message `feat(backend): finalize BE-029 and prepare BE-030`.
**Nothing was pushed, amended, reset, or cleaned**, and the BE-030 decisions D-1/D-2, OQ-3, and the
API/worker restart remain open exactly as §15.1 records them.
