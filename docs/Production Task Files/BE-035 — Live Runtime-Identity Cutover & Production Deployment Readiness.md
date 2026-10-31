# BE-035 — Live Runtime-Identity Cutover & Production Deployment Readiness

## 1. Mission

Repository: `D:\CODING\Projects\Proof-Of-Action-Final`

You are my autonomous engineering agent for Proof-Of-Action (PoA). I am the sole developer and project owner.

BE-035 follows the completed BE-034 milestone.

BE-034 proved on a disposable clone of the current `pofa_dev` database that:
- The database was restored at migration revision `t0u1v2w3x030`.
- The `poa_runtime` role could read ledger history and append through the application's own `append_event` path.
- Unauthorized ledger UPDATE, DELETE, TRUNCATE and privilege escalation attempts were denied.
- The authenticated anchored-verification endpoint worked.
- The known historical-gap classification remained stable.
- The API could start and report PostgreSQL healthy while using `poa_runtime`.
- Focused regression tests passed: 84 passed.
- The live `pofa_dev` database was not modified by BE-034.

The remaining task is to switch the actual development application from its current owner-level database identity to `poa_runtime`, restart the relevant development API/workers, and verify the running system.

**BE-035 is an operational cutover milestone, not another broad backend audit.**

The project owner has authorized proceeding with BE-035. This authorization is not permission to deploy to production, expose credentials, bypass recovery requirements, or make changes outside the defined development cutover.

### Required final outcome

Establish, with real evidence, whether:
1. The actual development API uses `poa_runtime`.
2. The actual development workers use the intended least-privilege identity.
3. Normal application operations still work.
4. Ledger append-only protections remain effective.
5. The historical audit gaps remain accurately classified.
6. API, readiness, worker and observability checks pass.
7. Production deployment can proceed, or which exact external deployment steps remain.

Do not declare production readiness merely because the development cutover succeeds.

## 2. Mandatory safety rules

### Git and user changes

Inspect the repository root, branch, HEAD, working tree, untracked files and diffs before making changes.

- Preserve all existing user modifications.
- Never use `git add .`, `git add -A`, `git clean`, `git reset --hard`, destructive checkout/restore or history rewriting.
- Do not stage, commit or push anything.
- Do not revert unrelated documentation deletions or modifications.
- Exclude `backend/.venv312_clean/`, `backend/.venv312_repro/`, `backend/BE-023_Status.txt` and `backend/BE-023_Summary.txt` from commit work.
- Do not assume the last reported HEAD or working-tree state remains current.

### Protected databases and live operations

The protected databases are `pofa_dev` and `pofa_test`.

BE-035 is authorized to perform the specifically scoped development runtime-identity cutover, subject to all preflight and recovery gates in this prompt.

Do not interpret this as permission to reset, truncate, downgrade, clean, backfill, repair or rewrite historical data in either protected database.

Never use a protected database for destructive experiments. Use a named disposable database for write-based tests.

The development cutover must be restricted to the confirmed development deployment. Do not switch production credentials, deploy production services, or modify an external production secret store as part of this milestone.

If the target environment cannot be conclusively identified as the intended development environment, stop before the live change.

### Audit history

Never delete, update, renumber, fabricate, reconstruct or reorder historical ledger events to make verification appear clean.

Do not weaken append-only enforcement or database safety guards.

The seven historical gap ranges are existing findings, not permission to ignore new gaps or hash mismatches.

### Secrets

Never print credentials, JWT secrets, tokens, passwords or password-bearing connection strings into logs, reports, console output or committed files.

Do not place the `poa_runtime` password into source code, command-line arguments that are exposed to process listings, shell history, or documentation.

Use the existing secure secret-provisioning mechanism where available. If the mechanism cannot be used safely, stop the affected operation and explain exactly what is missing.

## 3. Phase A — Preflight

Inspect the current repository and reconcile the BE-033 and BE-034 reports with the canonical backlog.

