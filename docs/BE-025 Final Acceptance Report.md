# BE-025 Final Acceptance Report — Organization, Role Assignment & Administrative Control Plane

Milestone: BE-025 · Branch: `Backend` · Baseline: `75c52b68` (BE-024 accepted)
Task file: `docs/Production Task Files/BE-025 — Organization, Role Assignment & Administrative Control Plane.md`
Gates: A (reconnaissance) → B (design) → C (implementation) → D (runtime verification) → E (hardening) → **F (full verification, this report)**

This report is the consolidated acceptance record. Stage-by-stage evidence lives in:

| Gate | Document | Decision |
|---|---|---|
| A | `docs/BE-025 Stage A Reconnaissance.md` | PASS |
| B | `docs/BE-025 Stage B Design.md` | PASS |
| C | `docs/BE-025 Stage C Implementation Summary.md` | PASS |
| D | `docs/BE-025 Stage D Runtime Results.md` | PASS |
| E | `docs/BE-025 Stage E Hardening Results.md` | PASS |
| F | this report | **PASS** (§12) |

Every claim below is either a quoted measurement from one of those documents or a
number produced by the Stage F runs in §8. No claim rests on reading source,
grepping, importing, or inspecting the OpenAPI file as a string.

---

## 1. What BE-025 had to deliver

From task §4/§5/§7 and the Stage A gap list (§6 of the reconnaissance doc): an
administrative control plane over the **already locked** BE-016 authorization
model — organizations, organizational units, managed users, scoped role
assignments, project scope/ownership administration, audit coverage for every
administrative mutation, pagination/enumeration safety, idempotency and
concurrency — **without** a parallel RBAC system, a new policy engine, a new ORM,
a new identity provider, a new dependency, or a hidden administrator bypass.

Stage A enumerated eight risks (R1–R8) and Stage B resolved them into five
containment rules (E1, E2, E4, E5 shipped; E3 was dropped — §6 of the Stage C
doc) plus one additive migration (M1).

---

## 2. Delivered surface (measured against the built artifact)

Counted from the regenerated `openapi.json` and the router in this working tree:

* **15 paths / 21 operations** under `/api/v1/auth`.
* **20 of 21 operations** declare `401` and `403` in the served document; the one
  exception is `GET /auth/me`, which is not an administrative mutation and
  documents its anonymous-mode outcome in its `summary` instead (finding
  **P6**, §6).
* **4 operations** declare `409` (`POST /auth/users`, `PATCH
  /auth/users/{id}/status`, `DELETE /auth/users/{id}/roles/{assignment_id}`,
  `POST /auth/clients`) — the conflict cases the guards actually produce.
* **7 distinct audit event kinds** emitted by the plane: `ORGANIZATION_UPDATED`,
  `ORGANIZATIONAL_UNIT_UPDATED`, `USER_STATUS_CHANGED`, `PROJECT_SCOPE_CHANGED`,
  `PROJECT_OWNERSHIP_CHANGED`, plus the extended `ROLE_ASSIGNED` / `ROLE_REVOKED`.
* **1 migration**: `o5p6q7r8s025` (`ck_assignment_scope_matrix`), linear on
  `n4o5p6q7r022`, single Alembic head, 20 revisions total
  (`alembic heads` → `o5p6q7r8s025 (head)`).
* **1 new targeted test module** — `tests/integration/test_be025_admin_control_plane.py`,
  16 tests, covering permitted **and** denied directions.

Files changed (whole milestone): `backend/services/authorization.py`,
`backend/api/v1/endpoints/auth.py`, `backend/schemas/authorization.py`,
`backend/db/models.py`, `alembic/versions/o5p6q7r8s025_be025_assignment_scope_check.py`,
`tests/unit/test_migrations.py`, `tests/integration/test_be025_admin_control_plane.py`,
`openapi.json` (tracked artifact), plus these six documents. `backend/services/audit_ledger.py`
and the BE-023 audit guard were not modified.

---

## 3. Gate history

| Gate | Primary evidence | Outcome |
|---|---|---|
| A | Gap list (8 capabilities verified absent), risk register R1–R8, migration assessment (M1 yes / M2 no) | design input, no code touched |
| B | Reuse map, containment rules E1–E5, invariant enforcement matrix, error contract, test plan | approved design; deliberately no parallel systems |
| C | Targeted suite 15 passed (22.85s); `test_authorization.py` 17 passed (28.21s); `alembic current` → head | 3 production defects found **by execution** and fixed (DF-C-01…03) |
| D | Targeted 16 passed; live probe **149 / 149** checks; `§12` migrations on two scratch DBs; chain `valid=True` over 12,121 events | 3 further defects fixed (DF-D-01…03); 5 preserved findings (R4, P1–P4) + P5 |
| E | §14 regression re-run; live hardening probe **162 / 162** checks; real container outages; injected audit-store failure; chain `valid=True` over 14,400 events | 1 production defect fixed (F-SE-01); 7 preserved findings |
| F | §18 full matrix (this report, §8) | see §12 |

---

## 4. Production defect register — FOUND → FIXED → VERIFIED

History is preserved, not rewritten. Each row states the runtime symptom, the
fix, and the measurement that verified it.

