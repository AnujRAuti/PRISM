# BE-028 — Schema Integrity & Drift Containment: Results

Task: `docs/Production Task Files/BE-028 — Schema Integrity & Drift Containment.md`
Depends on: BE-027 (whose audit produced B-1, B-2, B-3)
Date of execution: 2026-10-06 → 2026-10-08 (interrupted once by a Docker Desktop outage; see §9)
Branch: `Backend` | Migration head after this task: `q7r8s9t0u027`

---

## 1. Executive Summary

BE-027 left three defects. All three are now resolved in the sense the task asked
for — schema state is intentional, explainable, reproducible and protected against
accidental future drift — except B-1, which is an unresolved blocker by design
(§3 of the task file forbids destructive remediation without approval).

| Defect | Start | End | Mechanism |
| --- | --- | --- | --- |
| B-1 `users.username` / `users.email` declared unique, not enforced, duplicates exist | 2 mismatches | 2 mismatches, measured, explained, contained | Not forced. Documented as blocker + BE-029 remediation plan (§9, §10) |
| B-2 `alembic check` reports 16 unreviewed operations | 16 | 6 | 6 model-metadata corrections (Category C), 1 additive migration for 3 never-created indexes (Category D), exact-name PostGIS exclusion (Category B) |
| B-3 nothing detects future divergence | no gate | gate wired into the existing integration track | `tests/integration/test_schema_drift_gate.py` + `tests/schema_drift_baseline.py` (fail in both directions; proves its own ability to fail) |

What was deliberately **not** done: no row of user data was created, changed,
merged or deleted by BE-028 anywhere; `pofa_dev` was not migrated and was only
read; no historical migration was rewritten; `alembic check` was not suppressed.

Net repository changes: 2 new source files, 1 new migration, 1 new test file,
1 new baseline file, 2 edits (`backend/db/models.py`, `alembic/env.py`),
1 pin bump (`tests/unit/test_migrations.py`), this document.

---

## 2. B-1 Findings — user uniqueness

### ORM state

`backend/db/models.py` `User` (unchanged in this task, deliberately):

```python
username = Column(String(128), unique=True, index=True, nullable=False)
email    = Column(String(256), unique=True, index=True, nullable=False)
```

`Column(unique=True, index=True)` renders as a **unique index** named
`ix_users_username` / `ix_users_email`.

### Database state (measured, not inferred)

Measured identically on `pofa_be028_scratch`, `pofa_test` and `pofa_dev`:

* Constraints on `users`: `users_pkey` (PK on `id`), `ck_user_status` (CHECK),
  `uq_user_identity_subject` = `UNIQUE (identity_provider, external_subject)`.
  **No unique constraint or unique index on `username` or `email`.**
* Indexes on `users`: `users_pkey`, `uq_user_identity_subject`,
  `ix_users_username`, `ix_users_email` — the last two are **plain,
  non-unique** btree indexes:
  `CREATE INDEX ix_users_email ON public.users USING btree (email)`.

So the mismatch is real and bidirectional: the model claims a uniqueness rule the
database does not implement, and the database implements a weaker rule (plain
lookup indexes) the model describes as stronger.

### Which key is the enforced identity?

`backend/services/authorization.py` and `backend/db/models.py` agree that the
authentication key is `(identity_provider, external_subject)`:

* BE-016 backfilled `external_subject = id::text` for real deployments
  (`pofa_dev`: all 40 rows of the duplicate group carry `external_subject`).
* `resolve_user_principal(db, user_id)` and `get_user(db, user_id)` look users up
  **by id only**. A repository-wide search for any lookup by email or username
  (`User.email ==`, `User.username ==`, `filter_by(email=...)`, `by_email`,
  `by_username`) returns **no matches**: no code path reads a user by username or
  email.
* `create_user` (`backend/services/authorization.py:307`) normalises
  `username.strip()` / `email.strip().lower()` and defaults
  `external_subject = str(uuid4())`. It performs **no duplicate check** on
  username or email, which is how 19 (test) / 40 (dev) rows with
  `testuser` / `test@example.com` accumulated.
