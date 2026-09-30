# BE-025 — Stage B Design
## Organization, Role Assignment & Administrative Control Plane

Date: 2026-09-28
Inputs: `docs/BE-025 Stage A Reconnaissance.md` (approved)
Scope discipline: extension of BE-016 only. No new RBAC engine, no new framework,
no new dependencies, no frontend, no OIDC replacement, no dev-token replacement.

---

## 1. Design goals

1. Make organizations, units, users, role assignments, and project organizational
   binding administrable through `/api/v1/auth` endpoints.
2. Make administration possible **within scope**: a GLOBAL admin manages
   everything; an ORGANIZATION admin manages its own organization; narrower scopes
   manage strictly inside themselves.
3. Make privilege escalation structurally impossible: an actor can never create,
   modify, or move authority it does not itself hold over the target.
4. Keep every security-sensitive mutation transactionally audited (BE-015) and
   keep the audit chain untouched.
5. Enforce administrative invariants at the service + database level, deterministically.

## 2. Reuse map (what we do NOT rebuild)

| Need | Reused primitive |
|---|---|
| Endpoint authz + 401/403/404 mapping | `require()`, `enforce()`, `reject_malformed_resource_id` (`backend/security/authorization.py`) |
| GLOBAL-only operations | `require_global()` |
| Server-side scope resolution | `resolve_resource_scope()` (already resolves `organization`, `organizational_unit`, `project`, `user`-adjacent chains) |
| Assignment validation/races | `auth_service.assign_role()` (unique-constraint idempotency) |
| Audit emission | `_audit_admin()` → `audit_ledger.append_event()` in the same transaction |
| Pagination envelope | `limit/offset/total` convention from `GET /projects` |
| Principal snapshot | `resolve_user_principal()` (org/unit/role status filtering already correct) |

## 3. Permission model decisions

No new permissions, no new scope types, no changes to seeded role grants except
none — `organization.manage`, `user.manage`, `role.manage` already exist and stay
as-is. GLOBAL remains implicitly superior (covers all resources via `_scope_covers`).

### 3.1 Capability gate: scope containment (core escalation rule set)

Implemented in the service layer, evaluated against the actor's **principal
snapshot** (`can()`-style, no new engine). Let `S(a)` be the set of scopes at which
the actor holds the required admin permission.

- **E1 (GLOBAL containment).** Creating or targeting a GLOBAL-scope assignment, or
  managing a GLOBAL-only facility (user list/status, role catalogue read), requires
  the permission in GLOBAL scope. A non-GLOBAL actor attempting it gets **403**
  (capability statement about the actor; no resource existence revealed).
- **E2 (covering scope).** For any operation on an organization, unit, project, or
  assignment, the actor's grant of the required permission must `_scope_covers`
  the target resource (ORGANIZATION grant covers its units and its projects;
  UNIT grant covers the unit and projects in it; PROJECT grant covers exactly that
  project). Foreign target ⇒ **404** via the existing indistinguishability rule.
- **E3 (role-contentment on assignment).** A role assignment `R` into scope `T` is
  permitted only if, for **every** permission `p` granted by `R`, the actor itself
  holds `p` at a scope covering `T`. Consequences, all deterministic:
  - nobody can grant what they do not hold over the target (no indirect
    escalation, including self-grant beyond own reach);
  - an org admin holding ADMINISTRATOR at org scope may delegate ADMINISTRATOR
    down into their org's units/projects (subset of what they hold);
  - a unit admin cannot assign into a sibling unit or the parent org (E2);
  - API clients are subject to the same E1–E3 using their GLOBAL/PROJECT binding,
    closing "privilege escalation through API clients" (task §6).
- **E4 (movement operations).** Operations that move a resource **across** scope
  boundaries (project organization rebind, owner transfer) require covering
  authority over the current scope **and** the destination scope; GLOBAL covers
  both. Binding a project that is currently unscoped requires GLOBAL (the actor
  cannot demonstrate prior authority) — documented behavior.
