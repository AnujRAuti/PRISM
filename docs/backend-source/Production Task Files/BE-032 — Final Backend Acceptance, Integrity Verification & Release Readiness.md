# BE-032 — Final Backend Acceptance, Integrity Verification & Release Readiness

## 1. Mission

Act as a senior backend architect, QA lead, database reliability engineer, security engineer, and release-readiness reviewer for the existing Proof-of-Action (PoA) backend.

Execute **BE-032: Final Backend Acceptance, Integrity Verification & Release Readiness**.

This is the final planned backend acceptance milestone following BE-031.

Your mission is to establish, using verifiable evidence, whether the backend is ready for its intended release, which risks remain open, which actions require explicit owner authorization, and which acceptance criteria are still blocked.

This is an evidence-driven acceptance milestone, not an architecture rewrite or an excuse to implement speculative fixes.

You must:

1. Establish the actual repository and environment baseline.
2. Reconcile BE-023 through BE-031 and the canonical technical-debt backlog.
3. Verify migration history, schema state, identity constraints, database safety, audit-ledger enforcement, and critical API behavior.
4. Run appropriate tests safely and record fresh results.
5. Assess outstanding operational gaps and owner decisions.
6. Prepare remediation and deployment plans for owner-gated actions.
7. Produce a final acceptance report and an explicit release recommendation.

**A truthful `ACCEPTANCE BLOCKED` result is preferable to an unsupported claim of completion or production readiness.**

## 2. Known Project Context

The backend uses:

- FastAPI.
- SQLAlchemy 2.x.
- Alembic.
- PostgreSQL 15.
- PostGIS.
- pgvector.
- API routers under `/api/v1`.
- Authentication and authorization.
- Evidence ingestion and related processing.
- An append-only audit ledger.
- Background processing.

Inspect the actual repository before relying on this context. Verify the current implementation, migration history, test configuration, and documentation.

### Previous milestone history

- BE-027: backend foundation and CORS/request-ID hardening.
- BE-028: schema-drift containment.
- BE-029: user identity constraints and retirement of synthetic identity fixtures.
- BE-030: audit-ledger enforcement and integrity-related work.
- BE-031: production operations, deployment, backup, recovery, and operational-readiness assessment.

Read the actual specifications, code, and results reports. Do not assume that every reported result remains current.

### Historical baseline reported by BE-031

| Environment | Reported revision | Reported ledger state |
|---|---|---|
| `pofa_test` | `t0u1v2w3x030` | 42,545 rows, zero gaps, enforcement present |
| `pofa_dev` | `s9t0u1v2w029` | 6,023 rows, 36 missing sequence numbers across seven gap ranges, enforcement absent |

BE-031 reported a single Alembic head, `t0u1v2w3x030`, and a clean `alembic check` on `pofa_test`, with the known `uq_user_role_scoped` `nulls_not_distinct` comparison artifact handled by the documented BE-030 filter.

These are historical observations. Verify the current state using safe, read-only inspection. Do not mutate either database to make it match the report.

### BE-031 test results

BE-031 reported:

- Full suite: 792 passed, 1 skipped, 0 failed.
- Targeted matrix: 123 passed, 0 failed.
- The skip was `test_preflight.py:117`, concerning whether the ML stack was genuinely installed.
- Documentation-only changes were reported.
- No migrations, service restarts, live deployment, commits, or pushes were performed.

Use these counts only as historical comparison points. Obtain fresh test results for BE-032.

## 3. Non-Negotiable Safety Rules

### 3.1 Protected databases

The following databases are protected:

- `pofa_dev`
- `pofa_test`

BE-032 defaults to read-only inspection of these environments.

Do not perform database resets, destructive cleanup, live migrations, backfills, role/grant changes, destructive restores, write-capable probes, or tests that mutate either database.

Do not restart the API or workers, deploy live, or change production infrastructure.

Any exception requires explicit, operation-specific user authorization and a separate safety review. The authorization must not be inferred from this prompt.

Before running a database command, inspect the actual code path and determine whether the operation is read-only or write-capable.

A command is not safe merely because it contains words such as `check`, `verify`, `dry-run`, or `test`.

For write-capable tests:

1. Explicitly select a disposable database.
2. Verify the resolved connection target.
3. Prove that `.env` fallback cannot redirect the operation.
4. Confirm the database is disposable and intended for that test.
5. Stop if any of these conditions cannot be established.

Never silently fall back to `.env`, a default connection, or a protected database.

### 3.2 Audit-ledger protection

The audit ledger is append-only.

Never:

- Update or delete historical ledger events.
- Truncate the ledger.
- Renumber events.
- Manufacture missing events.
- Rewrite historical hashes.
- Reset sequence values to eliminate gaps.
- Suppress integrity failures to obtain a passing result.
- Modify history to make acceptance tests pass.

The reported `pofa_dev` gaps must remain preserved unless an authorized, separately governed recovery process is established. BE-032 itself must not repair them.

Do not decide the unresolved BE-030 policy for writers encountering an already-invalid chain. If no approved policy exists, retain it as an explicit blocker.

### 3.3 Identity and schema protection

- Preserve BE-029 username/email uniqueness constraints.
- Do not reintroduce retired synthetic identity fixtures.
- Do not decide the unresolved `external_subject` nullability/backfill policy.
- Do not drop extension-owned objects such as PostGIS `spatial_ref_sys`.
- Do not rewrite applied migration history.
- Do not suppress actual schema drift under the guise of handling a known comparison artifact.

### 3.4 Git and working-tree safety

Before modifying files:

1. Run `git status --short --branch`.
2. Record the branch and HEAD.
3. Inspect modified and untracked files.
4. Identify changes that predate BE-032.
5. Preserve unrelated changes and existing deletions.

Never run:

- `git add .`
- `git add -A`
- `git clean`
- `git reset --hard`
- Destructive checkout/restore commands.
- History rewriting.
- Force-push.

Explicitly exclude these paths from any staging or commit operation:

- `backend/.venv312_clean/`
- `backend/.venv312_repro/`
- `backend/BE-023_Status.txt`
- `backend/BE-023_Summary.txt`

Do not stage, commit, or push during BE-032.

Do not overwrite changes belonging to another process. If the scope or ownership of a change is unclear, preserve it and stop the affected operation.

## 4. Phase One — Establish the Baseline

Inspect the actual repository structure and relevant files, including where present:

- `backend/app/main.py`
- Database engine and session configuration.
- `backend/db/safety.py`
- `backend/db/models.py`
- Alembic environment and migration files.
- API routers and dependencies.
- Authentication and authorization.
- Audit-ledger implementation and enforcement.
- Background worker entry points.
- Environment configuration and examples.
- CI workflows and test fixtures.
- Database-target safety tests.
- Schema-drift checks.
- BE-027 through BE-031 results reports.
- Canonical technical-debt backlog.
- Deployment, operations, backup, and recovery documentation.

Discover actual paths rather than assuming the list is exhaustive.

Record:

- Branch, HEAD, and working-tree state.
- Python and dependency versions.
- Available test and infrastructure prerequisites.
- Repository migration heads.
- Database revisions where safely observable.
- Test commands and fixture behavior.
- Existing health/readiness mechanisms.
- Current operational and release limitations.

Clearly distinguish historical reports, fresh observations, inferences, and unverified claims.

Do not perform database writes during baseline discovery.

## 5. Phase Two — Backlog and Decision Reconciliation

Find the existing canonical backend technical-debt backlog. If none exists, use:

`docs/Backend Technical Debt and Deferred Fixes Backlog.md`

Reconcile relevant items from BE-023 through BE-031 against the actual repository.

Classify each item as:

- Resolved and verified.
- Implemented but not fully verified.
- Partially resolved.
- Deferred.
- Blocked by an owner decision.
- Superseded.
- Unresolved.

Do not silently close unresolved items.

### 5.1 OQ-3 — `external_subject`

Verify the current model, database schema, and all relevant read/write paths.

Determine whether the field remains effectively write-only or inert. Do not manufacture values, backfill historical data, add a `NOT NULL` constraint, or alter authentication semantics without an approved decision.

Document the exact decision required and its consequences.

### 5.2 Invalid-chain writer policy

Determine whether an approved policy exists for writers encountering an already-invalid audit chain.

If not, leave the decision open. Do not independently choose refusal, controlled continuation, or governed recovery.

