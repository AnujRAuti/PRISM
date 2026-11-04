# BE-031 — Post-BE-030 Operational Readiness & Deferred Debt Closure

## 0. Mission and operating mode

You are working on the Proof-Of-Action (PoA) backend repository:

- Repository: `AnujRAuti/Proof-Of-Action-Final`
- Expected branch: `Backend`
- Database technology: PostgreSQL, PostGIS, pgvector, SQLAlchemy and Alembic
- Completed milestones: BE-001 through BE-030, subject to verification of the actual repository state and Git history.
- Primary reference: the repository's existing `docs/` task specifications, results documents and backlog.

Your objective is to inspect the actual post-BE-030 state, reconcile outstanding issues, and safely advance operational readiness without compromising audit integrity, existing application behavior, or database safety.

**This is not permission to migrate `pofa_dev`, restart application services, rewrite historical audit records, or push Git changes.**

Do not assume a task is complete because a previous report says it is. Verify it against the current repository, database identity where authorized, Git state and executable evidence.

### Mandatory scope validation

Before changing any file:

1. Inspect the current branch, working tree, latest commits and repository root.
2. Locate and read the current authoritative backlog and relevant sections of the BE-029 and BE-030 task and results documents.
3. Search for an existing BE-031 specification or a previously approved next-task proposal.
4. Identify whether another task has already claimed any of the issues listed below.
5. Reconcile the task numbering, migration head and commit history against the actual repository.

If a canonical BE-031 specification already exists, follow it instead of replacing its scope with this proposal. Preserve the existing numbering and document conventions.

If the current working tree contains uncommitted changes, do not reset, clean, stash, overwrite or silently incorporate them. Record the state and protect unrelated work.

If the repository does not match the expected branch or baseline, stop and report the discrepancy before implementation.

---

## 1. Primary objective

Produce an evidence-backed operational-readiness assessment and close the highest-priority issues that can be resolved safely within the existing approval boundaries.

The intended areas of investigation are:

1. BE-029 identity remediation and the unresolved `external_subject` decision.
2. BE-030 audit-ledger enforcement and historical chain-integrity behavior.
3. The difference between the migration state of `pofa_test` and `pofa_dev`.
4. The outstanding audit-ledger `TRUNCATE` protection gap.
5. API and worker restart readiness.
6. The existing backlog of schema, migration, audit and application debt.
7. Documentation and regression-test consistency.

Do not interpret this list as permission to resolve every item immediately. Each item must be classified according to its technical prerequisites, risk, required owner decisions and authorization.

The desired result is a trustworthy operational-readiness baseline, not a collection of superficial green checks.

---

## 2. Non-negotiable safety rules

### 2.1 Live database protection

The databases `pofa_dev` and `pofa_test` are distinct targets and must never be treated interchangeably.

- Do not run migrations against `pofa_dev`.
- Do not execute INSERT, UPDATE, DELETE, TRUNCATE, DDL or data-cleanup statements against `pofa_dev`.
- Do not restart or launch API servers, workers, schedulers or background consumers that could write to `pofa_dev`.
- Do not reset, recreate, drop or restore over either database.
- Do not use application integration tests against `pofa_dev`.
- Do not assume a database URL identifies the intended database merely because its environment-variable name looks correct.
- Resolve the actual target from the connection and verify `current_database()` before any database operation.
- Follow the repository's existing database-safety guards. Never bypass them for convenience.

Read-only diagnostics against `pofa_dev` are permitted only when the repository's safety mechanism explicitly permits the operation and the query is genuinely read-only. Do not attempt to circumvent a safety refusal.

### 2.2 Owner approval gates

The following require explicit owner authorization before execution:

- Migrating `pofa_dev` to BE-030 or any later Alembic revision.
- Stopping, starting or restarting application services or workers.
- Changing production-like database roles, ownership or privileges.
- Performing a repair, backfill or reconciliation that changes existing database records.
- Changing the identity policy for `external_subject`.
- Removing or rewriting historical migrations.
- Any irreversible or destructive database operation.

You may prepare a migration plan, analyze a verified backup, write isolated tests, produce SQL for review or document the required commands. Preparation is not authorization to execute them.

