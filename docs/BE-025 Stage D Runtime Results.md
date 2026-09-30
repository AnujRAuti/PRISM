# BE-025 Stage D — Runtime Verification Results

Milestone: BE-025 Organization, Role Assignment & Administrative Control Plane
Branch: `Backend` · Baseline commit: `75c52b68` (BE-024 accepted)
Stage gate: task file §17 (Stage D — Runtime Verification), plus §12 (migrations) and §14 (security regression)

---

## 1. What this gate required, and how it was satisfied

Stage D forbids substitutes: no grep-only checks, no import smoke tests, no
reading the OpenAPI string out of a file, no mocked authorization. Every claim
below is produced by executing code against a live PostgreSQL with the real
FastAPI application and real principals.

Three evidence tracks were run:

| Track | Method | Artifact |
|---|---|---|
| Targeted suite | `pytest` over real HTTP (`TestClient`) against `pofa_test` | `tests/integration/test_be025_admin_control_plane.py` — 16 tests |
| Live endpoint probe | Standalone script driving the same app, 149 assertions over 12 sections | `probe_final.log` (scratch, outside the repo) |
| Migration verification | Real `alembic upgrade/downgrade/upgrade` on dedicated scratch databases | `migrations.py`, `migrations_existing.py` output |

No test, no assertion and no production file was weakened to reach a green
result. Two production defects and one stale artifact were found and fixed
(§7), then re-verified by re-running everything.

---

## 2. Environment (measured, not assumed)

```
$ DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test \
  PYTHONPATH=D:/CODING/Projects/Proof-Of-Action-Final \
  backend/.venv312_clean/Scripts/python.exe "$TEMP/poa_stageD/preflight.py"

database   pofa_test
postgres   15.13 (Debian 15.13-1.pgdg120+1)
dialect    postgresql/psycopg2
auth_mode  development
postgis    POSTGIS="3.4.2 c19ce56" [EXTENSION] PGSQL="150" GEOS="3.11.1-CAPI-1.17.1" PROJ="9.1.1"
pgvector   0.7.4
extension  plpgsql 1.0
extension  postgis 3.4.2
extension  vector 0.7.4
alembic    ['o5p6q7r8s025']
matrix     1                          # ck_assignment_scope_matrix is live
be025_tbls 4                          # organizations, organizational_units,
                                      # user_role_assignments, audit_ledger_events
redis      True                       # ping against settings.redis_url
buckets    ['pofa-evidence', 'pofa-quarantine']   # MinIO reachable via S3 API

$ backend/.venv312_clean/Scripts/python.exe -V
Python 3.12.0  (AMD64)

$ docker ps
pofa_db     Up    (postgres-postgis-pgvector, :5432)
pofa_redis  Up    (:6379)
pofa_minio  Up    (:9000)
```

Database revision under test: `o5p6q7r8s025` (single Alembic head, 20 linear
revisions, `n4o5p6q7r022 -> o5p6q7r8s025`).

Isolation: `tests/conftest.py` republishes `TEST_DATABASE_URL` as
`DATABASE_URL` and refuses to run without it, so the pytest track can never
fall back to `pofa_dev`. The two standalone tracks set `DATABASE_URL`
explicitly and print `current_database()` on every run (visible in the outputs
above). Post-run audit of `pofa_dev` confirmed zero contact in this session:

```
database pofa_dev | users 1094 | audit events 6016 | version ['n4o5p6q7r022']
                   | be025*-prefixed rows 0
```

---

## 3. Commands executed (verbatim, reproducible)