### 5.3 F-03 — Anchored/checkpoint control

BE-031 reported that the §9 anchored/checkpoint control was not wired to an endpoint.

Verify the implementation and its actual availability. Establish whether it is internal-only, scheduled, callable, or otherwise exposed.

Do not expose it merely to close an acceptance checklist. Document the intended consumer, authorization, semantics, and safety requirements.

### 5.4 F-04 — Historical versus newly detected gaps

BE-031 reported that runtime logic does not distinguish known historical gaps from newly detected gaps.

Verify the current implementation. Do not suppress an integrity error because a similar gap was previously recorded.

If an approved policy does not exist, document the design options, risks, and required owner decision.

### 5.5 F-05 — TRUNCATE protection

BE-031 reported that both database environments connected as the database owner and that stronger `TRUNCATE` protection requires a non-owner application role.

Inspect ownership, privileges, and existing trigger behavior using read-only checks where possible.

Do not change roles or grants in protected databases. Prepare a disposable-environment proof and rollout plan.

### 5.6 Live `pofa_dev` migration

Verify the current revision and enforcement state read-only.

Do not run a live migration. Any future migration requires a fresh backup immediately before the operation and a successful restoreability test using a disposable target.

The historical BE-029 backup predates BE-029 and is not a valid current restore point.

Prepare the prerequisites and explicit owner-approval gate.

### 5.7 Other deferred items

Verify, where applicable:

- `uq_user_role_scoped` Alembic comparison artifacts.
- Expression/GiST index reflection limitations.
- The legacy `audit_events` table, if it remains.
- API/worker restart status.
- Backup and recovery limitations.
- Known test skips.
- Other unresolved items in the canonical backlog.

Do not expand scope into unrelated features.

## 6. Phase Three — Migration and Schema Acceptance

Inspect the Alembic revision graph and migration files.

Verify:

- A single intended head exists, or justified branching is documented.
- Revision dependencies are valid.
- The latest revision agrees with repository documentation.
- Recent migration behavior has appropriate tests.
- No accidental orphaned or duplicate revision files exist.
- Known comparison artifacts follow the documented policy.
- Actual schema drift is not silently ignored.

Where safe, inspect protected database revision metadata read-only.

Do not apply or downgrade migrations against protected databases.

For any disposable-database migration test, verify the target, connection resolution, and absence of fallback before execution.

Report schema acceptance separately for each environment. A clean schema comparison does not establish audit enforcement, privilege safety, data integrity, or runtime correctness.

## 7. Phase Four — Audit-Ledger Acceptance

Assess audit integrity using the existing approved verification mechanisms.

Verify:

- Append-only enforcement.
- UPDATE and DELETE protection.
- TRUNCATE protection status.
- Hash/chain verification.
- Sequence continuity.
- Historical gap reporting.
- Anchored/checkpoint control availability.
- Historical-versus-new gap discrimination.
- Writer behavior when historical integrity is invalid.
- Whether diagnostic checks are read-only.
- Whether enforcement tests use explicitly selected disposable databases.

Test enforcement behavior only in a disposable database.

Do not generate test ledger events in protected databases.

Do not alter historical events to make verification pass.

Report `pofa_test` and `pofa_dev` separately. Passing verification in one environment does not prove equivalent enforcement in the other.

If a runtime policy remains unresolved, report the unresolved policy as a blocker.

## 8. Phase Five — Identity and Authorization Acceptance

Review BE-029 identity constraints and authentication handling.

Verify:

- Username uniqueness.
- Email uniqueness and normalization.
- Provider-subject uniqueness.
- Database indexes and constraints.
- Identity conflict classification.
- Transaction rollback following integrity failures.
- Session usability after rollback.
- Correct handling of unrelated integrity errors.
- Scoped-role behavior.
- Pagination totals and exactly-once traversal.
- Database safety protections.

Use existing tests and isolated fixtures. Any test that can write data must use a disposable database or suitable mocks.

Do not create test users or fixtures in protected databases.

Do not rewrite authentication or introduce unapproved identity policy changes.

## 9. Phase Six — API, Worker, and Operational Acceptance

Review BE-031 deliverables against the actual implementation.

Assess:

