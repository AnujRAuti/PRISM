BE-024 — Production Implementation & Verification Task

You are working on the Proof-of-Action (PoA) backend.

Repository:

D:\CODING\Projects\Proof-Of-Action-Final

GitHub repository:

https://github.com/AnujRAuti/Proof-Of-Action-Final

Active branch:

Backend

Python runtime:

Python 3.12

0. NON-NEGOTIABLE OPERATING MODE

You are operating inside an existing production-oriented backend with BE-001 through BE-023 already implemented and verified.

Do not treat this as a greenfield project.

Do not redesign existing architecture.

Do not replace working implementations merely because you prefer another approach.

Do not introduce shortcuts, mocks, fake intelligence, placeholder implementations, hardcoded outputs, or “demo” behavior.

Do not expand BE-024 beyond its explicitly defined scope.

If you discover a problem outside BE-024:

document it;
determine whether it blocks BE-024;
do not silently redesign the unrelated subsystem.
1. FIRST: RECONNAISSANCE ONLY

Before modifying any code:

Inspect
current Git branch/status
latest commits
docs/Final Architecture.md
all relevant previous BE task/specification files
current BE-024 specification
relevant production modules
relevant migrations
relevant unit tests
relevant integration tests
requirements.txt
requirements-dev.txt
pytest.ini
tests/conftest.py
tests/audit_guard.py
tests/preflight.py
backend/db/test_target.py

Determine:

A. What already exists
B. What BE-024 is actually responsible for
C. Which existing APIs/models/services BE-024 depends upon
D. Which architectural decisions constrain BE-024
E. Which tests already cover related behavior
F. What new migrations, endpoints, workers, models, services, or tests are genuinely required

Do not code during reconnaissance.

Produce a concise reconnaissance report before implementation.

2. ARCHITECTURE IS THE AUTHORITY

The file:

docs/Final Architecture.md

is authoritative unless the BE-024 specification explicitly supersedes a decision.

Respect the existing separation between:

Evidence
Evidence Metadata
Evidence Relationships
Claims
Activities
Projects
Analysis Runs
Fusion
Integrity Assessment
Review Priority
Explainability
Review Cases
Evidence Requests
Audit Ledger
Authentication
Authorization
Retention/Governance
Dispute/Correction
Publication/Transparency
External Integrations
Notifications
Observability

Do not collapse these concepts for convenience.

Do not create a second competing implementation of an existing subsystem.

3. EXISTING SYSTEM MUST BE TREATED AS REAL

PoA already has real implementations for:

FastAPI API
PostgreSQL
PostGIS
pgvector
SQLAlchemy
Alembic
S3-compatible storage
MinIO development storage
Redis Streams
background workers
SHA-256 fingerprinting
EXIF extraction
pHash
CLIP embeddings
duplicate intelligence
temporal analysis
YOLO vision analysis
Evidence Graph
deterministic Fusion
deterministic Explainability
Review Cases
Evidence Requests
Audit Ledger
Auth/AuthZ
Retention/Governance
Notifications
External Integrations
Observability
Dispute/Correction
Publication/Transparency
verification/test infrastructure

Reuse these systems where appropriate.

Do not recreate them.

4. IMPORTANT LESSON FROM BE-023: TEST AGAINST A CLEAN ENVIRONMENT

The backend has previously suffered from false verification caused by:

contaminated development databases;
stale state;
shared test data;
Python version mismatch;
missing ML dependencies;
environment-specific package behavior;
hidden automatic package installation.

Therefore:

Never use pofa_dev as the authoritative verification database.

Tests must support:

TEST_DATABASE_URL

and must fail clearly if the intended test database configuration is absent.

Never silently fall back to a development database.

For database verification:

create/use an isolated test DB;
apply migrations;
run tests;
classify failures;
destroy/recreate the test DB when necessary.

Do not “fix” a failure by deleting arbitrary rows from a shared database.

5. AUDIT LEDGER IS SACRED

This is one of the most important lessons from the repository history.

The audit ledger is:

append-only;
hash chained;
tamper evident;
independently verifiable.

Tests must never casually delete audit ledger rows.