### 2.3 Git discipline

- Do not use `git reset --hard`, `git clean`, force-push or history rewriting.
- Do not stage unrelated changes.
- Do not use `git add -A` or `git add .`.
- Do not stage, commit or push anything unless explicitly authorized.
- Do not silently revert user-owned modifications.
- Never commit secrets, `.env` files, local databases, dumps, credentials, temporary artifacts or generated caches.

For this task, the default is **no staging, no commit and no push**.

### 2.4 Audit-ledger integrity

Treat `audit_ledger_events` as immutable historical evidence.

- Never repair history by deleting, updating, renumbering or recreating existing events.
- Never manufacture missing events to make a sequence appear contiguous.
- Never weaken `verify_chain()` or integrity checks to obtain a passing result.
- Never change test expectations to conceal a genuine failure.
- Never use the sanctioned mutation hatch outside a narrowly scoped, authorized test.
- Preserve the existing audit guard and its restrictions.

---

## 3. Establish the real baseline

Record the following before making changes.

### 3.1 Git baseline

Capture and report:

- Repository root.
- Current branch.
- `git status --short --branch`.
- Current HEAD SHA and subject.
- Whether BE-029 and BE-030 commits exist locally.
- Whether the branch is ahead of or behind its remote, if the remote-tracking information is available locally.
- The exact set of pre-existing modified, staged and untracked paths.

Do not fetch, pull, push or alter the branch simply to obtain a cleaner baseline.

### 3.2 Migration baseline

Inspect:

- `alembic.ini`
- `alembic/env.py`
- The current migration revision graph.
- The BE-029 and BE-030 migrations.
- `backend/db/models.py`
- Schema-drift policy and baseline tests.
- Migration unit tests.
- The relevant task and results documents.

For every database that can be safely inspected, record the actual database name, current `alembic_version`, and the expected head from the migration graph.

Known historical reference points include:

- `pofa_dev` was previously recorded at `s9t0u1v2w029`.
- `pofa_test` was previously recorded at `t0u1v2w3x030`.
- BE-030's migration introduced audit-ledger append-only enforcement and a chain-integrity guard.

These are historical reference points, not proof of the current state. Re-measure them wherever authorized.

### 3.3 BE-030 verification baseline

Read `docs/BE-030 Audit Ledger Append-Only Enforcement Results.md` and verify that the repository contains the corresponding implementation and tests.

The previous report recorded:

- `pytest tests`: 792 passed, 1 skipped, 0 failed.
- `test_audit_guard.py`: 25 passed.
- Schema-drift gate: 6 passed.
- `alembic check`: clean under the documented reflection-artifact filter.
- Append-only UPDATE/DELETE enforcement and out-of-domain INSERT rejection.
- A chain-integrity guard that refuses unsafe appends when the predecessor is invalid.
- Successful migration upgrade/downgrade/re-upgrade on an isolated clone.

These are previous results. Do not present them as newly executed results. Re-run relevant tests where the environment permits, and record the exact command, target and output.

---

## 4. Investigate BE-029 carry-over: `external_subject`

Locate the authoritative BE-029 documentation and the backlog entry concerning `external_subject`.

Determine:

1. The actual database column definition and constraints.
2. Every code path that reads or writes this field.
3. Whether it represents an external identity-provider subject, a username, a display attribute or another concept.
4. The existing test coverage for null, duplicate and conflicting values.
5. Which policy decisions remain unresolved.

Do not invent external identities, derive identities from usernames without an approved mapping policy, backfill values speculatively or introduce `NOT NULL` without an approved data-migration plan.

Do not decide an unresolved product or identity policy on the owner's behalf.

If implementation depends on a missing policy decision, produce a concise decision brief containing:

- The exact unresolved question.
- The affected schema and API behavior.
- The viable options supported by the current implementation.
- The compatibility implications of each option.
- Required migration and test changes.
- The risks of deferring the decision.

Keep the issue in the authoritative backlog until the decision is explicitly made and implemented.

---

## 5. Investigate BE-030 audit-chain integrity

BE-030 established database-level enforcement, but it did not authorize a repair of the historical `pofa_dev` ledger.

