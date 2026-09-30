# BE-025 — Stage A Reconnaissance
## Organization, Role Assignment & Administrative Control Plane

Date: 2026-09-28
Branch inspected: `Backend` @ `75c52b68` (BE-024 accepted)
Mode: read-only inspection. **No production code, migrations, APIs, or commits were created in this stage.**

---

## 1. Current organization / auth / admin architecture (as implemented)

The BE-016 foundation is real, enforced, and already partially administrable. It is
**not** a stub: principal resolution, scope evaluation, role assignment, and audit
emission all run against real PostgreSQL tables and are covered by 17 integration
tests (`tests/integration/test_authorization.py`).

Layering (locked, must be preserved):

| Layer | Location | Responsibility |
|---|---|---|
| Models | `backend/db/models.py` | `Organization`, `OrganizationalUnit`, `User`, `Role`, `Permission`, `RolePermission`, `UserRoleAssignment`, `ApiClient` (+ BE-019 `ApiCredential`) |
| Catalogue (code-seeded) | `models.py:~1100-1343` | `AUTH_PERMISSIONS`, `AUTH_ROLES`, `AUTH_ROLE_PERMISSIONS` (CITIZEN / FIELD_OFFICER / REVIEWER / SUPERVISOR / ADMINISTRATOR / API_CLIENT) |
| Repository | `backend/repositories/authorization.py` | persistence + lookups only (insert/get org, unit, user, role, permission, assignment, client; `delete_assignment`; `assignments_for_user`) |
| Service | `backend/services/authorization.py` | `ensure_default_catalogue`, `create_user/create_organization/create_organizational_unit/assign_role/revoke_assignment/create_api_client`, `resolve_user_principal`, `resolve_client_principal`, `resolve_resource_scope`, `can()` |
| HTTP adapter | `backend/security/authorization.py` | `require()`, `require_target()`, `require_global()`, `enforce()`, `visible_project_ids()`, `filter_by_project_scope()`, `reject_malformed_resource_id()` (BE-024 DF-SD-01 fix) |
| AuthN adapter | `backend/security/authentication.py` | `resolve_principal` (dev tokens, `poa_<client>:<secret>` API credentials, enforcing/development modes) |
| Endpoints | `backend/api/v1/endpoints/auth.py` | mounted at `/api/v1/auth` via `backend/api/v1/router.py:39` |

Scope chain: `Organization → OrganizationalUnit → Project`; `resolve_resource_scope()`
transitively derives a resource's organization/unit from its project chain
(`authorization.py:534-745`), and `_scope_covers()` grants an ORGANIZATION-scope
assignment over everything in the org, UNIT-scope over the unit's projects, PROJECT
exactly, GLOBAL everywhere.

Key separation-of-duties guarantees already encoded (do not weaken):
- Administrators hold `organization.manage`, `user.manage`, `role.manage`,
  `configuration.manage`, audit/retention/notification/integration/publication-policy
  permissions — but **never** `review_case.decide`, `dispute.resolve`,
  `publication.approve/publish/unpublish` (BE-021 §12, BE-022 §14 semantics).
- Roles grant permissions; scope comes only from assignments. Out-of-scope ⇒ 404;
  no-permission ⇒ 403; unauthenticated ⇒ 401.
- Revoked/deleted assignment or a suspended org/unit immediately removes the grant:
  `resolve_user_principal` skips assignments whose org/unit is not `ACTIVE` and whose
  role is not `ACTIVE` (`authorization.py:218-232`).

## 2. Existing database structures

Created by migration `i9d0e1f2g016_be016_auth_authorization.py` (linear history,
current head `n4o5p6q7r022`):

- `organizations` — id, name, **code UNIQUE**, status CHECK ∈
  {ACTIVE, SUSPENDED, DISABLED}, timestamps.
- `organizational_units` — FK `organization_id ON DELETE RESTRICT`,
  **UNIQUE(organization_id, code)**, same status CHECK.
- `users` — BE-016 columns added: `external_subject`, `identity_provider`
  (default `local`), UNIQUE(`identity_provider`,`external_subject`), `display_name`,
  status CHECK, `updated_at`; legacy `is_active` retained.
- `projects` — `owner_id` FK users NOT NULL; **nullable** `organization_id`,
  `organizational_unit_id` FKs (unscoped = pre-BE-016 behavior).
- `roles` / `permissions` / `role_permissions` — catalogue tables,
  UNIQUE(`role_id`,`permission_id`), role status CHECK.