```bash
export TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test

# targeted BE-025 suite
backend/.venv312_clean/Scripts/python.exe -m pytest \
  tests/integration/test_be025_admin_control_plane.py -q -p no:randomly

# §14 security regression, per suite
for S in tests/unit/test_authorization.py tests/unit/test_integration.py \
         tests/unit/test_migrations.py tests/unit/test_audit_ledger.py \
         tests/unit/test_audit_guard.py tests/unit/test_preflight.py \
         tests/unit/test_test_target.py tests/integration/test_authorization.py \
         tests/integration/test_be025_admin_control_plane.py \
         tests/integration/test_audit_ledger.py tests/integration/test_be007_contracts.py; do
  backend/.venv312_clean/Scripts/python.exe -m pytest "$S" -q -p no:randomly
done
backend/.venv312_clean/Scripts/python.exe -m pytest \
  tests/integration/test_governance.py tests/integration/test_publication.py \
  tests/integration/test_retention.py tests/integration/test_review_case.py -q

# live HTTP endpoint probe (149 checks)
DATABASE_URL=$TEST_DATABASE_URL PYTHONPATH=$REPO \
  backend/.venv312_clean/Scripts/python.exe "$TEMP/poa_stageD/probe.py"

# §12 migration verification (dedicated scratch databases, dropped afterwards)
backend/.venv312_clean/Scripts/python.exe "$TEMP/poa_stageD/migrations.py"
backend/.venv312_clean/Scripts/python.exe "$TEMP/poa_stageD/migrations_existing.py"
```

---

## 4. Targeted BE-025 suite (real HTTP, isolated test database)

```
tests/integration/test_be025_admin_control_plane.py  16 passed, 7 warnings in 39.87s
```

16 tests, 0 failures, 0 skips. Coverage maps to task §13:

| Task §13 requirement | Test |
|---|---|
| Authorization matrix (admin allowed, others denied) | `test_administrator_can_manage_org_within_scope`, `test_non_admin_roles_denied_admin_plane` |
| Organizational units (valid create, wrong org, unauthorized modify, cross-org) | `test_unit_boundaries_enforced` |
| Role management (valid/invalid/duplicate/revocation/escalation/concurrency) | `test_scoped_assignment_lifecycle_via_api`, `test_duplicate_assignment_is_idempotent_and_concurrent_safe`, `test_privilege_escalation_attempts_denied` |
| Last-administrator protection | `test_last_global_administrator_guard` |
| Organization lifecycle, no-op audit suppression, isolation | `test_organization_lifecycle_noop_audit_and_isolation` |
| Project/team assignments, cross-org rejection, ownership | `test_project_scope_administration`, `test_project_ownership_transfer` |
| API-client scope enforcement | `test_api_client_scope_enforcement` |
| Pagination, enumeration safety, malformed IDs | `test_pagination_bounds_and_enumeration`, `test_malformed_admin_payloads_rejected` |
| Database constraint (M1) | `test_scope_matrix_check_constraint_enforced_by_database` |
| Audit chain remains valid | `test_admin_audit_chain_remains_valid` |
| OpenAPI accuracy (§9) | `test_openapi_documents_the_administrative_surface` (added at Stage D) |

---

## 5. Live runtime endpoint probe — 149 checks, 0 failures

```
database=pofa_test alembic_version=['o5p6q7r8s025']
checks=149 passed=149 failed=0
GATE: PASS
teardown: probe users remaining = 0, probe orgs remaining = 0
real 0m37.090s
```

Every section drives the HTTP surface with real principals (development dev
bearer tokens resolved from the database, plus one enforced-mode pass), and
verifies effects by reading the database back.

| Section | Task ref | Checks | Outcome |
|---|---|---|---|
| Setup (project create, scope bind) | §7 | 2 | PASS |
| A. Role matrix on the admin plane (4 non-admin roles × 6 admin routes) | §5 | 24 | PASS — uniform 403 |
| A2. Suspended administrator | §5 | 1 | PASS — 401 |
| B. Cross-organization isolation | §5, §11 | 8 | PASS — foreign org/unit ≡ absent (404), own org readable/updatable (200), list shows only own org |
| C. Privilege escalation + API-client scope | §5, §6 | 13 | PASS — GLOBAL target/ADMINISTRATOR grant 403, cross-org target 404, client scope bounded |
| D. Invariants + revoked access immediacy | §7 | 18 | PASS — wrong-org unit 422, missing scope id 422, duplicate 201→200 with exactly one row, revocation takes effect on the next request |
| E. Audit records | §8 | 31 | PASS — 8 event kinds found for the exact probe resources, correct actor + target, before/after state present, no secret material |
| F. Audit chain integrity | §8 | 3 | PASS — `valid=True`, `checked_events=12121`, `first_sequence=1`, `last_sequence=12121`, `failures=[]` |
| G. Enforcing mode, no hidden admin bypass | §5, §14 | 5 | PASS — unauthenticated 401 ×6, forged dev token 401, real principal 200, citizen 403 |
| H. OpenAPI accuracy | §9 | 15 | PASS — see DF-D-01 |
| I. Pagination / enumeration bounds | §11 | 13 | PASS — `limit=0`/`limit=1001` 422, disjoint stable pages, malformed UUID 422, unknown assignment 404, no-op update writes no audit event |
| J. Project-scope administration | §7 | 9 | PASS — cross-org move needs both scopes, partial clear that would orphan a unit refused 422 with state intact, zero dangling projects |
| K. Last-GLOBAL-administrator guard + concurrency | §7, §10 | 7 | PASS — concurrent revocation `[204, 404]` (exactly one removal), self-revoke 409, self-deactivate 409, stripped peer 403, refused revocation writes no `ROLE_REVOKED` row |