* There is no password storage in V1 (`create_user` docstring: "no credentials
  stored"), so no credential collision exists either.

**Conclusion:** under the current implementation `username` and `email` are
display/contact attributes, not identity keys. Enforcing uniqueness on them is an
identity-policy decision (which of the 19/40 accounts survives? are they the same
person?), not a schema correction. Two safe directions exist and they contradict
each other:

1. force uniqueness → requires deleting/merging user rows (prohibited without
   approval, §3) and changes identity semantics;
2. declare the truth in the model (drop `unique=True`) → asserts as policy that
   usernames/emails are *not* unique, which is also a product decision.

Neither was taken. Both are recorded, with the evidence, and routed to BE-029.

### Is a destructive migration required?

Yes — if the answer is direction (1). Proof, executed only against the isolated
clone `pofa_be028_rollback` (a `TEMPLATE` copy of `pofa_test`, so it holds the real
duplicates):

```
CREATE UNIQUE INDEX CONCURRENTLY ix_users_email_unique_probe ON public.users (email);
ERROR:  could not create unique index "ix_users_email_unique_probe"
DETAIL:  Key (email)=(test@example.com) is duplicated.

CREATE UNIQUE INDEX ix_users_email_unique_probe2 ON public.users (email);
ERROR:  could not create unique index "ix_users_email_unique_probe2"
DETAIL:  Key (email)=(test@example.com) is duplicated.
```

This is why `q7r8s9t0u027` creates only the three non-unique indexes and why the
`users` pair sits in the documented baseline as Category E.

---

## 3. Duplicate Data Analysis

Measured 2026-10-06 (before any BE-028 change) and re-measured 2026-10-08 (after):

| Fact | `pofa_test` | `pofa_dev` |
| --- | --- | --- |
| total users | 1960 before → 2098 after* | 1094 (unchanged) |
| duplicate **email** groups | 1 | 1 |
| rows inside those groups | 19 (18 redundant) | 40 (39 redundant) |
| duplicate **username** groups | 1 | 1 |
| rows inside those groups | 19 (18 redundant) | 40 (39 redundant) |
| `username` NULL / empty / whitespace-only | 0 / 0 / 0 | 0 / 0 / 0 |
| `email` NULL / empty / whitespace-only | 0 / 0 / 0 | 0 / 0 / 0 |
| case-insensitive duplicate groups | 1 | 1 |
| normalised (`lower` + `strip` + drop `+tag`) groups | 1 | 1 |

\* the increase is the integration suites' own fixtures; BE-028 ran no DML. The
duplicate **group** and **row** counts are identical before and after, so BE-028
neither created nor removed a collision.

Both databases contain exactly one colliding value pair: `testuser` /
`test@example.com`. NULL/empty/whitespace/case/normalisation variants add nothing
new — the case-insensitive and normalised group counts equal the exact-match group
count (1), so there is no hidden family of near-duplicates.

Shape of the colliding rows (`pofa_test`, 19 rows — the same values repeat in
`pofa_dev` with 40):

* all `status='ACTIVE'`, `identity_provider='local'`, `is_active=true`;
* created 2026-09-25 13:28 → 2026-10-06 16:26 (spread over 11 days of test runs);
* `display_name` NULL and `external_subject` **NULL** for all 19 rows in
  `pofa_test`; in `pofa_dev` the 40 rows have `display_name='testuser'` and
  `external_subject = id` (the BE-016 backfill).

Consequence worth recording: because PostgreSQL treats NULLs as *distinct* in an
ordinary unique constraint, `uq_user_identity_subject` does not cover those 19
`pofa_test` rows at all. `pofa_test`'s identity enforcement is therefore
conditional on the backfill, which BE-029 must confirm.

### Affected relationships (§8 of the task file)

Foreign keys pointing at `users(id)` — 14 in `pofa_test`, 8 in `pofa_dev` (the
difference is the BE-026 field-operations tables, absent from `pofa_dev`'s older
head). Rows referencing a duplicate id:

| child table | column | ON DELETE | rows referencing the duplicates (`pofa_test` / `pofa_dev`) |
| --- | --- | --- | --- |
| `projects` | `owner_id` | NO ACTION | 19 / 40 |
| `user_role_assignments` | `user_id` | **CASCADE** | 0 / 0 |
| `activities`, `claims`, `review_decisions`, `audit_events`, `notifications`, `notification_preferences`, `field_assignments` (×3), `field_sessions`, `field_capture_operations` (×2) | actor/claimant/reviewer/recipient/user columns | NO ACTION / RESTRICT | 0 each |
| **total** | | | **19 / 40** |

So a merge would move 19 (test) / 40 (dev) `projects.owner_id` rows and nothing
else. Two safety notes for BE-029: `user_role_assignments.user_id` is `CASCADE`,
so a naive `DELETE` of duplicate users silently deletes role assignments; and no
`audit_events.actor_id` row points at a duplicate, so no ledger row would be
retargeted or orphaned by remediation.

No personal data is exposed here: the colliding values are fixture constants
(`testuser` / `test@example.com`), and only ids of rows are enumerated in the raw
capture, not real user content.

---

## 4. B-2 Findings — all 16 drift operations and their classification

Verbatim `alembic check` capture before any change (isolated scratch database
`pofa_be028_scratch`, migrated base → head at `p6q7r8s9t026`):

```
INFO  [alembic.autogenerate.compare] Detected removed table 'spatial_ref_sys'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_analysis_jobs_status' on '['status']'
INFO  [alembic.autogenerate.compare] Detected removed unique constraint 'uq_duplicate_match_pair' on 'duplicate_matches'
INFO  [alembic.autogenerate.compare] Detected removed index 'ix_evidence_claim' on 'evidence'
INFO  [alembic.autogenerate.compare] Detected removed index 'ix_evidence_project' on 'evidence'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_evidence_metadata_evidence_id' on '['evidence_id']'
INFO  [alembic.autogenerate.compare] Detected removed index 'uq_graph_relationships_dedupe_active' on 'graph_relationships'
INFO  [alembic.autogenerate.compare] Detected removed index 'ix_projects_owner' on 'projects'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_projects_name' on '['name']'
INFO  [alembic.autogenerate.compare] Detected removed index 'uq_review_case_active_run' on 'review_cases'
INFO  [alembic.autogenerate.compare] Detected changed unique constraint 'uq_user_role_scoped' on 'user_role_assignments': expression (... 'user_id') to (... 'user_id', ('nulls_not_distinct', True))
INFO  [alembic.autogenerate.compare] Detected changed index 'ix_users_email' on 'users': unique=False to unique=True
INFO  [alembic.autogenerate.compare] Detected changed index 'ix_users_username' on 'users': unique=False to unique=True
ERROR [alembic.util.messaging] New upgrade operations detected: [ ... 16 tuples ... ]
FAILED: New upgrade operations detected: ...
```

Classification (task file §13). Totals: **A 0, B 3, C 6, D 3, E 4 = 16.**

| # | Operation | Category | Finding and action |
| --- | --- | --- | --- |
| 1 | `remove_table spatial_ref_sys` | **B** | Installed by `CREATE EXTENSION postgis` in the initial migration (`bb4bf0dd8fb7:25`); no model describes it. Measured 8,500 rows (SRID registry). Autogenerate would write `op.drop_table('spatial_ref_sys')` into a real migration. Fixed by an exact-name `include_object` exclusion in `backend/db/schema_drift_policy.py`, used by `alembic/env.py` for both offline and online runs. |
| 2 | `add_index analysis_jobs ix_analysis_jobs_status (status)` | **D** | `AnalysisJob.status` declares `index=True`; no revision ever created it. Created by `q7r8s9t0u027`. |
| 3 | `remove_constraint duplicate_matches uq_duplicate_match_pair` | **C** | The database has enforced this pair-unique rule since BE-006 (`f9b5d7e3c006`); the model never declared it, so the check proposed dropping a live integrity rule. Fixed in the model. |
| 4 | `remove_index evidence ix_evidence_claim` | **C** | Created by the initial migration under that name; `index=True` would auto-name `ix_evidence_claim_id`. Fixed with an explicit `Index("ix_evidence_claim", "claim_id")`. |
| 5 | `remove_index evidence ix_evidence_project` | **C** | Same, for `project_id`. Fixed with `Index("ix_evidence_project", "project_id")`. |
| 6 | `add_index evidence_metadata ix_evidence_metadata_evidence_id (evidence_id)` | **D** | Declared `index=True`, never created. Created by `q7r8s9t0u027`. |
| 7 | `remove_index graph_relationships uq_graph_relationships_dedupe_active` | **C** | BE-010's partial unique index (`WHERE relationship_status = 'ACTIVE'`) exists in the database; the model did not describe it. Declared in the model with the same `postgresql_where` convention the BE-021/022/026 models use. |
| 8 | `remove_index projects ix_projects_owner` | **C** | Historical name from the initial migration vs. `index=True`'s `ix_projects_owner_id`. Fixed with an explicit `Index("ix_projects_owner", "owner_id")`. |
| 9 | `add_index projects ix_projects_name (name)` | **D** | `Project.name` declares `index=True`; never created. Created by `q7r8s9t0u027`. |
| 10 | `remove_index review_cases uq_review_case_active_run` | **C** | BE-013's partial unique index (`WHERE origin = 'SYSTEM_SIGNAL' AND status <> 'RESOLVED'`) exists; model silent. Declared in the model. |
| 11 | `remove_constraint user_role_assignments uq_user_role_scoped` | **B** | Tooling artifact, proven by isolation experiment: Alembic 1.11.2's `postgresql.py:_dialect_sig` reads `postgresql_nulls_not_distinct` off the *compared* object, and reflection returns `NullType` columns with no dialect option, so the live `UNIQUE NULLS NOT DISTINCT` constraint is compared as if it lacked the flag. Toggling the model flag alone made exactly this pair appear/disappear, nothing else. Baseline entry; the real constraint is asserted separately from `pg_constraint` by the gate. |
| 12 | `add_constraint user_role_assignments uq_user_role_scoped (nulls_not_distinct=True)` | **B** | Second half of #11. Applying it would drop and rebuild a BE-025 integrity object with no change in behaviour — churn, not a fix. |
| 13 | `remove_index users ix_users_email` | **E** | B-1 (§2). Cannot be resolved safely. Baseline entry with reason. |
| 14 | `add_index users ix_users_email (unique=True)` | **E** | Second half of #13; proven to fail on live data (§2). |
| 15 | `remove_index users ix_users_username` | **E** | B-1. |
| 16 | `add_index users ix_users_username (unique=True)` | **E** | B-1. |

No operation was left unexplained; Category A had no members — none of the 16 was
"the migration is legitimately missing and already written".

**Result: 16 → 6.** The remaining 6 are exactly operations #11/#12 and #13–#16,
each with an entry and a reason in `tests/schema_drift_baseline.py`.

---

## 5. Schema Changes

### Migration added: `q7r8s9t0u027` (`alembic/versions/q7r8s9t0u027_be028_missing_indexes.py`)

```python
revision = "q7r8s9t0u027"
down_revision = "p6q7r8s9t026"

MISSING_INDEXES = (
    ("analysis_jobs", "ix_analysis_jobs_status", "status"),
    ("evidence_metadata", "ix_evidence_metadata_evidence_id", "evidence_id"),
    ("projects", "ix_projects_name", "name"),
)
```

Deterministic, additive-only, no data touched, no column altered. `downgrade()`
drops exactly those three indexes in reverse order. Hand-written, not committed as
autogenerate output: §22's policy was followed — candidate comparison inspected
operation by operation, unintended operations (the `users` pair, the
`spatial_ref_sys` drop, the `uq_user_role_scoped` rebuild) excluded, upgrade and
downgrade both tested (§8), application tests re-run (§7).

### No historical migration modified

`alembic/versions/` is untouched apart from the one added file. `git status` shows
exactly one new revision and zero modified revisions.

### Model metadata corrections (`backend/db/models.py`, +33 lines)

Five models, six objects — each change makes the model describe what the deployed
database already enforces; **none of them changes the database**:

| Model | Added to `__table_args__` | Removes drift ops |
| --- | --- | --- |
| `Project` | `Index("ix_projects_owner", "owner_id")` | #8 |
| `Evidence` | `Index("ix_evidence_project", "project_id")`, `Index("ix_evidence_claim", "claim_id")` | #4, #5 |
| `DuplicateMatch` | `UniqueConstraint("evidence_id", "matched_evidence_id", name="uq_duplicate_match_pair")` | #3 |
| `GraphRelationship` | partial unique `Index("uq_graph_relationships_dedupe_active", "dedupe_key", unique=True, postgresql_where=text("relationship_status = 'ACTIVE'"))` | #7 |
| `ReviewCase` | partial unique `Index("uq_review_case_active_run", "fusion_run_id", unique=True, postgresql_where=text("origin = 'SYSTEM_SIGNAL' AND status <> 'RESOLVED'"))` | #10 |

`User.username` / `User.email` were left as-is **on purpose** — see B-1.

An intermediate mistake is worth recording, because it is the reason the naming
corrections are explicit: switching `owner_id`/`project_id`/`claim_id` to
`index=True` *increased* the drift count (it proposed dropping `ix_projects_owner`
and adding `ix_projects_owner_id`), because SQLAlchemy's auto-naming appends the
`_id` suffix that the initial migration's hand-named indexes omit. Re-measured
after the change, then corrected.

### Migration-test pin (`tests/unit/test_migrations.py`)

`EXPECTED_HEAD: p6q7r8s9t026 → q7r8s9t0u027`, `EXPECTED_REVISION_COUNT: 21 → 22`,
each with the file's own provenance comment extended (§16/§17 — bumping the pin is
the deliberate act, and it happened only after `alembic heads` was confirmed to
report one head).

