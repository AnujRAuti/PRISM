BE-025 — Organization, Role Assignment & Administrative Control Plane
Mission

Implement and verify BE-025: Organization, Role Assignment & Administrative Control Plane for Proof-of-Action.

This milestone extends the existing backend authorization foundation into a production-usable administrative control plane.

This is not a new authentication system redesign.

This is not a frontend task.

This is not a redesign of the existing authorization architecture.

The goal is to make the existing organization, user, role, scope, project, and assignment concepts administratively manageable through properly authorized backend APIs while preserving the security, audit, and governance guarantees established through BE-001 → BE-024.

1. Non-negotiable operating rules
Reconnaissance before implementation.
Do not modify production code until the reconnaissance report and implementation plan are complete.
Read the existing architecture and authorization implementation before designing anything.
Treat the locked architecture as authoritative.
Do not invent a parallel RBAC system.
Reuse the existing Principal, require(), require_target(), permission, scope, assignment, organization, and audit infrastructure wherever applicable.
Backend authorization remains authoritative.
Never rely on frontend authorization.
Never silently fall back to unrestricted/global access.
Never weaken an existing permission to make an administrative workflow work.
Every administrative mutation must be auditable.
Audit ledger remains append-only and tamper-evident.
Do not delete audit ledger records.
Do not truncate or update audit ledger records.
Preserve the BE-023 audit guard.
Do not modify BE-015 audit-chain production logic unless a genuine BE-025 blocker is demonstrated.
Use the isolated TEST_DATABASE_URL.
Never silently fall back to pofa_dev.
Python 3.12 remains the supported backend runtime.
Do not introduce a second ORM, authorization framework, policy engine, or identity system.
Do not add unnecessary dependencies.
Do not create fake/mock administrative behavior merely to satisfy tests.
All API behavior must be backed by real database state.
All authorization tests must test both permitted and denied operations.
Preserve historical findings from BE-024.
Do not fix unrelated BE-024 backlog findings unless required for BE-025 correctness.
No destructive Git operations.
No force-push.
Never use git add . or git add -A.
Do not expand BE-025 into frontend implementation.
2. Architecture constraints

The locked architecture establishes:

Organization → Organizational Unit → Project

and defines actors including:

Citizen
Field Officer
Reviewer
Supervisor
Administrator
API Client

Authorization is based on:

RBAC
organizational/resource scope
contextual authorization
centralized backend authorization
project/team assignments

The architecture also explicitly separates:

authentication
authorization
substantive decision authority

BE-025 must preserve those distinctions.

3. Stage A — Reconnaissance

Before changing code, inspect the current implementation.

Inspect at minimum:

organization models
organizational unit models
user/principal models
role models
permission models
role assignments
project ownership
project/team assignments
activity assignments
authorization service
require()
require_target()
audit events
existing admin endpoints
existing development-token mechanisms
API client authorization
notification recipient resolution
database migrations
existing authorization integration tests

Search the repository for:

Organization

OrganizationalUnit

UserRoleAssignment

Role

Permission

Principal

