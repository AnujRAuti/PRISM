# BE-037 — FINAL BACKEND MILESTONE: Production Deployment, Security Closure, Operational Verification & Final Acceptance

## 1. Mission and Finality

You are executing **BE-037, the final planned backend milestone for Proof-Of-Action (PoA)**.

This is the final milestone in the planned backend engineering sequence. It must consolidate the work completed in BE-023 through BE-036, resolve outstanding backend issues that prevent safe production operation, complete the production deployment and verification process where the required infrastructure and authorization are available, and produce an auditable final acceptance decision.

**BE-037 is not another assessment-only milestone.** It must move beyond reviewing documentation and writing recommendations. Inspect the actual repository and available environments, establish the current state, implement necessary code and configuration changes, execute appropriate tests, close security and reliability findings, and verify operational behavior with evidence.

Do not create BE-038 or another successor milestone merely because BE-037 encounters work that can reasonably be completed within its existing scope. Incorporate such work into BE-037, maintain a clear task register, and continue until every safely executable requirement is complete.

There is one non-negotiable distinction:

- The milestone is intended to be final.
- The milestone may be declared complete only when its acceptance criteria have actually been satisfied.
- If an essential production dependency requires access, a decision, infrastructure, or authorization that is unavailable, stop the affected operation and report the exact blocker. Do not claim deployment, production readiness, or acceptance that has not been demonstrated.

If external prerequisites remain unresolved, BE-037 remains the final milestone but must be reported as **BLOCKED — FINAL ACCEPTANCE NOT GRANTED** until the outstanding gate can be completed. Do not invent another milestone to disguise the incomplete work.

## 2. Project Context and Verified Starting Position

The repository is the existing Proof-Of-Action backend project. Work within the current repository and its established architecture rather than creating a replacement backend or independently redesigning the application.

The latest reported backend state includes the following:

### BE-032R and BE-033 — Integrity Enforcement

- A versioned, default-deny audit integrity baseline registry exists in `backend/services/audit_integrity_baseline.py`.
- An anchored audit verification endpoint and associated schemas have been implemented.
- Audit enforcement migration `t0u1v2w3x030` has been applied to the development database.
- The development audit ledger was previously verified at 6,023 rows, with seven documented historical sequence-gap ranges.
- The classified verification result was `known_historical_only`, with seven known gaps, zero new gaps, zero hard gaps, and checkpoint 6023.
- The documented historical gaps must not be silently repaired, backfilled, deleted, or relabelled as new incidents without explicit authorization and evidence.

### BE-034 and BE-035 — Runtime Identity and Service Verification

- The development API was switched to the least-privileged `poa_runtime` database identity.
- Six health-related paths reportedly returned HTTP 200 during the development verification.
- The readiness endpoint confirmed PostgreSQL connectivity.
- Append-only controls were tested on a faithful disposable clone. App-path appends worked while UPDATE, DELETE, TRUNCATE, and privilege escalation attempts were denied.
- The production deployment was not verified. The production target and production secret store had not been established in the last reported state.

### BE-036 — Webhook Worker Reliability

- `backend/workers/webhook_worker.py` was corrected to use the existing `get_session()` interface rather than importing the nonexistent `SessionLocal`.
- The worker's module import, CLI help, database identity, and shutdown behavior were verified.
- Regression tests cover successful delivery, retry behavior, failure conditions, disabled subscriptions, automatic disabling, fanout idempotency, completed-delivery handling, and audit append behavior.
- The reported full test suite completed with 831 passed, one skipped, and zero failures.
- No real external webhook was sent during those tests.

### Remaining known concern

BE-036-D1 identified a security issue: `urllib` may follow HTTP redirects, potentially allowing a webhook destination that initially passes SSRF validation to redirect toward a prohibited destination.

This finding must be investigated and closed during BE-037. It must not be dismissed merely because the previous worker tests passed.

Other previously noted concerns include crash-stranded webhook deliveries in a `PROCESSING` state and the absence of explicit row-locking behavior for concurrent delivery attempts. Determine their actual severity and whether the current deployment model can trigger duplicate delivery or permanently stranded work.

### Repository state is not assumed

The information above is historical reported evidence, not proof that the current checkout, database, branch, remote, or production environment still has exactly that state.

At the beginning of BE-037, independently inspect the current repository and available environments. Record actual observations separately from inherited reports. Do not claim to have independently reproduced any historical result unless you actually do so.

## 3. Primary Objective