### DF-C-01 — new audit event types were not registered (Stage C)

* **FOUND:** `PATCH /auth/organizations/{id}` → `422 "Unknown audit event type:
  'ORGANIZATION_UPDATED'"`; all five new event types were rejected by the ledger.
* **FIXED:** the five types were added to `AUDIT_EVENT_TYPES`.
* **VERIFIED:** organization/unit/user/scope/ownership audits append; chain
  verification passes in every later gate (D: 12,121 events; E: 14,400; F: §8).

### DF-C-02 — project re-binding skipped the unit↔organization integrity check (Stage C)

* **FOUND:** changing only a project's organization returned `200` while leaving
  the project inside a unit belonging to a **foreign** organization; `422` was
  correct.
* **FIXED:** the integrity check runs whenever a unit ends up set; the
  destination-authority check stays conditional.
* **VERIFIED:** mismatch → deterministic `422`; Stage D probe section J (9
  checks) proves cross-org move needs both scopes and leaves no dangling
  projects; Stage E E5 re-verifies under 6-way contention (torn write impossible).

### DF-C-03 — last-administrator guard ignored deactivation semantics (Stage C)

* **FOUND:** suspending/disabling a lone GLOBAL administrator who held several
  grants was allowed: `removes_user` was not modelled, so the guard subtracted 0
  instead of every grant that user holds.
* **FIXED:** `_would_leave_no_global_administrator(..., removes_user=True)` used
  by `set_user_status`.
* **VERIFIED:** self-disable of the last administrator → `409` with **no** audit
  event; bystander suspension → `200`. Stage E E6 and E12 re-measured it
  (20 simultaneous `DISABLED` attempts on the last administrator: **all 409,
  audit delta 0**).

### DF-D-01 — administrative routes documented no authorization outcomes (Stage D)

* **FOUND:** in the served document the BE-025 `responses` maps contained only
  `200/201/204/422`, so `401/403/404/409` were invisible to API consumers.
* **FIXED:** every administrative operation declares exactly the statuses it can
  return, through one shared `_ERROR_RESPONSES` table (422 left to FastAPI).
* **VERIFIED:** Stage D probe section H (15 checks) and
  `test_openapi_documents_the_administrative_surface`; re-measured in this report
  against the built artifact (20 of 21 operations declare 401/403, §2).

### DF-D-02 — read and update on the same resource used two authority models (Stage D)

* **FOUND:** `GET /auth/organizations/{id}` was guarded by `require_global`, so an
  organization-scoped administrator received **403 on its own organization**,
  while `PATCH` on the same resource is scope-aware and answers `404` for foreign
  ones.
* **FIXED:** the read uses the identical guard as the update
  (`require("organization.manage", "organization", "organization_id")`).
* **VERIFIED:** runtime own 200 / foreign 404 / unknown 404 (probe B, 8 checks;
  Stage E E7 re-measured under 10-way concurrency: uniform 404, foreign row
  untouched). No caller gained authority over anything it could not already act
  on, and foreign-organization 403 → 404 **removes** an existence oracle.

### DF-D-03 — the committed OpenAPI snapshot was stale (Stage D)

* **FOUND:** `openapi.json` (last regenerated at `41174a4e`, BE-024) described the
  pre-BE-025 surface: no `/auth/units/{id}`, no project scope/ownership, no user
  status, none of the BE-025 response models.
* **FIXED:** regenerated from the live application — 4 paths added, 10 schemas
  added, **0 removed**, +1118/−119 lines.
* **VERIFIED:** Stage F §8 reads the artifact back: 15 paths / 21 operations with
  the BE-025 surface and status declarations present.

### F-SE-01 — audited administrative mutations read their target without a lock (Stage E)

* **FOUND:** contention bursts produced ledger rows that misdescribed reality — 6
  false `before=ACTIVE` deltas, 4 redundant `PROJECT_SCOPE_CHANGED` events for
  requests that changed nothing, and 4 × `204` with 4 phantom `ROLE_REVOKED` rows
  for a single live assignment.
* **FIXED:** `_lock_row()` — every audited mutation now reads its target under
  `with_for_update()`, matching the repository convention already used by
  `repositories/{governance,publication,dispute,correction,fusion}.py` and
  `services/retention.py`. Six call sites: `revoke_assignment`,
  `update_organization`, `update_unit`, `set_user_status`, `change_project_scope`,
  `change_project_owner`.
* **VERIFIED (same bursts, post-fix):** scope burst `events=7 accepted=8
  chained=True self_transitions=0`; identical-scope burst `events=1`; 8-way
  duplicate assignment → one row; revoke race `[204,404,404,404]` with exactly one
  `ROLE_REVOKED`; mutual last-administrator race `[204,409]` with `remaining=1`.

---

### DF-F-01 — the targeted suite destroyed the shared test database's administrator baseline (Stage F)

Classification: **shipped test defect** (production behavior was correct — the
guard refused exactly as specified).

