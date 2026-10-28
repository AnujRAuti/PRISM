# Stage 02-3 Report — Resource Scope Closure and Project Creation Identity

Date: 2026-10-17
Branch: `Backend`
Commit that contains this work: `298eac11` "cleanup auth" (parent `7b2f4673`), authored 2026-10-17 09:29 +0530 by the owner, **pushed and synced** (`git rev-list --count origin/Backend..Backend` → 0 ahead, 0 behind). Working tree clean at the time of writing.

Scope: 21 files, +2140 / −98. Two families of work: (A) the resource-scope closures for the integration, publication and retention families, and (B) BE-039 — project creation identity, birth-scope derivation, and the `PROJECT_CREATED` audit event with its additive migration.

---

## 1. Family A — resource scope and ownership rules (owner decisions A and B)

Closes the findings registered in `docs/Authorization Scope Classification — 2026-10-17.md` (§4A rows 8.4b/8.4c, §4B closure table).

| File | Change |
| --- | --- |
| `backend/security/authorization.py` | +35 — `visible_organization_ids()` (:144) added next to `visible_project_ids`, so an organization-scoped read has the same server-derived candidate set as a project-scoped read instead of a caller-supplied filter. |
| `backend/api/v1/endpoints/integration.py` | +118 — external-system/integration reads and writes are constrained to the caller's authorized organizations; cross-tenant ids are refused rather than filtered silently. |
| `backend/repositories/integration.py` | +40 — scope-aware query helpers behind the endpoint. |
| `backend/services/integration.py` | +9/−5 — the `EXTERNAL_SYSTEM_CREATED` audit payload now carries the organization id, so the creation is attributable to a tenant after the fact. |
| `backend/api/v1/endpoints/publication.py` | +55 — `GET /publications/policies` is now `require_global` (a policy list is global configuration); individual policy reads go through `_policy_readable`, which matches the policy's **own** scope columns against the principal's grants. |
| `backend/api/v1/endpoints/retention.py` | +182 — `_resolve_hold_scope` / `_hold_scope_for_row`: a hold whose `scope` is CASE/CLAIM/RESOURCE names a *target*, not a project, so the governing scope is now resolved from the target instead of being stored as NULL. This is what makes the row answerable to a scope check on read. |
| `tests/integration/test_be019_integration_scope.py` | NEW, 574 lines, 8 tests — integration-family scope matrix, each refusal paired with the authorized success in the same test. |
| `tests/integration/test_publication.py` | +95 — global-only policy list, per-policy readability. |
| `tests/integration/test_retention.py` | +180 — hold-scope resolution from the target; the previously NULL-scope rows. |

Head-proof of this family is preserved at `D:/CODING/Scratch/deploy1/be019/head_proof.log`:
`3 failed, 5 deselected, 6 warnings, 2 errors in 10.45s` — i.e. the tests demonstrably detect the pre-fix behaviour.

## 2. Family B — BE-039 project creation identity and audit

Contract (owner-approved, four points) and where each is implemented:

1. **Default owner from the authenticated principal** — `create_project` (`backend/services/authorization.py:807`): with no `owner_id` in the body the owner is the calling user's own id.
2. **Delegated ownership needs an explicit authority** — same function: naming a *different* owner requires a GLOBAL `project.create` grant (`_holds_global`, :950), else 403. GLOBAL was chosen over ORGANIZATION because `users` has no organization column and `resolve_resource_scope` (:1059) has no `user` branch, so an org-scoped delegation would need new derivation logic (decision D-2).
3. **Actor attribution is always the caller** — the audit `actor_id` and `payload["created_by"]` are the authenticated principal; `payload["owner_id"]` is the requested owner. "For whom" and "by whom" stay separate facts. An API-client principal may be the actor but can never be the owner (no `users` row) — it must supply `owner_id` and hold delegation, else 422 (D-4).
4. **Creation and audit commit together** — `append_event` (`backend/services/audit_ledger.py:208`) flushes without committing, so a refused audit aborts the domain write; `test_creation_and_audit_roll_back_together` proves the row is absent afterwards.

Plus the measured defect that was never in the original brief:

- **Birth scope** (`_birth_scope`, `backend/services/authorization.py:779`) is derived from the caller's own `project.create` grant: one unit → (parent org, unit); one org → (org, NULL); GLOBAL/ambiguous/inactive → unscoped. Without this, an organization-scoped supervisor got `201` on POST then `404` on GET of its own project (`Scratch/deploy1/be019/project_scope_probe.log`) because `organization_id IS NULL` is not covered by an ORGANIZATION or PROJECT grant. Body-supplied scope is not accepted — that would violate P4. (D-3)
- **Destination authority on transfer** — `change_project_owner` (:859) now additionally requires GLOBAL `organization.manage` before installing a *new* owner, closing the hole where the guard checked only the source project (D-5).
- **Development-mode exception** — an anonymous request under `AUTH_MODE=development` has no identity to derive from, so it must name an owner and is born unscoped with `payload["created_by"] is None`. This keeps the 29 existing `owner_id` request lines across 15 test files working. It mirrors the documented exception in `backend/security/attribution.py:26`. `security.authentication.is_development_bypass` cannot be imported here (that module imports this one), so the predicate is reproduced with a module-level `settings` import.

Migration (D-1, plan approved in `docs/Project Creation Identity and Audit — Migration Plan — 2026-10-17.md`):

