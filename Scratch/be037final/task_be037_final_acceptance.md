# PROOF-OF-ACTION — BE-037 FINAL BACKEND COMPLETION AND ACCEPTANCE

## 1. Mission

You are working on the Proof-Of-Action (PoA) backend repository:

`D:\CODING\Projects\Proof-Of-Action-Final`

Expected branch: `Backend`

BE-037 is the **final planned backend milestone**. Do not create BE-038 or any subsequent backend milestone.

Your task is to complete the remaining remediation and verification work identified in the BE-037 Phase B and G1/I1 remediation reports. You must make the necessary code, configuration, documentation, and test changes, verify them on isolated infrastructure, preserve the user's existing work, and produce one comprehensive final acceptance report.

The objective is to reach the strongest defensible backend completion state possible without deploying to production or making unsupported production-readiness claims.

This is an execution task, not merely a planning or advisory task. Inspect the repository, implement justified fixes, execute tests, gather evidence, and report actual results.

Do not stop after producing a plan. Continue through implementation and verification wherever the safety constraints permit. If an operation is blocked by an authorization requirement, unavailable resource, or missing prerequisite, record the blocker and continue with independent safe tasks.

## 2. Mandatory initial inspection

Before changing anything:

1. Confirm the repository root and current Git branch.
2. Record the exact HEAD commit.
3. Capture `git status --short`, `git diff --stat`, `git diff`, and the list of untracked files.
4. Identify existing user changes, deleted files, untracked artifacts, generated files, and unrelated modifications.
5. Read the existing BE-037 final report, Phase B report, G1/I1 remediation report, relevant backend runbooks, environment examples, and related tests.
6. Inspect the implementations of:
   - `backend/api/v1/endpoints/analysis.py`
   - `backend/services/authorization.py`
   - `backend/workers/analysis_worker.py`
   - `backend/core/config.py`
   - `backend/services/webhook.py`
   - `_complete_reprocessing_hook` and its callers
   - Redis queue creation and blocking dequeue logic
   - schema-drift baseline and verification code
   - storage integration tests, especially `tests/integration/test_storage.py`
   - protected-database verification tests
7. Inspect the existing Phase B evidence and distinguish verified facts from assumptions.
8. Create a written baseline in a new, uniquely named scratch directory outside the repository.

Do not assume the previous agent's report reflects the current working tree. Verify the actual code and environment.

If the repository or branch differs from expectations, do not force it back to the expected state. Report the discrepancy and work safely from the actual state.

## 3. Absolute safety constraints

These rules override convenience and test-suite expectations.

### Git and user changes

- Never execute `git add .` or `git add -A`.
- Never use `git clean`, `git reset --hard`, destructive checkout/restore operations, history rewriting, or force-push.
- Do not discard, overwrite, rename, or revert unrelated user changes.
- Do not commit or push anything.
- Do not switch branches unless explicitly authorized.
- Do not rewrite history or amend an existing commit.
- Do not stage any files.
- Preserve all existing documentation deletions and unrelated changes, including previously identified milestone-document deletions.
- Review changes before editing shared files. Make targeted changes only.
- Do not remove temporary files unless you can prove that the current run created them and they contain no pre-existing user data.

### Protected databases

The following databases are protected:

- `pofa_dev`
- `pofa_test`

For this task, do not perform writes, resets, destructive cleanup, migrations, backfills, fixture insertion, or write-based testing against either database.

Read-only inspection is allowed when needed to establish a baseline or investigate a discrepancy. Use read-only transactions and queries wherever possible. Do not change their database settings, roles, permissions, extensions, schemas, or data.

If a test cannot run because it explicitly refuses to use a disposable database, do not disable the protection. Adapt the test harness to test the intended safety property against an appropriate isolated fixture or use a separate, explicitly read-only assertion against the protected database if the existing test design requires it.

Never claim that a protected database was unchanged unless you captured and compared suitable before-and-after evidence.

### Protected Docker resources

Existing resources that must not be restarted, recreated, removed, or reconfigured:

- `pofa_db`
- `pofa_redis`
- `pofa_minio`
- Their existing volumes and networks.