### Drift policy (`backend/db/schema_drift_policy.py`, new) and `alembic/env.py`

`EXTENSION_OWNED_TABLES = frozenset({"spatial_ref_sys"})` with an
`include_object()` hook, imported by `alembic/env.py` and passed to **both**
`context.configure()` calls, and by the gate (via
`MigrationContext.configure(..., opts={"include_object": ...})`) so the gate and
the CLI measure the same thing. The list is exact-name and the gate asserts it
still contains exactly one member, so it cannot quietly become a suppression
switch.

---

## 6. B-3 Containment — how future drift is detected

`tests/integration/test_schema_drift_gate.py` (6 tests, module fixture
`pytestmark = pytest.mark.integration`):

1. `test_drift_is_exactly_the_documented_baseline` — recomputes `compare_metadata`
   and requires the observed set to equal the baseline **in both directions**.
2. `test_baseline_entries_are_all_observed` — every accepted operation must still
   be real, or the baseline is fiction.
3. `test_a_baseline_entry_that_stops_being_true_also_fails` — proves the stale
   direction on a synthetic list (a resolved-but-still-listed entry yields
   `resolved=(...)` and an unclean verdict).
4. `test_the_gate_detects_a_model_change_with_no_migration` — injects
   `Index("ix_be028_gate_probe_marker", projects.created_at)` into
   `Base.metadata`, re-runs the real comparison against the live schema, requires
   the signature to appear as *new*, then removes it and asserts metadata is
   clean again. This is the test that proves the gate is capable of failing.