* **FOUND:** the Stage F isolation snapshot compared `pofa_test` before and after
  the full suite: `user_role_assignments` went **71 → 5** and GLOBAL-scope
  assignments from 67 → 1. `test_last_global_administrator_guard` hard-deleted
  *every* GLOBAL assignment to make its count deterministic (lines 415-420) and
  its "restore" loop was a literal `pass` (lines 458-462), with a comment claiming
  the parked rows "belonged to users cleaned by their own tests" — false for
  pre-existing rows. Every run of the suite therefore permanently stripped
  administrator authority from `pofa_test` for any later run.
* **FIXED:** the test now snapshots the parked rows in full (`id`, `user_id`,
  `role_id`, `scope_type`, the three scope identifiers, `created_at`), deletes
  them for determinism, and in its `finally` re-inserts each row verbatim with
  `INSERT … ON CONFLICT (id) DO NOTHING` after cleaning up the two administrators
  it created. A new in-test assertion — `remaining == len(parked)` — makes the
  suite itself prove the restore contract instead of trusting it.
* **VERIFIED:** deterministic control with a non-trivial baseline — 3 throwaway
  GLOBAL assignments planted (`planted GLOBAL assignments: [3 ids]`), baseline
  measured at 4, guard test run (`1 passed in 7.97s`), then
  `verify: control rows still present = 3/3, GLOBAL assignments now = 4` →
  **RESTORE CONTROL: PASS**, control rows removed afterwards (0 remaining).
  The full-matrix baseline snapshots in §9 confirm the counts are stable across
  repeated runs.

### DF-F-02 — a targeted test leaked its created GLOBAL administrator (Stage F)

Classification: **shipped test defect** (cleanup hygiene).

* **FOUND:** `test_admin_audit_chain_remains_valid` calls `global_admin()` (which
  creates a `be025-admin-*` user plus a GLOBAL assignment) and never cleaned it
  up, so each run added one permanent GLOBAL administrator to `pofa_test`. This
  is why 9 `be025-admin-*` users were present at the Stage F baseline.
* **FIXED:** the assertions were wrapped in `try/finally` with
  `cleanup(user_ids=[str(admin.id)])`; the assertions themselves are unchanged.
* **VERIFIED:** repeated targeted runs leave
  `be025-last*/be025-bystander residue: 0` and a stable GLOBAL count (§9 baseline
  log). The 9 pre-existing `be025-admin-*` users were **not** deleted: they are
  referenced as `actor_id` values in the append-only ledger, so removing them
  would orphan audit history — recorded as preserved finding **P14**.

---

## 5. Test-side and harness defects (no production behavior involved)

Recorded because the task requires the history, and because each fix replaced a
weak expectation with an equal-or-stronger invariant rather than deleting it.

**Stage C (targeted suite):** raw SQL not wrapped in `text()`; `cleanup()`
deleting users before referencing projects/assignments (`ForeignKeyViolation`);
detached ORM rows returned by the `assign()` helper; wrong client registration
path; a missing-scope assertion aimed at a nonexistent user (user existence
legitimately precedes payload validation → `404`); one assertion expecting an
organization-bound `ADMINISTRATOR` to read project content.

**Stage D (probe):** the concurrency helper passed an ORM `User` where a user-id
string was required (both threads → `422`); the audit-target map kept the *oldest*
row of a descending query, attributing `ORGANIZATION_UPDATED` to the wrong
organization; a destructive last-administrator section wiped every GLOBAL
assignment mid-run and stripped the authority later sections needed; teardown
deleted projects before the `api_clients` referencing them (FK `RESTRICT`),
silently aborting cleanup and stranding 48 probe users in `pofa_test` — removed in
FK-safe order and re-verified at 0.

**Stage E (harness, runs 3–10):** killed uvicorn by mistake (run 3, aborted);
`UnicodeEncodeError` on a cp1252 console (run 4, fixed with
`sys.stdout.reconfigure`); `code()` returning −1 for every `httpx.Response` so all
eight bursts looked like transport failures (run 5); `UUID`-vs-`str` comparison
making a correct single-scope result look torn, a `/me` assertion against a
`username` field `PrincipalResponse` does not have, an absolute lifetime event
count on a shared organization, and the E8 subject created inside the injected
fault window (run 6, 4 failures); `MSYS_NO_PATHCONV` breaking path conversion so
the run never started (run 7); probing `/health/ready` when the route is `/ready`,
demanding `5xx` where `401` fail-closed is correct, and a latency assertion that
checked only timing so a `401` storm "passed" (run 8, 6 failures); a 128-char
boundary code outside the teardown filter, so the next run legitimately received
`422 duplicate code` (run 9, 1 failure). Run 10: **162 / 162**.

**Stage F (verification harnesses):** the read-only chain track queried
`audit_ledger_events.previous_event_hash`, which does not exist (the column is
`previous_hash`), and aborted before printing the chain verdict; the from-scratch
migration probe then crashed with `'NoneType' object is not subscriptable` because
a brand-new database has **no role catalogue** (roles are seeded by the
application, not by the migration chain) — it now calls
`ensure_default_catalogue` on the scratch target before probing the constraint;
the new parked-row snapshot used `dict(row)` on a SQLAlchemy 2.0 `Row`, which
raised `cannot convert dictionary update sequence element #0 to a sequence`
(fixed with `.mappings().all()`); and the first preflight invocation resolved to
`pofa_dev` because `DATABASE_URL` was not pinned (see incident 3 below — that
preflight is read-only by construction, so nothing was written). Each was a
harness bug: no assertion was relaxed to obtain it.