Do not write cleanup code such as:

delete by actor;
delete by project;
delete by resource;
truncate audit table;
update audit rows;
recreate audit rows.

Do not modify production audit-chain logic merely to make tests pass.

If a test intentionally tests tampering:

perform the mutation inside an isolated transaction;
verify the expected invalid state;
roll back;
never leave corruption behind.

Use the existing BE-023 audit guard.

If the guard reports a violation, fix the test design rather than weakening the guard.

6. NO DESTRUCTIVE GIT OPERATIONS

Git safety is mandatory.

NEVER run:

git reset --hard

git clean -fd

git checkout -- .

git restore .

branch deletion

stash deletion/clear

force push

history rewriting

mass destructive Git operations

NEVER run:

git add -A

or

git add .

Use explicit file paths when staging.

Before every commit:

git status --short --branch
git diff --cached --name-only
git diff --cached

Verify that:

no virtual environments are staged;
no .env files are staged;
no model weights are staged;
no generated artifacts are staged;
no unrelated files are staged.
7. VIRTUAL ENVIRONMENTS MUST NEVER ENTER GIT

Known local environments include:

backend/.venv312_clean/
backend/.venv312_repro/

They must remain ignored.

Never stage them.

Never modify them as a substitute for fixing project dependency declarations.

8. DEPENDENCY DISCIPLINE

If BE-024 introduces a dependency:

determine whether it is genuinely required;
add it to the correct dependency file;
pin or constrain it appropriately where project policy requires;
verify installation from a fresh Python 3.12 environment;
run the relevant tests.

Do not manually install packages and then claim the repository is reproducible.

Do not rely on automatic runtime package installation.

If a library attempts to download/install something automatically:

investigate it;
disable automatic mutation where appropriate;
make the required dependency explicit.
9. PYTHON VERSION

Authoritative runtime:

Python 3.12

Do not use Python 3.14 to determine backend compatibility.

Verification should be performed in the project's Python 3.12 environment.

If a failure occurs only on another Python version, classify it separately rather than changing production code blindly.

10. NO FAKE AI

PoA uses real intelligence components.

If BE-024 touches AI/vision/ML:

Never create:
fake confidence scores;
hardcoded detections;
random similarity;
fabricated embeddings;
fake risk scores;
fake authenticity scores;
fake fraud probabilities;
placeholder model outputs presented as real.

If a capability is unavailable:

represent it explicitly as:

unavailable;
unknown;
not executed;
failed;

according to the existing architecture.

Do not convert “unknown” into “false.”

11. ANALYSIS RUN DISCIPLINE

Every analytical execution must respect the existing Analysis Run model.

Preserve:

analysis capability;
input;
version;
configuration;
timestamps;
status;
provenance;
outputs;
failure state.

Do not overwrite previous analytical results when the architecture requires historical preservation.

Reprocessing should create a new run.

12. UNKNOWN ≠ FALSE

This project deliberately distinguishes:

TRUE / supported evidence
FALSE / contradicted evidence
UNKNOWN
unavailable
insufficient evidence

Do not silently convert:

missing metadata → negative;
missing GPS → outside geofence;
missing temporal information → temporal conflict;
failed analysis → suspicious;
low evidence quality → fraud;
no matching evidence → contradiction.

Follow the existing semantics.

13. HUMAN AUTHORITY

PoA is a decision-support and evidence-intelligence system.

Automated systems do not become the final substantive authority merely because they produce a score.

Do not introduce automatic:

fraud verdicts;
authenticity verdicts;
final claim decisions;
disciplinary decisions;
publication decisions;

unless the architecture explicitly permits that exact behavior.

Human decision workflows remain authoritative.

14. AUTHORIZATION MUST BE TESTED AT THE BACKEND

Never rely solely on frontend restrictions.

For every BE-024 endpoint/action involving protected resources, verify:

authentication;
permission;
organization scope;
project scope;
assignment/context;
resource ownership where applicable;
visibility;
action authority.

Test both:

allowed access

and

denied access.

Do not use a hidden frontend route as authorization.

15. DATABASE MIGRATIONS

