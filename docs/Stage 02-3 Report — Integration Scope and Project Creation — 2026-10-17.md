# Stage 02-3 Report — Integration Scope and Project Creation — 2026-10-17

**Status:** Completed and committed at `298eac11` (parent `7b2f4673`). 21 files, +2140 / −98 lines.

---

## 1. Executive Summary & State of the Work

The Stage 02-3 milestone closes authorization scoping and project creation identity across two major families:
- **Family A — Resource Scope Enforcement**: Closing scoping gaps across integration endpoints, retention holds, and publication policies.
- **Family B — BE-039 Project Creation Identity**: Transitioning `POST /projects` from an unverified caller-supplied id into a principal-derived, atomically audited creation workflow with server-derived birth scope.

All code and test changes are committed and pushed on branch `Backend` at commit `298eac11`.

---

## 2. Family A — Resource Scope Changes

1. **`visible_organization_ids`**: Introduced in `backend/security/authorization.py:144` to compute the caller's authorized organization set.
2. **Integration Endpoints & Repository Scoping**:
   - `GET /integrations/systems`: Filtered by caller's visible organizations (`endpoints/integration.py:113` → `repositories/integration.py:47`).
   - `GET /integrations/clients`: Filtered by caller's visible projects (`endpoints/integration.py:212` → `repositories/integration.py:86`).
   - `GET /integrations/webhooks`: Scoped via join to parent `ExternalSystem` organization (`endpoints/integration.py:684` → `repositories/integration.py:304`).
   - `GET /integrations/references`: Scoped via join to parent `ExternalSystem` organization (`endpoints/integration.py:408` → `repositories/integration.py:177`).
   - `POST /credentials/{id}/revoke`: Enforces `credential.manage` against client scope (`endpoints/integration.py:352`).
   - `GET /integrations/events`: Documented and retained as **GAP-SCHEMA** because `project_id` lacks a foreign key.
3. **Integration Writes (8.4b)**: `POST /integrations/systems` and `POST /integrations/clients` enforce authorization against target organization/project scope before inserting rows or checking uniqueness.
4. **Audit Payload**: `EXTERNAL_SYSTEM_CREATED` carries `organization_id` in its payload.
5. **Publication Policies**: Policy enumeration and creation require `GLOBAL` grant, matching item-read requirement.
6. **Retention Holds**: `_resolve_hold_scope` derives the hold's governing scope from its target rather than persisting NULL scope columns, and `_hold_readable` enforces scope on read.

---

## 3. Family B — BE-039 Project Creation Identity & Audit

1. **Service Separation**: Creation logic moved to `auth_service.create_project` (`backend/services/authorization.py:807`). Atomicity comes from a single `db.commit()` after `append_event` flushes without committing, so the project row and its `PROJECT_CREATED` event commit or roll back together (`test_creation_and_audit_roll_back_together`). No row lock is taken — creating a new row has nothing to lock.
2. **Owner Derivation**: `owner_id` defaults to the authenticated human user principal.
3. **Delegated Ownership (D-2 Option A)**: Naming another user as `owner_id` requires holding `project.create` at `GLOBAL` scope. The guard runs before any user lookup, so a non-GLOBAL caller is always refused `403` (never a `404` that would confirm the id exists) and leaves the database unchanged.
4. **Actor Attribution**: `actor_id` in the audit row is always the caller principal (`created_by`), while `owner_id` captures ownership.
5. **Audit Event**: Emits `PROJECT_CREATED` with full payload in the same database transaction.
6. **Birth Scope Resolution (D-3)**: `_birth_scope` (`backend/services/authorization.py:779`) server-derives scope from the creator's active grant, resolving the §1.1 defect.
7. **Destination Authority on Transfer (D-5)**: `change_project_owner` (`backend/services/authorization.py:859`) requires `GLOBAL` `organization.manage` for destination user.
8. **Database Migration (D-1)**: Migration `w3x4y5z6a033` (`alembic/versions/w3x4y5z6a033_be039_project_created_event.py`) updates audit vocabulary frozenset from 96 to 97 (`PROJECT_CREATED`) and rebuilds `ck_audit_ledger_event_type_domain`.

---

## 4. Verification on Disposable Infrastructure

- **BE-039 Integration Tests**: 8 passed in `tests/integration/test_be039_project_creation_identity.py`.
- **Migration & Ledger Contract Pins**: 21 passed (`test_be030_ledger_contract.py`, `test_migrations.py`, and `be019` tests).
- **Blast Radius**: 140 passed across every test file POSTing to `/projects`.
- **Focused Integration Regression**: 156 passed across publication, retention, and integration test suites.
- **Family A Head-Proof**: 3 failed / 2 errors on unpatched HEAD, establishing non-vacuity.

---

## 5. The §1.1 → FIXED → VERIFIED Chain

- **§1.1 Defect (Measured)**: An organization-scoped supervisor calling `POST /projects` for themselves received `201 Created`, but subsequent `GET /projects/{project_id}` returned `404 Not Found` and `GET /projects` returned `total=0` (`project_scope_probe.log`). Cause: the creation route took no scope field, resulting in `organization_id IS NULL`, which `_scope_covers` refuses under an ORGANIZATION grant.
- **FIXED**: `_birth_scope` (`backend/services/authorization.py:779`) resolves birth scope server-side from the creator's own active `project.create` grant. If the creator holds an unambiguous single ORGANIZATION (or unit) grant, the project is born inside that scope (`organization_id` and optional `organizational_unit_id` populated).
- **VERIFIED**: Proven in `tests/integration/test_be039_project_creation_identity.py::test_owner_defaults_to_the_principal_and_stays_visible` and `test_unit_scoped_creator_is_born_inside_the_unit`. Post-creation read returns `200` with the project visible and listed (`listed == True`).

---

## 6. Contract & Schema Snapshot (`openapi.json`)

The OpenAPI specification snapshot (`openapi.json`) has been refreshed and verified:
- `ProjectCreate.owner_id` is now optional (`UUID | None = None`) with comprehensive delegation guidance in description.
- `ProjectCreate.required` updated from `["name", "owner_id"]` to `["name"]`.
- `POST /api/v1/auth/projects/{project_id}/ownership` summary updated: `"Transfer project ownership to an active user (organization.manage must cover the project; the new owner needs GLOBAL authority)"`.
- Docstrings and descriptions refreshed across integration endpoints.

---

## 7. Deployment & Migration Ordering (D-6)

- **Ordering Invariant**: `pofa_dev` (at `t0u1v2w3x030`) and `pofa_test` (at `v2w3x4y5z032`) both reject `PROJECT_CREATED` until migrated.
- **Owner-Gated Constraint**: Applying `w3x4y5z6a033` to `pofa_dev` requires explicit owner approval and a fresh backup of `pofa_dev` before executing `alembic upgrade head`.

---

## 8. Remaining Actions & Out-of-Scope Items

1. **Full Armed Suite Execution**: Run against armed disposable PostgreSQL stack with target floor ≈1022 (baseline 1006 + 16 new tests).
2. **BE-039 Non-Vacuity Proof**: Execute `test_be039_project_creation_identity.py` against pre-fix code from `7b2f4673`.
3. **Quarantine Lifecycle Planning**: Proceed with issue #215 planning once Stage 02-3 closure is formally signed off.