**Environment incidents disclosed, not papered over:**

1. Stage C — one manual maintenance command exported `TEST_DATABASE_URL` while
   `alembic` and ad-hoc scripts build their engine from `DATABASE_URL`, so it
   resolved to `pofa_dev` and its cleanup `DELETE` removed one `be025`-prefixed
   leftover user there. Verified blast radius: full seed intact (1094 users), audit
   ledger untouched (6016 events). Every later manual command set `DATABASE_URL`
   explicitly.
2. Stage E — the host had been suspended ~17 h, so the Docker daemon was absent
   (`connection refused`, `containers up after restoration: []`). Docker Desktop
   was started, containers auto-restarted, and the revision/ledger/residue/GLOBAL
   state was verified **before** resuming. Classified environment, not code.
3. Stage F — the first preflight invocation repeated incident (1) in the same way
   (`TEST_DATABASE_URL` exported, `DATABASE_URL` unset → resolved to `pofa_dev`).
   It is **read-only by construction** (SELECTs plus a Redis PING and
   `list_buckets`), so nothing was written; it was re-run with `DATABASE_URL`
   pinned to `pofa_test` and the Stage F launcher now sets it per track (§9).
4. Stage F — Docker Desktop restarted the infrastructure inside the verification
   window: `pofa_db` and `pofa_redis` at 11:13 UTC (before the matrix began) and
   `pofa_minio` at **11:45:25 UTC**, i.e. while attempt 1's full integration track
   was finishing (`RestartCount = 0` on all three, which means an external
   start/restart rather than an in-place daemon restart). MinIO live health was
   verified at `HTTP 200` afterwards, but because one accepted result could have
   overlapped a storage restart, the **entire matrix was re-run as attempt 2**
   against a stable engine (§8), and only attempt-2 numbers are quoted as
   Stage F evidence.

---

## 6. Preserved findings — deliberately **not** "fixed" in BE-025

None is a security failure; each is outside the milestone's remit, and fixing it
would either widen a frozen grant, change BE-016/BE-024 semantics, or rewrite an
append-only ledger.

| ID | Finding | Why preserved |
|---|---|---|
| R4 | `project.update` is granted to no seeded role, so domain rename stays unreachable for every role | Carried from BE-024 per the standing instruction; BE-025 does not widen a seeded catalogue. |
| P1 | `GET /auth/roles` and `/auth/permissions` require the permission at **GLOBAL** scope, so an org-scoped administrator cannot enumerate the catalogue | Neither entity is organization-scoped, so scope-aware enforcement has no resource to resolve; BE-016 behavior. The delegation path admins actually need is scope-aware and verified. |
| P2 | The served document declares no `securitySchemes`/`HTTPBearer`; authentication is expressed per operation | Application-wide, inherited from BE-016, touches every router. DF-D-01 covers the BE-025-scoped part. |
| P3 | Organization/unit deactivation is lifecycle-only: no DELETE route, `RESTRICT` FKs, no cascade | This **is** the required semantics — silent orphaning is impossible at the schema level; the last-admin guard covers lockout. |
| P4 | `AUTH_MODE=development` allows an anonymous bypass and accepts dev bearer tokens | Documented BE-016 contract, warned on every request, and verified to disappear in enforcing mode (probe G; Stage E E7). Not a hidden admin bypass. |
| P5 | `pofa_dev`'s ledger has seven historical sequence gaps (6016 rows below max 6052), so `verify_chain` is `valid=False` **on that database only** | Pre-existing dev condition; origin documented in-repo at `tests/audit_guard.py:5-9` (cleanups from before the BE-023 guard). Repair would require writing audit rows — an append-only violation. `pofa_test` verifies `valid=True`. |
| P6 | `GET /auth/me` declares only `200` in `responses`; its anonymous-`401` behavior lives in the operation `summary` | Not an administrative mutation, so it was outside DF-D-01's 19-operation scope. Runtime behavior verified: anonymous → `401` in enforcing mode (Stage E E7). |
| P7 | Duplicate organization/unit `code` → `422`, not `409` | Deterministic, documented, and shipped in `openapi.json`; changing the status would alter a published contract. |
| P8 | No application-wide request-body size cap; a 2 MB JSON body is accepted (0.14 s, one row) | Pydantic drops undeclared fields, so the real risk is schema widening — measured absent. A platform-wide limit is not a BE-025 decision. |
| P9 | A PostgreSQL outage surfaces as `401` ("Invalid credentials"), not `503` | Principal resolution reads the user row. Fail-closed, never a false success; distinguishing `503` would change BE-016 authentication semantics. |
| P10 | Pre-existing logging defect: `ValueError: Formatting field not found in record: 'request_id'` on audited writes | `BE-001` lineage, unrelated to BE-025; no data loss and no behavior change. |
| P11 | Starlette deprecation warning for `HTTP_422_UNPROCESSABLE_ENTITY` (`backend/security/authorization.py:84`) | Emitted by pre-existing code; warning-only. |
| P12 | Full read-only `verify_chain()` costs ~3.9 s over ~14.4 k events | Operator path, not a request path. |
| P13 | 9 `org-*` organizations from the Stage D probe remain in `pofa_test` (created 2026-09-28) | They predate Stages E/F and only shift list totals, which every later run reads dynamically. |
| P14 | 9 `be025-admin-*` users (plus 1 surviving GLOBAL assignment) remain in `pofa_test` as test debris from Stages C–E | Their ids appear as `actor_id` values in the append-only ledger; deleting the users would orphan those audit references, which the append-only rule forbids repairing by construction. **DF-F-02's fix stops the accumulation** — each further run leaves the population it found. |
| P15 | `tests/integration/test_publication.py:81` (BE-024-era) creates `be022-<uuid>` users holding `GLOBAL` `ADMINISTRATOR` assignments and never cleans them up, so every full integration run adds ~66 GLOBAL administrators to `pofa_test` | Measured at Stage F: GLOBAL count went 1 → 67 across the run, every new row created by that suite between 12:03:49 and 12:04:23. It is **another milestone's test file**; BE-025 must not modify it or broaden scope. It is, however, precisely the population that **DF-F-01** was silently deleting on every run — which is why the restore contract now belongs to the BE-025 suite. |