Deliver a production-ready PoA backend with:

1. A confirmed and documented production deployment target.
2. Secure production configuration and secret management.
3. A least-privileged runtime database identity.
4. Separate runtime and migration privileges.
5. Verified database schema and migration state.
6. Effective audit integrity enforcement and append-only protections.
7. A safe, functioning API and webhook worker deployment.
8. Closure of the BE-036-D1 webhook redirect/SSRF finding.
9. Verified health, readiness, audit integrity, and critical API behavior.
10. A tested operational recovery procedure appropriate to the available infrastructure.
11. A complete deployment and rollback runbook.
12. A final evidence-based acceptance report.
13. An explicit final disposition of every inherited blocker and deferred finding.

Do not stop after creating documentation, passing unit tests, or deploying code. Complete the operational verification as well.

## 4. Phase 0 — Repository, Git, Environment and Authorization Audit

Before making any changes, establish the current state.

### 4.1 Repository identity

Record:

- Repository root.
- Current branch.
- Current HEAD commit.
- Configured remotes, without exposing embedded credentials.
- Whether the current branch tracks a remote branch.
- Git status, including modified, staged, deleted, untracked, and ignored files where relevant.
- Existing changes to backend code, tests, migration files, configuration, and documentation.
- The presence of the BE-033, BE-034, BE-035, and BE-036 reports and the backend technical-debt backlog.

Verify that the BE-036 implementation and regression tests are present in the actual checkout.

Do not assume the local checkout is identical to the remote `Backend` branch. If synchronization is needed, inspect the divergence first and preserve all existing work.

### 4.2 Runtime and dependency discovery

Identify the actual:

- Python version and active virtual environment.
- Dependency lock/configuration files.
- Database driver and migration framework.
- API startup command and application entry point.
- Webhook worker startup command.
- Process manager or hosting platform, if configured.
- Container and orchestration setup, if present.
- Existing deployment automation.
- Environment-variable loading mechanism.
- Secret-management facilities.
- Health and readiness routes.
- Existing backup and restore procedures.

Do not create a second deployment architecture before determining what already exists.

### 4.3 Environment inventory

Identify every environment that is actually accessible and classify it explicitly:

- Disposable test environment.
- Development environment.
- Staging environment, if present.
- Production environment, if present.
- Any restored database clone.

Record database names, current migration revisions, relevant database identities, and application connectivity without exposing passwords, tokens, or connection-string secrets.

Do not infer that a database is production merely from its name. Do not infer that a deployment is production merely because it is remotely hosted.

### 4.4 Authorization gates

Before deploying or modifying a live target, determine:

- The intended production hosting target.
- The correct production database.
- The intended deployment mechanism.
- The authorized method for managing production secrets.
- Whether the required permissions are available.
- Whether a maintenance window or explicit deployment approval is required.
- Whether backup and recovery facilities are adequate for the planned operation.

If the target or authorization cannot be established, continue with repository work, security fixes, tests, runbooks, and preflight validation. Do not guess a target or perform a live deployment against the wrong environment.

Never ask the user to paste production secrets into chat or terminal output. Use the available approved secret-management mechanism.

## 5. Phase 1 — Build the Final Blocker and Acceptance Register

Inspect:

- `docs/Backend Technical Debt and Deferred Fixes Backlog.md`
- `docs/BE-032R Post-Acceptance Remediation and Release-Gate Closure Report.md`
- `docs/BE-033 Live Enforcement Rollout and Production Readiness Report.md`
- `docs/BE-034 Runtime Identity Cutover and Live Service Verification Report.md`
- `docs/BE-035 Live Runtime-Identity Cutover and Production Deployment Readiness Report.md`
- `docs/BE-036 Webhook Worker Reliability and ImportError Remediation Report.md`
- Relevant task files under `docs/Production Task Files/`
- Relevant implementation code, tests, configuration, and migration history.

Use the exact paths found in the repository if naming or capitalization differs.

Create a BE-037 work register that maps each inherited finding to:

- Finding identifier.
- Original problem.
- Current verified status.
- Required corrective action.
- Implementation location.
- Test or verification method.
- Evidence artifact.
- Final status.
- Any remaining external dependency or accepted residual risk.

At minimum, address these previously identified gates:

| Finding | Required disposition |
|---|---|
| D-PFD | Verify live audit enforcement and confirm it is present in the actual intended production target. |
| F-05 | Verify effective least-privileged runtime identity and resistance to destructive database operations. |
| D-CHAIN | Verify and document the existing controlled-continuation policy for historical chain defects. |
| OQ-3 | Confirm the pinned `external_subject` identity contract and document its adoption, backfill, or retirement decision. Do not make a speculative schema or identity change. |
| F-03 | Verify the anchored/checkpoint audit verification endpoint and its failure semantics. |
| F-04 | Verify known historical gaps remain distinguishable from new gaps and hard integrity failures. |
| D-RESTART | Perform the required API and worker restart or deployment verification on the actual target, when authorized. |
| BE-036-D1 | Resolve and test the webhook redirect/SSRF issue. |
| Production JWT configuration | Verify the production configuration validator is effective and a valid secret is supplied through the approved secret store. |

A previously accepted decision is not automatically a verified deployment result. Confirm implementation and operational behavior where appropriate.

Do not re-open settled product decisions without evidence that the current implementation contradicts them or introduces a new risk.

## 6. Phase 2 — Close Webhook Redirect/SSRF Vulnerability

Treat BE-036-D1 as a security-critical issue that must be resolved within BE-037.

### 6.1 Audit the entire request path

Inspect the webhook destination-validation and delivery implementation, including:

- URL scheme validation.
- Hostname validation.
- IP address validation.
- DNS resolution.
- IPv4 and IPv6 handling.
- Loopback, private, link-local, multicast, reserved, and otherwise prohibited address ranges.
- Redirect behavior.
- Request timeout and response-size limits.
- Retry behavior.
- Subscription failure handling.
- Audit logging and secret redaction.

Trace the actual behavior from subscription configuration through URL validation to the network request.

### 6.2 Required redirect protection

Ensure that an HTTP redirect cannot bypass the SSRF policy.

The preferred behavior is to reject redirects by default. If the current product contract requires redirects, follow them only through a bounded, explicit redirect policy that revalidates every destination before any subsequent connection. Do not rely solely on validation of the original URL.

At minimum, ensure:

- A redirect toward loopback or private infrastructure is rejected.
- A redirect toward link-local or prohibited addresses is rejected.
- DNS rebinding or changes in resolved addresses cannot silently bypass the security policy.
- Redirect chains are bounded.
- HTTPS-to-HTTP downgrade behavior is explicitly controlled.
- Credentials, authorization headers, and sensitive request data are not leaked across origins.
- A redirect rejection produces a predictable delivery status and appropriate audit evidence.
- Existing retry and permanent-failure behavior remains correct.

Account for the fact that a simple preflight DNS lookup alone may not fully prevent DNS rebinding if the HTTP client independently resolves the hostname later.

Implement protection using the project's existing networking and dependency architecture. Avoid introducing a large new dependency solely for this fix unless a concrete need is established.

### 6.3 Required regression tests

Add tests for:

1. An ordinary valid webhook destination.
2. A redirect to loopback.
3. A redirect to a private IPv4 address.
4. A redirect to a private or link-local IPv6 address.
5. A redirect to a disallowed hostname or prohibited resolved address.
6. A redirect chain exceeding the permitted limit.
7. A redirect from HTTPS to HTTP.
8. A permitted redirect, only if permitted redirects are part of the chosen contract.
9. No request being sent to the prohibited redirect destination.
10. Correct delivery state, retry behavior, and audit records after rejection.
11. Existing BE-036 delivery and idempotency behavior remaining intact.

Use mocked network responses, controlled DNS resolution, and disposable test infrastructure. Do not send requests to real internal services or arbitrary public webhook endpoints.

Document the security invariant clearly. Do not mark the finding closed just because a test checks the validator's return value; verify that the actual request path cannot follow the prohibited destination.

## 7. Phase 3 — Webhook Worker Reliability and Concurrency

Review the BE-036 worker fix and its surrounding state machine.

Preserve the corrected `get_session()` interface. Do not reintroduce imports of nonexistent session factories.

### 7.1 State-machine correctness

Verify the transitions between the actual delivery states, including:

- Pending delivery.
- Processing.
- Successful delivery.
- Retryable failure.
- Permanent failure.
- Disabled subscription or equivalent terminal handling.

Use the existing state names and semantics from the repository rather than inventing incompatible states.

Confirm that successful deliveries are not repeated merely because the worker restarts.

### 7.2 Crash recovery

Determine whether a process crash can leave deliveries indefinitely in `PROCESSING`.