Do not run broad `docker compose down`, `docker compose down -v`, `docker system prune`, `docker volume prune`, or any cleanup command that could affect unrelated resources.

Do not run `docker compose up` against an existing Compose project merely to test a service. Compose dependencies can resurrect stopped services.

Do not restart or recreate `pofa_minio`, even if its health check fails. The previous reports recorded unexplained MinIO restart events. Investigate them using read-only inspection first; do not attempt to reproduce the anomaly by manipulating the existing service.

### Isolated infrastructure

All new integration, failure-injection, schema, authorization, queue, and storage tests must use a newly created isolated stack with uniquely named resources for this run.

Use a unique run identifier, such as `be037final_<timestamp>_<short-id>`, in all disposable resource names and Compose project names.

The stack must have its own:

- PostgreSQL/PostGIS/pgvector database and database roles
- Redis instance
- MinIO instance and dedicated disposable data volume
- API and worker containers
- Network
- Environment/configuration files

Use repository-supported Compose and database initialization mechanisms where possible.

Before running commands that could affect containers or volumes, capture the exact resource name, full container or volume ID, Compose project label, creation time, and relevant labels. Cleanup must target only the resources positively identified as belonging to this run.

Never use broad pattern-based deletion as the sole cleanup criterion.

### Secrets and external side effects

- Never print, commit, or include passwords, JWT secrets, access keys, signed URLs, or secret environment values in reports.
- Do not provision cloud infrastructure.
- Do not deploy to staging or production.
- Do not contact external webhook destinations or send real email/notifications.
- Do not download model weights or large ML artifacts without explicit approval.
- Do not alter production identities, secret stores, external services, or deployment configurations.
- Do not perform production cutovers.
- Do not hand off the task. Complete the safe work within the current repository and environment.

## 4. Workstream A — Fix BE-037B-G5 reprocessing-hook behavior

The previous report identified `_complete_reprocessing_hook` logging an ERROR and traceback after completed jobs when reprocessing is unavailable or not configured.

Investigate the function, its callers, the expected reprocessing lifecycle, and relevant tests.

Determine whether the missing hook is:
1. An expected optional configuration or no-op.
2. A genuine programming error.
3. A failed operation that must remain visible.

Implement the behavior appropriate to the verified contract.

Requirements:

- Expected optional absence must not produce a misleading ERROR or traceback.
- Genuine execution failures must remain observable and must not be silently swallowed.
- Preserve job completion, transaction, audit, retry, and acknowledgement semantics.
- Do not mask exceptions broadly.
- Avoid duplicate logging if the caller already records the same failure.
- Add tests for the expected no-op, successful hook execution, and genuine hook failure.
- Verify log level and error propagation, not just the returned value.

Acceptance criteria:

- A completed job with no configured reprocessing hook produces no false error.
- A configured hook executes when expected.
- A genuine hook failure remains diagnosable.
- Existing job lifecycle and audit tests pass.

Record the actual contract and the reason for the chosen behavior in the code or appropriate documentation.

## 5. Workstream B — Document analysis-worker settings

The I1 remediation introduced these configuration settings:

- `ANALYSIS_RETRY_BACKOFF_BASE_SECONDS`
- `ANALYSIS_RETRY_BACKOFF_MAX_SECONDS`
- `ANALYSIS_SHUTDOWN_POLL_SECONDS`

Trace how configuration names map to application settings and identify the canonical environment example and operations documentation.

Update the appropriate existing files rather than creating competing documentation sources.

Document:

- Purpose of each setting.
- Actual default value.
- Accepted range and validation behavior.
- Relationship between base and maximum backoff.
- How shutdown polling affects worker termination responsiveness.
- How operators should diagnose repeated Redis disconnections.
- Any implications for queue latency and retry timing.

Use the actual implemented defaults and validators. Do not invent ranges or promise timing guarantees the implementation cannot provide.

Ensure that sample values agree with application configuration.

Do not place secrets in example configuration. Do not introduce a real environment-file change containing credentials.

Acceptance criteria:

- Every new setting is discoverable in the canonical example configuration and/or canonical operations guide.
- Documentation accurately reflects runtime behavior.
- Configuration validation and documentation are consistent.
- Existing unrelated documentation changes are preserved.

## 6. Workstream C — Make Redis outage and hung-connection recovery robust

The existing I1 fix handles `redis.exceptions.ConnectionError`, applies bounded exponential jittered backoff, retries abandoned-job recovery after reconnection, and keeps shutdown interruptible during retry sleeps.

However, the previous report identified a potential unresolved failure mode: a Redis socket that hangs without raising an exception can leave the worker stuck inside a blocking queue operation.

Investigate the Redis client, connection pool, blocking dequeue operation, queue acknowledgement discipline, and Redis-py version.

### Required investigation

Establish:

- Whether the current blocking operation has a finite socket timeout.
- Whether Redis-py health checks apply to the actual blocking connection.
- Whether a network blackhole can leave a worker blocked indefinitely.
- How timeout exceptions interact with the existing retry loop.
- How the queue's blocking timeout and socket timeout interact.
- Whether changing timeouts affects job delivery, duplicate processing, visibility, or acknowledgement semantics.

Do not assume that `health_check_interval` alone solves a frozen connection.

### Implementation requirements

Implement a finite, explicitly configured timeout strategy if the current implementation can hang indefinitely.

Choose timeout values based on the actual blocking dequeue behavior and client-library semantics. Do not choose arbitrary values simply to make tests pass.

If the correct solution requires an owner decision about queue semantics, make the narrowest safe change possible and document the remaining decision. Do not invent an architectural contract.

Requirements:

- Handle only the documented connection and timeout exception types in the retry path.
- Continue propagating programming errors, invalid commands, Redis `ResponseError`, and unrelated failures.
- Preserve queue acknowledgements and database transaction ordering.
- Never acknowledge a job before its intended database outcome is committed.
- Do not silently discard queued jobs.
- Ensure that shutdown remains responsive during retry waits.
- Ensure recovery runs after reconnecting, not only at startup.
- Ensure repeated connection failures do not create a tight retry loop.
- Keep retry delays bounded and preserve the configured backoff behavior.
- Add focused unit tests and real isolated-Redis integration tests.

### Required failure scenarios

Test on the disposable stack:

1. Redis unavailable before worker startup.
2. Redis disconnect during blocking dequeue.
3. Connection failure during queue access.
4. Connection that stalls or becomes unreachable without a clean disconnect, using a fault-injection method confined to the disposable network.
5. Redis restoration while queued jobs remain.
6. SIGTERM during a retry delay.
7. SIGTERM during a blocked or timed-out dequeue.
8. Repeated outages without a tight loop or uncontrolled container restart cycle.
9. Recovery of abandoned processing entries.
10. No premature acknowledgement or silent loss of queued jobs.
11. Unrelated Redis command errors still propagate.

Use finite test timeouts so the test suite cannot hang indefinitely.

The tests must distinguish:
- Recovery of queue mechanics.
- Correct terminal job state.
- Successful inference.

Do not claim successful inference if the synthetic evidence has no real object stored in isolated MinIO.

Acceptance criteria:

- Worker behavior is bounded under the tested Redis failure modes.
- Queued work survives an outage.
- Recovery and shutdown are demonstrated with measured results.
- Unrelated programming or command errors remain visible.
- Any unsupported network-failure mode is explicitly reported.

## 7. Workstream D — Make database bootstrap and schema-drift verification reproducible

The previous full integration suite produced three failures:

1. A protected-database verification test intentionally rejected a disposable database.
2. The disposable database had additional extension-owned objects and an unexplained `exemplo_dados` table.
3. The schema-drift result differed substantially between the disposable database and `pofa_test`.

The report recorded that the same PostgreSQL/PostGIS/pgvector image was used, but the initialization paths differed.

Do not simply update the expected schema baseline to accommodate unexplained objects.

### Required investigation

Compare:

- Repository-supported database initialization.
- Container first-boot initialization.
- Any `CREATE DATABASE` or extension installation scripts.
- Alembic migration state.
- Installed extensions and versions.
- Extension-owned objects and dependencies.
- Database and object owners.
- Search paths, schema configuration, and initialization variables.
- All relevant baseline registry entries.
- The provenance of `exemplo_dados`.

