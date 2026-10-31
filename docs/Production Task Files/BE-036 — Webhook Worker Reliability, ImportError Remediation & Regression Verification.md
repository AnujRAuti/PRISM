# BE-036 — Webhook Worker Reliability, ImportError Remediation & Regression Verification

## 1. Mission

Repository: `D:\CODING\Projects\Proof-Of-Action-Final`

You are my autonomous engineering agent. I am the sole developer and project owner.

BE-035 is complete with the disposition:

**DEVELOPMENT RUNTIME CUTOVER VERIFIED — PRODUCTION DEPLOYMENT PENDING**

BE-035-D1 remains an explicitly documented finding: `webhook_worker` has a reported `ImportError`. The issue was deliberately deferred, not fixed.

Your mission is to investigate this specific failure, establish its exact cause, implement the smallest correct fix, and verify that the webhook worker starts and performs its intended work under the current development runtime configuration.

This is a reliability milestone, not a production deployment milestone and not a broad backend rewrite.

### Required outcome

1. Reproduce or conclusively diagnose the `webhook_worker` import failure.
2. Fix the root cause if it is safely identifiable and within scope.
3. Verify imports, startup, configuration and database access.
4. Verify webhook processing using a controlled test environment without unintended network side effects.
5. Run focused and relevant regression tests.
6. Update the canonical backlog and create the BE-036 completion report.
7. Determine whether BE-035-D1 is genuinely closed or must remain open with a precise explanation.

Do not move into Option B production deployment planning as part of this milestone.

## 2. Mandatory safety rules

### Git discipline

Before changing anything, inspect:
- Repository root.
- Current branch and HEAD.
- `git status --short --branch`.
- Existing modified and untracked files.
- Relevant diffs and recent history.

The previously reported branch is `Backend`, HEAD `d5685abf`. Treat this as historical information and verify the actual current state.

Never:
- Run `git add .` or `git add -A`.
- Run `git clean`, `git reset --hard`, destructive checkout/restore or history rewriting.
- Stage unrelated changes.
- Commit or push.
- Revert unrelated documentation changes.

Preserve all existing user changes.

Exclude `backend/.venv312_clean/`, `backend/.venv312_repro/`, `backend/BE-023_Status.txt` and `backend/BE-023_Summary.txt` from commit work.

### Database safety

The protected databases are `pofa_dev` and `pofa_test`.

- Do not reset, truncate, downgrade, clean, backfill or repair either database.
- Do not use either as a scratch database.
- Do not use the webhook worker as an excuse to run broad write-based experiments against protected data.
- Use a named disposable database for any integration test that writes data.
- Verify the database target before running write-based tests.
- Never silently fall back to `.env` or a default database URL.

Read-only inspection of `pofa_dev` is permitted when needed to diagnose configuration. Any actual database writes during this milestone must be confined to an explicitly verified disposable database.

### Runtime identity

BE-035 established the development runtime identity as `poa_runtime`.

Do not switch the development configuration back to `postgres`. Do not add broad grants or change table ownership to bypass a permission error.

Verify that worker processes use the intended runtime identity without printing credentials.

### External side effects

Webhook delivery can make outbound HTTP requests and cause real external effects.

- Never execute an unrestricted webhook-delivery loop.
- Never invoke a real outbound webhook merely to prove that a worker starts.
- Use mocks, a local test receiver or a disposable test environment.
- Do not send real emails, webhooks or external notifications unless a separately documented, explicitly authorized test requires it.

### Secrets

Never print JWT secrets, database passwords, API keys, tokens or password-bearing connection strings into logs, reports or source files.

Do not change production secret settings or attempt a production deployment.

## 3. Phase A — Locate the failure

Inspect the actual worker and its dependency graph.

At minimum, investigate:
- `backend/workers/webhook_worker.py`, or the actual current path.
- The module and symbol named in the `ImportError`.
- The code that imports or invokes the worker.
- Shared services, schemas, models and configuration imported by the worker.
- The worker launch entry point and command.
- Dependency declarations and the reproducible Python environment.
- Relevant tests and recent changes to the imported symbols.
- The BE-035 report and backlog entry documenting BE-035-D1.

Locate actual paths before assuming filenames.

Capture the exact import error, including the missing module or symbol, the importing file and the relevant stack trace. Redact sensitive values.

Determine whether the failure is caused by:
- A nonexistent or renamed symbol.
- A stale import path.
- A circular import.
- An unavailable dependency.
- A package/version mismatch.
- A working-directory or Python path issue.
- An environment/configuration issue.
- A genuinely broken worker implementation.