If this is possible, implement an appropriately bounded stale-processing recovery mechanism using the existing schema and architecture. The recovery logic must:

- Identify stale work using a reliable timestamp or lease mechanism.
- Avoid reclaiming actively processed work.
- Respect the retry budget.
- Avoid resetting completed or terminal deliveries.
- Emit appropriate audit events.
- Be tested for restart recovery and repeated execution.

If the schema or product contract makes this unsafe to implement without a broader decision, document the exact blocker and do not silently change the contract.

### 7.3 Concurrency and duplicate delivery

Determine whether two workers can claim and send the same delivery concurrently.

Where the deployed execution model permits parallel workers, implement an appropriate atomic claim or row-locking strategy using the project's actual database capabilities.

Verify that:

- Competing workers cannot both claim the same eligible row under normal operation.
- Failed attempts do not leave permanent locks or corrupted state.
- Completed deliveries remain idempotent.
- Audit events accurately reflect delivery outcomes.
- The solution does not require unsafe global locking or serialize unrelated work unnecessarily.

Do not claim exactly-once delivery across arbitrary external HTTP endpoints. Explain the actual delivery guarantee and remaining limitations.

Add deterministic concurrency tests where feasible. Use isolated test data and controlled transactions.

## 8. Phase 4 — Production Configuration and Secret Management

Inspect the actual configuration system and verify that production cannot start with insecure defaults.

### 8.1 JWT secret

The existing production validator in `backend/core/config.py` reportedly rejects a blank secret, `changeme`, and secrets shorter than 32 characters.

Verify the real behavior rather than relying on the report.

Test:

- Blank or missing secret in production mode.
- The known insecure placeholder.
- An undersized secret.
- A valid configured secret.
- Development/test behavior under the project's intended rules.
- Secret values not appearing in logs, exceptions, test output, or generated reports.

Use synthetic test values only. Never print a real secret to prove that it exists.

Confirm that the actual production deployment obtains its secret through the approved secret store or environment injection mechanism.

Do not generate a fake production configuration and call it deployed.

### 8.2 Environment validation

Verify all required production settings, including:

- Application environment.
- JWT secret.
- Runtime database URL.
- Migration database URL or authorized migration credential.
- CORS/origin settings where applicable.
- Debug mode.
- Logging configuration.
- Worker configuration.
- Any required signing, encryption, or storage credentials.

Do not invent variable names if the project already has a defined configuration contract.

Production must fail safely and clearly when a required security-critical setting is absent or insecure.

### 8.3 Runtime and migration identities

Use `poa_runtime` or the repository's explicitly documented equivalent least-privileged runtime role.

The application runtime identity must not be a database owner or superuser.

Separate runtime and migration credentials:

- The application API and worker use the least-privileged runtime credential.
- Schema migrations run only through an authorized migration identity.
- The runtime credential must not be able to perform privileged schema changes.
- The runtime credential must not be able to escalate to the owner role.

Do not store migration credentials in the application runtime configuration if they are not needed by the running application.

Do not expose credentials in command-line arguments, logs, reports, source files, or Git history.

## 9. Phase 5 — Database and Audit Integrity Readiness

Verify the database schema, migration state, identity, integrity controls, and backup posture.

### 9.1 Migration consistency

Confirm that:

- The application schema matches the migration history.
- The intended target is at the expected revision.
- Required audit enforcement triggers, functions, and constraints exist and are enabled.
- The runtime identity has only the required privileges.
- Migration execution is separated from normal application operation.

Do not downgrade a database merely to make the migration history look clean.

Do not rewrite historical migrations that have already been applied to shared or live databases. If a correction is required, use an appropriate new migration after reviewing its effects.

### 9.2 Append-only enforcement

Verify the audit ledger's actual database enforcement.

Under the runtime role, test the effective permissions and controls for:

- Appending a valid event through the supported application path.
- Updating existing audit events.
- Deleting existing audit events.
- Truncating the ledger.
- Escalating to a privileged database role.
- Inserting an event with an invalid event type or otherwise invalid required data.

Unauthorized destructive operations must be denied by effective database privileges and enforcement, not merely by an API-level check.

Perform potentially destructive negative tests only against a disposable clone or explicitly isolated test database. Never test destructive SQL against the protected development or production ledger.

Do not assume that a trigger alone prevents TRUNCATE. Verify the actual role privileges and database ownership.

### 9.3 Historical chain gaps

Preserve the documented seven historical gap ranges in the development database unless a separate explicit remediation decision authorizes a specific data change.

