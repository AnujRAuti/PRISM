BE-023 — Verification Hardening, CI Safety & Reproducible Test Infrastructure

You are working on the Proof-of-Action (PoA) backend repository:

https://github.com/AnujRAuti/Proof-Of-Action-Final

Current branch:

Backend

Current remote HEAD is:

9374db4a956fc7acd020886218515349fb70dd84

Parent:

44991cbdb72edbecec02d44ab7ee22ecc7034f80

The previous milestones BE-001 through BE-022 are implemented.

PRIMARY OBJECTIVE

Do not add a new product feature.

BE-023 is an engineering-hardening milestone whose purpose is to make the existing PoA backend:

reproducibly testable
isolated from contaminated databases
safe against destructive test cleanup
migration-verifiable
CI-ready
explicit about environment dependencies
honest about verification status
resistant to false-positive tests
safe for future agents/developers to modify

The goal is:

A future developer/AI agent should be able to clone the repository, provision the documented dependencies, create a clean database, run the verification suite, and obtain trustworthy results without manually guessing which database/environment/state is being tested.

1. FIRST: REPOSITORY RECONNAISSANCE

Before changing ANY code:

Inspect the current Backend branch.
Inspect the latest commits.
Read:
docs/Final Architecture.md
BE-021 verification documentation
BE-022 verification documentation
relevant implementation summaries
README.md
docker-compose.yml
.env.example
Alembic configuration
pytest configuration
test fixtures
Identify the existing:
database configuration
Redis configuration
MinIO configuration
Python version requirements
ML dependencies
migration process
test database behavior
test cleanup behavior
Do NOT assume the current working tree is clean.
Do NOT reset, checkout, restore, clean, delete branches, delete stashes, force-push, or rewrite history.
HARD GATE

Before implementation, produce an internal inventory:

CURRENT_BRANCH
CURRENT_COMMIT
REMOTE_BRANCH
REMOTE_HEAD
WORKTREE_STATE
DATABASE_CONFIGURATION
REDIS_CONFIGURATION
MINIO_CONFIGURATION
PYTHON_VERSION
ML_RUNTIME
ALEMBIC_HEAD
TEST_COUNT
KNOWN_TEST_DATABASE_RISKS

If the working tree contains unrelated user changes, preserve them.

Never discard them.

2. TEST DATABASE ISOLATION

Introduce a clearly documented test-database strategy.

The test suite must NOT silently depend on whatever database happens to be configured in .env.

The implementation must provide an explicit mechanism for selecting the test database.

Requirements:

production/development DB configuration remains unchanged
test execution can explicitly target a dedicated database
test documentation clearly identifies which database is being used
tests must fail clearly if the intended test DB is unavailable
no test may silently connect to pofa_dev when a dedicated test DB is intended

Prefer an explicit environment variable such as:

TEST_DATABASE_URL

or an equivalent clean architecture already consistent with the repository.

Do not duplicate database configuration logic unnecessarily.

3. CLEAN-DATABASE VERIFICATION

Provide a documented reproducible procedure for:

creating a fresh test database
installing required PostgreSQL extensions
running:

alembic upgrade head

verifying the migration reaches the current head
running the integration suite
reporting the exact database used

The procedure must work on a completely fresh database.

Do NOT rely on an existing contaminated database.

4. AUDIT LEDGER SAFETY — CRITICAL

The audit ledger is append-only and tamper-evident.

Existing production behavior must NOT be weakened.

Tests must NEVER delete AuditLedgerEvent rows as ordinary cleanup.

Add or maintain a static regression guard that detects attempts in the test tree to:

ORM-delete AuditLedgerEvent
raw-SQL-delete audit ledger rows
truncate the audit ledger
otherwise mutate/delete historical audit rows for cleanup

The guard must distinguish legitimate assertions/testing of tampering from destructive test cleanup.

The objective is:

Tests may test audit tampering explicitly inside controlled rollback transactions, but must never permanently destroy audit history merely to clean test data.

Do not modify the production hash-chain implementation to compensate for test contamination.

5. TEST ISOLATION PRINCIPLE

Audit events are globally interleaved.

Therefore cleanup based on:

actor
project
organization
resource

is unsafe for append-only global audit history.

Do not introduce cleanup rules that remove historical audit events by those dimensions.

Use transactional rollback, dedicated databases, or safe fixture isolation instead.

6. MIGRATION VERIFICATION

Add a deterministic migration verification test/process.

It must verify:

fresh database can upgrade from base → head
current Alembic head matches expected repository head
no migration requires undocumented pre-existing schema
required PostgreSQL extensions are available
downgrade/upgrade behavior is tested where appropriate
migration state is not accidentally dependent on developer-local state

Do not alter historical migrations merely to make a contaminated database pass.

Historical migrations should remain immutable unless there is a demonstrable migration defect.

If a migration itself is genuinely defective, document the evidence before modifying it.

7. REAL-CODE TEST REQUIREMENT

Tests must exercise real application behavior.

Do not "fix" failures by:

mocking the implementation under test
replacing production services with fake success responses
bypassing authorization
bypassing database constraints
bypassing audit emission
bypassing storage
bypassing Redis
replacing ML inference with fabricated results

Mocks are allowed only at genuine external boundaries where appropriate.

For every important integration test, determine whether it actually reaches the real implementation.

8. ML ENVIRONMENT VERIFICATION

PoA currently depends on real ML functionality including:

CLIP embeddings
YOLO vision inference

Document the supported Python version and compatible dependency versions.

The test system must clearly distinguish:

ML AVAILABLE
ML UNAVAILABLE
ML TEST SKIPPED
ML TEST FAILED

Do NOT silently convert missing ML dependencies into successful tests.

Do NOT commit model weights into Git.

If model downloads are required, document the expected cache behavior.

