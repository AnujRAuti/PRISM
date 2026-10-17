# Project Creation Identity and Audit — Migration Plan (2026-10-17)

**Status: PLAN ONLY. No schema, model, endpoint or migration file has been changed for
this work.** Every number below was measured today; the measurement is named next to it.
Owner approval is requested before any file in §2 or §3 is touched.

Scope: the owner's second approved work item — `POST /projects` (default owner from the
principal, delegated ownership only through an explicit authorization path, actor always
derived from the principal, a `PROJECT_CREATED` audit record that commits or rolls back
with the project).

---

## 1. Measured starting state

| Fact | Value | How it was measured |
| --- | --- | --- |
| Alembic head | `v2w3x4y5z032` (27 revisions) | `tests/unit/test_migrations.py:61,70` pins; `ls alembic/versions` |
| Audit vocabulary | `len(AUDIT_EVENT_TYPES) == 96` | interpreter import |
| `PROJECT_CREATED` | **not in the vocabulary** | interpreter import (`in` → False); only `PROJECT_SCOPE_CHANGED` and `PROJECT_OWNERSHIP_CHANGED` exist |
| Writer behaviour | `append_event` raises `ValueError("Unknown audit event type")` for an unknown type, flushes without committing | `backend/services/audit_ledger.py:228` |
| DB CHECK | `ck_audit_ledger_event_type_domain` is generated from the same frozenset | `backend/db/models.py`; migration `v2w3x4y5z032` rebuilds it from `AUDIT_EVENT_TYPES` |
| Current `POST /projects` | `require("project.create")` resource-less; `owner_id` **required** in the body; `_require_user` checks existence only; no audit row | `backend/api/v1/endpoints/context.py:50-66`, `backend/schemas/context.py:7-9` |
| Who holds `project.create` | `SUPERVISOR` only (`project.read` too, **not** `project.update`) | `AUTH_ROLE_PERMISSIONS` import |
| `audit_ledger_events` columns | no `organization_id` — organization scope must live in `payload` | column list (used in the §4A integration pass) |
| Users have no organization column | organization membership exists only on `user_role_assignments` | `backend/db/models.py` `User` (id…status), `UserRoleAssignment` |
| Ledger rows / projects on `pofa_dev` | 6023 / 544 | read-only count |
| `pofa_dev` alembic revision | `t0u1v2w3x030` — **three revisions behind** | read-only `select version_num from alembic_version` |
| `pofa_dev` CHECK contains `PROJECT_CREATED` | **no** (constraint definition has no such literal) | read-only `pg_constraint` query |
| Local dev API | not listening on :8000 right now | `curl /ready` → connection refused |

### 1.1 New finding from this reconnaissance (measured, not inferred)

`D:/CODING/Scratch/deploy1/be019/project_scope_probe.log`:

```
PROBE born_organization_id=None own_project_read=404 listed=False list_total=0
```

A `SUPERVISOR` granted at `ORGANIZATION` scope calls `POST /projects` for themselves,
gets **201**, and then **cannot read the project they just created** (404) and it does not
appear in their own list (`total=0`). Cause: the request has no scope field, so the row is
born with `organization_id IS NULL`, and `_scope_covers`
(`backend/services/authorization.py:1199-1204`) matches an ORGANIZATION grant only against
a non-NULL `resource.organization_id`. Today only a GLOBAL principal can see a newly
created project. The probe test file is at
`D:/CODING/Scratch/deploy1/be019/probe_project_scope.py` (kept out of the repo test tree;
it was verified to leave 0 orphan rows in the disposable suite DB).

This is inside the owner's contract ("with appropriate organization … validation"), and it
decides D-3 below.

---

## 2. The migration (one additive revision, no column changes)

Template: `alembic/versions/v2w3x4y5z032_be038_analysis_lifecycle_audit.py` — drop and
recreate the one vocabulary CHECK, build the value list from `AUDIT_EVENT_TYPES` so the
migration can never drift from the model, and refuse downgrade because the ledger is
append-only.

1. **New file** `alembic/versions/w3x4y5z6a033_be039_project_created_event.py`
   (`revision = "w3x4y5z6a033"`, `down_revision = "v2w3x4y5z032"`).
   `upgrade()`: drop `ck_audit_ledger_event_type_domain`, recreate it from
   `sorted(AUDIT_EVENT_TYPES)`. `downgrade()`: `raise
   RuntimeError("BE-039 cannot downgrade an append-only audit vocabulary")`.
   No table, column, index, or constraint other than that CHECK is touched.