The previous investigation found that the historical `pofa_dev` ledger had missing sequence numbers. The exact measured baseline must be taken from the current BE-030 results document and, if permitted, remeasured read-only.

Investigate:

- The current `verify_chain()` implementation.
- The append path and predecessor validation.
- How sequence gaps, missing predecessors, invalid hashes and malformed chain state are classified.
- Whether diagnostics distinguish a pre-existing invalid history from a new integrity violation.
- Whether an invalid historical chain prevents safe future appends.
- Whether the application exposes an accurate, actionable failure rather than a false success.
- Whether all these behaviors have isolated regression tests.

Do not alter historical events to make the chain valid.

If the existing guard is correct, document its proven behavior and any operational limitation. If a defect is found, reproduce it on an isolated test database, implement the narrowest correct fix and add regression tests.

### Required test cases, where applicable

- A valid chain accepts an ordinary append.
- An invalid predecessor is rejected.
- A newly corrupted chain is not reported as valid.
- Historical gaps remain visible.
- A refused append does not create a partial event.
- Concurrent writers do not bypass predecessor validation.
- Transaction rollback preserves consistency.
- Failure messages and HTTP responses, where applicable, accurately represent the failure.

Do not run write probes against `pofa_dev`.

---

## 6. Investigate the `TRUNCATE` enforcement gap

BE-030 deliberately leaves `TRUNCATE` as a known gap under its selected trigger design.

Determine the actual protection model from the migration and PostgreSQL catalogs:

- Trigger type and enabled state.
- Trigger function and behavior.
- Table ownership.
- Application connection role.
- Database grants and role memberships.
- Whether the application can execute `TRUNCATE` on `audit_ledger_events`.
- Whether deployment uses an owner role or a restricted runtime role.

Do not assume a row-level UPDATE/DELETE trigger also protects against `TRUNCATE`.

Do not modify live database roles or privileges.

On an isolated database or disposable clone, determine whether the existing deployment model can enforce the intended rule with a least-privilege runtime role. Consider role ownership, migrations, test setup, operational tooling and rollback requirements.

Document the difference between:

1. A verified mitigation in the current code.
2. A mitigation that works only when deployed with a restricted database role.
3. A remaining gap that requires owner authorization or a deployment change.

Do not claim `TRUNCATE` is protected until a test proves that the effective application role is denied the operation while legitimate migrations and maintenance remain possible.

If closing the gap requires a change to the database-role architecture, produce a proposed follow-up task and keep the change gated.

---

## 7. Plan safe `pofa_dev` migration readiness

The current known state is that `pofa_dev` was not migrated to BE-030. Do not migrate it in this task.

Produce a reviewed migration-readiness plan based on actual repository state.

The plan must cover:

1. Confirmation of the target database and current Alembic revision.
2. A fresh custom-format PostgreSQL backup stored outside the repository.
3. Backup integrity and SHA-256 recording.
4. Restoration of that backup into a separately named disposable verification database.
5. Comparison of relevant schema, data counts, constraints and audit-ledger measurements between the source snapshot and the restored clone.
6. Execution of the migration against the clone.
7. Verification of enforcement objects and relevant application behavior.
8. A tested rollback or recovery strategy that is compatible with append-only audit history.
9. Required service and worker shutdown procedures.
10. A pre-migration and post-migration verification checklist.
11. Explicit owner approvals required at each stage.
12. A clear stop/go decision with objective criteria.

Account for the fact that an ordinary `pg_dump` is a snapshot, not point-in-time recovery. Do not promise recovery of writes made after the backup.

A database restore must never overwrite `pofa_dev` or `pofa_test`.

If backup restoration, migration execution or rollback cannot be proven safely, report the blocker instead of proceeding.

The final plan must explicitly state that **no live migration was executed by BE-031**.

---

## 8. API and worker restart readiness

The earlier BE-029/BE-030 history recorded API and worker restart as pending owner action.

Do not start, stop or restart any services.

Instead, inspect the current repository and configuration to determine:

- Which API and worker processes are relevant.
- Which database each process would connect to.
- Whether environment variables and connection URLs are unambiguous.
- Whether the process startup path runs migrations automatically.
- Whether startup could trigger background jobs or write audit events.
- Whether a readiness check can establish the database target safely.
- Whether workers require queue draining or other coordination.
- Whether restart could expose the application to a database schema mismatch.

Produce an operator-ready restart checklist with:

- Preconditions.
- Explicit target confirmation.
- Required owner approvals.
- Safe startup order.
- Health checks.
- Audit-ledger verification expectations.
- Rollback and stop conditions.

Do not claim the API or workers are running or healthy unless their status was actually observed through an authorized read-only method.

---

## 9. Backlog reconciliation

The repository's existing backlog is the single source of truth for outstanding technical debt and deferred decisions.

Do not create a competing backlog.

For every relevant item:

1. Find the current entry.
2. Confirm its current status against the repository.
3. Identify dependencies and risk.
4. Determine whether it is safe to close in BE-031.
5. Update the existing entry only when the evidence justifies the change.
6. Record a concrete follow-up task for unresolved work if the backlog's existing convention requires one.

At minimum, inspect the documented carry-overs involving:

- `external_subject`.
- Live `pofa_dev` migration.
- Historical audit-chain gaps.
- `TRUNCATE` protection and database-role hardening.
- API and worker restart.
- Alembic reflection artifacts and schema-drift blind spots.
- The legacy `audit_events` table.
- Other deferred findings in the current backlog.

Do not remove an item merely because it has been mentioned in a results document. Do not mark an item complete without evidence.

Do not clean up unrelated debt just because it is nearby.

---

## 10. Implementation policy

After reconnaissance, implement only fixes that satisfy all of the following:

- The defect is reproducible or independently demonstrated.
- The fix is within the approved BE-031 scope.
- It does not require an unresolved owner decision.
- It does not require an unauthorized live database change.
- It can be verified on an isolated test target.
- It preserves completed BE-001 through BE-030 contracts unless a documented defect requires a narrow compatibility fix.
- It includes regression tests.
- It updates the existing backlog and documentation consistently.

Prefer a small, independently verifiable change over a broad refactor.

Do not introduce new dependencies unless a demonstrated requirement justifies them.

Do not implement new product functionality, fabricate behavior or replace real operations with mocks in production paths.

If no implementation change is safely justified, a well-evidenced readiness assessment and an explicit list of gated decisions is a valid result.

---

## 11. Required verification

Run the narrowest relevant tests first, then expand the test matrix.

At minimum, where supported by the available environment:

- BE-031 targeted regression tests.
- BE-029 identity-conflict tests.
- BE-030 audit-ledger enforcement and chain-integrity tests.
- Audit guard tests.
- Migration revision-graph tests.
- Schema-drift containment tests.
- Relevant authorization and API integration tests.
- Full test suite against the explicitly configured isolated `pofa_test` database.

Also verify:

- Alembic upgrade behavior on an isolated disposable database.
- Downgrade/re-upgrade behavior where appropriate.
- The final Alembic head.
- `alembic check` output, including documented filters and known reflection artifacts.
- `git diff --check`.
- No accidental secrets, dumps, database files or generated artifacts.
- No unauthorized writes to live databases.
- No audit-ledger guard violations.

Do not run multiple database-mutating test suites concurrently against the same database if they could interfere with one another.

If a test fails:

1. Capture the exact failure.
2. Establish whether it is a new regression, a known baseline issue, an environment failure or a test-isolation problem.
3. Reproduce it safely.
4. Fix the cause when in scope.
5. Re-run the affected test and relevant regression matrix.
6. Report remaining failures honestly.

Never hide failures by changing test selection, suppressing exceptions or silently weakening assertions.

Report skipped tests and explain their skip conditions.

---

## 12. Documentation deliverables

Follow the existing repository naming and formatting conventions.

Create a task specification only if no canonical BE-031 specification already exists.

Create a results document using the repository's established naming convention, for example:

`docs/BE-031 Post-BE-030 Operational Readiness Results.md`

The results document must distinguish:

