# BE-025 Stage C — Implementation Summary

Gate: **Stage C implementation complete.** Targeted suite green on the isolated
test database; BE-016 authorization regression green. Stage D (runtime
verification) has **not** been started.

## 1. Scope implemented

BE-025 extends the BE-016 authorization plane with an administrative control
surface. No parallel RBAC, identity, policy-engine or ORM system was introduced;
every new guard reuses the existing `Principal` / `can()` / `_scope_covers()` /
`require()` / audit-ledger primitives.

The containment model from Stage B shipped as **E1, E2, E4, E5**. **E3
(role-contentment) was dropped** — see §6.

## 2. Files changed

| File | Change |
| --- | --- |
| `backend/services/authorization.py` | Containment helpers + admin mutations |
| `backend/api/v1/endpoints/auth.py` | New/relaxed admin endpoints |
| `backend/schemas/authorization.py` | BE-025 request/response models |
| `backend/db/models.py` | `ck_assignment_scope_matrix` CHECK + 5 audit event types |
| `alembic/versions/o5p6q7r8s025_be025_assignment_scope_check.py` | Migration M1 (new head) |
| `tests/integration/test_be025_admin_control_plane.py` | 15 targeted tests |

No other milestone's files were touched. BE-015 audit-chain logic
(`backend/services/audit_ledger.py`) was **not** modified.

## 3. Service layer

New helpers: `AdminOperationError`, `_deny_for()`, `_holds_global()`,
`_assignment_target_resource()`, `_lock_last_admin()`,
`_active_global_administrators()`, `_would_leave_no_global_administrator()`,
`visible_organization_ids()`, `list_visible_assignments()`, `UNSET`.

New admin operations: `update_organization`, `update_unit`, `set_user_status`,
`change_project_scope`, `change_project_owner`.

Extended operations: `assign_role` and `revoke_assignment` now accept an
optional `actor` and enforce E1/E2 when it is supplied.

Containment rules as implemented:

- **E1** — a `GLOBAL`-scope assignment target, and *any* `ADMINISTRATOR`
  assignment, requires `role.manage` held at `GLOBAL`; otherwise `403`.
- **E2** — `role.manage` must cover the target scope; a foreign target is
  refused as `404`, matching the BE-016 out-of-scope ≡ absent contract.
- **E4** — movement operations require authority over both the current and the
  destination scope; clearing a project's organizational binding requires
  `GLOBAL`.
- **E5** — revocation is guarded by coverage plus last-administrator protection.

`actor=None` remains the internal/system convention (seeding, in-process
callers, development-mode anonymous bypass). Enforcing-mode HTTP callers always
carry a real actor, so the containment checks are never skipped on the served
path.

### Last-GLOBAL-administrator guard

`pg_advisory_xact_lock(0x504F413235)` serialises the count-and-act window, then
the operation is refused with `409` if it would leave zero distinct active users
holding an `ACTIVE` `GLOBAL` `ADMINISTRATOR` assignment. Two removal shapes share
the helper but differ in semantics:

- revocation removes **one** assignment (`exclude_assignment_id`), so an admin
  holding a second `GLOBAL` grant may lawfully lose the first;
- deactivation (`SUSPENDED`/`DISABLED`) removes **every** grant the user holds
  (`removes_user=True`).

## 4. API surface

| Endpoint | Guard | Notes |
| --- | --- | --- |
| `GET /auth/organizations` | `organization.manage` (any scope) | filtered by `visible_organization_ids` |
| `PATCH /auth/organizations/{id}` | `require(organization.manage, organization, id)` | code immutable; no-op suppresses audit |
| `GET /auth/organizations/{id}/units` | `require(organization.manage, organization, id)` | paginated envelope |
| `GET`/`PATCH /auth/units/{id}` | `require(organization.manage, organizational_unit, id)` | org membership immutable |
| `GET /auth/users` | `require_global(user.manage)` | batched role map (no N+1) |
| `PATCH /auth/users/{id}/status` | `require_global(user.manage)` | `409` last-admin guard |
| `POST /auth/users/{id}/roles` | `require(role.manage)` (**was** GLOBAL-only) | `201` created / `200` duplicate |
| `GET /auth/users/{id}/roles` | `require(role.manage)` | per-assignment filtering, exposes `assignment_id` |
| `DELETE /auth/users/{id}/roles/{assignment_id}` | `require(role.manage)` | `204`; `409` last-admin guard |
| `PATCH /auth/projects/{id}/scope` | `require(organization.manage, project, id)` | set-or-clear via `model_fields_set` |
| `POST /auth/projects/{id}/ownership` | `require(organization.manage, project, id)` | owner must be `ACTIVE` |
| `GET /auth/roles`, `/auth/permissions` | `require_global(role.manage)` | bounded `limit`/`offset`, plain-array shape kept |