- **E5 (no downgrade escape).** Revocation/disabling is guarded by E2/E3-analogue
  (actor must cover the target) plus the last-admin guard (R3 below).

Rationale for 404-vs-403 split matches BE-016: out-of-scope resources are 404;
operations the actor's own grant level can never do (GLOBAL requests from
non-GLOBAL) are 403.

### 3.2 Explicitly preserved existing semantics (documented, not "fixed")

- A GLOBAL `user.manage` holder may register API clients with arbitrary permission
  strings (BE-016 V1 design). E3 now blocks those clients (or anyone) from using
  that to escalate beyond their own holdings at operation time. No new restriction
  is invented on client creation itself.
- `role_id` FK is RESTRICT and org FK on units is RESTRICT → no hard deletes of
  referenced catalog/org rows; lifecycle is status-based. Kept.
- Disabling/suspending users/orgs/units already revokes access instantly via
  `resolve_user_principal`. No soft-revocation column added.

## 4. API design (all under `/api/v1/auth`, `/api/v1` prefix canonical)

Path params typed `UUID` (FastAPI 422); request bodies via Pydantic v2 models in
`backend/schemas/authorization.py`; DB models never exposed directly.

### 4.1 Organizations

| Method + path | Guard (E-model) | Success | Errors | Audit |
|---|---|---|---|---|
| `GET /auth/organizations` | `organization.manage` (GLOBAL lists all; org-scoped lists own orgs; empty grants ⇒ empty page, never 403-only leak beyond normal 403) | 200 `OrganizationListResponse{items,limit,offset,total}` | 401/403 | — |
| `PATCH /auth/organizations/{organization_id}` | `organization.manage` covering that org (E2) | 200 | 404 (missing/foreign), 422 (blank name, invalid status transition) | `ORGANIZATION_UPDATED` with before/after name+status |
| `GET /auth/organizations/{organization_id}` | `organization.manage` covering that org (E2) — added at Stage D so a detail **read** demands exactly the same authority as the **update** of the same resource; previously GLOBAL-only, which locked a scoped administrator out of its own organization | 200 | 404 (missing/foreign) | — |
| `GET /auth/organizations/{organization_id}/units` (exists) | unchanged guard, **now paginated** envelope `OrganizationalUnitListResponse` | 200 | 403/404 | — |

- `code` is **immutable** after creation (referential stability); updates change
  `name` and `status` only.
- Status transitions: `ACTIVE ⇄ SUSPENDED`, `ACTIVE/SUSPENDED → DISABLED`,
  `DISABLED → ACTIVE` allowed (restore path); all deterministic, all audited.
  No DELETE endpoint (R6: deactivation semantics per task §4).

### 4.2 Organizational units

| Method + path | Guard | Success | Errors | Audit |
|---|---|---|---|---|
| `GET /auth/units/{unit_id}` | `organization.manage` covering the unit | 200 | 404 | — |
| `PATCH /auth/units/{unit_id}` | same; **organization_id immutable** (invariant: unit belongs to referenced org; moving a unit across orgs is E4-class → requires GLOBAL authority over both orgs and is deferred out of V1 BE-025 to keep scope minimal) | 200 | 404, 422 | `ORGANIZATIONAL_UNIT_UPDATED` |

### 4.3 Users

| Method + path | Guard | Success | Errors | Audit |
|---|---|---|---|---|
| `GET /auth/users` | `require_global("user.manage")` (users are not org-scoped entities) | 200 paginated, stable order `(created_at, id)` | 401/403 | — |
| `PATCH /auth/users/{user_id}/status` | `require_global("user.manage")` + last-admin guard (below) | 200 | 404, 422 | `USER_STATUS_CHANGED` before/after |
| `GET /auth/users/{user_id}/roles` | `role.manage`; returns only assignments within the actor's covering scopes (E2 filtering); GLOBAL sees all | 200 list of `RoleAssignmentResponse` (with real `id`) | 403/404 | — |

`UserResponse` for list includes roles names as today (single batched join, no N+1).

### 4.4 Role assignments (existing endpoints upgraded to the E-model)