If BE-024 changes the database:

create a proper Alembic migration;
verify migration dependencies;
run upgrade from a clean database;
verify downgrade where project policy requires it;
run upgrade again;
test the resulting schema;
ensure migration ordering is correct.

Never manually alter the database and treat that as the migration.

Never edit old applied migrations unless explicitly authorized.

16. TESTING STRATEGY

Do not stop at unit tests.

BE-024 must use the appropriate layers:

Unit tests

For:

pure business logic;
validation;
deterministic services;
policy logic;
edge cases.
Integration tests

For:

PostgreSQL;
PostGIS;
pgvector;
Redis;
storage;
workers;
migrations;
API boundaries.
API tests

For:

authentication;
authorization;
status codes;
response schemas;
error handling.
Regression tests

For any bug discovered during implementation.

If BE-024 touches existing functionality, run the affected existing test suites.

17. TEST QUALITY: DON'T CHEAT

A test is not considered successful merely because it returns the expected value.

Verify that the test actually exercises the intended production path.

Avoid:

excessive mocking;
mocking the function being tested;
bypassing authorization;
bypassing the database;
directly inserting the final state instead of exercising the workflow;
asserting implementation details instead of behavior;
weakening assertions;
deleting problematic rows during cleanup;
changing production behavior solely for tests.

If a test passes because the implementation is never reached, the test is invalid.

18. FAILURE CLASSIFICATION

When verification fails, classify it before modifying code.

Use categories such as:

PRODUCT BUG

Production implementation violates the intended specification.

TEST BUG

Test is incorrect or tests the wrong boundary.

ENVIRONMENT BUG

Dependency/runtime/system configuration problem.

FIXTURE/DATA BUG

Invalid or contaminated test data.

MIGRATION BUG

Schema/migration issue.

INFRASTRUCTURE BUG

PostgreSQL/Redis/MinIO/etc. unavailable or misconfigured.

SPECIFICATION GAP

Required behavior is not defined clearly enough.

Do not automatically modify production code whenever a test fails.

19. REGRESSION PROTECTION

Every genuine bug discovered during BE-024 implementation should receive a regression test if that bug is within BE-024 scope.

The regression test must reproduce the failure before the fix and pass after the fix.

Do not create a regression test that merely encodes the implementation.

20. PERFORMANCE

Do not introduce obviously dangerous patterns such as:

N+1 database queries;
unbounded database scans;
loading huge evidence files into memory;
unbounded Redis operations;
repeated expensive ML inference;
unnecessary embedding generation;
synchronous long-running analysis inside request handlers.

If BE-024 requires expensive processing, follow the existing asynchronous job architecture.

21. STORAGE SAFETY

Evidence files are immutable source artifacts.

Do not modify the original uploaded evidence to produce a derivative.

Derived artifacts must maintain provenance and relationship to the source according to the architecture.

Never silently overwrite original evidence.

22. OBSERVABILITY

If BE-024 introduces a new operational workflow:

consider whether it requires:

structured logs;
request IDs;
correlation IDs;
metrics;
traces;
failure counters;
latency measurements;
health visibility.

Do not expose sensitive evidence, PII, credentials, tokens, or raw secrets in logs.

Reuse the existing observability infrastructure.

23. API DISCIPLINE

Use the canonical API structure:

/api/v1/...

Follow existing conventions for:

Pydantic schemas;
error responses;
request IDs;
authentication;
authorization;
pagination;
idempotency;
async job behavior;
OpenAPI.

Do not introduce a parallel API style.

24. NO SCOPE CREEP

BE-024 is not permission to redesign:

authentication;
Evidence Graph;
Fusion;
Publication;
Retention;
Dispute;
Audit;
Notifications;
External Integrations;
Observability;

unless BE-024 explicitly requires interaction with one of them.

If something would be useful but is outside scope:

document it as a follow-up.

Do not implement it.

25. DOCUMENTATION MUST MATCH REALITY

This repository has previously had stale verification documentation.

Therefore, after implementation:

documentation must reflect what was actually executed, not what was intended.

Do not write:

“verified”