Read:
- `docs/BE-033 Live Enforcement Rollout and Production Readiness Report.md`
- `docs/BE-034 Runtime Identity Cutover and Live Service Verification Report.md`
- `docs/Backend Technical Debt and Deferred Fixes Backlog.md`
- `docs/BE-032R Operational Runbook - Runtime Roles, Ledger Migration, Restart & Recovery.md`
- `scripts/provision_runtime_roles.sql`
- `backend/services/audit_integrity_baseline.py`
- The current database configuration, guarded engine creation, authentication configuration, worker entry points, health endpoints, audit-ledger writer and Alembic environment.

Confirm the actual paths rather than assuming they exist exactly as reported.

Record:
1. Current branch and HEAD.
2. Existing uncommitted changes.
3. Actual development API and worker launch mechanisms.
4. Current effective database identity without exposing credentials.
5. Current development database revision and ledger count.
6. Whether `poa_runtime` exists, its role properties and its effective privileges.
7. Whether the application can use a separate runtime URL without accidentally inheriting the owner URL.
8. How the existing processes will be stopped and restarted.
9. Where a fresh backup can be stored outside the repository.
10. How to verify and recover from a failed cutover.

Do not repeat the entire BE-032R/BE-033/BE-034 test matrix unless the current state contradicts previous evidence.

## 4. Phase B — Validate runtime-role readiness

Inspect the actual role and privilege state of `pofa_dev` using read-only queries.

Verify that:
- `poa_runtime` exists.
- It is not a superuser.
- It does not own protected audit-ledger tables.
- It cannot perform unauthorized UPDATE, DELETE or TRUNCATE operations on protected ledger data.
- It cannot elevate itself to `postgres`.
- It has the minimum privileges required for legitimate application and worker operations.
- Migration privileges remain separate from runtime privileges.
- Required ordinary-table operations used by workers are granted only where needed.

If any property differs from the documented state, investigate before proceeding.

Do not re-run the role-provisioning script blindly. Review whether it is idempotent and whether its effects match the current authorization. Do not make broad grants merely to fix a runtime error.

Use the disposable clone if privilege behavior needs additional experimentation.

## 5. Phase C — Fresh recovery point

Before changing the live development application configuration or restarting services:

1. Confirm the current `pofa_dev` database is at the expected revision.
2. Take a fresh, consistent backup of the actual current development database.
3. Store it outside the repository and record its size and SHA-256 checksum.
4. Restore it into a named disposable database.
5. Verify that the restored revision, ledger row count and enforcement objects match the live source.
6. Verify that the disposable restoration is usable.
7. Confirm the backup is not the older pre-BE-033 dump.

The previous BE-033 backup is historical and is not a substitute for a fresh recovery point.

`archive_mode=off` means a dump is a consistent snapshot, not point-in-time recovery. Document this limitation accurately.

Do not proceed if backup or restore verification fails.

## 6. Phase D — Cut over the actual development runtime identity

### Objective

Switch the actual development API and workers from the PostgreSQL owner identity to `poa_runtime`.

### Procedure

1. Identify every configuration source that can set `DATABASE_URL`, including environment variables, `.env` files, launch scripts and service configuration.
2. Determine the precedence rules so the owner-level URL cannot silently override the runtime URL.
3. Preserve the original configuration securely so recovery is possible.
4. Configure the development application and workers to use the approved `poa_runtime` connection.
5. Keep migration credentials separate.
6. Do not put secrets into source code, tracked configuration, documentation or logs.
7. Stop the actual development API and workers cleanly.
8. Confirm no old process remains running with the owner-level database connection.
9. Start the API and workers through their real launch mechanisms using the runtime identity.
10. Inspect startup logs and verify the effective role through a safe database identity check.
11. Confirm that the application did not silently fall back to `postgres`.

If the application currently has no safe way to provision runtime credentials, implement or document the narrowest suitable configuration change without exposing secrets.

Do not change the production environment or external deployment store.

### Failure handling