5. `test_extension_owned_objects_are_excluded_not_suppressed` — no `remove_table`
   may ever appear; `spatial_ref_sys` must still exist and be populated; the
   exclusion set must still be exactly `{"spatial_ref_sys"}`.
6. `test_the_assignment_constraint_is_still_nulls_not_distinct` — the accepted
   Category-B artifact is guarded at catalog level
   (`pg_get_constraintdef` must contain `NULLS NOT DISTINCT`) instead of through
   the component that is confused about it.

The fixture also refuses to judge a stale database: if
`ScriptDirectory` head ≠ `alembic_version.version_num` it fails with the remedy
(`python -m alembic upgrade head`) rather than comparing against an outdated
schema.

### §20 requirements met

* ORM change without migration → fails (test 4).
* Unexpected schema change → fails (tests 1, 2).
* Inconsistent migration metadata → fails via the pre-existing hermetic graph test
  (`tests/unit/test_migrations.py`: single head, linear root-to-head path, no
  dangling `down_revision`, pinned head/count), now bumped for this task.
* Known intentional objects don't cause false failures → `spatial_ref_sys` is
  excluded by name at the Alembic layer, not by ignoring the diff (test 5).
* Not a blanket suppression → the baseline is a set of six exact
  `kind|table|object` signatures with per-entry classification and reason; anything
  new fails; anything that disappears also fails.