- `user_role_assignments` — one role held in exactly one scope; CHECK
  `scope_type IN ('GLOBAL','ORGANIZATION','ORGANIZATIONAL_UNIT','PROJECT')`;
  **UNIQUE(user_id, role_id, scope_type, organization_id, organizational_unit_id,
  project_id) with `postgresql_nulls_not_distinct=True`** → duplicate assignment is
  DB-impossible and `assign_role` returns the existing row (idempotent, concurrent-safe);
  `role_id` FK is ON DELETE RESTRICT, user FK CASCADE.
- `api_clients` — JSONB `scopes`, optional `project_id`, status CHECK.
  BE-019 added `api_credentials` (hashed secrets) and credential rotation in
  `endpoints/integration.py` guarded by `api_client.manage` / `credential.manage`.
- `activities` — `actor_id` FK users (this is the only "activity assignment"
  concept that exists; there is **no** ProjectMembership / team / supervisor table).

**No table exists for:** project supervisors, team memberships, soft-revoked
assignment status, admin action counters, or org hierarchies beyond one unit level.
`alembic/versions/` shows no other admin-plane tables at head.

## 3. Existing API surface (administrative)

All under `/api/v1/auth`, all via `require_global(...)` — i.e. the permission must be
held with **GLOBAL scope** (`security/authorization.py:242-268`):

| Endpoint | Guard | Notes |
|---|---|---|
| `GET /auth/me` | `get_current_principal` | principal snapshot incl. roles/permissions/org ids |
| `POST /auth/users` | global `user.manage` | 201; 409 on unique clash; audits `USER_CREATED` |
| `GET /auth/users/{user_id}` | global `user.manage` | includes role **names** only, not assignment rows |
| `POST /auth/organizations` | global `organization.manage` | audits `ORGANIZATION_CREATED`; 422 on dup code |
| `GET /auth/organizations/{organization_id}` | global `organization.manage` | |
| `POST /auth/organizations/{organization_id}/units` | global `organization.manage` | audits `ORGANIZATIONAL_UNIT_CREATED`; org must exist (404) |
| `GET /auth/organizations/{organization_id}/units` | global `organization.manage` | **unbounded list, no pagination** |
| `GET /auth/roles`, `GET /auth/permissions` | global `role.manage` | **unbounded lists** |
| `POST /auth/users/{user_id}/roles` | global `role.manage` | assign; 201 created / 200 idempotent duplicate; audits `ROLE_ASSIGNED` |
| `DELETE /auth/users/{user_id}/roles/{assignment_id}` | global `role.manage` | hard delete; audits `ROLE_REVOKED` |
| `POST /auth/clients` | global `user.manage` | BE-019 offers the richer `api_client.manage`-guarded credential flows in `/integration` |

Project endpoints (`/api/v1/projects…` in `endpoints/context.py`) use `require()`:
create takes `owner_id` only; **no endpoint can set or change
`organization_id` / `organizational_unit_id` / ownership**; PATCH changes only `name`.

## 4. Existing authorization primitives (reusable as-is)

- `require(action, resource_type, id_param)` — server-side scope enforcement with
  401/403/404 mapping + `reject_malformed_resource_id` ⇒ **already supports
  organization-scoped admin checks** via `require("organization.manage",
  "organization", "organization_id")` — `resolve_resource_scope` handles
  `organization` and `organizational_unit` (`authorization.py:552-559`), so an
  ORGANIZATION-scoped grant covers its own org and a foreign org yields 404.
- `require_global(action)` — for operations that must stay GLOBAL-only (e.g. issuing
  GLOBAL-scope assignments).
- `can()` + `_scope_covers()` — fail-closed decision core; unknown permission ⇒ deny.
- `visible_project_ids` / `filter_by_project_scope` — list filtering conventions
  (limit/offset/total) already used by `GET /projects`.
- Development token mechanism and enforcing mode are unchanged per task §15
  ("do not replace the current development authentication mechanism").
- API clients: explicit scopes only, PROJECT or GLOBAL binding; empty default
  permission set (`API_CLIENT: ()`).

## 5. Existing role/assignment capabilities in services

- `assign_role` validates scope/ID matrix exhaustively (GLOBAL carries no ids;
  ORGANIZATION exactly org id; etc.), checks existence + ACTIVE status, handles the
  unique-violation race by returning the existing row. **This logic is correct and
  should be reused, not duplicated.**
- `revoke_assignment` 404s on unknown id; hard-deletes; audits with before-state
  snapshot.
- Audit emission `_audit_admin(...)` → `audit_ledger.append_event` **inside the same
  transaction as the mutation, then a single `db.commit()`** — matches task §8
  ("mutation and audit event commit together"). Preserve this pattern.