Notable runtime facts established (not asserted from source):

* **Immediate authorization change.** A `REVIEWER` granted at ORGANIZATION
  scope reads the bound project (200); the same request after `DELETE
  /auth/users/{id}/roles/{assignment_id}` returns 403 — principals are rebuilt
  per request, so revocation cannot linger.
* **Concurrency is applied exactly once.** Two simultaneous `DELETE`s of the
  same assignment returned `[204, 404]`: the advisory lock plus the
  row-count-checked delete means the loser reports "not found" instead of
  double-revoking or double-auditing.
* **No enumeration oracle.** A foreign organization, unit, project and
  assignment are all 404 for a scoped administrator — identical to absent.
* **Development bypass is the documented BE-016 contract, not an admin
  backdoor.** In enforcing mode the entire admin plane returns 401 to
  anonymous callers and to forged dev tokens, while real principals keep
  working. `AUTH_MODE=development` prints its own warning on every request.
* **Refused mutations leave no misleading audit trail.** The 409 last-admin
  refusals appended zero `ROLE_REVOKED` events, while the one successful
  concurrent revocation appended exactly one.

---

## 6. §12 migration verification

From-scratch build, downgrade, and existing-database upgrade were run against
two dedicated scratch databases (`pofa_stageD_mig`, `pofa_stageD_mig2`), each
created only if absent and dropped at the end. `pofa_test` and `pofa_dev` were
not rebuilt or migrated.

```
=== FROM-SCRATCH UPGRADE ===   20 revisions, bb4bf0dd8fb7 -> … -> o5p6q7r8s025
version: o5p6q7r8s025 | public tables: 71 | ck_assignment_scope_matrix: 1
BE-025 tables present: 9 | extensions created by migrations: postgis, vector

=== DOWNGRADE -1 ===
version: n4o5p6q7r022 | ck_assignment_scope_matrix: 0        # clean reversal

=== EXISTING-DATABASE UPGRADE (n4o5p6q7r022 -> head) ===
version: o5p6q7r8s025 | ck_assignment_scope_matrix: 1
```

The upgrade path was then exercised against **pre-existing data**, which is
the case that actually matters for a populated deployment:

```
assignments before upgrade: 3 (1 deliberately malformed)
upgrade over the malformed row  -> alembic returncode 1, still n4o5p6q7r022, CHECK absent
                                    RESULT: upgrade correctly refused the malformed pre-existing row
after removing the malformed row -> returncode 0, version o5p6q7r8s025, CHECK present
assignments after upgrade: 2 (both valid BE-016 rows survived)
post-upgrade malformed insert    -> CheckViolation: new row for relation
                                   "user_role_assignments" violates check
                                   constraint "ck_assignment_scope_matrix"
```

So M1 is enforced by the database, it validates rows that already exist rather
than only new writes, and it does not damage legitimate BE-016 data.

Deployment readiness check (read-only): `pofa_dev` currently sits at
`n4o5p6q7r022` with **872 assignments and 0 matrix-violating rows**, so its
eventual `alembic upgrade head` will apply M1 without a data fix.

Historical revisions were not modified (`git status` shows exactly one new
revision file). `tests/unit/test_migrations.py` still asserts one head, one
linear path and full reachability; its pinned head/revision-count constants
were advanced to `o5p6q7r8s025` / 20 after `alembic heads` confirmed a single
head — the guard is not weakened.

---

## 7. §14 security regression — before and after

Baseline = the same suites run earlier in Stage D, before any Stage D
production edit. After = the identical suites re-run after DF-D-01/DF-D-02/
DF-D-03 landed. No suite was edited to make it pass.