### §21: which existing mechanism was integrated, and why

Inspected for something to plug into: `.github/` (absent — no GitHub Actions),
`Makefile` (absent), `*.ps1` / `*.sh` CI scripts (absent), `package.json`
scripts (absent), `.pre-commit-config.yaml` / `tox.ini` / `noxfile.py` (absent),
`docker-compose.yml` (services only, no test step), `scripts/` (only
`inspect_db.py`), `diagnostics/` (the BE-015 read-only audit-gap SQL), `pytest.ini`
(`testpaths = tests`, `--strict-markers`, markers `be023` and `integration`).

The repository's verification mechanism **is** pytest plus the documented BE-023
tracks, so the gate was added as an integration-track test file and nothing else.
No new CI system, no new config file, no redundant runner: `pytest tests/integration`
now fails on unexplained drift, and `-m "not integration"` skips only the
database-bound check.

### Manual developer workflow (§21)

```
change model
   |
   v
python -m alembic revision --autogenerate -m "..."     # a PROPOSAL, never committed as-is
   |
   v
inspect every operation; delete unintended ones        # §22; watch for remove_table / unique-on-data
   |
   v
DATABASE_URL=<db> python -m alembic upgrade head
DATABASE_URL=<db> python -m alembic downgrade -1       # prove reversibility
DATABASE_URL=<db> python -m alembic upgrade head
   |
   v
TEST_DATABASE_URL=... pytest tests/integration tests/unit
   |
   v
DATABASE_URL=<db> python -m alembic check              # must be clean, or be justified below
   |
   v
commit
```

If `alembic check` reports an operation you cannot fix safely: classify it with
§13's categories, add one `AcceptedDrift(kind|table|object, classification, reason)`
entry to `tests/schema_drift_baseline.py` **in the same change**, and state it in
the task's results document. Resolving a documented entry requires deleting its
line in the same change — the gate fails otherwise. Adding entries to make a
failure go away is visible in review, because each entry is one row with a
category and a reason.

---

## 7. Testing — exact commands and exact results

All commands run from the repository root with the project interpreter
`backend/.venv312_repro/Scripts/python.exe`.