2. **Model**: add `"PROJECT_CREATED"` to `AUDIT_EVENT_TYPES`
   (`backend/db/models.py`, next to the two existing PROJECT entries). The ORM CHECK
   definition follows automatically because it is generated from the frozenset.
3. **Test pins** (exactly two files):
   - `tests/unit/test_be030_ledger_contract.py:33` → `96` becomes `97` (and the test name).
   - `tests/unit/test_migrations.py:61` → `EXPECTED_HEAD = "w3x4y5z6a033"`; `:70` →
     `EXPECTED_REVISION_COUNT = 28`; append one line to the bump-history comment.
4. **No permission or role changes**, therefore **no catalogue seed revision**. (The seed
   migration `u1v2w3x4y031` documents that a permission added to the constants needs its
   own seed revision — this plan deliberately avoids adding one; see D-2.)
5. **Historical ledger rows are never rewritten**, and the payload for the new event is
   built to the existing scrubbing rules.

Proof sequence before anything is claimed: disposable suite DB
(`poa_disp_suite`, currently at head) → `alembic upgrade head` → assert the CHECK accepts
`PROJECT_CREATED` and still rejects a bogus type → assert the 97-member vocabulary tests
and `test_migrations` pass → re-run the chain verification (the new event must chain like
every other).

---

## 3. The endpoint contract (four points, one open question each)

**Common shape**: `create_project` moves out of the endpoint's inline `db.add/commit` and
into a service function (`backend/services/authorization.py`, beside `change_project_scope`
and `change_project_owner`, which already use `_lock_row` + `_audit_admin` + one commit),
so creation and its `PROJECT_CREATED` record commit or roll back together. The endpoint
keeps `require(...)` as the guard and passes the verified principal; the body value is
validated, never trusted, exactly as `derive_actor` does.

1. **Default owner** — `ProjectCreate.owner_id` becomes optional. When absent, the owner is
   `principal.principal_id` **and** the principal must be an authenticated USER. `dev-user-*`
   tokens resolve a real, ACTIVE user row (`backend/security/authentication.py:87-97`), so
   the derived id is always a valid `users.id` FK; no new `users` row can be invented from a
   token.
2. **Delegated ownership** — a supplied `owner_id` that differs from the caller is accepted
   only through an explicit authorization path. **This is decision D-2.** Target-user
   validation mirrors `change_project_owner`: the user must exist and be ACTIVE
   (`status == "ACTIVE"` and `is_active`), otherwise 404 / 422.
3. **Actor attribution** — `actor_id` in the audit row is always `principal.principal_id`
   (via `derive_actor`, which already 403s on `ACTOR_MISMATCH`). Requested owner ≠ creator:
   the payload records both (`owner_id` and `created_by`), so a delegation is auditable as a
   delegation.
4. **Audit** — one `PROJECT_CREATED` event: `resource_type="project"`,
   `resource_id=project.id`, `project_id=project.id`, `actor_id=<principal>`,
   `payload={"name", "owner_id", "created_by", "organization_id", "organizational_unit_id"}`
   (organization goes in the payload because the table has no column for it — the same
   convention adopted for `EXTERNAL_SYSTEM_CREATED` in the integration pass).

`AUTH_MODE=development` anonymous callers stay working: they have no verified identity to
derive from, `AUTH_MODE=enforcing` returns 401 before the handler runs, and this is the same
documented exception `backend/security/attribution.py` already makes. A dev-mode anonymous
`POST /projects` still needs an explicit `owner_id` (it cannot be derived) and keeps today's
existence + ACTIVE check.

---

## 4. Decisions I need before writing code

**D-1 — revision id / task label.** Proposed `w3x4y5z6a033`, labelled BE-039 (there is no
task file for BE-038 either, so the label is just the next number in the chain). Objection
costs one rename.

**D-2 — what authorizes a delegated owner.** Three shapes, all provable:
- **A (recommended): delegated ownership requires a GLOBAL grant.** The caller may name
  another owner only if their `project.create` is held at GLOBAL scope. Precedent already in
  the codebase: `change_project_scope` refuses to clear a project's scope without GLOBAL
  authority. Cheapest: no new permission, no new migration, no user→organization derivation;
  three tests (self-create ok, org-scoped delegation 404/403, GLOBAL delegation 201 + audit).
  Consequence: an org-scoped supervisor can only create projects for themselves — which is
  what policy P2 already implies.