Verify that the classifier distinguishes:

- Known historical gaps.
- Newly observed gaps.
- Hard integrity failures.
- Hash mismatches.
- A healthy chain.

The existing expected result for the historical development ledger is `known_historical_only`, with seven known gaps, zero new gaps, and zero hard gaps, subject to confirming the actual current state.

A known historical gap must not conceal a new gap or a hash mismatch.

Verify the anchored/checkpoint endpoint and its reported checkpoint against the actual persisted ledger.

Do not manufacture historical audit events, backfill sequence numbers, rewrite hashes, or claim that a ledger is completely healthy when known defects remain.

### 9.4 External identity contract

Review the existing `external_subject` contract and the documented OQ-3 decision.

Preserve the pinned identity contract. Do not introduce speculative unique constraints, backfills, account merges, identity reassignment, or deletion of existing users.

If the production identity provider requires an unresolved product decision, record the exact decision needed and block the affected production authentication rollout until it is resolved.

### 9.5 Backup and restore

Identify the actual backup mechanism for the target environment.

Verify, to the extent permitted by the available environment:

- Backup creation and integrity.
- Backup retention and access controls.
- Restore procedure.
- Required migration and configuration steps after restoration.
- The ability to run integrity verification following restoration.
- Recovery objectives that are documented and actually supported.

Distinguish a logical snapshot from point-in-time recovery. Do not claim PITR capability unless WAL archiving, retention, and restore behavior have been verified.

Do not restore over a protected or production database as a test. Use a disposable target for restore verification.

## 10. Phase 6 — API and Worker Deployment

Deploy the verified application to the confirmed production target only after all required prerequisites and approvals are satisfied.

### 10.1 Pre-deployment gates

Before changing the live service, require:

- Correct target identification.
- Successful required test suites.
- Successful configuration validation.
- Valid production secret injection.
- Correct runtime database identity.
- Compatible database migration state.
- Verified backup/recovery plan.
- Resolved security-critical findings.
- A documented rollback procedure.
- Authorization for any required live migration or service restart.

If any gate fails, stop the affected deployment step. Continue independent safe work and report the exact blocker.

### 10.2 Deployment execution

Use the repository's established deployment process.

Deploy the API and webhook worker consistently from the same intended release/version, unless the architecture explicitly requires otherwise.

Verify:

- Correct release/version is running.
- API processes started successfully.
- Worker processes started successfully.
- Both use the intended runtime identity.
- Both load the correct configuration.
- Neither falls back to a superuser or developer-only credential.
- Logs contain no secrets.
- Startup and shutdown are clean.
- No unintended duplicate worker processes were created.

Do not assume that a local successful launch constitutes a production deployment.

Do not restart services that are outside the authorized target.

### 10.3 If no production target exists

If no production target, authorized credential, or approved secret store can be identified, do not invent one or deploy to a random environment.

Complete the implementation, tests, preflight validation, and deployment runbook. Clearly identify the specific external prerequisite that remains unavailable.

In this situation, BE-037 remains the final planned milestone, but the final disposition must be blocked rather than falsely accepted.

## 11. Phase 7 — Production Smoke Tests and Operational Verification

After deployment, execute safe, evidence-based verification against the actual deployed service.

### 11.1 Health and readiness

Verify every health path defined by the repository, including the existing six health-related paths where still applicable.

Confirm:

- Correct HTTP response.
- Correct service identity/version where exposed.
- PostgreSQL connectivity.
- Readiness reflects actual dependency state.
- No sensitive information is exposed by health responses.
- Unavailable critical dependencies produce appropriate readiness failure behavior.

Do not equate a generic HTTP 200 response with complete operational readiness.

### 11.2 Authentication and authorization

Verify representative valid and invalid authentication flows.

Check that protected endpoints reject unauthenticated or unauthorized requests as intended.

Verify that administrative operations remain inaccessible to ordinary users and that runtime credentials have not accidentally acquired elevated privileges.

Use synthetic accounts and data. Do not expose production tokens or personal data in the report.

### 11.3 Audit integrity

Execute the supported audit verification paths against the actual target.

Record:

- Current migration revision.
- Current ledger checkpoint/count.
- Classified chain status.
- Known gap count.
- New gap count.
- Hard gap count.
- Hash mismatch count.
- Enforcement presence.
- Effective runtime role.

Do not create artificial audit entries merely to make a verification report look active.

### 11.4 Webhook worker