| # | Command | Result (verbatim numbers) |
| --- | --- | --- |
| 1 | `TEST_DATABASE_URL=...pofa_test python -m pytest -q tests/unit` | `420 passed, 1 skipped` in 22.09s — identical to the BE-027 baseline. Skip is `tests/unit/test_preflight.py:117: ML stack genuinely installed in this environment` |
| 2 | `TEST_DATABASE_URL=...pofa_test python -m pytest -q tests/integration` | `1 failed, 281 passed, 9 warnings` in 483.57s. Baseline was 275 passed / 1 failed; 275 + 6 new gate tests = 281. The failure is the pre-existing one, unchanged and not weakened: `tests/integration/test_be025_admin_control_plane.py::test_organization_lifecycle_noop_audit_and_isolation` — `assert str(org.id) in ids` fails because a freshly created organization is not on the first page of the paginated list (volume-sensitive assertion, 94+ organizations vs `limit=50`; documented in BE-025/BE-027 results) |
| 3 | `TEST_DATABASE_URL=...pofa_test python -m pytest -q -m "not integration" tests` | `1 failed, 695 passed, 1 skipped, 6 deselected` in 400.48s. 695/1/1 equals the BE-027 combined baseline exactly; the 6 deselected are this task's gate tests |
| 4 | `TEST_DATABASE_URL=...pofa_test python -m pytest -q tests/integration/test_schema_drift_gate.py tests/unit/test_migrations.py` | `14 passed` in 11.94s (6 gate + 8 graph) — re-run at the end of the task, after all experiments |
| 5 | `DATABASE_URL=...pofa_test python -m alembic check` | **`FAILED: New upgrade operations detected` — 6 operations**, listed verbatim in `D:/CODING/Scratch/be028/alembic_check_pofa_test_after.txt`. Reported honestly: the CLI itself does not pass. The containment verdict is **PASS WITH DOCUMENTED BASELINE** — all 6 are classified (#11/#12 Category B, #13–#16 Category E) and the gate holds them exactly |
| 6 | `DATABASE_URL=...pofa_test python -m alembic current` | `q7r8s9t0u027 (head)` |
| 7 | `python -m alembic heads` | `q7r8s9t0u027 (head)` — one head only |
| 8 | `python -m alembic history` | 22 lines, continuous base → `q7r8s9t0u027` |
| 9 | fresh scratch base → head (`pofa_be028_fresh`) | 22 `Running upgrade` log lines, no error/traceback lines, final `alembic_version = q7r8s9t0u027` |
| 10 | drift signatures on `pofa_be028_fresh` (fresh) vs `pofa_test` (upgraded in place) | **identical 6 signatures** — the migrated-from-nothing schema and the long-lived test schema agree with the ORM the same way, so the result is not an artifact of one database's history |
| 11 | live-server §30/§31 probe (`D:/CODING/Scratch/be028/probe_a_development.py`, uvicorn on 127.0.0.1:8125) | `RESULT: PASS - all six surfaces behaved as documented` (detail in §7a) |
| 12 | `AUTH_MODE=enforcing` server (uvicorn on 127.0.0.1:8126) + curl | anonymous `/auth/roles` → `401`, `/audit/events` → `401`, `/auth/me` → `401`, `Bearer dev-user-nope` → `401`, unguarded `/health` → `200` |
| 13 | read-only `verify_chain` (`D:/CODING/Scratch/be028/chain_check_readonly.py`) | `pofa_test`: rows=30821, span=(1, 30821), `valid=True failures=0`. `pofa_dev`: rows=6016, max sequence=6052, `valid=False failures=7` (see §9 — pre-existing, already documented by `diagnostics/audit_gap_diagnostic.sql`) |

### 7a — live-server regression detail (all six §30 surfaces)

```
database: pofa_be028_rollback | schema: q7r8s9t0u027
BE-028 indexes: ['ix_analysis_jobs_status', 'ix_evidence_metadata_evidence_id', 'ix_projects_name']
chain before             valid=True events=28584
GET /health 200 | GET /ready 200 | GET /openapi.json 200
DELETE /projects/{id} exists in OpenAPI: False
GET /auth/roles anonymous (development bypass)              -> 200
GET /auth/roles as authenticated non-admin                   -> 403
GET /audit/events as authenticated non-admin                 -> 403
GET /auth/me with a real dev token                           -> 200
GET /auth/me with a garbage token                            -> 401
POST /projects 201 | GET /projects/{id} 200 | PATCH /projects/{id} 200 | GET /projects 200
GET /projects?name=... 200 | DELETE /projects/{id} 405
POST /auth/organizations 201 | PATCH /auth/organizations/{id} 200
ledger rows for the probe org: [(28585, 'ORGANIZATION_CREATED'), (28586, 'ORGANIZATION_UPDATED')]
chain after              valid=True events=28586   (grew by exactly 2)
residue users: 0 | projects: 0 | organizations: 0
chain after cleanup      valid=True events=28586
```

The development-mode anonymous pass-through is shipped, pre-existing behaviour,
logged once by the server itself:
`WARNING backend.security.authentication: AUTH_MODE=development: anonymous
requests bypass authorization. Set AUTH_MODE=enforcing for any shared deployment.`
It is not a BE-028 change; BE-028 touched no auth code, and the 403/401 lines above
show the guard is still real for authenticated non-admins and invalid tokens.

---

## 8. Data Safety — what was tested, what was deliberately not touched

**Reversibility, tested not assumed (§27).** `pofa_be028_rollback` was created with
`CREATE DATABASE ... TEMPLATE pofa_test`, so the experiment ran on a full copy of
real data (`pofa_test` itself was never downgraded):

| Measurement | A: clone at head | B: after `downgrade -1` | C: after `upgrade head` |
| --- | --- | --- | --- |
| schema version | `q7r8s9t0u027` | `p6q7r8s9t026` | `q7r8s9t0u027` |
| `analysis_jobs` rows | 36 | 36 | 36 |
| `evidence_metadata` rows | 41 | 41 | 41 |
| `projects` rows | 983 | 983 | 983 |
| `users` rows | 1960 | 1960 | 1960 |
| BE-028 indexes present | all 3 | none | all 3 |
| PK / FK / UNIQUE counts | 134 / 113 / 79 | 134 / 113 / 79 | 134 / 113 / 79 |
| NULLs on the indexed columns | all 0 | all 0 | all 0 |
| duplicate email / username groups | 1 / 1 (19 / 19 rows) | 1 / 1 (19 / 19) | 1 / 1 (19 / 19) |

Row, PK, FK, null and duplicate counts identical across all three states:
the migration and its rollback are additive/reversible with zero data effect.

**Application startup verified against a head-migrated database** (fresh uvicorn
boot, `Application startup complete`, `/ready` 200 = live `SELECT 1`).

**PostgreSQL / PostGIS / pgvector proof (§15/§16) on the fresh scratch database:**
PostgreSQL 15.13; `pg_extension` = `postgis 3.4.2`, `vector 0.7.4`, `plpgsql 1.0`;
`postgis_version()` = `3.4 USE_GEOS=1 USE_PROJ=1 USE_STATS=1`;
`spatial_ref_sys` = 8,500 rows (survives the chain, and the gate asserts it stays
populated); 72 base tables in `public` = 70 model tables + `spatial_ref_sys` +
`alembic_version`; 264 indexes.

**`pofa_dev` — not touched.** Never migrated (still `n4o5p6q7r022`), never reset,
never dropped; only `SELECT`s were issued. Re-checked after every experiment:
`users` 1094, `projects` 584 (identical to BE-027's recorded state) and its newest
ledger row still dated 2026-09-27, i.e. before BE-028 began.

**No user data was modified anywhere.** No `INSERT`/`UPDATE`/`DELETE`/`MERGE`
against `users` was executed by this task. `pofa_test`'s user count moved
1960 → 2098 solely through the integration suites' own fixtures; the duplicate
group counts (1 email group / 19 rows, 1 username group / 19 rows) are unchanged
before and after, so no collision was created or destroyed.

**Duplicates were not deleted or merged.** No duplicate user row was touched —
including the 19 rows that each own a project.

**Scratch databases used (all created by BE-028, all isolated, all still present):**
`pofa_be028_scratch` (16 → 6 measurement), `pofa_be028_fresh` (base → head proof),
`pofa_be028_rollback` (rollback + unique-index-failure + live-server probe). Drop
commands, left to the operator rather than executed unilaterally:
`docker exec pofa_db psql -U postgres -c "DROP DATABASE pofa_be028_scratch;" -c
"DROP DATABASE pofa_be028_fresh;" -c "DROP DATABASE pofa_be028_rollback;"`
(they must not be connected while dropping; `pofa_test`, `pofa_dev`,
`pofa_audit_verify` are untouched by these commands).

**Audit ledger.** Append-only discipline respected: no ledger row was deleted,
updated or truncated; the only ledger growth was produced by the application
during the live probe (2 rows, sequences 28585–28586, on the scratch clone). Chain
validity re-verified (§13 line of §7).

---

## 9. Blockers

1. **B-1 — user uniqueness cannot be enforced safely (Category E, unresolved by
   decision).** Two contradicting safe directions, both identity-policy decisions
   (§2 of the task file, §3's prohibition); forcing either would modify or delete
   user rows without approval. Evidence in §2, plan in §10. **BE-028 stops here and
   reports the blocker rather than corrupting data.**
2. **`alembic check` cannot be made clean without unsafe changes.** Reported
   exactly: the CLI still exits `FAILED` with 6 operations. Containment is
   PASS-WITH-DOCUMENTED-BASELINE; the check is *not* suppressed.
3. **`pofa_dev`'s audit chain has 7 gaps (36 missing sequence numbers).**
   `verify_chain` on `pofa_dev` returns `valid=False`. Classified as **pre-existing
   and not caused by BE-028**: the gaps sit at sequences ~5344–5381 dated
   2026-09-25, `pofa_dev`'s newest ledger row is 2026-09-27, `pofa_dev` was never
   migrated or written to by this task, and the repository already contains
   `diagnostics/audit_gap_diagnostic.sql` whose header states the exact same
   finding ("36 missing sequence numbers across 7 gaps"). `pofa_test` (the
   migration-canonical database) is `valid=True` with a gap-free span 1 → 30,821.
   No stop condition triggered: audit integrity did not *change* during BE-028.
4. **`pofa_test`'s duplicate users have `external_subject = NULL`,** so
   `uq_user_identity_subject` does not constrain them, unlike `pofa_dev`'s
   backfilled rows. Whether `pofa_test` is missing the BE-016 backfill or the
   rows predate it must be established before BE-029 picks a canonical-selection
   rule.
5. **Environment outage mid-task.** Docker Desktop stopped (Postgres/Redis/MinIO
   unreachable); restarted with the user's approval, containers came back on their
   restart policies, and every database was re-verified before continuing. The
   unit/integration/migration/drift evidence above is from after recovery.

Also recorded, not acted upon (out of scope, §36/§37): expression/GiST indexes such
as `idx_evidence_location` are not reflectable, so they are invisible to Alembic's
comparison — a genuine blind spot in drift detection that this task neither fixed
nor papered over.

---

## 10. Recommended Next Task

**BE-029 — User Identity Constraint Remediation** (design below, per task file §25;
**not implemented in BE-028**).

Decision the product owner must make first, because everything else follows from it:
are `username` / `email` identity keys, or display attributes? The enforced key
today is `(identity_provider, external_subject)`.

*If uniqueness is required:*

* **Duplicate detection.** Deterministic query, exact-value grouping on
  `email` and `username` (both already normalised at write time by
  `create_user`: `strip()` and `strip().lower()`), so no new collation or
  expression index is needed. Report groups, member ids, creation order and
  per-member reference counts before touching anything. Case-folding and
  `+tag` normalisation must be *reported separately* — measured today they add no
  groups in either database, so the policy question is arguable but unobserved.
* **Canonical selection.** Do not pick a rule without evidence. Evidence
  available now: all 19/40 colliding rows are `ACTIVE`, `identity_provider='local'`,
  and each owns exactly one project, so "most referenced user" and "one legit
  identity per row" both fail to discriminate. `external_subject` is the only
  differentiator in `pofa_dev` (present on all 40) and must be established for
  `pofa_test` first (blocker 4). Candidate rule to *propose*, not apply: keep the
  row whose `external_subject` equals its own `id` (the BE-016 backfill shape,
  i.e. the row that a real provider would have produced), break remaining ties by
  earliest `created_at`, and log every non-kept row's full record into the audit
  ledger before any deletion.
* **Reference migration.** Surface measured: 14 FKs reference `users(id)`;
  only `projects.owner_id` holds referencing rows (19 test / 40 dev), all
  `NO ACTION`; `user_role_assignments.user_id` is `CASCADE` and currently has 0
  rows for these ids. Plan: one transaction per group, `UPDATE projects SET
  owner_id = :canonical WHERE owner_id = :losing` re-counted row by row, then
  re-check that no FK anywhere points at a losing id, then delete the losing users,
  then `db.flush()` + FK validation before commit. Never rely on `CASCADE` to clean
  up role assignments — assert 0 first, so an unexpected assignment aborts the
  transaction instead of silently deleting authorisation state.
* **Authentication implications.** V1 stores no passwords and no session or
  refresh-token table keyed by username/email, and nothing looks a user up by
  either column, so: sessions — none to invalidate; refresh tokens — none exist;
  provider ids — `external_subject` must be *preserved* for the canonical row and
  archived (not dropped) for merged rows, because it is the only link back to a
  provider subject; passwords — none stored, nothing to carry; verification state
  — no email-verification column exists today, so nothing to reconcile. If any of
  those changes before BE-029 is executed, re-audit from `backend/security/`
  rather than reusing this paragraph.
* **Rollback.** Full logical backup of `users`, `projects`, `user_role_assignments`
  plus an audit-ledger snapshot before any write; execute against a
  `TEMPLATE`-cloned scratch database first (exactly the technique used in §8);
  write the migration so `downgrade()` is a *restore*, not a re-merge — which means
  the merge must be reversible by construction (archive losing rows into a
  `..._retired` table rather than deleting them, so downgrade re-inserts and
  re-points).
* **Verification.** Before/after row counts per affected table, per-group
  reference counts preserved (`19 → 19` on `projects.owner_id`, not `→ 18`),
  `pg_constraint` FK validation, `SELECT count(*) FROM users GROUP BY email HAVING
  count(*) > 1` returning zero, `verify_chain` still valid, project CRUD + auth +
  audit regression re-run, and only then delete the two `remove_index`/`add_index`
  Category-E baseline entries in the same change — which the gate requires and
  rewards by going clean.

*If uniqueness is **not** required:* the correct BE-029 is much smaller — drop
`unique=True` from `User.username`/`User.email` (keeping `index=True` under the
existing `ix_users_*` names), state the non-unique policy in the model, delete the
4 Category-E baseline entries, and add a CHECK-based duplicate *detector* instead of
a constraint. This is the branch that involves no data migration at all, and it is
the branch the current code already behaves as.

Secondary recommendation, independent of B-1: the `pofa_dev` ledger gaps (§9.3)
deserve their own diagnosis→decision task, using `diagnostics/audit_gap_diagnostic.sql`
as the starting point, because `verify_chain` returning `valid=False` on the
development database will otherwise be normalised as "expected failure".

`Do not implement the next task automatically.` — BE-029 was not started.