- Notification escalation (`services/notification.py:249-285`) resolves SUPERVISOR /
  ADMINISTRATOR recipients **by role name via assignment joins** — any BE-025 change
  to assignment semantics must keep that join working (e.g. if assignments ever gain
  soft status, resolution must filter it consistently).

## 6. Missing capabilities (BE-025 gap list)

Domain (from task §4/§5, verified absent):
1. **Organization**: no update (name/status deactivation), no list, no
   org-scoped administration — every admin call currently requires GLOBAL grants,
   so an ORGANIZATION-scoped ADMINISTRATOR can administrate **nothing** through the
   API despite the scope model supporting it.
2. **Organizational units**: no single-unit GET, no update, no PATCH moving/renaming;
   unit listing unbounded.
3. **Assignments**: no list endpoint (an admin literally cannot discover
   `assignment_id` values through the API — DELETE requires an id only obtainable
   from the DB/tests); no per-user assignment detail (id, scope, role id).
4. **Users**: no list, no status management (suspend/disable/reactivate) despite
   CHECK-constrained `status` column and resolution honoring it.
5. **Project administration**: no way to bind/change project → organization/unit,
   no ownership transfer. Supervisor/team: **schema has no dedicated concept**; the
   supported mechanism is PROJECT-scoped `user_role_assignments` (task §4 "project
   ownership … where the existing schema supports it" — ownership yes via
   `owner_id`, supervisor column does not exist → out of scope unless Stage B
   justifies a migration).
6. **Last-administrator protection**: `revoke_assignment`/org status changes can
   silently strip the only GLOBAL ADMINISTRATOR (task §6/§7 invariant not
   implemented).
7. **Audit coverage gaps**: no events for organization/unit update, user status
   change, project scope/owner change (creation/assignment/revocation are covered).
8. **Pagination**: `list_units`, `list_roles`, `list_permissions` are unbounded;
   new list endpoints must use the existing limit/offset/total convention (task §11).

## 7. Security risks / gaps identified

- **R1 — GLOBAL-only admin gate is coarse** but currently *fails closed*; relaxing
  to org-scoped administration must use `require(action, "organization", "organization_id")`
  so foreign orgs return 404 (not 403) and never leak existence.
- **R2 — privilege escalation surface**: whoever holds GLOBAL `role.manage` can
  grant themselves/anything GLOBAL. Today only GLOBAL holders can reach it (closed
  loop). If BE-025 lets ORGANIZATION-scope admins manage assignments, a unit/org
  admin must be unable to (a) assign roles granting permissions the actor does not
  hold at ≥ the target scope, (b) create GLOBAL assignments, (c) assign into a
  foreign org. Needs explicit server-side rules, not UI checks.
- **R3 — destructive self-lockout**: revoking the last GLOBAL ADMINISTRATOR (or
  disabling that user/org) leaves no one able to administer the system. Task §6
  requires protection; not present today.
- **R4 — `project.update` is granted to no seeded role** (exists in
  `AUTH_PERMISSIONS`, used by `PATCH /projects/{project_id}`, never assigned) —
  nobody, including admins, can rename projects today. BE-025 must decide whether
  admin project mutation goes through `project.update` (grant to ADMINISTRATOR) or
  through a dedicated administrative permission; document, don't silently widen.
- **R5 — no DB constraint tying scope ids to `scope_type`** (e.g.
  `scope_type='ORGANIZATION' AND organization_id IS NULL` is only prevented in
  Python). Task §10 prefers DB constraints; candidate CHECK in a new migration.
- **R6 — organization "deletion"** is impossible by design (`ON DELETE RESTRICT` on
  units, FKs from projects/external systems) — deactivation via status transitions is
  the correct BE-025 semantics (task §4 explicitly prefers it).
- **R7 — IDOR/enumeration**: admin GETs by UUID already 404 uniformly
  (`require`/`require_global` mapping); malformed UUIDs 422 via FastAPI path typing
  and BE-024's `reject_malformed_resource_id`. Preserve; new endpoints must type
  path params as `UUID` and/or route through `require()`.
- **R8 — audit chain**: unchanged; BE-023 audit guard and append-only ledger apply
  to every new mutation (no deletes/updates of `AuditLedgerEvent`).

## 8. Migration requirement assessment

Existing schema already supports: scoped assignments (with DB-level idempotency
unique), org/unit status lifecycle, user status lifecycle, project org binding
columns. **BE-025 core capabilities need no migration.**

A migration is required only if Stage B approves either:
- **M1**: CHECK constraints enforcing the scope-id matrix in
  `user_role_assignments` (mitigates R5 at DB level; low risk, additive);