Determine whether the difference is due to initialization, a legitimate environment contract, an extension version, an unrelated object, or a real schema defect.

Do not remove the unexplained object from a protected database. Do not drop or alter protected extensions.

### Bootstrap requirements

Create a reproducible disposable-database setup using the repository's intended initialization process.

Ensure that a fresh database reaches the expected migration head without manual undocumented interventions.

Keep environment-specific bootstrap differences explicit.

The schema-drift checker must continue to detect unexplained application-owned schema changes.

Extension-owned exclusions must be narrow and based on verified ownership/dependency information. Do not suppress all objects in a schema or expand exclusions merely to achieve a passing test.

### Protected-database verification test

The test named `test_verification_context_refuses_the_shared_test_database_over_a_real_connection`, or its current equivalent, must continue to enforce the safety property that protected databases are rejected for write-based verification contexts.

Do not weaken the protection or allow the test harness to bypass it.

Refactor the test so that:
- The rejection behavior can be tested without writing to a protected database.
- A disposable database is accepted when appropriate.
- The protected-database guard is verified through a safe, read-only assertion or a mocked identity/configuration boundary when a real protected connection is unnecessary.
- Test naming and assertions reflect the exact behavior being tested.

### Required schema tests

Run and report:

- Fresh bootstrap.
- Migration to head.
- Exact expected drift baseline.
- Extension-owned-object classification.
- Detection of an intentionally introduced application-owned drift in a disposable database.
- Rejection of an invalid or protected verification target.
- Repeatability across a fresh second disposable database if resources allow.

Never add a baseline exception without documenting the exact object, its owner, provenance, and why the exception is safe.

Acceptance criteria:

- Fresh isolated database creation is reproducible.
- Migrations reach the intended head.
- Expected schema drift is stable and explainable.
- Deliberate application-owned drift is detected.
- No unexplained object is hidden by the baseline.
- Both protected database guards remain enforced.

## 8. Workstream E — Make storage and owner-DSN tests safe

### E1. Storage integration test and MinIO protection

The previous report identified `tests/integration/test_storage.py:77` as capable of restarting the existing `pofa_minio` service.

Inspect the current test and related fixtures. Remove any dependency on an existing named service or shared Compose project.

The storage test must use the MinIO instance created by this run, with a uniquely named disposable volume and isolated network.

Requirements:

- Never restart, recreate, or reconfigure the existing `pofa_minio`.
- Never use `docker compose up` against the protected service's Compose project.
- Never delete or alter the protected MinIO volume.
- Avoid global service names and shared ports when not necessary.
- Use a unique bucket and disposable credentials.
- Ensure cleanup only targets this run's resources.
- Keep all test object names inside the disposable bucket.
- Test upload, retrieval, integrity checks, and cleanup as applicable.
- Keep production storage configuration unchanged.

Inspect the previous MinIO restart records using read-only evidence. Compare container ID, creation time, start time, restart count, logs, and relevant Compose metadata when available.

Do not attribute the restart to this run without evidence. If its cause cannot be established, report it as unresolved.

### E2. Owner-DSN integrity verification

The previous report recorded that the owner-DSN case was not proven because the relevant protection is intentional.

Investigate how ledger integrity verification behaves when executed with:
- The application runtime role.
- A privileged disposable database owner.
- A connection with insufficient permissions.

Use only disposable roles and databases for write-based or permission-changing tests.

Do not modify the owner, grants, roles, or configuration of `pofa_dev` or `pofa_test`.

Determine the intended integrity-verification contract and test it accurately. If owner-level access is supposed to expose a different tampering threat model, document that distinction rather than claiming that an application-level trigger defeats a database owner.

Acceptance criteria:

- Storage integration tests cannot restart protected services.
- Storage tests execute against the isolated MinIO instance.
- The owner-DSN and runtime-role integrity behavior is verified or explicitly documented as a limitation.
- The unexplained historical MinIO restart is not falsely attributed.

## 9. Workstream F — End-to-end isolated verification