The repository must remain runnable on the documented CPU environment.

9. REDIS + MINIO DEPENDENCY VERIFICATION

Integration tests requiring Redis or MinIO must clearly detect missing services.

Add/maintain explicit connectivity checks.

Do not turn dependency failures into false passing tests.

Document:

PostgreSQL
PostGIS
pgvector
Redis
MinIO
Python
ML dependencies

and how each is started for integration testing.

10. FULL-SUITE VERIFICATION

After implementation:

Stage A — targeted tests

Run the tests directly related to BE-023.

Stage B — affected historical suites

Run suites whose behavior was changed.

Stage C — complete integration suite

Run:

pytest tests/integration -v

Record:

exact test count
passed
failed
skipped
warnings
duration
database used
Stage D — unit suite

Run the complete unit suite.

Do not claim success unless the command was actually executed.

11. FAILURE TRIAGE RULE

If tests fail:

DO NOT immediately modify production code.

First classify every failure as one of:

PRODUCTION_DEFECT
TEST_DEFECT
ENVIRONMENT_DEFECT
DATABASE_CONTAMINATION
MIGRATION_DEFECT
DEPENDENCY_DEFECT
STALE_EXPECTATION
UNRELATED_PREEXISTING_FAILURE

For database-related failures:

reproduce on a fresh database
compare fresh vs existing DB behavior
inspect database state
inspect test cleanup
only then modify production code if evidence points to production

Never treat a failure on a contaminated shared database as proof of a production defect.

12. NO SILENT TEST FIXES

Every test modification must answer:

Why was the old test wrong?
What production behavior is actually being verified?
Why does the new test detect regressions?
Does the test execute the real production path?
Could the test itself corrupt persistent state?

Document these decisions in the verification report.

13. VERIFICATION REPORT

Create/update:

docs/BE-023 Verification Report.md

It must contain:

Environment
OS
Python version
dependency/runtime versions
PostgreSQL version
PostGIS
pgvector
Redis
MinIO
database name/type
Alembic head
Test Strategy

Explain:

database isolation
fixture isolation
rollback strategy
audit-ledger protection
ML dependency handling
Redis/MinIO handling
Results

Use exact executed numbers.

Example:

Integration:
XXX passed
X failed
X skipped
X warnings
Duration: XX

Unit:
XXX passed
X failed
X skipped
X warnings
Duration: XX

Never invent these numbers.

Failure Investigation

For every failure encountered during implementation:

symptom
reproduction
investigation
root cause
fix
regression test
verification
Known Warnings

List deprecation warnings separately from failures.

Do not classify warnings as failures.

14. ANTI-CONTAMINATION REGRESSION TEST

The repository must contain an automated guard ensuring that future tests cannot accidentally reintroduce the exact audit contamination pattern encountered previously.

The guard must scan the test tree for destructive operations against AuditLedgerEvent.

It should detect both:

ORM deletion patterns
raw SQL deletion/truncation patterns

It must not be fooled by comments/docstrings containing example code.

Add regression tests for the guard itself.

15. GIT SAFETY — ABSOLUTE RULE

This project has previously suffered from accidental Git operations.

Therefore:

NEVER execute automatically:
git reset --hard
git clean -fd
git checkout -- .
git restore .
git branch -D
git stash drop
git stash clear
git push --force
git push --force-with-lease
history rewriting
deleting remote branches

unless the human explicitly instructs you to do that exact operation.

Before any Git mutation:

git status
git branch --show-current
git log -5 --oneline
git remote -v

If uncertain, stop and ask.

Never assume uncommitted changes belong to you.

16. COMMIT SAFETY

Do not commit automatically after implementation.

Before committing:

run git status
inspect changed files
inspect git diff --stat
inspect important diffs
verify no secrets
verify no virtual environments
verify no model weights
verify no generated database files
verify no temporary diagnostic output
verify tests pass

Only then create a commit.

Use a clear message:

BE-023: harden reproducible verification infrastructure

Do not amend previous commits.

Do not rewrite history.

17. SCOPE CONTROL

BE-023 is NOT permission to redesign:

authentication
authorization
evidence graph
fusion
publication
retention
dispute/correction
review cases
frontend
ML models
audit-chain architecture

If you discover a separate defect, document it and add it to a follow-up list unless it is necessary for BE-023 correctness.

No unrelated refactors.

No dependency upgrades merely for convenience.

No architecture changes without explicit approval.

18. DEFINITION OF DONE

BE-023 is complete only when:

 clean test database procedure exists
 tests cannot silently use the wrong database
 fresh Alembic migration succeeds
 audit ledger cannot be accidentally deleted by test cleanup
 regression guard exists for destructive audit operations
 Redis dependency behavior is explicit
 MinIO dependency behavior is explicit
 ML dependency/runtime behavior is explicit
 integration tests exercise real application paths
 full integration suite executed
 full unit suite executed
 exact results recorded
 all failures investigated rather than blindly patched
 no destructive Git operations performed
 no secrets/model weights/generated artifacts committed
 verification report updated
 working tree reviewed before commit
 commit created only after verification
FINAL AGENT RULE

Do not optimize for making the test suite green. Optimize for making the test suite trustworthy.

A passing test against the wrong database, mocked production behavior, stale state, or corrupted audit history is not a successful verification.

When something fails, investigate the environment and test isolation before changing production logic.

When something passes, record exactly what was executed and against what environment.

Evidence of verification is part of the deliverable.

One change I'd make compared with our previous milestone prompts

For BE-023, I'd explicitly tell the agent not to start coding immediately.

The first output should be a reconnaissance report and proposed implementation plan. Then we approve the plan before it modifies anything.

That single gate would have made the earlier audit-ledger incident much easier to catch before it contaminated thousands of rows.