Do not choose a fix before understanding the root cause.

## 4. Phase B — Reproduce safely

Use the existing reproducible Python environment if it exists:

`backend/.venv312_repro/Scripts/python.exe`

Verify the interpreter and dependency versions first.

Run the narrowest useful checks:
1. Import the exact failing module.
2. Import the worker's dependencies.
3. Execute the actual worker entry point in a bounded, non-delivery mode if supported.
4. Run the existing tests that cover the failing module.
5. Confirm whether the failure reproduces under the same working directory and configuration used by the real worker launcher.

Do not launch an unbounded worker loop during reproduction.

If the failure cannot be reproduced, compare the actual launch command, environment and working directory with the successful test environment. Do not declare the issue fixed merely because a different import command succeeds.

## 5. Phase C — Implement the smallest correct fix

Fix the root cause using the repository's existing architecture and conventions.

Requirements:
- Keep the change narrow.
- Preserve existing public interfaces unless the root cause requires a documented correction.
- Avoid broad refactoring.
- Do not duplicate service or schema implementations to work around an import error.
- Do not introduce a new dependency unless necessary and justified.
- If a dependency is genuinely missing, update the appropriate dependency manifest and lockfile consistently, following existing project conventions.
- Avoid importing heavy modules at package initialization if doing so creates a circular import; fix the dependency structure cleanly.
- Preserve error handling, authorization and transaction behavior.
- Preserve the existing append-only audit guarantees.
- Keep the worker compatible with the `poa_runtime` database identity.

If the cause is an environment-specific problem rather than a code defect, correct the documented environment or launch configuration if safe. Do not modify ignored `.env` files blindly or expose their contents.

If the failure depends on missing external credentials or infrastructure, implement all safe local work and document the remaining prerequisite instead of inventing credentials.

## 6. Phase D — Verify worker startup and identity

After implementing the fix, verify the actual worker startup path.

Establish that:
1. The worker module imports successfully.
2. Its entry point starts without the original `ImportError`.
3. Configuration loads correctly.
4. Database connectivity works where the worker requires it.
5. The effective database identity is `poa_runtime`.
6. The worker can access only the privileges required for its intended operations.
7. Startup failure is reported clearly if a dependency or configuration is missing.
8. The worker can shut down cleanly.

Prefer a bounded startup/initialization test or a controlled test harness.

If the worker requires a persistent loop, provide a safe way to exercise one iteration or a controlled test mode without introducing a permanent test-only production code path.

Do not claim the worker is operational merely because its Python file imports successfully.

## 7. Phase E — Verify webhook processing without real external delivery

Inspect the existing webhook-delivery implementation and its retry, status-update, error-handling and audit-event behavior.

Use the existing abstractions and tests wherever possible.

Create or update tests covering the relevant behavior:
- A pending delivery is selected and processed correctly.
- Successful delivery updates the expected status.
- A failed or timed-out delivery follows the intended retry/error path.
- Database transaction handling remains correct.
- Audit events are appended through the established `append_event` path.
- Invalid or missing configuration produces a controlled failure.
- The worker does not repeatedly process completed deliveries without a documented reason.
- Shutdown or cancellation does not leave misleading success states.
- Existing authorization and runtime-role constraints remain intact.

Mock external HTTP delivery or use a local test receiver. Do not call a real customer endpoint.

Use a disposable database for integration tests that write records. Verify that the test environment does not fall back to `pofa_dev` or `pofa_test`.

Do not weaken existing assertions to make the new tests pass.

## 8. Phase F — Regression verification

Run the narrowest relevant tests first, then broader regression checks.

At minimum:
- Exact worker import test.
- Worker startup/configuration tests.
- Webhook delivery success/failure tests.
- Audit-ledger append and integrity tests affected by the worker.
- Database safety and runtime-role tests where relevant.
- Relevant existing integration tests.
- The full backend test suite if the environment and available time permit after focused tests pass.

Use the explicit test database configuration. Never let tests silently use `.env` as a fallback.

The historical BE-035 result was 168 passed, 0 failed. This is a comparison point, not a claim about the current run.

Record exact commands, interpreter, database target, exit code and pass/fail/skip counts.

If a test fails:
1. Identify whether it is a regression, environment issue or pre-existing failure.
2. Fix in-scope regressions.
3. Do not modify unrelated functionality just to obtain a green suite.
4. Report any remaining failure honestly.

Do not rerun a failing full suite repeatedly without a specific diagnostic reason.

## 9. Phase G — Check for related reliability defects