After implementing the fixes, perform one comprehensive acceptance run.

Use a unique disposable Compose project and capture a manifest of every resource created.

Do not reuse the previous Phase B or remediation resource names.

### F1. Security and authorization

Re-run the G1 authorization matrix against an isolated API configured with enforcing authentication and development tokens disabled.

At minimum verify:

- Anonymous request rejection.
- Invalid token rejection.
- Malformed identifier validation.
- Unauthorized role rejection.
- Authorized job creation.
- Authorized job retrieval.
- Cross-organization isolation.
- Correct 401/403/404/422 behavior.
- No database row creation for rejected cross-organization requests.
- Development bypass behavior remains explicitly limited and does not disable authentication in enforcing mode.
- API-client behavior matches the defined permission contract.

Verify both HTTP behavior and the relevant database side effects.

### F2. Worker reliability

Re-run the I1 test matrix from Workstream C and the BE-037 worker shutdown tests.

Measure actual:
- Retry intervals.
- Worker exit codes.
- Shutdown latency.
- Queue length.
- Processing-list length.
- Number of jobs recovered.
- Final job states.
- Container restart counts.

Do not report expected values as observed values.

### F3. Real synthetic evidence flow

Where supported by the current architecture, create a completely synthetic evidence object in the disposable MinIO bucket and corresponding records in the disposable database.

Use no real personal or government evidence.

Exercise the actual supported API flow:
1. Create or seed the minimum valid synthetic project/evidence fixture.
2. Upload a valid synthetic object to disposable MinIO.
3. Record the matching object key and metadata.
4. Submit the analysis job through the actual API.
5. Observe worker processing.
6. Verify the final job state.
7. Verify expected database and audit effects.
8. Confirm object retrieval and integrity.
9. Clean up only this run's resources.

Use the repository's real API and storage contracts. Do not invent endpoints, bypass required authorization, or create invalid fixtures just to force a result.

If a required ML model or approved artifact is unavailable, do not download it without approval. Report the exact limitation and test all remaining supported behavior.

### F4. Regression suites

Run the repository-supported unit, integration, authorization, worker, storage, migration, and schema-drift tests.

First inspect the repository's documented test commands and environment requirements.

Run tests in sensible groups, but complete the full applicable suite where feasible.

For every test run, capture:
- Exact command.
- Environment/target category, without secret values.
- Exit code.
- Passed, failed, skipped, and error counts.
- Duration if available.
- Failure details and classification.

If a suite requires a protected database, adapt it to a disposable environment. Do not silently skip it or claim it passed.

If the full suite cannot run, report the exact blocker and the largest verified subset.

### F5. Production configuration safeguards

Re-run existing tests for:
- Production JWT secret requirements.
- Rejection of unsafe development authentication in production.
- Rejection of wildcard CORS in production.
- Enforcing authentication behavior.
- Webhook redirect validation and SSRF defenses.
- Audit-ledger integrity and known historical gaps.
- Database migration and startup behavior.

Do not change production secrets, live roles, or deployment state.

## 10. Workstream G — Final report and repository hygiene

Produce one final comprehensive report in the repository's existing BE-037 documentation location or update the canonical final report if that is the established project convention.

Do not create another milestone. Do not overwrite an existing report blindly. If an existing report is a user change, preserve it and create a clearly named supplementary report only when necessary.

The report must contain:

1. Executive summary.
2. Final verdict: PASS, CONDITIONAL PASS, or BLOCKED, with a precise definition of the scope.
3. Initial and final Git HEAD.
4. Initial and final working-tree status.
5. Exact files changed and reason for each.
6. G5 behavior and test evidence.
7. Worker configuration documentation changes.
8. Redis outage and hung-connection behavior.
9. Database bootstrap and schema-drift findings.
10. Storage test isolation and MinIO anomaly investigation.
11. Owner-DSN/runtime-role integrity findings.
12. G1 authorization matrix results.
13. End-to-end synthetic evidence flow results.
14. Unit and integration suite totals.
15. Every failure, skip, warning, and deviation.
16. Disposable-resource manifest and cleanup results.
17. Protected-resource before-and-after evidence.
18. Remaining owner decisions and production blockers.
19. Explicit statement of whether any cloud deployment occurred.
20. Explicit statement of whether any commit or push occurred.