- `AUDIT_EVENT_TYPES` gains `PROJECT_CREATED` (`backend/db/models.py:1079`) — 96 → **97** members.
- `alembic/versions/w3x4y5z6a033_be039_project_created_event.py`: `revision w3x4y5z6a033`, `down_revision v2w3x4y5z032`; drops and recreates `ck_audit_ledger_event_type_domain` from the sorted vocabulary. `downgrade()` raises `RuntimeError("BE-039 cannot downgrade an append-only audit vocabulary")`. **No historical ledger row was altered.** No permission or role changed, so no catalogue-seed revision was needed.
- Pins: `tests/unit/test_migrations.py` → `EXPECTED_HEAD = "w3x4y5z6a033"`, `EXPECTED_REVISION_COUNT = 28`; `tests/unit/test_be030_ledger_contract.py` → `test_event_type_vocabulary_is_exactly_97_members`.
- `tests/integration/test_be039_project_creation_identity.py`: NEW, 486 lines, 8 tests.

## 3. Two test-shape corrections (neither weakens an assertion)

- `tests/integration/test_audit_ledger.py::test_failed_domain_operation_leaves_no_audit_row` failed `8152 == 8151`: it created a project **inside** the window it measures, and a successful creation now audits by design. The POST moved above `before`; the refusal assertions are unchanged.
- The unknown-owner 404 detail had drifted to `"User not found: <uuid>"`. Restored `LookupError("Owner not found")` **in the service**, keeping the published contract, instead of editing the test.

## 4. Verification actually performed (disposable infra only)

| Evidence | Result |
| --- | --- |
| `armfull.py up` → both disposable DBs migrated | `alembic w3x4y5z6a033 \| 75 tables` |
| `be019/be039_newtests_round1.log` | `1 failed, 7 passed` — the org-scoped caller hit the 403 delegation gate before the 404 target lookup |
| `be019/be039_newtests_round2.log` (after routing that case through a GLOBAL holder and adding the no-leak assertion) | `8 passed, 6 warnings in 14.85s` |
| `be019/pins_and_be019_final.log` (migration pins + ledger contract + integration scope family) | `21 passed, 6 warnings in 17.63s` |
| `be019/blast_round3.log` — every test file that POSTs `/projects` | `140 passed, 8 warnings in 310.84s` |
| `be019/focused_regression.log` — affected publication/retention/integration set | `156 passed, 7 warnings in 162.51s` |
| `be019/head_proof.log` — Family A tests at pre-fix source | `3 failed, 5 deselected, 2 errors` (non-vacuity proven) |

## 5. NOT yet done — do not treat this pass as verified

1. **Full armed suite** has not been run since these changes. Last known baseline `1006 passed / 1 skipped / 0 failed` at `61762341`; this batch adds ≥16 tests, so the expected floor is ≈1022 — **unmeasured**.
2. **HEAD-proof of the BE-039 file** has not been run. The baseline to prove against is now `7b2f4673` (not `HEAD`, because `HEAD` = `298eac11` already contains the fix).
3. **`openapi.json` is stale**, measured just now: `ProjectCreate.required` is still `['name', 'owner_id']` although `owner_id` is now optional, and the ownership-transfer summary in the snapshot is still `"...(organization.manage must cover the project)"` while `backend/api/v1/endpoints/auth.py:652` publishes the longer text.
4. The scope-classification document does not yet record the D-1…D-6 outcomes or the §1.1 → FIXED → VERIFIED chain for the 404-on-own-project defect.

## 6. Database posture and the ordering rule

| Database | `alembic_version` | Accepts `PROJECT_CREATED`? |
| --- | --- | --- |
| `poa_disp_suite` / `poa_disp_owner` (disposable) | `w3x4y5z6a033` | yes — proven |
| `pofa_test` | `v2w3x4y5z032` | **no** — 1 revision behind |
| `pofa_dev` (live local dev) | `t0u1v2w3x030` | **no** — 3 revisions behind, 6023 ledger rows / 544 projects, untouched per D-6 |

The CHECK violation is the failure mode if code and migration are separated: with the emitting code in place and the database behind, every creation raises `psycopg2.errors.CheckViolation ... ck_audit_ledger_event_type_domain`. Measured directly — 76 failures before `armfull.py up`. **Rule: `w3x4y5z6a033` must be applied to a database before any process holding this code is allowed to write to it.** Applying it to `pofa_dev` and `pofa_test` is owner-gated (D-6: ask first; fresh `pofa_dev` backup first).

## 7. Carry-over, still open

- Four same-class integration writes not yet scoped: `POST /references`, `POST /integrations/evidence/external`, `POST /claims`, `POST /webhooks`.
- 5 pre-existing NULL-scope `RetentionHold` rows need a backfill decision (code now resolves scope for reads; the stored rows are untouched).
- Notification-deliveries read (row 8.5); `GET /publications/policies` route-shadowing correction; the 185-route scanner note (a candidate count, not a finding count).
- Then stage 02 continues: #215 quarantine, #216 idempotency + uploader attribution + evidence target validation, #217 regression/deploy/live re-verification incl. the real Supabase provider gate. Stage 03 = #218/#219/#220.
- Production is **not** cleared: `AUTH_OIDC_*` unset on the VM, no domain, so no secure public production claim is made.

## 8. Artifacts

Logs and probes: `D:/CODING/Scratch/deploy1/be019/` (`be039_newtests_round1.log`, `be039_newtests_round2.log`, `pins_and_be019_final.log`, `blast_round1..3.log`, `focused_regression.log`, `head_proof.log`, `project_scope_probe.log`, `probe_project_scope.py`, `orphan_inventory.py`, `orphan_cleanup.py`, `headsrc/*.bak`).
Disposable stack: `poa_disp_pg`, `poa_disp_redis`, `poa_disp_minio` still **up** — tear down with `armfull.py down` only after the remaining runs.