The previously GLOBAL-only `assign`/`revoke` guards were **relaxed to
scope-aware `require()`**, which is the capability BE-025 asked for; containment
(E1/E2) then re-narrows what a non-GLOBAL `role.manage` holder may actually
target. No existing permission was weakened to make a workflow pass.

Error contract is uniform: `AdminOperationError → its status`, `ValueError →
422`, `LookupError → 404`, `IntegrityError → 409/422`. Out-of-scope reads and
writes on foreign resources are indistinguishable from absent (`404`), never a
`403` oracle.

Audit events emitted (all newly registered): `ORGANIZATION_UPDATED`,
`ORGANIZATIONAL_UNIT_UPDATED`, `USER_STATUS_CHANGED`, `PROJECT_SCOPE_CHANGED`,
`PROJECT_OWNERSHIP_CHANGED`, alongside existing `ROLE_ASSIGNED`/`ROLE_REVOKED`.
Payloads carry before/after scope and identity only — no secrets. The ledger
stays append-only; no audit record is updated or deleted, and the BE-023
append-only guard is untouched.

## 5. Migration M1

`o5p6q7r8s025` (down_revision `n4o5p6q7r022`, new head) adds
`ck_assignment_scope_matrix` to `user_role_assignments`, enforcing the
`scope_type` ↔ identifier matrix at the database level. Already-applied
idempotency/concurrency behaviour comes from the pre-existing
`uq_user_role_scoped` unique index (`postgresql_nulls_not_distinct=True`), so
duplicate assignment resolves to `201`-created / `200`-duplicate and a concurrent
double-submit yields exactly one row.

Verified on the isolated test database: `alembic current` → `o5p6q7r8s025 (head)`.

## 6. Design refinement — E3 dropped

Stage B proposed E3 "role-contentment": an actor could only assign roles it
itself holds. Implemented and tested, it **rejected already-verified BE-016
behaviour** — a GLOBAL administrator delegating `REVIEWER`/`FIELD_OFFICER`
without holding those roles, exercised by
`test_role_assignment_audit_and_concurrency`. That is intentional delegation, not
a vulnerability: containment over the *scope* and over *ADMINISTRATOR/GLOBAL
targets* is what prevents escalation.

Per the task's instruction to preserve documented semantics rather than invent
new restrictions, E3 was dropped. E1 + E2 + "ADMINISTRATOR requires GLOBAL
`role.manage`" close the escalation paths the task enumerates. This is the one
deviation from the approved design and is recorded here so Stage D can verify it
deliberately rather than inherit it silently.

## 7. Defects found and fixed during Stage C

Discovered by executing the suite, not by reading code.

| ID | Classification | Symptom | Fix | Verified |
| --- | --- | --- | --- | --- |
| `DF-C-01` | **production** | `PATCH /auth/organizations/{id}` → `422 "Unknown audit event type: 'ORGANIZATION_UPDATED'"`; all five new event types rejected | registered the five types in `AUDIT_EVENT_TYPES` | org/unit/user/scope/ownership audits now append; chain verify passes |
| `DF-C-02` | **production** | rebinding only a project's organization skipped the unit↔organization integrity check, letting a project end up inside a foreign unit (`200` where `422` was correct) | integrity check now runs whenever a unit ends up set; destination-authority check stays conditional | mismatch case returns deterministic `422` |
| `DF-C-03` | **production** | deactivating a lone `GLOBAL` admin holding several grants was allowed: `removes_user` was not modelled, so the guard subtracted 0 instead of every grant | `_would_leave_no_global_administrator(..., removes_user=True)` used by `set_user_status` | self-disable of the last admin → `409`; bystander suspension still `200` |