require(

require_target(

project_id

assignment

scope

ADMINISTRATOR

SUPERVISOR

audit

Determine exactly what already exists.

Do not assume the architecture document represents code that doesn't exist.

Produce:

docs/BE-025 Stage A Reconnaissance.md

Include:

existing implementation
existing database schema
existing API surface
existing authorization model
reusable services
missing capabilities
potential security risks
migration requirements
test coverage
proposed BE-025 boundaries
explicit out-of-scope items

Stop after Stage A and report findings.

Do not implement anything yet.

4. Stage B — Administrative domain foundation

After reconnaissance approval, implement only the missing domain capability required for administrative management.

The intended administrative capabilities are:

Organization management

Authorized administrators should be able to:

create organization
retrieve organization
update organization
list organizations where authorized
manage organizational units belonging to an organization

Do not introduce arbitrary organization deletion if existing data dependencies make deletion unsafe.

Prefer controlled deactivation/archival semantics where appropriate.

Organizational units

Support:

create
retrieve
update
list
organization relationship

Enforce organization boundaries.

User role assignments

Provide a controlled mechanism for authorized administrators to:

assign a role to a user
remove/revoke a role
inspect current role assignments
scope assignments appropriately

The system must distinguish between:

global/system role
organization-scoped role
organizational-unit-scoped role
project-scoped assignment

Do not invent additional scope types unless the existing architecture/database requires them.

Project/team assignment

Where the existing schema supports it, provide administrative management for:

project ownership
project supervisor
project/team assignment
field officer/activity assignment

Do not give administrators substantive review authority merely because they can administer access.

5. Authorization requirements

Every administrative endpoint must have explicit backend authorization.

At minimum verify:

Administrator

Can perform authorized administrative operations within their permitted organization/system scope.

Supervisor

Can perform only operations explicitly permitted by the existing authorization model.

Reviewer

Cannot administer roles or organization membership unless explicitly authorized.

Field Officer

Cannot administer organization membership or permissions.

Citizen

Cannot access administrative endpoints.

API Client

Can only access operations permitted by its explicit scopes.

Cross-organization access

Must be denied unless the principal has explicit authority for the target organization/resource.

Unauthenticated

Must be rejected.

Do not create a hidden "admin bypass."

6. Privilege-escalation protection

This is a major BE-025 requirement.

Test and prevent:

administrator assigning themselves unauthorized higher privileges
lower-level administrator creating higher-level administrators where prohibited
cross-organization role assignment
modifying another organization's users
changing project ownership without authority
manipulating resource IDs to escape scope
deleting/revoking the last required administrator accidentally
assigning permissions indirectly through an unauthorized role
privilege escalation through API clients
IDOR/resource enumeration

If the existing architecture permits some of these operations, preserve the documented semantics rather than inventing new restrictions—but explicitly document them.

7. Administrative invariants

Implement deterministic validation for important invariants.

Examples:

organization must exist before organizational unit creation
organizational unit must belong to the referenced organization
scoped role assignment must reference a valid scope
project assignment must belong to the correct organization/unit boundary
revoked assignment cannot continue authorizing access
duplicate assignment must be idempotent or return a deterministic conflict
deleting/deactivating an organization cannot silently orphan security-critical records
role/permission relationships must remain internally consistent

Do not allow partial administrative mutations.

8. Audit requirements

Every security-sensitive administrative mutation must generate an audit event.

At minimum cover:

organization creation/update
organizational-unit creation/update
role assignment
role revocation
project ownership change
assignment creation/revocation
administrative security configuration changes

Audit records must identify, where applicable:

actor
action
target
organization
project/resource
timestamp
relevant before/after state or deterministic summary

Never place secrets or credentials into audit records.

Do not make audit logging best-effort if the existing transactional architecture requires the mutation and audit event to commit together.

9. API design

Use the existing canonical:

/api/v1

REST conventions.

Follow existing FastAPI patterns.

Use:

Pydantic request/response models
structured errors
request IDs
existing authorization dependencies
existing pagination conventions
existing audit infrastructure

Do not create an alternative /admin-v2 API.

Do not expose database models directly.

OpenAPI must accurately represent:

authentication requirements
permissions
parameters
request bodies
responses
error statuses
10. Idempotency and concurrency

Administrative operations must behave deterministically under duplicate requests.

Test:

duplicate role assignment
concurrent role assignment
concurrent revocation
concurrent organization/unit updates where applicable
repeated requests after successful mutation

No duplicate security assignments should be produced.

Use database constraints/transactions where appropriate rather than relying exclusively on Python checks.

11. Pagination and enumeration safety

Any list endpoint must have bounded pagination.

Verify:

default page size
maximum page size
stable ordering
correct total/has-next semantics if the existing API convention provides them
authorization filtering before data exposure

Do not allow an unauthorized user to infer cross-organization records through:

pagination counts
IDs
error messages
ordering
search endpoints
12. Database/migrations

Only create a migration if the existing schema genuinely requires it.

Before adding one:

inspect existing tables
inspect constraints
inspect indexes
inspect relationships
determine whether the required capability already exists

If migration is required:

make it linear
use the existing Alembic conventions
test upgrade
test downgrade where supported
test from-scratch migration
test existing database upgrade
do not modify historical migrations
13. Testing

Create focused BE-025 tests.

At minimum cover:

Authorization
administrator allowed
administrator denied outside scope
supervisor allowed only where applicable
reviewer denied
field officer denied
citizen denied
API client scope enforcement
unauthenticated denied
Organization isolation
organization A cannot access organization B
organization-scoped administrator cannot modify organization B
project scope cannot escape organization scope
Role management
valid assignment
invalid assignment
duplicate assignment
revocation
revoked role immediately stops authorization
privilege escalation attempts
concurrent assignment
Organizational units
valid creation
wrong organization
unauthorized modification
cross-org access
Project/team assignments
valid assignment
invalid cross-org assignment
unauthorized modification
duplicate/concurrent assignment
Audit
expected event exists
correct actor
correct target
no sensitive data leakage
audit chain remains valid
API
validation errors
malformed UUID/resource IDs
not-found
forbidden
unauthorized
conflict
pagination
14. Security regression requirement

Run the existing authorization suite before and after BE-025.

BE-025 must not regress:

BE-016 authorization
BE-019 API-client authorization
BE-021 dispute authorization
BE-022 publication authorization
BE-023 test isolation
BE-024 authorization hardening

If an existing authorization test fails, stop and classify it.

Do not weaken the test to make it pass.

15. Stage C — Implementation

Only after Stage A/B approval:

Implement the minimum required backend changes.

Expected categories may include:

schemas
services
endpoints
authorization rules
audit events
database constraints
tests
documentation
migration if genuinely necessary

Do not add frontend work.

Do not add OIDC/OAuth2 implementation unless reconnaissance demonstrates that BE-025 explicitly requires it.

Do not replace the current development authentication mechanism in this milestone.

16. Stage D — Runtime verification

Use:

TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test

Verify real:

PostgreSQL
PostGIS
pgvector
Redis where required
MinIO where required
Python 3.12

Run actual HTTP/API tests.

Do not substitute:

grep
import checks
static inspection
documentation
mocked authorization

for runtime verification.

Produce:

docs/BE-025 Stage D Runtime Results.md

Include exact:

commands
test counts
failures
skips
warnings
durations
environment
database revision
17. Stage E — Hardening

Test:

malformed IDs
malformed payloads
missing resources
duplicate operations
concurrent operations
unauthorized operations
cross-organization access
privilege escalation
revoked access
partial transaction failures
audit failures
database failure where safely testable
rollback
retry behavior
pagination boundary cases

If fault injection is used, restore infrastructure afterward.

Re-verify the audit chain after fault injection.

Do not fake unavailable dependency tests.

18. Stage F — Full verification

Run:

BE-025 targeted suite
affected integration suites
full unit suite
full integration suite
migration verification
from-scratch migration
BE-023 preflight
authorization regression
audit-chain verification

Expected final state:

zero unexplained failures
zero hidden environment fallback
no unauthorized access
no audit-chain corruption
no migration drift
no fake AI behavior
no regression to previous milestones
19. Documentation

Create:

docs/BE-025 Stage A Reconnaissance.md

docs/BE-025 Stage B Design.md

docs/BE-025 Stage C Implementation Summary.md

docs/BE-025 Stage D Runtime Results.md

docs/BE-025 Stage E Hardening Results.md

docs/BE-025 Final Acceptance Report.md

The final report must preserve historical findings using:

FOUND → FIXED → VERIFIED

Do not rewrite defects out of history.

20. Git safety

Before committing:

git status

git diff --stat

Inspect every modified production file.

Stage files explicitly.

Never use:

git add .

or

git add -A

Do not stage:

virtual environments
caches
logs
generated reports unless intentionally part of the milestone
scratchpads
unrelated changes
temporary scripts

Commit only after final verification.

Proposed commit:

BE-025: implement organization and administrative control plane

Do not force-push.

Do not rewrite existing BE-024 history.

21. Scope exclusions

Explicitly out of scope for BE-025:

frontend implementation
mobile application
OIDC provider implementation
OAuth provider implementation
replacing JWT infrastructure
new AI/ML models
fraud detection
authenticity detection
LLM decision making
evidence graph redesign
fusion redesign
publication redesign
retention redesign
dispute redesign
notification redesign
external webhook redesign
Kubernetes
cloud migration
performance optimization unrelated to this milestone
fixing unrelated BE-024 findings
rewriting historical migrations
replacing the existing RBAC architecture

If something outside this list becomes necessary, stop and report it rather than silently expanding scope.

22. Final acceptance gate

BE-025 may only be declared PASS / ACCEPTED when:

Stage A reconnaissance completed
Stage B design approved
implementation completed
administrative authorization verified at runtime
organization isolation verified
privilege escalation tests pass
role assignment/revocation verified
project/team assignment verified
audit events verified
concurrency/idempotency verified
API errors verified
pagination verified
migration verification passes
full unit suite passes
full integration suite passes
authorization regression passes
audit chain remains valid
BE-023 test isolation remains intact
final Git state is intentional and synchronized

If any gate fails, report the failure and do not claim PASS.

FIRST ACTION

Do Stage A reconnaissance only.

Do not write production code.

Do not create migrations.

Do not create APIs.

Do not commit anything.

Return:

Current organization/auth/admin architecture
Existing database structures
Existing APIs
Existing authorization primitives
Existing role/assignment capabilities
Missing capabilities
Security risks/gaps
Required changes
Files likely to change
Migration requirement or confirmation that none is needed
Proposed BE-025 implementation plan
Explicit out-of-scope confirmation