- Previously documented evidence.
- Newly executed checks.
- Code changes actually made.
- Issues resolved.
- Issues still open.
- Owner decisions required.
- Operations prepared but not executed.
- Tests not run and why.
- Limitations of the evidence.

Do not write a success claim unless the relevant command or check was actually executed.

Update the authoritative backlog rather than creating a parallel document that duplicates its function.

---

## 13. Required results report

The final report must contain these sections.

### A. Baseline

- Repository root and branch.
- HEAD before and after.
- Initial working-tree state.
- Actual database targets and Alembic revisions observed.
- Source documents inspected.

### B. Findings

For every finding:

- Exact problem.
- Evidence.
- Severity and operational impact.
- Whether it was pre-existing.
- Whether it is resolved, deferred or blocked.

### C. Changes made

For each change:

- Files modified or created.
- Why the change was necessary.
- Tests that exercise it.
- Actual verification output.

### D. Database safety

State explicitly whether any operation wrote to `pofa_dev` or `pofa_test`, and distinguish permitted test-database operations from live operations. Do not infer safety from intention alone.

### E. Audit integrity

Report the measured chain state for each database actually inspected, the enforcement objects verified and the results of relevant integrity tests.

### F. Migration readiness

Report the current observed migration heads and the evidence supporting the proposed live-migration plan. Explicitly confirm that BE-031 did not migrate `pofa_dev`.

### G. Test results

Include exact commands, target database, passed, failed and skipped counts, duration where available, and known baseline failures.

### H. Backlog changes

List each entry updated, closed or added, with the supporting evidence.

### I. Outstanding approvals

List every decision or action that still requires explicit owner authorization.

### J. Git status

Report:

- Modified and untracked files.
- Staged files, if any.
- Commit created, if any.
- Push performed, if any.

Expected for this task: **nothing staged, nothing committed and nothing pushed**.

### K. Final disposition

Choose exactly one:

- **COMPLETE** — all approved BE-031 requirements are implemented and verified.
- **COMPLETE WITH DOCUMENTED BLOCKERS** — safe in-scope work is finished, but gated decisions or operational actions remain.
- **PARTIAL** — some approved requirements remain unfinished.
- **BLOCKED** — a prerequisite or safety condition prevents meaningful execution.

Explain the disposition with evidence.

---

## 14. Stop conditions

Stop the affected operation and report the blocker if:

- The repository or branch is unexpected.
- The existing task specification conflicts with this proposal.
- A database URL resolves to an unexpected database.
- A safety guard refuses the operation.
- A migration would alter `pofa_dev`.
- A repair would modify historical audit records.
- A necessary identity or operational policy has not been approved.
- The required backup cannot be restored and verified on an isolated database.
- A test requires a live write to establish its result.
- A change would weaken authorization, validation, audit integrity or database isolation.
- An unrelated working-tree change would be overwritten.
- Evidence is insufficient to distinguish an actual fix from a false positive.

Do not bypass the stop condition. Continue with other independent, safe reconnaissance work when possible.

## 15. Definition of Done

BE-031 is complete only when:

- [ ] The existing BE-031 specification and backlog were checked before implementation.
- [ ] The real repository and migration baseline were recorded.
- [ ] Every investigated finding is classified with supporting evidence.
- [ ] `external_subject` remains governed by an explicit owner decision; no speculative identity backfill occurred.
- [ ] Historical audit records were not rewritten to conceal chain damage.
- [ ] The `TRUNCATE` gap is accurately characterized and either safely mitigated in an isolated environment or retained as an explicit blocker.
- [ ] The `pofa_dev` migration plan is evidence-based and was not executed.
- [ ] API and worker restart readiness is documented without restarting services.
- [ ] The existing backlog is reconciled without deleting unresolved debt.
- [ ] Any code changes have focused regression tests.
- [ ] Relevant verification commands have been run and exact outcomes recorded.
- [ ] Documentation accurately reflects observed reality.
- [ ] No live database operation was performed without explicit authorization.
- [ ] No unrelated files were staged, committed or pushed.
- [ ] The final report accurately identifies completed work, limitations and outstanding owner decisions.

Begin with reconnaissance. Do not start with implementation. Do not claim completion until the evidence supports it.