Test-side defects fixed in the same pass (no production code involved): raw SQL
not wrapped in `text()`; `cleanup()` deleting users before the projects/
assignments that reference them (`ForeignKeyViolation`); detached ORM rows
returned from the `assign()` helper (`DetachedInstanceError`); wrong client
registration path (`/api/v1/clients` → `/api/v1/auth/clients`); a
missing-scope-id `422` assertion that targeted a random nonexistent user (user
existence legitimately precedes payload validation → `404`); and one assertion
that expected an organization-bound `ADMINISTRATOR` to read project content.

## 8. Test results (isolated `TEST_DATABASE_URL`, real HTTP via TestClient)

```
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test
backend/.venv312_clean/Scripts/python.exe -m pytest tests/integration/test_be025_admin_control_plane.py -q
→ 15 passed, 7 warnings in 22.85s

backend/.venv312_clean/Scripts/python.exe -m pytest tests/integration/test_authorization.py -q
→ 17 passed, 6 warnings in 28.21s
```

The 15 targeted tests cover, in both permitted **and** denied directions:
organization-scope administration and foreign-org `404`; the four non-admin
roles denied across the plane plus an enforcing-mode `401`; unit boundaries;
assignment lifecycle with the new list endpoint and its audit trail; 8-thread
duplicate assignment (one row, `200`/`201`); six privilege-escalation attempts;
the last-administrator guard; organization lifecycle with no-op audit
suppression and org suspension cutting off a scoped user; project scope
administration including cross-org escape and clear-requires-GLOBAL; ownership
transfer; API-client scope enforcement; pagination bounds and enumeration safety
with malformed IDs; malformed admin payloads; and the M1 CHECK constraint
enforced against a repository-level insert that bypasses the service. Audit
chain validity is asserted through `GET /api/v1/audit/verify`.

`py_compile` clean on all changed production files.

## 9. Environment incident (disclosed, not papered over)

One manual maintenance command exported `TEST_DATABASE_URL` while `alembic` and
the ad-hoc Python scripts build their engine from `DATABASE_URL`. Only
`tests/conftest.py` republishes `TEST_DATABASE_URL` as `DATABASE_URL`, so that
command resolved to **`pofa_dev`** and its cleanup `DELETE` removed one
`be025`-prefixed leftover user (plus projects it owned and its role assignments)
from the development database.

Blast radius, verified afterwards: `pofa_dev` retained its full seed (1094 users,
846 GLOBAL administrator assignments) and its **audit ledger is intact** (6016
events — no audit row was touched, consistent with the append-only rule). The
removed row was test debris from a prior session, not milestone data. Every
subsequent manual command used an explicit `DATABASE_URL`. The verification
suite itself was never affected: conftest guarantees it runs against
`pofa_test`, and it refuses to run rather than fall back to `pofa_dev`.

All BE-025 evidence in this stage comes from `pofa_test`.

## 10. Preserved findings

- **R4** (from Stage A): `project.update` is granted to no seeded role, so
  renaming a project via the admin plane is unreachable for every current role.
  Preserved and documented; **not** fixed, as changing the frozen role catalogue
  is out of BE-025 scope.
- Organization suspension cutting off all users scoped to it is verified as
  existing BE-016 behaviour, now covered by a BE-025 test.

## 11. Not done in this stage

Stage D runtime verification, Stage E hardening/fault injection, Stage F full
matrix, Final Acceptance Report, and any commit/push. Per the staged-gate
pattern, work stops here for review.

## 12. Gate conclusion

Stage C passes its own criteria: the design is implemented against real database
state, every administrative mutation is auditable, backend authorization remains
authoritative, no fallback to unrestricted access exists on any path, the audit
ledger stays append-only, and behaviour is backed by executed tests rather than
static reasoning. Three production defects were found by execution and fixed
with verification.

**Proceeding requires approval to start Stage D.**