- API startup and shutdown.
- Worker startup and shutdown.
- Database connection cleanup.
- Health and readiness.
- Configuration validation.
- Secret redaction.
- Request-ID propagation.
- Error handling.
- Worker retry and idempotency assumptions.
- Migration execution.
- Backup/restore instructions.
- Deployment and forward-fix procedures.
- Proposed RPO/RTO.
- Monitoring and alerting.

Distinguish implemented controls from proposed controls.

Do not claim a backup is recoverable without restoration evidence. Do not claim alerting is active without verifying its configuration. Do not claim restart or deployment behavior was tested when it was not.

Do not restart the API or workers. Produce a prerequisite checklist for a separately authorized restart.

## 10. Phase Seven — Regression Testing

Inspect test fixtures and database selection before running tests.

Execute tests sequentially, never concurrently against a shared database.

Recommended order:

1. Static checks and import/collection checks.
2. Focused database-safety tests.
3. Audit enforcement and contract tests.
4. Identity, authorization, and rollback tests.
5. Migration graph and schema-drift tests.
6. Relevant API integration tests.
7. Broader unit tests.
8. Disposable-database migration/enforcement tests, if safe infrastructure is available.

Use the reported BE-031 suite count of 792 passed, 1 skipped, 0 failed only as a historical comparison point.

Requirements:

- Do not weaken assertions.
- Do not delete failing tests.
- Do not silently skip failures.
- Record all skips and reasons.
- Distinguish unit, integration, and infrastructure-dependent results.
- Report exact commands and pass/fail/skip counts.
- Document environmental blockers honestly.
- Do not claim complete acceptance from a partial suite.

If a test unexpectedly selects a protected database, stop immediately. Never attempt to clean up an accidental ledger event by altering historical records.

## 11. Phase Eight — Release Gate Matrix

Create a release gate matrix with evidence, status, owner, dependencies, and closure criteria.

At minimum, cover:

| Gate | Required evidence | Default disposition |
|---|---|---|
| Repository/test integrity | Fresh tests and reviewed diff | Verify |
| Migration consistency | Valid revision graph and documented schema state | Verify |
| `pofa_test` enforcement | Read-only state and existing test evidence | Verify |
| `pofa_dev` enforcement migration | Fresh backup, restore proof, reviewed plan, explicit authorization | Blocked until approved |
| `external_subject` policy | Recorded product/security decision | Open |
| Invalid-chain writer policy | Recorded governance decision and acceptance tests | Open |
| TRUNCATE hardening | Non-owner role proven in disposable environment | Prepare; do not apply live |
| Anchored/checkpoint exposure | Consumer, authorization, semantics, and safety decision | Open until verified |
| Gap discrimination | Approved policy and testable semantics | Open until verified |
| API/worker restart | Operational checklist and explicit authorization | Do not execute |
| Production deployment | Approved release plan and authorization | Do not execute |
| Backup/recovery | Restore evidence or explicit limitation | Report |
| Git delivery | Reviewed changes and user authorization | No commit/push |

Update the matrix based on actual evidence.

A prepared migration is not an executed migration. A successful disposable test is not proof that a protected database has been updated. An owner-gated action is not resolved simply because its runbook exists.

## 12. Phase Nine — Remediation Rules

Fix only defects that are:

1. Demonstrably within BE-032 scope.
2. Safe to implement without protected-environment mutation.
3. Supported by a clear acceptance requirement.
4. Testable without violating safety constraints.

If no in-scope code defect can safely be fixed, the correct outcome may be a documented acceptance assessment and owner-gated backlog.

For every code change:

- Record the defect and supporting evidence.
- Identify affected files.
- Explain behavioral risk.
- Add or update focused tests.
- Verify unrelated behavior is unchanged.
- Review the final diff.

Do not introduce code changes simply to make the milestone look substantial.

Where a change requires a policy decision, present the options and implications instead of choosing on the owner's behalf.

## 13. Phase Ten — Required Deliverables

Inspect existing documentation first and avoid duplicate reports.

### A. Final Backend Acceptance Report

Suggested path:

`docs/BE-032 Final Backend Acceptance and Release Readiness Report.md`

Include:

- Executive verdict.
- Repository and Git baseline.
- Milestone history and verified state.
- Fresh test results.
- Migration and schema findings.
- Audit-ledger findings.
- Identity and authorization findings.
- Operational readiness.
- Environment-specific differences.
- Owner-gated actions.
- Remaining risks.
- Release recommendation.
- Acceptance criteria and supporting evidence.

### B. Release Gate Matrix

Include each critical gate, evidence, status, owner, dependencies, and closure criteria. This can be part of the main report or an existing release checklist.

### C. Backlog Reconciliation

Update the canonical technical-debt backlog. Do not duplicate issues or close decision-dependent items without approval and verification.

### D. Owner Decision Register

Record decisions required for:

- `external_subject` policy.
- Invalid-chain writer behavior.
- Anchored/checkpoint control exposure.
- Historical-versus-new gap discrimination.
- Authorization for `pofa_dev` enforcement migration.
- Non-owner database role and TRUNCATE hardening.
- API/worker restart, if still required.

For each decision, document options, implications, evidence, and what remains blocked. Recommendations are allowed when supported by evidence, but do not fabricate owner approval.

## 14. Acceptance Criteria

BE-032 can be fully accepted only when every critical gate has sufficient evidence and all mandatory decisions for the intended release have been resolved.

- [ ] Initial Git baseline recorded.
- [ ] Existing changes preserved.
- [ ] Canonical backlog reconciled.
- [ ] Alembic revision graph verified.
- [ ] Schema-drift behavior documented accurately.
- [ ] Audit enforcement assessed independently for each environment.
- [ ] Historical ledger gaps preserved and reported.
- [ ] No historical ledger events rewritten or deleted.
- [ ] Identity and authorization constraints verified.
- [ ] Database safety protections verified.
- [ ] Fresh regression results recorded.
- [ ] Skips and blockers explained.
- [ ] Operational documentation checked against implementation.
- [ ] Backup/recovery claims supported by evidence.
- [ ] Environment differences recorded.
- [ ] Owner decisions registered.
- [ ] Live migration/restart prerequisites documented.
- [ ] No unauthorized database mutation or live operation.
- [ ] Final diff reviewed.
- [ ] No commit or push performed.

If critical gates remain open, use `ACCEPTANCE BLOCKED` or `CONDITIONALLY ACCEPTED — NOT CLEARED FOR PRODUCTION`, as appropriate.

Engineering assessment completion does not itself authorize deployment.

## 15. Final Report Format

Use this structure:

1. **Overall status:** ACCEPTED, CONDITIONALLY ACCEPTED, ACCEPTANCE BLOCKED, or NOT ACCEPTED.
2. **Production recommendation:** CLEARED, CONDITIONALLY CLEARED, or NOT CLEARED.
3. **Repository baseline:** branch, HEAD, initial/final Git status.
4. **Verified findings:** evidence-based summary.
5. **Fresh tests:** exact commands, environment, and pass/fail/skip counts.
6. **Migration/schema acceptance:** revision graph and drift status.
7. **Audit-ledger acceptance:** per-environment enforcement and integrity.
8. **Identity/authorization acceptance:** constraints and behavior.
9. **Operational acceptance:** health, lifecycle, configuration, backup, recovery, logging.
10. **Environment differences:** particularly `pofa_test` versus `pofa_dev`.
11. **Owner decisions:** required decision, options, recommendation, blocker.
12. **Release gate matrix:** gate status and evidence.
13. **Remaining backlog:** severity, dependencies, closure criteria.
14. **Files changed:** paths and rationale.
15. **Safety statement:** protected database handling, ledger preservation, live-operation status.
16. **Git status:** explicit no-commit/no-push confirmation.
17. **Next action:** the single highest-priority step supported by the evidence.

Support every claim with actual repository evidence, test output, or a clearly labeled inference.

## 16. Execution Directive

Start by recording the repository baseline. Reconcile existing milestone reports and the canonical backlog. Perform safe read-only inspection, and run tests only after verifying their targets. Implement only narrow, justified fixes. Prepare owner-gated remediation plans without executing them.

Finish with an evidence-based acceptance verdict.

**Optimize for proving what is correct, exposing what remains uncertain, and preventing release based on unverified assumptions—not for declaring the milestone complete.**