- **B: organization-scoped delegation.** Derive the target user's organization set from their
  active `user_role_assignments` (unit grants resolve to the parent org; project grants to
  the project's org) and require the caller's `organization.manage` to cover it. Faithful to
  "appropriate organization … validation", but `User` has no organization column, a user can
  sit in several organizations, and "must cover all of them" vs "covers one" is a semantic
  choice that needs its own test matrix. Roughly the same size as the whole integration pass.
- **C: a new permission** (e.g. `project.create.delegate`). Most explicit in the catalogue,
  but it forces a **second** additive migration (the seed revision) plus the catalogue-pinned
  tests, for the same guarantee A gives for free.

**D-3 — the born-unscoped defect from §1.1.** Options:
- **Fix in this pass (recommended): scope at birth is derived server-side, never from the
  body.** If the caller's `project.create` grant sits at exactly one ORGANIZATION (or unit)
  scope, the new project is born inside that scope; a GLOBAL or ambiguous (multi-org) caller
  gets an unscoped project as today. No new request field, nothing the caller can lie about,
  and the probe assertion (`read == 200`, `listed == True`) becomes a kept test.
- Fix by auto-granting the creator a PROJECT-scope role assignment on their own project.
  Fixes the same symptom but makes project creation a side-effecting identity mutation — a
  bigger policy statement.
- Record and defer; keep creation unscoped, and the creator still cannot read their project.
  I would not recommend shipping the contract while this is true, because it makes the new
  `PROJECT_CREATED` event the only record that the project exists for its own creator.

**D-4 — API-client principals.** `Project.owner_id` is a NOT NULL FK to `users`, and an API
client has no user row. Proposal: a client principal may create a project only with an
explicit `owner_id` **and** the D-2 delegation authority; otherwise 422 ("owner_id is
required for non-user principals"). Alternative: refuse clients outright at this route.

**D-5 — the same hole in `POST /projects/{project_id}/ownership`.** Its guard pins authority
over the project's *current* scope, and `change_project_owner` validates the target user only
for existence + ACTIVE — so today a project-scoped admin can hand a project to any user id in
the database. That is the identical "authority by supplying an id" invariant the owner approved
for the integration family, applied to ownership. Recommendation: close it in this pass with
the same D-2 rule (it is the destination half of contract point 2), extending the existing
`test_be019_integration_scope.py`-style assertions to the ownership route.

**D-6 — where the migration is applied, and the ordering constraint.** The emitting code and
the migrated database must not be deployed independently: `pofa_dev` is at `t0u1v2w3x030` and
its CHECK rejects `PROJECT_CREATED` today, so project creation on `pofa_dev` would fail
(500) the moment this code runs against it. Proposed sequence: (1) implement + prove on the
disposable DB and `pofa_test`; (2) full armed suite; (3) owner approves a fresh `pofa_dev`
backup, then `alembic upgrade head` on `pofa_dev` (it is 3 revisions behind — the catalogue
seed and BE-038 land with it), then restart. Nothing is applied to `pofa_dev` without a
separate explicit go-ahead, and the local API is currently stopped, so there is no live
breakage in the meantime.

---

## 5. Tests to be added (all against the disposable suite DB, enforcing mode)

1. Default owner is the principal: create with no `owner_id` → 201, row owner == caller.
2. Impersonation refused: org-scoped caller names another user → refused, **and the project
   count is unchanged afterwards** (the pattern used in the integration pass: a refusal that
   still wrote the row would still look like a refusal).
3. Ghost owner id → 404/422 before any row exists; inactive target user → 422.
4. Authorized delegation → 201, owner == target, audit `actor_id` == caller, payload
   `owner_id` == target and `created_by` == caller (the two concepts stay distinct).
5. `PROJECT_CREATED` lands: exactly one ledger row for the new project id, actor correct.
6. Atomicity: force the audit append to fail → the project row is absent (no half-state).
7. Vocabulary: 97 members; migration CHECK accepts `PROJECT_CREATED` and rejects a bogus type;
   `test_migrations` head/count; chain stays valid.
8. §1.1 regression: the creator can read and list their own project after creation.
9. Dev-mode anonymous passthrough still creates with an explicit owner (blasts radius guard).

## 6. Blast radius (measured)

`owner_id` appears on 29 POST-to-`/projects` request lines across the test tree; making the
field optional is backwards-compatible for all of them **provided** the dev-mode anonymous
path keeps accepting a body owner. `openapi.json` is a hand-committed snapshot and will be
refreshed as part of this change. No frontend exists, so no external caller breaks.

## 7. Out of scope for this pass (recorded, not fixed)

The four remaining resource-less integration writes (`POST /references`,
`POST /integrations/evidence/external`, `POST /claims`, `POST /webhooks`) already listed in
the §4B closure table; the backfill of the 5 pre-existing NULL-scope `RetentionHold` rows;
notification-delivery reads (8.5); quarantine (#215) and everything after it.