Verify the worker through the actual intended runtime.

Use a controlled test subscription and a controlled destination where available. Do not send real customer data or arbitrary external webhooks.

Confirm:

- A valid delivery completes.
- Retryable failures follow the intended retry policy.
- Permanent failures reach the expected terminal state.
- Redirect/SSRF protection remains effective in the actual request path.
- Repeated sweeps do not duplicate completed deliveries.
- A restart does not corrupt delivery state.
- Stale processing recovery works if implemented.
- Concurrent worker behavior respects the implemented claim mechanism.
- Audit events are written through the supported append-only path.

Remove test data only when it is clearly isolated, owned by the test, and safe to remove. Never delete historical or user-owned records to clean up a smoke test.

### 11.5 End-to-end verification

Run a minimal, safe end-to-end flow across the key backend functionality that PoA actually supports.

Use the existing product APIs and schemas. Do not invent a new business workflow for the sake of testing.

The end-to-end verification should demonstrate that the API, database, audit ledger, and background worker operate together without violating the security or integrity invariants.

## 12. Phase 8 — Full Regression and Test Evidence

Use the project's established Python environment and test commands.

The previous BE-036 baseline was 831 passed, one skipped, zero failed. This is a historical comparison point, not an automatic acceptance result.

Run:

1. The new BE-037 security regression tests.
2. Webhook worker tests.
3. Audit integrity tests.
4. Authentication/configuration tests.
5. Database/migration tests against appropriate isolated targets.
6. API and integration tests.
7. The full backend regression suite.
8. Any additional targeted test required by an issue discovered during implementation.

Record the exact commands, exit codes, test counts, skipped tests, failures, and relevant environment identifiers.

Do not claim tests passed if they were not executed. Distinguish tests executed against mocks, disposable databases, `pofa_test`, development, staging, and production.

Do not use a production database as a test fixture.

Do not suppress a regression or weaken a test merely to restore a green suite. Investigate and fix the underlying problem, or document the precise blocker.

A skipped test is acceptable only if its reason is understood and the skip does not conceal an essential production gate.

## 13. Phase 9 — Observability, Operations and Recovery

Inspect the existing logging and operational facilities.

Ensure that the deployment provides sufficient diagnostic evidence for:

- API startup and shutdown.
- Worker startup and shutdown.
- Failed webhook delivery.
- Retry exhaustion.
- SSRF/redirect rejection.
- Audit integrity verification failures.
- Database connection failures.
- Authentication/configuration failures.
- Readiness degradation.
- Recovery or reclamation of stale processing work, if implemented.

Logs must not expose JWT secrets, database passwords, authorization headers, raw tokens, or sensitive payloads.

Document:

- Deployment procedure.
- Configuration validation.
- Database migration procedure.
- Service restart procedure.
- Health verification.
- Audit integrity verification.
- Backup and restore.
- Rollback.
- Incident triage.
- Recovery from a failed worker.
- Response to a new audit chain gap.
- Required operational permissions.

Use commands and configuration examples that match the actual repository and hosting platform. Do not fabricate deployment commands for a platform that has not been identified.

## 14. Phase 10 — Production Security Review

Perform a focused final review of the actual implementation and deployment configuration.

At minimum, examine:

- JWT configuration and secret management.
- Runtime versus migration database permissions.
- Audit ledger append-only enforcement.
- Privilege escalation paths.
- Authentication and authorization boundaries.
- Webhook SSRF, redirects, DNS resolution, and timeout behavior.
- CORS/origin policy where relevant.
- Debug settings and error responses.
- Sensitive logging.
- Dependency or startup failures.
- Worker retry and concurrency behavior.
- Migration safety and rollback implications.
- Any default credentials or unsafe fallback configuration.

Do not broaden this into an unrelated architectural rewrite or speculative feature work.

Fix findings that are within the current backend scope and can be addressed safely. For anything requiring an external decision, explain the risk and the exact required decision.

Do not mark a security issue as closed merely because it is documented. A closure requires implementation evidence and appropriate verification.

## 15. Phase 11 — Documentation and Final Deliverables

Create the final report at:

`docs/BE-037 Final Backend Production Deployment and Acceptance Report.md`

Update:

`docs/Backend Technical Debt and Deferred Fixes Backlog.md`

Use the repository's existing naming conventions and report style.

The final report must contain:

### A. Executive verdict

Choose exactly one:

- `ACCEPTED — PRODUCTION DEPLOYED AND VERIFIED`
- `CONDITIONALLY ACCEPTED — EXPLICITLY BOUNDED RESIDUAL RISK`
- `BLOCKED — FINAL ACCEPTANCE NOT GRANTED`
- `REJECTED — CRITICAL DEFECTS REMAIN`

Use the first verdict only when the actual intended production target has been deployed and the required operational acceptance gates have passed.

Use conditional acceptance only for non-critical residual risks that are explicitly documented, bounded, approved by the appropriate owner, and do not invalidate a mandatory security or integrity gate.

Do not use conditional acceptance to disguise missing production credentials, an unknown target, an unverified deployment, or unresolved critical security failures.

### B. Actual environment matrix

Include the environments actually tested, their role, application version/commit, migration revision, database identity, test coverage, and verification status. Redact secrets and sensitive connection information.

### C. Change inventory

List every implementation file, migration, test, configuration change, and document changed, with a brief explanation.

### D. Inherited finding closure

Provide a disposition for D-PFD, F-05, D-CHAIN, OQ-3, F-03, F-04, D-RESTART, BE-036-D1, and every additional finding discovered during BE-037.

### E. Test results

Record actual commands, results, failures, skips, and environment limitations.

### F. Production deployment evidence

Include release identity, deployment time, API and worker verification, health/readiness results, runtime database identity, integrity classification, and safe smoke-test outcomes.

Do not include secrets or sensitive payloads.

### G. Security and recovery

Document the verified runtime privilege boundary, audit enforcement, webhook redirect policy, backup/restore evidence, rollback procedure, and remaining risks.

### H. Final acceptance checklist

Mark each requirement `PASS`, `FAIL`, `BLOCKED`, or `NOT APPLICABLE`, with evidence.

### I. Final deferred-finding register

List each remaining item, severity, risk, owner or required decision, and whether it prevents acceptance.

Do not leave a known critical finding labelled merely "deferred" while simultaneously declaring full production acceptance.

### J. Final repository state

Record the branch, HEAD, working-tree state, and any commit or remote status actually verified.

Do not claim a commit or push occurred unless it actually did.

## 16. Git and Repository Safety Rules

These rules are mandatory throughout BE-037.

1. Inspect Git status before modifying files.
2. Preserve unrelated modifications, staged changes, deleted documents, and untracked files.
3. Never run `git add .` or `git add -A`.
4. Never run `git clean`.
5. Never run `git reset --hard`.
6. Never use destructive checkout/restore operations to discard changes.
7. Never rewrite history or force-push.
8. Never create a commit or push unless explicitly authorized.
9. If a commit is separately authorized, stage only individually reviewed and approved paths.
10. Inspect the staged diff before committing.
11. Do not include unrelated work in the BE-037 change set.
12. Do not stage or commit these excluded paths:
   - `backend/.venv312_clean/`
   - `backend/.venv312_repro/`
   - `backend/BE-023_Status.txt`
   - `backend/BE-023_Summary.txt`
13. Never claim that local repository state or remote synchronization has been verified without checking it.
14. Do not delete the previously preserved milestone reports or documentation.
15. If a migration, secret, backup, or generated artifact must remain outside Git, document that fact without exposing its contents.

If the working tree contains unexplained changes, stop before operations that could overwrite them and determine a safe way to proceed.

## 17. Database and Live-Environment Safety

The following are protected:

- `pofa_dev`
- `pofa_test`
- Any confirmed production database.

Do not reset, truncate, drop, backfill, downgrade, or destructively clean these databases to simplify testing.

Use named disposable databases or isolated clones for experiments and destructive negative tests.

Do not delete the documented historical audit gaps or modify the existing audit ledger merely to produce a healthy verification result.

Before an authorized live schema migration:

1. Confirm the exact target and current revision.
2. Confirm the approved migration.
3. Verify backup and recovery prerequisites.
4. Review the migration's effects.
5. Establish a recovery plan.
6. Record pre-migration evidence.
7. Apply only the approved migration.
8. Verify the resulting revision and invariants.
9. Record post-migration evidence.

Do not restart services, change production roles, or perform a production deployment without the appropriate target, access, and authorization.

Do not assume the existence of a production secret store or deployment target. Discover it or document it as unavailable.

## 18. Execution Discipline

Work systematically.

For every substantial change:

1. State the finding being addressed.
2. Inspect the relevant implementation and tests.
3. Determine the minimal safe correction.
4. Implement the correction.
5. Add regression coverage.
6. Run the focused tests.
7. Run the relevant integration tests.
8. Run the broader suite.
9. Review the diff and security implications.
10. Record the evidence in the final report and backlog.

Do not perform a broad rewrite when a small correction is sufficient.

Do not modify unrelated frontend functionality or introduce new product features unrelated to backend production readiness.

Do not change public API contracts unnecessarily. If a contract change is unavoidable, update schemas, implementation, tests, and documentation consistently.

Do not weaken validation or remove tests to obtain passing results.

Do not confuse a successful local test with a successful production operation.

If a required external action is unavailable, finish all independent safe work and produce a precise, actionable blocker report. Do not repeatedly attempt a blocked operation using different guessed targets or credentials.

## 19. Definition of Done — Final Backend Acceptance

BE-037 may receive `ACCEPTED — PRODUCTION DEPLOYED AND VERIFIED` only when all applicable mandatory requirements below are satisfied.

- [ ] The actual production target has been positively identified.
- [ ] The deployed release is identifiable and corresponds to reviewed repository code.
- [ ] Required configuration validation passes.
- [ ] Production JWT secret management is verified without exposing secret values.
- [ ] API and worker use the intended least-privileged runtime database identity.
- [ ] Runtime and migration permissions are separated.
- [ ] The deployed database is at the expected migration revision.
- [ ] Append-only enforcement is verified against the actual target.
- [ ] TRUNCATE and other prohibited destructive operations are effectively denied to the runtime identity.
- [ ] Audit integrity classification works correctly and distinguishes known gaps from new gaps and hard failures.
- [ ] The anchored/checkpoint endpoint is operational and correctly reflects the ledger.
- [ ] The `external_subject` contract has an appropriate final disposition for the deployed authentication architecture.
- [ ] BE-036-D1 is fixed and its actual request path has regression coverage.
- [ ] Webhook retries, terminal failures, idempotency, and worker restart behavior are verified.
- [ ] Concurrency and stale-processing risks are resolved or explicitly shown not to apply to the actual deployment model.
- [ ] API and worker deployment/restart has been verified on the actual target.
- [ ] Health and readiness checks pass.
- [ ] Safe authentication, authorization, audit, and end-to-end smoke tests pass.
- [ ] The required regression suite passes.
- [ ] Backup/recovery and rollback procedures are documented and verified to the degree claimed.
- [ ] The final security review is complete.
- [ ] The final report and technical-debt backlog are updated.
- [ ] Every remaining finding has an explicit disposition.
- [ ] The final repository state is accurately recorded.
- [ ] No unrelated work was discarded or included unintentionally.
- [ ] No unsupported claim of deployment, test success, or acceptance appears in the report.

A requirement that cannot be verified is not a pass.

A blocked external prerequisite must be identified explicitly and must not be hidden in a general caveat.

## 20. Finality Rule — No BE-038

BE-037 is the final planned backend milestone.

Do not create BE-038, BE-039, or another successor milestone in response to a finding discovered during this work.

Instead:

- Resolve in-scope findings within BE-037.
- Add necessary regression tests and documentation within BE-037.
- Track any approved, non-critical residual risk in the final backlog with a named owner and disposition.
- If an essential external prerequisite is unavailable, report BE-037 as blocked and specify the exact action required to unblock it.
- If a critical defect remains, do not declare production acceptance.
- Do not artificially expand the scope into unrelated features or architectural rewrites.

Finality does not mean ignoring defects. It means completing the backend work to a clearly defined standard and making the final status truthful.

## 21. Required Final Response

When finished, provide a concise but evidence-rich final summary containing:

1. **BE-037 verdict** and whether production is actually deployed.
2. What was implemented and what was fixed.
3. The final test results, including passed, skipped, and failed counts.
4. Actual production health, readiness, database identity, and audit integrity results, if deployment was possible.
5. The status of BE-036-D1 and the other inherited findings.
6. The final report and backlog paths.
7. Any residual risks, blocked prerequisites, or required owner decisions.
8. The branch, HEAD, and working-tree state.
9. Whether any commit or push was performed, stated accurately.

Never finish with “everything is production-ready” unless the evidence satisfies the definition of done above.

**Begin BE-037 now by auditing the actual repository, environment, outstanding findings, and authorization boundaries. Continue through implementation, regression testing, deployment where authorized, and final acceptance. BE-037 is the final planned backend milestone; do not create a successor milestone.**