| Method + path | New guard | Notes |
|---|---|---|
| `POST /auth/users/{user_id}/roles` | E1 for `scope_type=GLOBAL` (⇒ `require_global("role.manage")` equivalent check); otherwise `role.manage` covering the target scope + **E3 role-contentment** | 201 created / 200 idempotent duplicate (existing semantics preserved); 403 GLOBAL-from-non-GLOBAL; 404 foreign org/unit/project target; 422 scope/id matrix invalid (existing `assign_role` validation); 409 role not ACTIVE? — kept as existing 422; audit `ROLE_ASSIGNED` (existing) |
| `DELETE /auth/users/{user_id}/roles/{assignment_id}` | actor must hold `role.manage` covering the **assignment's** scope (E2) + last-admin guard | 204; 404 unknown/foreign assignment (also enforces `user_id` match as today); 409 last-GLOBAL-administrator; audit `ROLE_REVOKED` (existing) |

**Last-admin guard (R3).** An operation (revoke assignment, disable/suspend user,
disable org carrying the holder's only grant — see §5) is rejected with
`409 LAST_GLOBAL_ADMINISTRATOR` when it would leave zero `ACTIVE` users holding an
`ACTIVE` ADMINISTRATOR role in GLOBAL scope. The guard runs inside the mutating
transaction while holding a transaction-scoped advisory lock
(`pg_advisory_xact_lock` on a fixed namespace key) so two concurrent "second-to-last"
revocations serialize; the second sees count 1 and is rejected. No new table, no
new scope type.

### 4.5 Project administration (administrative control plane; domain edits unchanged)

| Method + path | Guard | Semantics |
|---|---|---|
| `PATCH /auth/projects/{project_id}/scope` | E2/E4 | body `{organization_id?, organizational_unit_id?}` sets/clears BE-016 binding. Invariants: unit (if set) must belong to org (if effective); target org/unit must be `ACTIVE`; initial bind of an unscoped project requires GLOBAL; rebind within same org requires covering authority of that org; **cross-org move requires authority over old and new org (or GLOBAL)**. 400-class violations return 422 with deterministic messages; 404 for foreign targets. Audit `PROJECT_SCOPE_CHANGED` (before/after org+unit). |
| `POST /auth/projects/{project_id}/ownership` | E2 + GLOBAL-or-covering `user.manage`? — decided: guard is `organization.manage` covering the project **plus** the new owner must be an `ACTIVE` user; current owner does not need to consent (administrative plane). Audit `PROJECT_OWNERSHIP_CHANGED` (before/after owner). | 200; 404 project/owner; 422 inactive owner. |

Out of scope here: `PATCH /projects/{id}` (domain rename via `project.update`)
keeps its current guard; finding **R4 stays as-is and is re-documented**:
`project.update` is granted to no seeded role, so domain rename remains
unreachable until a future milestone decides the grant. BE-025 does not silently
widen `ADMINISTRATOR`.

**Activity/team assignment:** the sanctioned mechanism is PROJECT-scoped role
assignments (FIELD_OFFICER etc.) managed via §4.4 — no membership table will be
invented (task §4 "where the existing schema supports it"). Activity `actor_id`
setting stays a domain operation under existing guards. No supervisor column is
added (does not exist in schema; adding one is a redesign, out of scope).

### 4.6 Role catalogue

Read-only as today (`GET /auth/roles`, `/auth/permissions` — now paginated
envelopes too, task §11 applies to *any* list endpoint). No create/update/delete
API: the catalogue is code-seeded via `ensure_default_catalogue` and DB-authoritative;
`role.manage` governs *assignments*, not catalogue contents. Documented boundary.

## 5. Administrative invariants (task §7) — enforcement matrix

| Invariant | Enforcement |
|---|---|
| Org exists before unit creation | existing service check → 404 |
| Unit belongs to referenced org | existing FK + PATCH immutability + project-scope check in §4.5 |
| Scoped assignment references valid scope | existing checks + **M1 CHECK constraint** (§6) |
| Project assignment respects org/unit boundary | §4.5 service validation (unit.org == org) |
| Revoked assignment stops authorizing immediately | hard delete + principal rebuilt per request (verified by test) |
| Duplicate assignment deterministic | existing DB unique (`nulls not distinct`) + 200-on-duplicate semantics |
| No silent orphaning on org disable | status lifecycle only (delete impossible via RESTRICT FKs); disable effects asserted in tests; last-admin advisory guard covers admin lockout |
| Role/permission consistency | catalogue code-owned + idempotent seed; no API mutation path |
| No partial admin mutations | service pattern: validate → mutate → `_audit_admin` → single `db.commit()`; on IntegrityError → `db.rollback()` and deterministic error |

## 6. Database / migration decision

**M1 (included, additive, single revision on head `n4o5p6q7r022`):** CHECK
constraint on `user_role_assignments` enforcing the scope/id matrix that today only
Python guarantees (closes R5, task §10 DB-constraint preference):

```
scope_type = 'GLOBAL'                  AND organization_id IS NULL AND organizational_unit_id IS NULL AND project_id IS NULL
OR scope_type = 'ORGANIZATION'         AND organization_id IS NOT NULL AND organizational_unit_id IS NULL AND project_id IS NULL
OR scope_type = 'ORGANIZATIONAL_UNIT'  AND organizational_unit_id IS NOT NULL AND organization_id IS NULL AND project_id IS NULL
OR scope_type = 'PROJECT'              AND project_id IS NOT NULL AND organization_id IS NULL AND organizational_unit_id IS NULL
```

- Linear; reversible (`downgrade` drops the constraint); no data rewrite; existing
  rows already satisfy it (created exclusively through `assign_role`).
- Upgrade, downgrade, from-scratch, and existing-DB-upgrade all exercised in Stage D/F.
- **No other migration.** No soft status columns, no supervisor/membership tables.

## 7. Audit design (task §8)

New event types appended through the existing `_audit_admin` path (same
transaction, source `authorization_service`):
`ORGANIZATION_UPDATED`, `ORGANIZATIONAL_UNIT_UPDATED`, `USER_STATUS_CHANGED`,
`ROLE_ASSIGNED`*, `ROLE_REVOKED`*, `PROJECT_SCOPE_CHANGED`,
`PROJECT_OWNERSHIP_CHANGED` (*exist already — extended payload).

Payload fields per event: actor id/type, target id + type, organization context
where derivable, and a deterministic before/after summary
(e.g. `{"status": {"before": "ACTIVE", "after": "SUSPENDED"}}`).
Never any secret, token, credential, or payload blob material. The append-only
ledger, hash chain, BE-023 audit guard and verification endpoint are untouched.

## 8. Idempotency & concurrency (task §10)

- Duplicate create-user / create-org / create-unit / create-client → existing
  deterministic 409/422 conflicts (unchanged).
- Duplicate role assignment → DB unique + 200 (already correct; test under
  N-thread concurrent assign asserts exactly one row).
- Concurrent revoke × revoke, revoke × last-admin → advisory-lock guard; exactly
  one succeeds when only two admins remain and one is protected.
- PATCH endpoints are set-semantics (idempotent replay → same state, second
  identical PATCH audits a no-op change pair before==after? No: **no-op suppresses
  audit** — if nothing changed, respond 200 with zero events; deterministic and
  prevents audit spam. State this in tests).
- Concurrent org/unit updates: last-commit-wins per column set; no cross-row
  invariants can break (name/status only).

## 9. Pagination & enumeration safety (task §11)

- Every new/updated list endpoint: `limit` (default 50, ge 1, le 100), `offset`
  (ge 0), envelope `{items, limit, offset, total}`, stable ordering
  (`name`/`created_at, id`).
- Authorization filtering happens **before** counting: `total` reflects only rows
  the caller may see → no cross-organization inference through counts, ids,
  ordering, or error text. Non-visible org resources return 404 like absent ones.

## 10. Error contract (uniform)

401 unauthenticated (enforcing mode) · 403 capability denial (E1, missing
permission on any scope) · 404 missing **or** out-of-scope (BE-016 indistinguishability)
· 409 conflict (duplicate unique, last-admin guard) · 422 validation (Pydantic,
malformed UUID via FastAPI path typing + `reject_malformed_resource_id` on
require-guarded params) · 201 create · 200 idempotent duplicate/patch · 204 delete.

## 11. Implementation surface (Stage C file plan)

| File | Change |
|---|---|
| `backend/services/authorization.py` | `update_organization`, `list_organizations_for_principal`, `update_unit`, `list_user_assignments`, `set_user_status`, `assign_role` (E1–E3 extensions, actor param), `revoke_assignment` (E2 + last-admin advisory guard), `change_project_scope`, `change_project_owner`, audit payloads; advisory-lock helper |
| `backend/security/authorization.py` | thin helper `require_covering_scope(principal, db, action, scope_type, ids...)` reusing `can()`/`enforce()` (no new engine) |
| `backend/api/v1/endpoints/auth.py` | §4 endpoints; pagination; guards per matrix |
| `backend/schemas/authorization.py` | update/list/status/scope/ownership request+response models, list envelopes |
| `backend/db/models.py` | mirror the M1 CHECK constraint definition (comment parity) |
| `alembic/versions/<new>_be025_assignment_scope_check.py` | M1 only |
| `tests/integration/test_be025_admin_control_plane.py` | §12 suite |
| `docs/BE-025 Stage C/D/E/F docs` | produced per stage |

No changes to: audit ledger logic, fusion/review/dispute/publication services,
authentication adapters, ML pipeline, notification service (its role-name joins
keep working because assignment semantics are unchanged for readers).

## 12. Test plan (task §13 — targeted suite)

Authorization matrix per capability: GLOBAL admin allowed; ORG admin allowed on own
org only; ORG admin denied (404) on foreign org; UNIT/PROJECT admin containment;
SUPERVISOR (no admin perms) → 403; REVIEWER → 403; FIELD_OFFICER → 403; CITIZEN →
403; anonymous in enforcing → 401; API client GLOBAL-with-grants vs PROJECT-bound
client behavior under E1–E3.
Escalation attempts: assign beyond held permissions; org admin creating org admin in
foreign org; self-demote-lockout blocked (last-admin 409); unit→sibling assignment;
project rebind escaping org; client holding `role.manage` cannot exceed scopes.
Lifecycle: assign→verify access→revoke→verify immediate denial; disable org→
org-scoped grants inert, GLOBAL unaffected; user suspend/reactivate.
Idempotency/concurrency: N-thread duplicate assign (1 row), concurrent revokes,
repeated PATCH (no-op audit suppression).
Invariants: unit-with-wrong-org 422; rebind inactive org 422; malformed UUIDs 422;
missing resources 404; pagination bounds + authz-filtered totals.
Audit: every mutation event exists with correct actor/target, before/after present,
no secret-looking keys; chain verify after suite (reuse `/api/v1/audit/verify`).
Regression: full `test_authorization.py` + BE-019/021/022 suites run unchanged before
and after (task §14); BE-023 audit guard + preflight still green.

## 13. Deliberate non-goals (restated with reasons)

- Role/permission catalogue CRUD API — catalogue is code-owned; exposing it would
  let admins author arbitrary permission strings (untested semantics).
- Organization/unit deletion — RESTRICT FKs prove data dependency; status lifecycle
  satisfies the requirement.
- Project supervisor field / team membership table — no schema precedent; inventing
  one is architecture change, forbidden by task §1/§21.
- Cross-org unit relocation — deferred; needs its own invariant story.
- Granting `project.update` to ADMINISTRATOR (R4) — kept documented-but-unfixed
  (would change substantive/domain semantics; not required for BE-025 correctness).
- Replacing dev tokens, adding OIDC, JWT infra — out of scope per task §15/§21.

## 14. Stage B gate

Design complete and internally consistent with Stage A findings and the locked
architecture. Awaiting approval; **no production code changed in Stage B.**
Implementation proceeds in Stage C only after this design is approved.