- **M2**: any new column (e.g. soft-revocation status) — *not recommended*: hard
  delete + audit snapshot already satisfies "revoked assignment cannot continue
  authorizing access" and keeps `resolve_user_principal` and notification joins
  untouched.

Recommendation: M1 yes (one linear, testable down-revision migration), M2 no.

## 9. Existing test coverage relevant to BE-025

- `tests/integration/test_authorization.py` — 17 tests incl. org isolation,
  unit-scope narrowing, admin-can't-decide, role assignment audit + concurrency
  (threading), stale assignment loses access immediately, forged scope ignored,
  API client scopes, `test_user_and_org_admin_endpoints` (current admin surface).
- `tests/integration/test_be019` coverage lives in `test_governance` / integration
  suites for clients/credentials; BE-022/021 suites guard the substantive/admin
  separation.
- `tests/audit_guard.py` static scanner + `tests/preflight.py` runtime probes
  (BE-023) remain mandatory in Stage D/F; `TEST_DATABASE_URL` fallback refusal in
  `tests/conftest.py`.
- Gap: no tests for BE-025 capabilities (they don't exist). Plan:
  `tests/integration/test_be025_admin_control_plane.py` covering task §13 matrix.

## 10. Proposed BE-025 boundaries (for Stage B design)

In scope (minimal additions reusing existing primitives):
1. `backend/services/authorization.py`: `update_organization`, `update_unit`,
   `set_user_status`, `list_assignments_for_user/org`, guarded `revoke` with
   last-global-admin protection, project scope/owner administration helpers — each
   audited in-transaction.
2. `backend/api/v1/endpoints/auth.py` (+ `backend/schemas/authorization.py`):
   PATCH org/unit, GET org list (paginated), GET user assignments (with ids),
   PATCH user status, project administration endpoints (org/unit binding, owner
   transfer) — guarded by `require("organization.manage"|"user.manage"|"role.manage",
   "organization", "organization_id")` for org-scoped ops, `require_global` for
   GLOBAL-scope operations (assigning GLOBAL roles stays GLOBAL-only).
3. Privilege-escalation rules in the service layer (actor-scope containment; R2).
4. Optional M1 migration (CHECK constraints on assignment scope matrix).
5. New integration test suite + audit assertions; Stage D runtime verification;
   Stage E hardening (concurrent assign/revoke, last-admin races, cross-org 404s);
   full regression per task §14.

Explicitly out of scope (confirmed per task §21 plus Stage A additions):
- Frontend, OIDC/OAuth2/JWT replacement, replacing dev tokens, new RBAC engine or
  parallel permission system, role/permission **catalogue** CRUD via API (catalogue
  stays code-seeded + DB-authoritative; `GET /roles`/`/permissions` remain read),
  organization hard delete, project "supervisor" column (no existing schema concept;
  PROJECT-scoped assignments are the sanctioned mechanism), notifications redesign
  (joins must keep working, nothing more), BE-024 open findings DF-SD-02,
  DF-SE-01, DF-SE-02, audit-chain logic, any unrelated migration rewrite.

## 11. Files likely to change (Stage C preview — none touched yet)

| File | Change |
|---|---|
| `backend/services/authorization.py` | admin update/status/list/revoke-guard functions + escalation rules (reuse `_audit_admin`, `assign_role`) |
| `backend/api/v1/endpoints/auth.py` | new/patched admin endpoints, pagination, UUID path params |
| `backend/schemas/authorization.py` | request/response models (update/list/status/project-binding) |
| `backend/repositories/authorization.py` | a few list queries only |
| `backend/security/authorization.py` | possibly a `require_admin_scope` helper composing existing `require`/`require_global` (no new engine) |
| `backend/db/models.py` | only if M1 approved (mirrored CHECK) — otherwise untouched |
| `alembic/versions/<new>` | M1 only, linear on head `n4o5p6q7r022` |
| `tests/integration/test_be025_admin_control_plane.py` | new suite |
| `docs/BE-025 Stage B–F + Final Acceptance` | mandated documents |

## 12. Stage A gate conclusion

All required recon areas inspected against real code (models, repositories, service,
`require()`/`require_target()`/`require_global()`, endpoints, authN adapters, audit
emission, notification recipient joins, migrations, tests). The architecture document
matches implemented code; no parallel admin system exists. The milestone is an
**extension** of BE-016, not a redesign — feasible without new dependencies, new
frameworks, or audit-chain changes.

**No code, migration, API, or commit was produced in Stage A.** Awaiting approval to
proceed to Stage B design (`docs/BE-025 Stage B Design.md`).