If a process cannot start:
- Preserve logs without secret values.
- Determine whether the cause is authentication, permissions, configuration or an unrelated dependency.
- Do not add unrestricted grants or restore owner credentials as a permanent workaround.
- If recovery requires restoring the prior development configuration, follow the documented recovery procedure and report the actual identity afterward.
- Do not claim the cutover succeeded unless the running processes demonstrably use `poa_runtime`.

## 7. Phase E — Verify the running API

Against the actual development API running with `poa_runtime`, test the health surface according to its real implementation:

- `/api/v1/health`
- `/api/v1/ready`
- `/health`
- `/ready`
- `/healthz`
- `/metrics`

First inspect which paths are actually registered. A route that is not implemented must be reported as such, not counted as a successful check.

For each existing endpoint, record:
- HTTP status.
- Relevant safe response fields.
- Whether the readiness result explicitly confirms PostgreSQL health.
- Whether Redis and object storage dependencies report their real status.
- Any startup or runtime errors.

A static health response returning HTTP 200 is not proof of database connectivity. Use readiness and database identity evidence to establish the effective runtime connection.

## 8. Phase F — Verify worker behavior

Inspect the actual worker implementations and their database access requirements.

Do not invoke a worker method that sends external webhooks, emails or other network side effects merely to test startup.

Verify:
1. Each relevant worker starts successfully.
2. The worker uses `poa_runtime`, not `postgres`.
3. Its ordinary database reads and writes work within the granted privileges.
4. The worker can use the shared `append_event` path where applicable.
5. An appropriate safe smoke test completes without creating unintended business records.
6. Logs contain no credential leakage or unexpected permission errors.

If a meaningful worker test requires external delivery, use a mocked or disposable test environment and state the limitation clearly.

Do not claim a worker append or delivery succeeded unless the operation was actually executed and verified.

## 9. Phase G — Verify audit integrity and append-only protections

Use the existing implementations:
- `verify_chain_classified()`
- `audit_integrity_baseline.py`
- `GET /api/v1/audit/verify/anchored`
- The established audit writer `append_event`.

Before and after the smoke tests, record the relevant integrity classification and ledger state.

Expected behavior:
- The approved historical seven-gap baseline remains visible.
- The classification reports the known historical gaps rather than concealing them.
- No new gaps or hash mismatches are introduced.
- Unauthorized UPDATE, DELETE and TRUNCATE attempts remain denied.
- The runtime role cannot elevate itself to `postgres`.
- Legitimate application appends work and preserve chain behavior.

Prefer read-only verification for existing history.

For a write smoke test, use a documented, safe operation with a clearly identified test event and verify that it creates no unintended business records. If a suitable live-development test event cannot be justified, perform the write test on a disposable clone and report the limitation.

Never attempt to remove the smoke-test event from the ledger merely to restore the previous row count. Append-only history must remain intact.

## 10. Phase H — JWT secret and deployment readiness

The application-side production validator has been implemented and tested. That does not prove that a real production deployment has a valid secret configured.

Verify:
- Production mode rejects `changeme`, an empty secret and a secret shorter than 32 characters.
- Valid secrets are accepted without appearing in logs.
- Development configuration continues to behave as designed.
- The effective production configuration path is documented.
- The actual deployment mechanism can inject a distinct secret of at least 32 characters.

The BE-034 report states that no production deployment secret store exists in this environment.

Do not invent one or claim a secret was injected.

If there is still no production deployment target or secret store, record the production configuration requirement as an external deployment action and continue with the development cutover.

Do not call the project production-ready merely because the application validator works.

## 11. Phase I — Regression tests

Use the known reproducible Python environment if it still exists:

`backend/.venv312_repro/Scripts/python.exe`

Verify the actual interpreter path before using it.

Use an explicitly selected test database. Never allow tests to silently target `pofa_dev` or fall back to `.env`.

Run the relevant focused suites for:
- Database safety.
- Runtime role and permission behavior.
- Audit-ledger enforcement.
- Historical-gap classification.
- Anchored verification.
- Authentication and JWT configuration.
- Health/readiness behavior where automated tests exist.
- Relevant integration tests.