Include actual command results and sanitized evidence references. Do not include secret values.

### Cleanup

After testing:
- Stop and remove only containers created by this run.
- Remove only volumes and networks created by this run.
- Remove temporary credentials and secret-bearing files created by this run after confirming they are not pre-existing files.
- Verify the protected containers remain untouched.
- Verify the protected databases remain unchanged using appropriate before-and-after evidence.
- Verify that no disposable resource from this run remains.
- Verify the Git diff and working-tree status.

If cleanup cannot be proven safe, stop and report the remaining resources instead of using broad cleanup commands.

### Final Git rules

Do not stage, commit, or push anything. The user will review and explicitly authorize any later commit.

## 11. Acceptance gate

The task is complete only when every safe workstream has either passed or has a specific, evidence-backed blocker.

### Technical completion criteria

- G5 no longer produces false error logs, and genuine hook failures remain observable.
- The three I1 configuration settings are documented accurately.
- Redis connection failure and supported hung-connection scenarios have bounded, tested behavior.
- Queue acknowledgement, recovery, and shutdown semantics remain correct.
- Fresh database bootstrap and schema-drift checks are reproducible.
- Extension-owned exclusions remain narrow and justified.
- The protected-database guard remains enforced.
- Storage integration tests use isolated MinIO and cannot restart protected services.
- Runtime-role and owner-DSN integrity behavior is tested or accurately bounded.
- G1 authorization tests pass.
- Worker, storage, and supported synthetic evidence flow are tested end-to-end.
- Full applicable regression results are recorded honestly.
- Disposable resources are cleaned up safely.
- User changes remain intact.
- No commits, pushes, cloud provisioning, or deployments occur.

### Production acceptance is a separate decision

Even if all isolated tests pass, do not declare PoA production-ready unless the actual production requirements are independently met.

Previously identified production blockers include:
- Approved production target environment.
- Approved secret store and production secret management.
- Production runtime identity and deployment/cutover.
- Required live health and integrity verification.
- Outstanding owner decisions, including the unresolved `external_subject` policy decision where applicable.
- Backup/PITR and recovery guarantees.
- Any remaining audit-ledger integrity limitations and historical gaps.

Do not change these controls as part of this isolated completion task. Report their current status and what evidence would be required to close each one.

## 12. Execution protocol

Proceed in this order:

1. Inspect repository and protected resources read-only.
2. Record the initial baseline.
3. Implement Workstreams A and B.
4. Implement and test Workstream C.
5. Resolve Workstream D.
6. Resolve Workstream E.
7. Create the isolated stack and run Workstream F.
8. Fix regressions introduced by these changes.
9. Re-run affected tests and the complete applicable regression suite.
10. Review the final diff for correctness, security, unintended changes, and secret leakage.
11. Clean up only verified disposable resources.
12. Verify protected-resource state and Git status.
13. Write the final report and give a concise final summary.

Run independent safe tasks even when another task is blocked. Do not abandon the entire mission because one owner decision is unresolved.

Never fabricate test results, resource states, file contents, or verification evidence.

If the environment does not support a required test, distinguish between:
- Not run.
- Blocked.
- Failed.
- Passed.
- Passed with limitations.

Do not call a partial test run a full acceptance run.

## 13. Required final response

When finished, report:

- Overall verdict.
- Workstreams completed.
- Exact unit/integration/regression totals.
- Whether G5, Redis frozen-connection handling, schema bootstrap, and storage isolation passed.
- Whether a real synthetic evidence object completed the supported analysis flow.
- Any remaining blockers and owner decisions.
- Whether protected databases and containers remained unchanged.
- Whether cleanup was verified.
- Git HEAD and working-tree status.
- Confirmation that nothing was staged, committed, pushed, or deployed.

If a blocking defect remains, name it explicitly and provide the smallest next action required to resolve it.

**Start with read-only inspection. Preserve user changes. Complete every safe task. Stop before any prohibited operation. BE-037 remains the final planned backend milestone.**