| Suite | Milestone | Before | After |
|---|---|---|---|
| `tests/unit/test_authorization.py` | BE-016 / BE-024 | 17 passed (1.62s) | 17 passed (1.66s) |
| `tests/unit/test_integration.py` | BE-019 | 19 passed (2.39s) | 19 passed (1.65s) |
| `tests/integration/test_authorization.py` | BE-016 | 17 passed (37.10s) | 17 passed (43.63s) |
| `tests/integration/test_be007_contracts.py` | BE-007 contracts | 3 passed (10.42s) | 3 passed (13.66s) |
| `tests/integration/test_audit_ledger.py` | BE-015 | 10 passed (27.17s) | 10 passed (38.16s) |
| `tests/unit/test_audit_ledger.py` | BE-015 | 10 passed (2.26s) | 10 passed (1.61s) |
| `tests/unit/test_audit_guard.py` | BE-023 guard | included in batch | 20 passed (0.96s) |
| `tests/unit/test_migrations.py` | BE-023 | included in batch | 8 passed (0.16s) |
| `tests/unit/test_preflight.py` | BE-023 | included in batch | 23 passed, 1 skipped (0.17s) |
| `tests/unit/test_test_target.py` | BE-023 | included in batch | 9 passed (0.08s) |
| `tests/integration/test_governance.py` | BE-021 | 14 passed (135.29s) | 14 passed (117.08s) |
| `tests/integration/test_publication.py` | BE-022 | 44 passed (69.44s) | 44 passed (76.99s) |
| `tests/integration/test_retention.py` | BE-017 | 10 passed (33.70s) | 10 passed (41.31s) |
| `tests/integration/test_review_case.py` | BE-013 | 9 passed (28.78s) | 9 passed (35.83s) |
| `tests/integration/test_be025_admin_control_plane.py` | BE-025 | 15 passed (26.12s) | 16 passed (39.87s) |

Combined runs recorded for the same suites: unit authorization cluster
`74 passed in 4.62s`; `integration/test_authorization + unit authorization +
unit integration + audit guard + migrations` `81 passed in 54.71s`;
`BE-025 + integration auth + audit ledger + be007` `46 passed, 7 warnings in
95.33s`; `governance + publication` `58 passed, 7 warnings in 216.14s`;
BE-023 infrastructure cluster `78 passed, 1 skipped, 6 warnings in 14.83s`.

### 7.1 Slow integration suites after the fixes

These four suites were re-run **individually, after DF-D-01, DF-D-02 and
DF-D-03 had all landed**, so the "After" column above is measured on the final
code state rather than inferred from the earlier combined run.

Command (verbatim):

```bash
cd /d/CODING/Projects/Proof-Of-Action-Final
for SUITE in tests/integration/test_governance.py \
             tests/integration/test_publication.py \
             tests/integration/test_retention.py \
             tests/integration/test_review_case.py; do
  printf '%-48s ' "$SUITE"
  TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test" \
    backend/.venv312_clean/Scripts/python.exe -m pytest "$SUITE" -q -p no:randomly \
    2>&1 | tail -1
done
```

Recorded output:

```
tests/integration/test_governance.py               14 passed, 7 warnings in 117.08s (0:01:57)
tests/integration/test_publication.py              44 passed, 6 warnings in 76.99s (0:01:16)
tests/integration/test_retention.py                10 passed, 6 warnings in 41.31s
tests/integration/test_review_case.py              9 passed, 6 warnings in 35.83s
```

Totals: **77 passed, 0 failed, 0 skipped, 27 warnings** across the four suites;
the shell reported exit code 0. Same counts as the pre-fix run (`14/44/10/9`),
so the OpenAPI `responses` declarations, the `GET /auth/organizations/{id}`
guard change and the regenerated `openapi.json` changed none of these
milestones' behavior. Per-suite durations differ from the pre-fix run in both
directions (governance 117.08s vs 135.29s, publication 76.99s vs 69.44s)
because the probe and the §12 migration scratch databases were running
concurrently; the pass counts are identical.

### 7.2 Failures classified

**Zero production failures remained at the end of Stage D.** The three defects
Stage D did find, and their disposition:

| ID | Kind | Symptom (runtime evidence) | Disposition |
|---|---|---|---|
| DF-D-01 | Production (§9) | No BE-025 admin route declared its authentication/authorization outcomes: `responses` in the served document contained only `200/201/204/422`, so 401/403/404/409 were invisible to API consumers | **FOUND → FIXED → VERIFIED.** All 19 administrative operations now declare exactly the statuses they can return (via one shared `_ERROR_RESPONSES` table, with 422 left to FastAPI's automatic validation response). Verified by probe section H (15 checks) and by the new `test_openapi_documents_the_administrative_surface`. |
| DF-D-02 | Production (§5/§7 read-vs-update asymmetry) | `GET /auth/organizations/{id}` was guarded by `require_global`, so an organization-scoped administrator got **403 on its own organization** while `PATCH` on the same resource is scope-aware and returns **404 for foreign** ones: the same resource had two different authority models, and the scoped admin could not even read what it administers | **FOUND → FIXED → VERIFIED.** The read now uses the identical guard as the update (`require("organization.manage", "organization", "organization_id")`). Runtime: own org 200, foreign org 404, unknown org 404, and in enforcing mode 200/404 unchanged. Verified in probe B (8 checks), the extended `test_administrator_can_manage_org_within_scope`, and the Stage B design table (row added). No permission was widened for any caller that could not already act on the resource: strictly more authority is granted only over an organization the caller already administers, and the foreign-org answer moved from 403 to 404, which removes an oracle rather than adding one. |
| DF-D-03 | Repository artifact staleness (§9) | The committed `openapi.json` snapshot (last regenerated at `41174a4e`, BE-024) still described the pre-BE-025 admin surface: no `/auth/units/{unit_id}`, no `/auth/projects/{project_id}/scope`, no `/auth/projects/{project_id}/ownership`, no `/auth/users/{user_id}/status`, and none of the BE-025 response models | **FOUND → FIXED → VERIFIED.** Regenerated from the live application: 4 paths added, 10 schemas added (`AdminProjectResponse`, `OrganizationListResponse`, `OrganizationUpdate`, `OrganizationalUnitListResponse`, `OrganizationalUnitUpdate`, `ProjectOwnershipUpdate`, `ProjectScopeUpdate`, `RoleAssignmentListResponse`, `UserListResponse`, `UserStatusUpdate`), **0 paths and 0 schemas removed**, +1118/−119 lines. |

Probe-side (test-only) defects found and fixed during Stage D, none of them
production behavior: the concurrency helper passed an ORM `User` object where a
user id string was required (both threads returned 422); the audit-target map
kept the *oldest* row of a descending query, attributing
`ORGANIZATION_UPDATED` to the wrong organization; the destructive
last-administrator section wiped every GLOBAL assignment mid-run and thereby
stripped the authority the later sections depended on; the teardown deleted
projects before the `api_clients` rows that reference them (FK RESTRICT), which
silently aborted cleanup and left 48 probe users in `pofa_test`. All four were
corrected, the leftovers were removed in FK-safe order, and the final run
reports `probe users remaining = 0`.

### 7.3 Preserved findings — deliberately not "fixed" in BE-025

| ID | Finding | Why preserved |
|---|---|---|
| R4 | `project.update` is granted to no seeded role, so domain rename stays unreachable for every role | Carried forward from BE-024 per the standing instruction to preserve historical findings; BE-025 does not widen a seeded grant. |
| P1 | `GET /auth/roles` and `GET /auth/permissions` require the permission in **GLOBAL** scope, so an organization-scoped administrator cannot enumerate the role catalogue | Both the catalogue and the user directory are not organization-scoped entities, so scope-aware enforcement has no resource to resolve; this is BE-016 behavior and predates BE-025. Changing it would invent a new authority rule rather than reuse the locked architecture. The delegation path that scoped admins actually need (`POST /auth/users/{id}/roles`) is scope-aware and verified working. |
| P2 | The served OpenAPI document declares no `securitySchemes` / `HTTPBearer`, so authentication is expressed per-operation (401 declarations, guards, and prose) rather than as a global security requirement | Application-wide gap inherited from BE-016; it touches every router, not the BE-025 surface. Declaring it would require a new global security dependency, i.e. a change well outside this milestone. DF-D-01 makes the 401 outcome explicit on every admin operation, which is the BE-025-scoped part of §9. |
| P3 | Organization/Unit deactivation is lifecycle-only: no DELETE route, `RESTRICT` foreign keys make silent orphaning impossible, and deactivating an organization does not cascade | Task §7 asks that deactivation "cannot silently orphan security-critical records"; the schema already guarantees this by refusing deletion, and the last-administrator advisory guard covers admin lockout. Recorded in the Stage B design table. |
| P4 | `AUTH_MODE=development` lets an anonymous caller bypass authorization, and dev bearer tokens are accepted when `auth_dev_tokens_enabled` | Documented BE-016 contract, loudly warned on every startup/request, and **verified at runtime to disappear in enforcing mode** (probe G). Not a hidden admin bypass: no admin route accepts an unauthenticated caller once `auth_mode=enforcing`. |
| P5 | `pofa_dev`'s audit ledger has seven historical sequence gaps (6016 rows below max sequence 6052), so `verify_chain` returns `valid=False` on that database only | Pre-existing dev-data condition discovered in the §8 final-state re-check, not produced by BE-025 (the §2 checkpoint counts are unchanged and no write touched `pofa_dev`). Its origin is documented in-repo: `tests/audit_guard.py:5-9` records that "two integration cleanups used to do exactly that, which produced seven historical gaps spanning 36 sequence numbers" — i.e. DELETEs from before the BE-023 guard existed, matching the observed 36-number deficit exactly. Repairing it would mean inserting or updating audit rows — an append-only violation. `pofa_test` verifies `valid=True`. |

---

## 8. Audit ledger, isolation and side-effect evidence

* Ledger is append-only and unbroken throughout: `valid=True`,
  `checked_events=12121`, `first_sequence=1`, `last_sequence=12121`,
  `failures=[]`. No Stage D step deleted, truncated or updated an audit row;
  the two scratch migrations ran on purpose-built databases that were dropped,
  and probe teardown never touches `audit_ledger_events`.
* Administrative audit payloads were scanned for secret material:
  `(password|secret|token|credential|access_key|apikey)` over every BE-025
  event payload **and** metadata returned `[]`.
* `pofa_test` was left clean: `be025d-%` users 0, organizations 0, units 0, API
  clients 0 after the final probe run; the 48 rows stranded by the earlier
  teardown defect were removed in FK-safe order (assignments → clients →
  projects → users → units → organizations) and re-verified.
* The GLOBAL-scope assignments that section K temporarily removed to create a
  controlled "last administrator" scenario were restored from an id snapshot
  (`GLOBAL assignments restored (count now 8, snapshot 7)` — the extra row is
  the section's own probe user, deleted by teardown).
* `openapi.json` is a **tracked repository artifact** (`git ls-files` resolves
  it), so DF-D-03 was a real checked-in update of a committed file, not merely a
  local regeneration of a generated-and-ignored output.
* Three tracked BE-024-era verification scripts live at the repository root —
  `stage_d_runtime_checks.py`, `stage_e_runtime_checks.py`,
  `test_vision_temporal_auth.py` (all last touched in `41174a4e`, "be-024
  verification stages"). Despite the colliding filenames they belong to BE-024
  and Stage D left them **untouched and unmodified**; this milestone's probe ran
  from a temporary directory outside the repository, so no BE-025 scratch code
  entered the tracked tree. Verified: `git status --short` over the three paths
  returns empty, and `git log -1` for each is still `41174a4e`.
* `pofa_dev` was not written to, migrated, or polluted (row counts and revision
  unchanged, 0 `be025*` rows).

**Final-state re-check (after the §7.1 slow-suite runs, read-only):**

```
--- pofa_test ---  revision ['o5p6q7r8s025']
  ledger rows/min/max (13158, 1, 13158)
  matrix violations  0
  verify_chain       {'valid': True, 'checked_events': 13158, 'first_sequence': 1,
                      'last_sequence': 13158, 'failures': []}
  users 1275 | organizations 9 | organizational_units 2 | user_role_assignments 71
--- pofa_dev ---
  revision ['n4o5p6q7r022']        (not migrated by BE-025 — unchanged from session start)
  users 1094 | audit events 6016 | organizations 0 | organizational_units 0
  user_role_assignments 872 | matrix violations 0
  ledger rows/min/max (6016, 1, 6052)
```

`pofa_test`'s 13158 events and 1275 users are the cumulative total of every
milestone's integration suite against this shared test database, not BE-025
residue — probe teardown had already reduced BE-025's own rows to 0 before the
four slow suites ran, and those suites created their own fixtures. The counts
above were captured after them, so the ledger stayed append-only and unbroken
across the whole session, and `ck_assignment_scope_matrix` admits no violating
row in either database.

`pofa_dev`'s `verify_chain` returns `valid=False` with seven `sequence gap`
failures and a `6016 rows / max sequence 6052` mismatch. Classified
**pre-existing, not a BE-025 regression**: the mid-session isolation checkpoint
in §2 recorded `users 1094 | audit events 6016 | version ['n4o5p6q7r022']` for
this database and every one of those figures is unchanged in the re-check above,
while no Stage D step opened a write connection against `pofa_dev` (all writes
went to `pofa_test` or to the two dropped scratch databases). The gap list is a
property of the historical dev database: `tests/audit_guard.py:5-9` documents
that two pre-BE-023 integration cleanups deleted ledger rows and "produced
seven historical gaps spanning 36 sequence numbers", which is exactly the
`6052 - 6016 = 36` deficit and 7-gap list observed here; the same verifier run
against `pofa_test`, the gate's target database, returns
`valid=True` with no gaps, so the chain logic itself is sound. Nothing was
written to `pofa_dev` to "repair" it — that would mean updating audit rows,
which the append-only rule forbids.

---

## 9. Skips, warnings and durations

* **Skips: 1** — `tests/unit/test_preflight.py:117` "ML stack genuinely
  installed in this environment". Expected and correct: the skip fires only
  when the optional ML extras are present, which is this environment.
* **Warnings: 7 per integration run**, all pre-existing and unrelated to
  BE-025:
  * `DeprecationWarning: on_event is deprecated, use lifespan event handlers` —
    FastAPI, raised by `backend/app/main.py:132` (BE-001 lineage).
  * `StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is
    deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT'` — raised from
    `backend/security/authorization.py:84` (`reject_malformed_resource_id`,
    BE-024 lineage). Left as-is: renaming the constant is an unrelated sweep
    and the numeric status contract is unchanged.
* **Durations**: targeted suite 39.87s · probe 37.09s · §14 unit cluster
  4.62s · §14 integration cluster 95.33s · slow integration cluster 216.14s
  (combined) · §7.1 slow suites 271.21s of test time across four individual
  runs (117.08 + 76.99 + 41.31 + 35.83).
* No test was deselected, marked `xfail`, or reordered to reach these results.

---

## 10. Stage D gate decision

**Stage D: PASS.**

* Real HTTP against real PostgreSQL/PostGIS/pgvector with Redis and MinIO
  reachable: 149/149 live runtime checks passed, plus 16/16 targeted BE-025
  tests and 77/77 post-fix slow-suite tests (§7.1) with 0 failures and 0 skips.
* §5 role matrix, §6 escalation attempts, §7 invariants, §8 audit records,
  §9 OpenAPI surface, §10 idempotency/concurrency, §11 pagination/enumeration,
  §12 migrations (from-scratch, downgrade, populated upgrade), §13 test matrix
  and §14 regression are each backed by executed evidence above.
* DF-D-01, DF-D-02 and DF-D-03 are fixed and re-verified; R4 and P1–P5 are
  recorded as preserved findings with reasons, not silently ignored. P5 is the
  one pre-existing **environment** observation (`pofa_dev` historical audit
  gaps) and is outside the gate's target database.
* No existing authorization test regressed: every pre-BE-025 suite in the §14
  table reports the identical count before and after the fixes (the BE-025 row
  rises 15 → 16 only because DF-D-01 added `test_openapi_documents_the_
  administrative_surface`). `pofa_test` verifies `valid=True` at 13158 events
  with zero `ck_assignment_scope_matrix` violations, and `pofa_dev`'s §2
  checkpoint counts (1094 users / 6016 events / revision `n4o5p6q7r022`) are
  unchanged.

Open for Stage E (not part of this gate): nothing outstanding from Stage D.
Stage E will add the fault-injection / concurrency / limit hardening evidence
(failure-mode behavior under contention, oversized pages, dead dependencies)
and any resulting production fixes.