---

## 7. Stage A risk register → control → verifying evidence

| Risk | Control implemented | Where proven |
|---|---|---|
| R1 — GLOBAL-only admin gate is coarse; relaxation must not leak existence | `require(action, "organization", "organization_id")`; foreign ≡ absent (`404`) | Stage D probe B (8 checks); Stage E E7 (10-way concurrency, uniform 404, foreign row byte-identical) |
| R2 — privilege-escalation surface once scoped admins can manage assignments | E1 (GLOBAL target or any `ADMINISTRATOR` grant needs GLOBAL `role.manage`), E2 (the actor's `role.manage` must cover the target) | Stage D probe C (13 checks); Stage E E7 self-promotion 403, ADMINISTRATOR grant 403, foreign-org grant 404; targeted `test_privilege_escalation_attempts_denied` |
| R3 — destructive self-lockout | `pg_advisory_xact_lock(0x504F413235)` count-and-act guard → `409`, and refusals append **no** audit row | Stage D probe K (7 checks); Stage E E6 (mutual race `[204,409]`, `remaining=1`, one `ROLE_REVOKED`) and E12 (20 × `DISABLED` → all `409`, audit delta 0) |
| R4 — `project.update` granted to no seeded role | Preserved, documented; admin project mutation goes through `organization.manage` on the administrative routes instead | §6 P-registry; Stage C §10 |
| R5 — no DB constraint tying scope ids to `scope_type` | M1 `ck_assignment_scope_matrix` | Stage D §12; targeted `test_scope_matrix_check_constraint_enforced_by_database`; Stage F §8 (from-scratch build, downgrade/re-upgrade, malformed pre-existing row refused) |
| R6 — organization deletion impossible by design | Status lifecycle only; `RESTRICT` FKs | §6 P3; Stage E E5/E11 (deactivate/reactivate, no orphan) |
| R7 — IDOR / enumeration | Typed UUID paths, `reject_malformed_resource_id`, uniform 404, authorization filtered **before** `total` | Stage D probe I (13 checks); Stage E E1 (143 malformed-id probes, no 5xx, no success), E4 (no count oracle) |
| R8 — audit chain and append-only ledger must stay intact | Existing `_audit_admin`/`append_event` path, advisory append lock, same-transaction commit, BE-023 guard untouched | Stage D §8; Stage E E8 (injected audit-store failure → domain change rolled back, ledger unchanged), E9, E-final; Stage F §8 chain verification after the full matrix |

---

## 8. Stage F — §18 full verification matrix, as executed

Nine required tracks plus two added integrity checks. All ran against
`pofa_test` (`DATABASE_URL`/`TEST_DATABASE_URL` pinned per track), `-p no:randomly`,
on the final code in this working tree.

The first pass of the matrix (attempt 1, 11:37–11:48 UTC) completed every track
green, but was **discarded as the acceptance evidence**: `pofa_minio` restarted at
11:45:25 UTC while its full integration track was finishing (§5 incident 4), and
its isolation comparison exposed DF-F-01 (assignments 71 → 5). Attempt 2 below was
run **after** the DF-F-01/DF-F-02 fixes, on a stable engine, and is the accepted
record.

| # | §18 track | Command scope | Measured result |
|---|---|---|---|
| 1 | Environment preflight (BE-023) | `tests/preflight.py` primitives + raw probe | `pofa_test`, Postgres **15.13**, PostGIS **3.4.2**, pgvector **0.7.4**, revision `o5p6q7r8s025`, `ck_assignment_scope_matrix` = 1, BE-025 tables = 4, Redis PING `True`, buckets `['pofa-evidence','pofa-quarantine']`; `ML AVAILABLE: all of torch, transformers, ultralytics importable`; `require(): all required dependencies AVAILABLE` |
| 2a | BE-025 targeted suite | `tests/integration/test_be025_admin_control_plane.py` | **16 passed**, 7 warnings, 36.05 s |
| 2b | Same suite, repeated (stability) | identical command | **16 passed**, 7 warnings, 36.85 s — baseline counts identical before/after both runs (§9) |
| 3 | Full unit suite | `tests/unit` | **348 passed, 1 skipped**, 6 warnings, 20.41 s |
| 4 | Full integration suite (all affected suites included) | `tests/integration` | **216 passed**, 8 warnings, 362.88 s (6:02) — **0 failures, 0 skips** |
| 5 | Authorization regression | the 8 explicit §14 files (`test_authorization` unit+integration, `test_be025_admin_control_plane`, `test_audit_ledger` unit+integration, `test_audit_guard`, `test_preflight`, `test_migrations`) | **121 passed, 1 skipped**, 7 warnings, 91.54 s |
| 6 | BE-023 verification-hardening suite | `-m be023` | **60 passed, 1 skipped, 504 deselected**, 20.28 s |
| 7 | Audit-chain verification | read-only `verify_chain()` + independent SQL cross-checks | **PASS** — `rows=16380 min=1 max=16380 distinct=16380 contiguous=True`, `sequence gaps: 0`, `duplicate sequences: 0`, `hash chain breaks (stored prev-hash mismatch): 0`, `chain valid: True checked: 16380 first: 1 last: 16380 failures: []`, `scope matrix violations: 0`, residue orgs/units/users/projects/clients = `0 0 0 0 0` |
| 7b | Schema-drift check (added) | ORM `Base.metadata` vs migrated `pofa_test` | **NO DRIFT** — `tables declared in models but absent in DB: none`, `tables in DB not declared by models: none`, `column drift: none`; constraints present: `uq_organizations_code`+`ck_organization_status`, `uq_org_unit_code`+`ck_org_unit_status`, `uq_user_role_scoped`+`ck_assignment_scope`+`ck_assignment_scope_matrix`, `uq_audit_ledger_sequence` |
| 8 | Migration verification + from-scratch migration | 20-revision chain on scratch DB `pofa_stageF_mig` | from-scratch `upgrade head` → version `o5p6q7r8s025`, **71 tables**, matrix CHECK = 1, postgis+vector installed; `downgrade -1` → `n4o5p6q7r022`, CHECK = 0; `upgrade head` → CHECK = 1; live probe on the migrated schema: **`invalid matrix row rejected by PostgreSQL -> violates check constraint "ck_assignment_scope_matrix"`**; scratch DB dropped |
| 9 | Existing-database upgrade with pre-existing rows | scratch DB `pofa_stageF_mig2` | built at `n4o5p6q7r022`, planted 3 assignments (1 deliberately malformed): `upgrade head` → **returncode 1, CHECK still 0** — "upgrade correctly refused the malformed pre-existing row"; after removing it → returncode 0, CHECK 1; valid rows survive (2) and the upgraded database rejects malformed inserts; scratch DB dropped |

**DF-F-01 restore control (deterministic, run against the final suite):** planted 3
throwaway GLOBAL administrator assignments → baseline measured at 4 → guard test
`1 passed in 7.97 s` → `control rows still present = 3/3, GLOBAL assignments now =
4` → **RESTORE CONTROL: PASS**, control rows removed (0 remaining).

**Skips and warnings, classified:** the two skips are the same pre-existing
BE-023 condition — `tests/unit/test_preflight.py:117` skips when the ML stack is
genuinely installed (`ML AVAILABLE`), i.e. it reports an environment fact rather
than laundering a failure. No test was added, removed, marked `xfail`, or edited to
reach these counts, and no dependency was simulated: Postgres, Redis, MinIO and the
ML stack were live and probed (§8 track 1). The 6–8 warnings per track are the
documented pre-existing deprecations (P10, P11) plus FastAPI `on_event`
deprecation from `backend/app/main.py`, none introduced by BE-025.

---

## 9. Baseline, isolation and side-effect evidence (Stage F)

Administrator-baseline snapshots, taken read-only around the suite tracks:

```
BEFORE targeted run 1   GLOBAL=1   total=5   users=1419  residue(last*/bystander)=0  ledger rows/max=15365/15365
AFTER  targeted run 1   GLOBAL=1   total=5   users=1419  residue(last*/bystander)=0  ledger rows/max=15427/15427
AFTER  targeted run 2   GLOBAL=1   total=5   users=1419  residue(last*/bystander)=0  ledger rows/max=15489/15489
AFTER  full integration GLOBAL=67  total=71  users=1489  residue(last*/bystander)=0  ledger rows/max=16243/16243
```

Read literally: the BE-025 targeted suite is now **baseline-neutral** — two full
runs leave the GLOBAL population exactly as they found it (before DF-F-01 it
deleted every row it parked). The 67 GLOBAL administrators present afterwards were
created by the pre-existing BE-024 publication suite during the integration run
(P15), and the guard test parked and restored them inside that run. `ledger
rows == max sequence` at every snapshot, so the matrix's 1,015 new events
(15,365 → 16,380) appended contiguously with no gap and no deletion.

Isolation, from the launcher's before/after snapshots:

```
pofa_dev  | rev=n4o5p6q7r022 | maxSeq=6052 | users=1094 projects=584 assignments=872 ledger=6016 | stageE/F rows=0   (BEFORE)
pofa_dev  | rev=n4o5p6q7r022 | maxSeq=6052 | users=1094 projects=584 assignments=872 ledger=6016 | stageE/F rows=0   (AFTER)
```

`pofa_dev` is byte-for-byte identical across the whole Stage F matrix — same
revision, same row counts, same max sequence: no BE-025 migration, write or test
touched it. `pofa_test` carries only legitimate growth (users 1419 → 1489 and
ledger 15,365 → 16,380 from suites that create principals and audit real
mutations) and `scratch_rows=0` for the `STGF*`/`stageF*` patterns.

Databases before and after the migration tracks: `['pofa_audit_verify', 'pofa_dev',
'pofa_test']` — `pofa_audit_verify` is pre-existing (from BE-023 verification, not
created by this milestone) and the two Stage F scratch databases
(`pofa_stageF_mig`, `pofa_stageF_mig2`) were created, used and dropped, leaving no
trace. Containers at postflight: `pofa_db Up 53 minutes`, `pofa_redis Up 54
minutes`, `pofa_minio` restarted at 12:05:28 UTC and verified healthy afterwards
(`live` endpoint `HTTP 200`, `list_buckets succeeded`).

Nothing in the Stage F harness entered the repository: the launchers, probes,
baseline/drift/control scripts live in `%TEMP%\poa_stageF`, and `git status` at
§12 confirms the working tree contains only BE-025's own files.

---

## 10. §18 expected final state — verdict per requirement

| Required final state | Verdict | Measurement |
|---|---|---|
| Zero unexplained failures | **MET** | 16 + 16 + 348 + 216 + 121 + 60 passed, 0 failed across tracks 2a–6; the two skips are one documented BE-023 ML-installed condition; the only defects found at this gate (DF-F-01, DF-F-02, four harness bugs, one container restart) are each classified and explained in §4, §5 |
| Zero hidden environment fallback | **MET** | `PoA test database source: TEST_DATABASE_URL`, `pofa_test` printed by every track; `require(): all required dependencies AVAILABLE`; conftest refuses to run without the test URL; the one invocation that resolved to `pofa_dev` was read-only and is disclosed (§5 incident 3) |
| No unauthorized access | **MET** | Stage D probe A/A2/C/G and Stage E E7 (55 admin-route attempts across five non-admin principals: zero successes, 403/404/401 only; GLOBAL grants and `ADMINISTRATOR` minting refused; foreign organizations indistinguishable from absent) — re-run green here as tracks 4/5 |
| No audit-chain corruption | **MET** | Track 7: `rows=16380 min=1 max=16380 distinct=16380`, gaps 0, duplicate sequences 0, stored prev-hash mismatches 0, `verify_chain` `valid=True failures=[]`. No DELETE/TRUNCATE/UPDATE was issued against `audit_ledger_events` at any stage; the BE-023 guard suite passes (tracks 3/5) |
| No migration drift | **MET** | Single head (`alembic heads` → `o5p6q7r8s025`), linear 20-revision chain enforced by `tests/unit/test_migrations.py`; from-scratch build, `downgrade -1` and re-`upgrade head` all correct on scratch databases; ORM-vs-database comparison: **NO DRIFT** (track 7b) |
| No fake AI behavior | **MET** | `ML AVAILABLE: all of torch, transformers, ultralytics importable` — the vision/embedding suites really executed (216 integration passes include CLIP/YOLO paths); no `Mock` stands in for a model or a dependency, and no ML test skipped itself silently (the single skip states the environment fact) |
| No regression to previous milestones | **MET** | Every pre-existing suite passed unmodified: BE-016 authorization, BE-015 audit ledger, BE-023 guard/preflight/migrations, BE-007 contracts, BE-008 temporal, BE-011 fusion, BE-012 explainability, BE-013 review cases, BE-014 evidence requests, BE-017 retention, BE-019 clients, BE-021 governance, BE-022/BE-024 publication. `pofa_dev` unchanged; BE-023 §14 regression: 121 passed |

---

## 11. Commands (verbatim, reproducible)

```bash
REPO=/d/CODING/Projects/Proof-Of-Action-Final
PY=$REPO/backend/.venv312_clean/Scripts/python.exe        # Python 3.12.0
export TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test
export PYTHONPATH=$REPO
T="$TEMP/poa_stageF"     # harness directory, outside the repository

# track 1 — environment + BE-023 dependency report (DATABASE_URL pinned per run)
DATABASE_URL=$TEST_DATABASE_URL "$PY" -u "$T/preflight.py"
DATABASE_URL=$TEST_DATABASE_URL "$PY" -u "$T/preflight_report.py"

# tracks 2a/2b — targeted suite, twice, with read-only baseline snapshots between
DATABASE_URL=$TEST_DATABASE_URL "$PY" -u "$T/baseline.py"
"$PY" -m pytest tests/integration/test_be025_admin_control_plane.py -q -p no:randomly
"$PY" -m pytest tests/integration/test_be025_admin_control_plane.py -q -p no:randomly

# tracks 3-6 — full unit, full integration, authorization regression, BE-023 marker
"$PY" -m pytest tests/unit -q -p no:randomly
"$PY" -m pytest tests/integration -q -p no:randomly
"$PY" -m pytest tests/unit/test_authorization.py tests/integration/test_authorization.py \
  tests/integration/test_be025_admin_control_plane.py tests/unit/test_audit_ledger.py \
  tests/integration/test_audit_ledger.py tests/unit/test_audit_guard.py \
  tests/unit/test_preflight.py tests/unit/test_migrations.py -q -p no:randomly
"$PY" -m pytest -m be023 -q -p no:randomly

# tracks 7/7b — read-only chain and schema-drift verification
DATABASE_URL=$TEST_DATABASE_URL "$PY" -u "$T/chain_verify.py"
DATABASE_URL=$TEST_DATABASE_URL "$PY" -u "$T/drift_check.py"

# tracks 8/9 — migration verification, from-scratch and existing-database upgrade
"$PY" -u "$T/migrations_f.py"          # scratch db pofa_stageF_mig,  dropped at exit
"$PY" -u "$T/migrations_existing_f.py" # scratch db pofa_stageF_mig2, dropped at exit

# DF-F-01 deterministic control
DATABASE_URL=$TEST_DATABASE_URL "$PY" -u "$T/seed_control.py" plant
"$PY" -m pytest tests/integration/test_be025_admin_control_plane.py -q -p no:randomly \
  -k test_last_global_administrator_guard
DATABASE_URL=$TEST_DATABASE_URL "$PY" -u "$T/seed_control.py" verify

# single-flight launcher used for the accepted run (isolation snapshots around it)
nohup bash "$T/run_f_all2.sh" > "$T/run_f_all2.out" 2>&1 & disown
```

---

## 12. Acceptance decision

**BE-025 is accepted at Stage F. Gate: PASS.**

* Every §18 track ran against live PostgreSQL/Redis/MinIO with real principals and
  real ML; all counts are in §8, none are substitutes.
* Zero failures across 16 + 16 + 348 + 216 + 121 + 60 tests; the only skips are the
  documented BE-023 ML-installed condition; the only warnings are pre-existing
  deprecations (P10, P11).
* The audit ledger remains append-only and provably intact after the whole matrix —
  `valid=True`, 16,380 contiguous events, `rows == max sequence`, zero stored-hash
  mismatches, zero scope-matrix violations.
* No migration drift: one head, linear 20-revision chain, reversible M1, and an
  existing populated database refuses the malformed shape M1 forbids.
* Pre-commit artifact check (this gate): the tracked `openapi.json` is
  structurally identical to the live `app.openapi()` (144 paths, 21 `/api/v1/auth`
  operations) — the file being committed is the schema the server actually serves.
* No hidden administrator bypass, no weakened permission, no parallel RBAC/identity
  /policy system, no new dependency, no frontend expansion.

**What changed at this gate:** `tests/integration/test_be025_admin_control_plane.py`
only — the DF-F-01 snapshot/restore contract plus its new `remaining == len(parked)`
assertion, and DF-F-02's leaked-administrator cleanup. **No production file was
modified at Stage F**: the last production change was `_lock_row` and its six call
sites in `backend/services/authorization.py` at Stage E (F-SE-01). No shipped
assertion was relaxed; the two fixes strictly add obligations.

**Proposed commit (§20 git safety, pending your approval — nothing has been
committed or pushed):**

```
BE-025: implement organization and administrative control plane
```

Explicitly staged, file by file — never `git add .`/`-A`:

| Path | Status |
|---|---|
| `backend/api/v1/endpoints/auth.py` | modified |
| `backend/db/models.py` | modified |
| `backend/schemas/authorization.py` | modified |
| `backend/services/authorization.py` | modified |
| `openapi.json` | modified (tracked artifact, DF-D-03) |
| `tests/unit/test_migrations.py` | modified (head + revision count) |
| `tests/integration/test_be025_admin_control_plane.py` | new |
| `alembic/versions/o5p6q7r8s025_be025_assignment_scope_check.py` | new |
| `docs/BE-025 Stage A…E` + this report (6 files) | new |
| `docs/Production Task Files/BE-025 — …md` | new (task file) |

Deliberately **not** staged: `%TEMP%\poa_stageF` and `poa_stageE`/`poa_stageD`
harnesses, server logs, `__pycache__`, `backend/.venv312_clean`, and the
BE-024-era root scripts (`stage_d_runtime_checks.py`, `stage_e_runtime_checks.py`,
`test_vision_temporal_auth.py`), which Stage D left untouched. Verification already
performed: `git status --short` lists exactly the fifteen paths above (six
modified, nine new, nothing else), `git diff
--stat` shows +1968/−153 across the six modified files, every modified production
file was read line by line at Stages C/D/E, and no secret-bearing file is included.
On approval: commit on `Backend`, confirm with `git show --stat` and a final
`git status --short`, then push **only** `Backend` — no force-push, no rewrite of
the BE-024 history.

---