unless the test was actually run.

Do not write:

“all tests pass”

unless the relevant suite actually passed.

Include:

exact environment;
Python version;
database;
relevant external dependencies;
test command;
result;
skipped tests;
warnings;
known limitations.

Never hide failures.

26. IMPLEMENTATION PROCESS

After reconnaissance, proceed in stages:

Stage A — Reconnaissance

No code.

Produce:

existing implementation map;
BE-024 dependency map;
architecture constraints;
test map;
risks;
implementation plan.
Stage B — Foundation

Implement only the minimum required schema/domain foundations.

Run focused tests.

Stage C — Core implementation

Implement BE-024 behavior.

Run focused unit/integration tests.

Stage D — API/workflow integration

Connect it to the existing application.

Test authorization and failure paths.

Stage E — Regression/hardening

Add regression tests.

Test:

empty inputs;
malformed inputs;
missing dependencies;
unauthorized access;
repeated requests;
duplicate requests;
concurrent requests where relevant;
partial failures;
retry behavior;
rollback behavior.
Stage F — Full verification

Run:

BE-024 targeted suite
affected existing integration suites
full unit suite
full integration suite
migration verification
preflight/dependency verification if relevant

Do not claim completion until these results are recorded.

27. STOP CONDITIONS

Stop and report instead of improvising if:

BE-024 specification contradicts Final Architecture.md;
a required dependency is unclear;
database semantics are ambiguous;
authorization semantics are ambiguous;
an existing subsystem must be redesigned to proceed;
tests require destructive cleanup;
a production change appears necessary solely to accommodate a test;
the implementation would require breaking an existing API;
an external service is required but not specified;
a model capability is unavailable;
you discover evidence of repository corruption;
Git shows unexpected modifications.

Do not make a speculative decision.

28. GIT RULES

Before implementation:

git status --short --branch
git log -5 --oneline

Do not modify unrelated files.

During implementation, keep changes scoped.

Before commit:

git status --short --branch
git diff --stat
git diff --name-only

Stage explicit paths only.

Never:

git add -A

Never:

git add .

Before pushing:

git status --short --branch
git diff origin/Backend..HEAD --stat
git diff origin/Backend..HEAD --name-only

Then push normally:

git push origin Backend

Never force-push.

29. REQUIRED FINAL REPORT

At completion provide:

BE-024 Completion Report
Implementation
what was implemented
files changed
migrations added
APIs added
workers/services changed
Architecture
which existing architecture decisions were used
confirmation that no unrelated architecture was redesigned
Testing

Report exact results:

BE-024 targeted:
X passed
X failed
X skipped

Affected integration:
X passed
X failed
X skipped

Unit:
X passed
X failed
X skipped

Full integration:
X passed
X failed
X skipped
Environment

Include:

Python version
PostgreSQL version if relevant
Redis availability
MinIO availability
ML availability if relevant
test database source
Migrations
upgrade result
downgrade result if applicable
final revision
Security
authorization tests
scope tests
sensitive-data handling
Regression tests

List each newly protected failure.

Known limitations

Explicitly list anything not implemented.

Git

Report:

commit hash
commit message
branch
whether working tree has untracked files
whether pushed
30. FINAL PRINCIPLE

The goal is not:

“Make the tests green.”

The goal is:

Implement the BE-024 specification faithfully inside the existing PoA architecture, prove that the implementation works against a clean reproducible environment, and leave the repository safer and more verifiable than before.

A passing test suite that does not exercise the real behavior is a failure.

A workaround that hides a production defect is a failure.

A test that corrupts shared state is a failure.

A dependency that only works on one developer's machine is a failure.

A stale verification report is a failure.

A destructive Git operation is unacceptable.

Correctness, reproducibility, architectural integrity, provenance, and safe engineering take priority over speed.

BE-024 SPECIFICATION

Do not invent the BE-024 scope.

Before implementation, read the authoritative BE-024 task/specification provided with this prompt/repository.

If the specification is missing, stop after reconnaissance and request the BE-024 specification.

Do not start coding until the exact BE-024 scope has been identified and mapped against the existing architecture.