Perform a narrow inspection of the webhook worker's immediate dependencies and lifecycle. Do not conduct a repository-wide refactor.

Look for:
- Import-time side effects.
- Missing dependency declarations.
- Incorrect launch paths.
- Duplicate delivery risks.
- Incorrect status transitions.
- Transaction/session leaks.
- Retry loops that can run indefinitely.
- Missing timeouts on external requests.
- Unsafe logging of payloads or credentials.
- Runtime-role permission assumptions.
- Incorrect audit-event handling.

Fix additional issues only if they are directly caused by the same defect, are clearly unsafe, and can be changed and tested within this milestone without expanding scope.

Otherwise, document them as separate backlog items.

Do not turn BE-036 into production deployment planning. Production infrastructure and the production JWT secret store remain outside scope.

## 10. Phase H — Documentation and backlog

Update:

`docs/Backend Technical Debt and Deferred Fixes Backlog.md`

Reconcile the BE-035-D1 entry with the actual result.

Create:

`docs/BE-036 Webhook Worker Reliability and ImportError Remediation Report.md`

Include:
1. Original error and reproduction conditions.
2. Root cause.
3. Exact code/configuration changes.
4. Worker import and startup verification.
5. Runtime identity evidence.
6. Webhook processing tests and external-side-effect controls.
7. Regression commands and results.
8. Files changed.
9. Any related findings intentionally deferred.
10. Whether BE-035-D1 is closed.
11. Production deployment status and the fact that it remains outside this milestone.

Do not change the BE-035 report to make it appear the original finding had already been resolved there.

Keep the backlog statuses precise:
- Confirmed defect.
- Fix implemented.
- Unit-tested.
- Integration-tested.
- Verified through actual worker startup.
- Deferred.
- Blocked by missing external prerequisites.

Do not mark an import issue closed based only on a successful unit test if the actual worker launch path remains broken.

## 11. Completion gates

### Root cause
- [ ] Exact `ImportError` captured or conclusively diagnosed.
- [ ] Root cause explained.
- [ ] Smallest correct fix implemented, or the non-code blocker documented.

### Worker
- [ ] Worker imports.
- [ ] Actual launch/initialization path works.
- [ ] Configuration and required database connectivity verified.
- [ ] Runtime identity remains `poa_runtime`.
- [ ] Shutdown behavior verified.

### Delivery
- [ ] Successful delivery path tested with a mock or local receiver.
- [ ] Failure/retry behavior tested.
- [ ] Audit append path remains correct.
- [ ] No unintended real outbound delivery occurred.
- [ ] Database writes stayed within the disposable test environment.

### Regression
- [ ] Focused tests pass.
- [ ] Relevant broader tests pass or residual failures are documented.
- [ ] No security assertion was weakened.
- [ ] Protected databases were not used as scratch databases.

### Documentation
- [ ] BE-035-D1 status is reconciled.
- [ ] BE-036 report exists.
- [ ] Canonical backlog is updated.
- [ ] No commits or pushes were made.

## 12. Final verdict

Choose one:

**BE-035-D1 CLOSED — WORKER VERIFIED**

Use only when the root cause is resolved and the actual worker startup/processing path is verified with safe tests.

**FIX IMPLEMENTED — RUNTIME VERIFICATION PENDING**

Use when code tests pass but the real worker launch path cannot be verified.

**BLOCKED — ROOT CAUSE OR ENVIRONMENT UNRESOLVED**

Use when the failure cannot safely be fixed or necessary dependencies are unavailable. State exactly what is missing.

Production remains **NOT CLEARED** unless a separate production deployment milestone establishes a real target, secret store, deployment configuration and successful production verification.

## 13. Git and final report

Do not commit or push.

At completion, report:
1. Final verdict.
2. Original `ImportError` and root cause.
3. Files changed.
4. Worker startup and runtime-identity evidence.
5. Webhook-processing verification.
6. Exact test commands and results.
7. Database targets used.
8. Whether any real external webhook was sent.
9. Whether BE-035-D1 is closed.
10. Remaining backlog items.
11. Actual branch, HEAD and working-tree status.
12. Confirmation that production deployment remains outside BE-036.

Begin with Phase A and continue through every safe in-scope phase. Do not stop after generating a plan, do not invent successful results, and do not expand into Option B.

## 14. Next milestone boundary

BE-036 is limited to webhook-worker reliability.

Once BE-036 is complete, the next workstream is **Option B — Production Deployment Planning**, which must identify the real production target and secret-management mechanism before any production deployment or credential cutover is attempted.