If source code is changed, add focused tests and run the full relevant regression suite after the implementation stabilizes.

The BE-032R historical baseline was 821 passed, 1 skipped, 0 failed. BE-034 reported 84 focused tests passed. These are comparison points, not claims about a new test run.

Capture exact commands, target database, exit status, pass/fail/skip counts and failure summaries.

Do not weaken security assertions or modify the historical ledger to make tests pass.

## 12. Phase J — Documentation and backlog

Update `docs/Backend Technical Debt and Deferred Fixes Backlog.md` and create:

`docs/BE-035 Live Runtime-Identity Cutover and Production Deployment Readiness Report.md`

Record:
- The actual configuration change and files modified.
- The effective database identity for the API and each relevant worker.
- Backup location, checksum and restore evidence.
- The actual restart results.
- Endpoint results.
- Worker verification results.
- Before/after audit classification.
- Evidence that unauthorized ledger mutations remain denied.
- Regression test commands and results.
- JWT configuration verification and deployment-store limitations.
- Recovery procedure and whether it was needed.
- Any work that remains blocked.

Keep statuses distinct:
- Implemented and unit-tested.
- Proven on a disposable clone.
- Applied to live development.
- Verified against a running development service.
- Configured in an actual production deployment.
- Still pending.

Do not label production deployment complete when only development has been verified.

Preserve BE-033 and BE-034 reports as historical records. Do not rewrite them to make the new results appear to have happened earlier.

## 13. Completion gates

### Development runtime cutover
- [ ] API uses `poa_runtime`.
- [ ] Relevant workers use `poa_runtime`.
- [ ] No unintended owner-level application connection remains.
- [ ] Legitimate operations succeed.
- [ ] Unauthorized ledger mutations remain denied.

### Running-service verification
- [ ] Actual health and readiness endpoints pass.
- [ ] PostgreSQL readiness is verified, not inferred from a static 200 response.
- [ ] Worker checks are completed safely.
- [ ] Ledger appends and integrity classification behave as expected.
- [ ] Historical gaps remain preserved.
- [ ] No new unexplained integrity anomalies appear.

### Security and recovery
- [ ] Fresh backup and restore proof are recorded.
- [ ] Runtime and migration identities remain separated.
- [ ] No secrets are exposed.
- [ ] Recovery instructions match the actual configuration.

### Production deployment
- [ ] Production deployment target is identified.
- [ ] A distinct valid production JWT secret is configured.
- [ ] Production runtime identity is configured.
- [ ] Production health and integrity checks are performed.
- [ ] All mandatory production gates have evidence.

If the production target or secret store is absent, mark this gate pending rather than inventing evidence.

## 14. Final verdict

Choose and justify one:

**DEVELOPMENT RUNTIME CUTOVER VERIFIED — PRODUCTION DEPLOYMENT PENDING**

The actual development API/workers use the least-privilege role and the running-service checks pass, but production deployment has not been verified.

**BE-035 PARTIALLY COMPLETE — CUTOVER BLOCKED**

A concrete configuration, permission, recovery or service issue prevents the cutover. Report the exact failure and required action.

**PRODUCTION READY**

Use only if a real production deployment exists, its runtime identity and secret are correctly configured, and all mandatory production health and integrity checks have passed.

A successful development cutover alone is never sufficient for the third status.

## 15. Final response

Report:
1. Final verdict.
2. Actual development DATABASE_URL identity, without credentials.
3. API and worker identity verification.
4. Endpoint results.
5. Ledger classification before and after verification.
6. Backup and restore evidence.
7. JWT configuration and production-store status.
8. Exact test commands and results.
9. Files changed.
10. Recovery or rollback performed, if any.
11. Remaining production actions.
12. Actual branch, HEAD and working-tree state.
13. Whether another milestone is needed and the narrow scope of that milestone.

Start with Phase A and proceed through the safe and authorized development cutover. Do not stop after creating a plan. Do not silently expand the task into production deployment, and do not claim production clearance without evidence.