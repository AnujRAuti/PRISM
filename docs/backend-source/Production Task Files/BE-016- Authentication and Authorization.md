# BE-016 — Authentication & Authorization Foundation

## Status

PLANNED

## Milestone

BE-016

## Title

Authentication & Authorization Foundation

## Depends On

- BE-001 — Database/API Foundation
- BE-007 — Projects, Claims & Geospatial Context
- BE-010 — Evidence Graph
- BE-013 — Review Cases
- BE-014 — Evidence Requests
- BE-015 — Tamper-Evident Audit Ledger

---

# 1. Objective

Implement the foundational authentication and authorization layer for Proof-of-Action.

The purpose of this milestone is to establish a secure, centralized authorization model that can be used by all subsequent API and workflow milestones.

BE-016 must establish the distinction between:

1. Authentication
2. Authorization
3. Organizational/resource scope
4. Substantive decision authority

Authentication answers:

> Who is making this request?

Authorization answers:

> Is this authenticated actor allowed to perform this action on this resource in this context?

Substantive authority answers:

> Is this actor authorized to make the actual domain decision?

These concerns MUST remain separate.

This milestone must NOT implement the final government SSO integration, citizen identity provider integration, frontend login experience, or complete production IAM deployment.

It establishes the backend authorization foundation that those integrations can use later.

---

# 2. Architectural Requirement

The implementation MUST conform to the locked architecture decisions in:

`docs/Final Architecture.md`

Relevant decisions include:

- Authentication is configurable through OIDC/OAuth2.
- API clients use explicit scopes.
- Authorization is RBAC + organization/resource scope + contextual rules.
- Backend authorization is authoritative.
- A centralized authorization decision function is required.
- V1 does not require a heavyweight policy engine.
- Authentication, authorization, and substantive decision authority are separate.
- Human decisions remain subject to the Review Case workflow.
- Administrator access MUST NOT automatically imply substantive decision authority.
- Cross-project intelligence remains authorization-aware.
- Auditability of sensitive actions is required.

---

# 3. Scope

## IN SCOPE

BE-016 implements:

- authenticated principal abstraction
- user/actor model
- organization model foundation
- organizational unit model foundation
- role model
- permission model
- role-permission mapping
- user-role assignment
- organization/resource scope
- centralized `can(...)` authorization service
- FastAPI authentication dependency
- API scope validation
- project/resource authorization
- cross-project access checks
- ownership/scope enforcement
- authorization failures
- authenticated actor propagation
- audit actor integration
- authorization tests
- security-focused integration tests
- database migration
- API documentation

---

# 4. OUT OF SCOPE

The following MUST NOT be implemented in BE-016:

- government SSO production integration
- production OIDC provider deployment
- Google/Microsoft/Apple login
- citizen identity verification
- biometric authentication
- MFA implementation
- password reset flows
- email verification
- frontend login pages
- frontend RBAC UI
- session-management UI
- administrator dashboard
- policy engine such as OPA/Casbin
- ML-based authorization
- LLM-based authorization
- automatic substantive decisions
- fraud detection
- authenticity detection
- risk scoring
- fusion changes
- review-case decision changes
- evidence truth determination
- blockchain
- external audit anchoring
- notification system
- chat/messaging
- API gateway implementation

BE-016 is an authorization foundation, not a complete identity-management product.

---

# 5. Security Model

The authorization model MUST evaluate at least:

```text
Principal
+
Action
+
Resource
+
Organization Scope
+
Resource Scope
+
Context
+
Required Permission

Conceptually:

can(
    principal,
    action,
    resource,
    context
)
→ AuthorizationDecision

The backend MUST be the authoritative enforcement point.

Frontend checks may later improve UX, but frontend checks MUST NEVER be trusted as the security boundary.

6. Principal Model

Introduce a backend principal abstraction.

Example conceptual structure:

Principal
├── principal_id
├── principal_type
├── authenticated
├── roles
├── permissions
├── organization_ids
├── organizational_unit_ids
├── scopes
└── attributes

Supported principal types should include at minimum:

USER
API_CLIENT
SYSTEM

Anonymous access MUST be explicitly represented rather than silently treated as an authenticated user.

Example:

AnonymousPrincipal
AuthenticatedPrincipal
ApiClientPrincipal
SystemPrincipal

The exact implementation may differ, but the authorization service MUST NOT depend directly on FastAPI's request object.

7. User Model

Create a persistent user/actor representation.

Minimum conceptual fields:

id
external_subject
identity_provider
display_name
email
status
created_at
updated_at

User status should support at least:

ACTIVE
SUSPENDED
DISABLED

The external identity subject MUST NOT be treated as a globally unique identifier without also considering its identity provider.

Recommended uniqueness:

(identity_provider, external_subject)

Authentication providers are expected to be configurable.

Do not assume one specific identity provider.

8. Organization Model

Implement the organization hierarchy defined by the architecture:

Organization
    ↓
Organizational Unit
    ↓
Project

Organizations represent the top-level ownership/scope boundary.

Organizational Units allow internal government/agency structures without hard-coding a particular government hierarchy.

Minimum organization fields:

id
name
code
status
created_at
updated_at

Minimum organizational unit fields:

id
organization_id
name
code
status
created_at
updated_at

Organizations and organizational units MUST NOT be hard-coded to a specific department structure.

9. Project Ownership

Existing projects from BE-007 must gain explicit organizational ownership/scope.

A project should belong to:

Organization
    or
Organizational Unit

The implementation MUST preserve existing project behavior.

Existing project records must be migrated safely.

Do not destroy or recreate existing projects.

If necessary, existing development projects may receive an explicit development organization during migration.

10. Roles

Implement the architecture's actor roles.

Minimum roles:

CITIZEN
FIELD_OFFICER
REVIEWER
SUPERVISOR
ADMINISTRATOR
API_CLIENT

System-level/internal roles may be introduced only when required by implementation.

Roles MUST NOT themselves automatically imply unrestricted access.

A role grants permissions.

Resource scope determines where those permissions apply.

11. Permissions

Implement explicit permissions.

Permissions should use a stable format.

Example:

project.read
project.create
project.update

activity.read
activity.create
activity.update

claim.read
claim.create
claim.update

evidence.read
evidence.create
evidence.update_context
evidence.read_sensitive

graph.read

fusion.read
fusion.execute

review_case.read
review_case.assign
review_case.investigate
review_case.decide
review_case.escalate
review_case.resolve
review_case.reopen

evidence_request.read
evidence_request.create
evidence_request.issue
evidence_request.respond

audit.read

organization.manage
user.manage
role.manage
configuration.manage

The exact permission catalogue may be refined during implementation, but permissions MUST be:

explicit
stable
testable
independently assignable
independent of frontend routes

Do not use arbitrary string checks scattered throughout endpoints.

12. Role-Permission Mapping

Implement:

Role
RolePermission
Permission

A role may have many permissions.

A permission may belong to many roles.

Use database constraints to prevent duplicate assignments.

Authorization MUST resolve the effective permissions of the principal.

13. User Role Assignment

Implement role assignments with scope.

Conceptually:

User
 ↓
Role Assignment
 ↓
Role
 ↓
Organization / Organizational Unit / Project scope

A user should be able to have:

Reviewer
    Organization A

without automatically becoming a reviewer for every organization in the system.

Similarly:

Field Officer
    Project X

must not grant access to:

Project Y

unless another explicit assignment permits it.

14. Scope Model

Authorization must support resource scope.

At minimum support:

GLOBAL
ORGANIZATION
ORGANIZATIONAL_UNIT
PROJECT

The implementation must support narrowing access.

Example:

GLOBAL
    ↓
Organization
    ↓
Organizational Unit
    ↓
Project

A project-scoped permission MUST NOT automatically become organization-wide permission.

A project-scoped user MUST NOT gain access to another project merely because both projects share similar evidence, claims, graph relationships, or analysis results.

15. Central Authorization Service

Create:

backend/services/authorization.py

The service must expose a centralized decision function conceptually equivalent to:

can(principal, action, resource, context)

It should return a structured decision.

Example:

AuthorizationDecision
├── allowed
├── reason
├── permission
├── scope
└── policy_version

The authorization service MUST be deterministic.

It MUST NOT call an LLM or ML model.

It MUST NOT make probabilistic authorization decisions.

16. Authorization Evaluation Order

Authorization should evaluate in a predictable order.

Recommended order:

1. Principal authentication state
2. Principal status
3. Required permission
4. Role assignment
5. Organization scope
6. Resource ownership/scope
7. Contextual restrictions
8. Substantive authority where applicable
9. Final allow/deny

A denied prerequisite MUST short-circuit the decision.

Do not leak sensitive resource existence through authorization errors.

17. Authentication Dependency

Implement a FastAPI authentication dependency.

Conceptually:

get_current_principal()

The dependency should establish:

request
→ authentication credentials
→ authenticated principal
→ authorization context

For development/testing, a deterministic development authentication mechanism may be used.

It MUST be clearly marked as development-only.

Production code MUST NOT silently fall back to anonymous authentication.

18. API Client Authentication

API clients are first-class actors.

They should support explicit scopes.

Conceptually:

API Client
    ↓
Credential
    ↓
Scopes

Example scopes:

evidence.read
evidence.write
analysis.read
graph.read
review_case.read

An API client with:

evidence.read

must not be able to:

review_case.decide

unless that permission is explicitly granted.

Do not implement production API key issuance/rotation unless required by the existing repository architecture.

The model should be ready for it.

19. Resource Authorization

Authorization must be applied to real domain resources.

At minimum integrate with:

Projects
Activities
Claims
Evidence
Evidence Graph
Fusion results
Review Cases
Evidence Requests
Audit Ledger

The implementation MUST NOT merely create unused authorization tables.

At least representative existing endpoints must enforce authorization.

20. Project Isolation

Project isolation is mandatory.

A principal authorized for:

Project A

must not access:

Project B

unless an explicit organization/global permission permits it.

This must be tested at the API level.

Tests must cover:

same project → allowed
different project → denied
same organization → depends on permission/scope
different organization → denied
global authorized principal → allowed where permission permits
21. Cross-Project Intelligence

BE-010 and BE-011 permit cross-project relationships and signals.

Authorization MUST NOT assume that the existence of a graph relationship grants access to the related project.

Example:

Project A Evidence
       ↓
ASSOCIATED_WITH
       ↓
Project B Evidence

A reviewer authorized only for Project A must not automatically gain access to Project B evidence.

Cross-project graph traversal must apply authorization filtering.

If a relationship points to an inaccessible resource, the response must not expose unauthorized sensitive details.

22. Evidence Authorization

Evidence requires particular care because it may contain:

raw media
EXIF
GPS
metadata
citizen identity information
operational intelligence
derived analysis

Authorization MUST occur before returning sensitive evidence data or storage URLs.

A valid authenticated user is NOT automatically authorized to download evidence.

Presigned storage URLs MUST only be issued after authorization succeeds.

23. Audit Ledger Integration

BE-015 already provides the dedicated audit ledger.

BE-016 must integrate actor identity into sensitive authorization-related actions.

Examples:

AUTHORIZATION_GRANTED
AUTHORIZATION_DENIED
ROLE_ASSIGNED
ROLE_REVOKED
SCOPE_ASSIGNED
SCOPE_REVOKED

However:

Routine authorization checks SHOULD NOT automatically create a ledger event for every request.

Otherwise normal API traffic could overwhelm the ledger.

At minimum, security-sensitive administrative changes must be auditable.

Authorization failures involving sensitive resources may be logged according to the existing secure logging model.

Do not modify the append-only guarantees of BE-015.

24. Substantive Decision Authority

Authorization MUST distinguish between:

permission to access a review case

and:

authority to make the substantive decision

For example:

review_case.read

does not imply:

review_case.decide

Likewise:

review_case.investigate

does not automatically imply:

review_case.resolve

The existing BE-013 lifecycle remains authoritative.

BE-016 must not bypass:

decision vocabulary
rationale requirements
lifecycle validation
reviewer/supervisor workflow
25. Administrator Role

Administrator access must be scoped to administrative responsibilities.

Administrator permissions may include:

identity management
organization configuration
system configuration
operational settings
security configuration

Administrator status MUST NOT automatically grant substantive review authority unless explicitly assigned.

This preserves:

Administrator
≠
Reviewer
≠
Supervisor
26. Citizen Access

BE-016 should establish the authorization foundation for citizen access but MUST NOT implement the complete citizen portal.

Citizen permissions should remain limited.

Citizens must not automatically gain:

internal intelligence access
reviewer access
organization-wide project access
audit ledger access
graph-wide access
fusion configuration access

Citizen-owned resources can later be exposed through explicit visibility policies.

27. Error Handling

Authorization failures must use structured API errors.

Recommended:

401 Unauthorized

when authentication is missing/invalid.

403 Forbidden

when authentication succeeds but authorization fails.

Do not return internal policy details that expose sensitive information.

For resource lookup:

unauthorized resource existence

should not necessarily be distinguishable from:

resource not found

where disclosure would create an information leak.

28. Database Design

Introduce the minimum required tables.

Recommended:

users
organizations
organizational_units
roles
permissions
role_permissions
user_role_assignments

Additional scope tables may be introduced if required.

Every table MUST include:

UUID primary key
created timestamp
updated timestamp where mutable

Use explicit foreign keys.

Use database uniqueness constraints.

Use indexes for:

external identity lookup
organization lookup
organizational unit lookup
role lookup
permission lookup
user-role lookup
scoped assignments
29. Migration

Create a single Alembic migration.

Naming convention:

i9d0e1f2g016_be016_auth_authorization.py

Parent MUST be the current BE-015 migration:

h8c9d0e1f015

Before committing:

alembic heads

must report exactly one head.

Test:

alembic upgrade head
alembic downgrade <previous_revision>
alembic upgrade head

Do not modify historical migrations.

30. API Requirements

Implement representative authorization-aware API behavior.

At minimum:

GET /api/v1/auth/me

Returns the current authenticated principal.

Potential response:

{
    "id": "...",
    "principal_type": "USER",
    "status": "ACTIVE",
    "roles": [...],
    "permissions": [...],
    "scopes": [...]
}

Administrative APIs may include:

POST /api/v1/organizations
GET  /api/v1/organizations/{id}

POST /api/v1/organizations/{id}/units
GET  /api/v1/organizations/{id}/units

POST /api/v1/users/{id}/roles
DELETE /api/v1/users/{id}/roles/{assignment_id}

Exact endpoint naming may follow the existing API conventions.

Do not expose unrestricted role/permission mutation through normal user-facing APIs.

31. Existing Endpoint Integration

Authorization should be integrated into representative existing endpoints.

Minimum recommended integration:

Projects
GET /projects
GET /projects/{id}
PATCH /projects/{id}
Evidence
GET evidence
GET evidence/{id}
PATCH evidence/{id}/context
PATCH evidence/{id}/location
Review Cases
GET review cases
GET review case/{id}
POST review case/{id}/assign
POST review case/{id}/decision
Evidence Requests
GET evidence requests
GET evidence request/{id}
POST evidence request
Audit
GET audit/events
GET audit/events/{id}
GET audit/verify

Only permissions appropriate to each action should be enforced.

32. Authorization Context

Introduce an explicit authorization context rather than passing arbitrary booleans.

Conceptually:

AuthorizationContext
├── organization_id
├── organizational_unit_id
├── project_id
├── resource_type
├── resource_id
├── request_id
└── action

Context should be derived from trusted server-side resource relationships.

Never trust client-supplied:

organization_id
project_id
role
permission

as proof of authorization.

33. No Scattered Authorization

Avoid patterns such as:

if user.role == "admin":

throughout endpoint code.

Instead:

principal = get_current_principal()

authorize(
    principal,
    action="evidence.read",
    resource=evidence,
)

Authorization rules belong in the authorization layer.

Endpoints should remain thin.

34. Repository Layer

Create:

backend/repositories/authorization.py

The repository should handle persistence and lookup for:

users
organizations
organizational units
roles
permissions
role assignments
scoped assignments

Do not put business authorization logic directly into SQL queries unless it is required for secure resource filtering.

35. Schema Layer

Create:

backend/schemas/authorization.py

Schemas should cover:

principal
user
organization
organizational unit
role
permission
role assignment
authorization decision

Use Pydantic validation.

Never expose password/secret material through schemas.

36. Service Layer

Create:

backend/services/authorization.py

Responsibilities:

resolve effective permissions
evaluate role assignments
evaluate resource scope
evaluate contextual rules
return structured authorization decisions
prevent privilege escalation
enforce separation between administrative and substantive permissions

Authentication parsing should remain separate from authorization evaluation.

37. Testing Requirements
Unit tests

Minimum coverage:

Principal
anonymous principal
authenticated principal
disabled principal
API client principal
Permission
permission resolution
duplicate permission prevention
role-permission mapping
Scope
global scope
organization scope
organizational-unit scope
project scope
unrelated project denial
unrelated organization denial
Authorization
allowed action
missing permission
wrong scope
disabled user
inactive role
unauthorized resource
administrative vs substantive permission separation
38. Integration Tests

Run against real PostgreSQL.

Minimum scenarios:

User
create user
assign role
resolve principal
Project isolation
User A → Project A → allowed
User A → Project B → denied
Organization isolation
Org A user → Org A project → allowed
Org A user → Org B project → denied
Scoped reviewer
Reviewer Project A
→ read Project A case
→ cannot read Project B case
Substantive authority
Reviewer with read permission
→ cannot decide

Reviewer with decision permission
→ can invoke decision endpoint
Administrator separation
Administrator
→ can manage configured administrative resource
→ cannot automatically make review decision
Evidence protection
authenticated but unauthorized user
→ cannot obtain evidence download URL
Cross-project graph
Project A reviewer
→ sees authorized graph relationship
→ cannot retrieve unauthorized Project B evidence
Audit

Administrative authorization changes MUST produce appropriate BE-015 ledger events.

39. Security Tests

Explicitly test:

privilege escalation
horizontal privilege escalation
vertical privilege escalation
cross-project access
cross-organization access
disabled-user access
stale-role access
forged scope
forged role
forged organization ID
forged project ID
unauthorized presigned URL

Client-supplied role/permission fields MUST never influence authorization.

40. Concurrency

Role assignment and scope assignment must be safe under concurrent requests.

Test:

10 concurrent identical role assignments

Expected:

exactly one effective assignment

Database uniqueness constraints must provide final protection.

Application-level checks alone are insufficient.

41. Performance

Authorization should not require a large number of database queries per request.

Avoid:

1 query → user
1 query → roles
1 query → permissions
1 query → organization
1 query → project
...

when the same information can be safely loaded efficiently.

However, do NOT sacrifice authorization correctness for premature optimization.

Future caching may be introduced, but BE-016 does not require distributed authorization caching.

42. Fail-Safe Requirements

Authorization failures MUST fail closed.

If authorization data is unavailable:

DO NOT allow access

Do not implement:

if authorization_service_unavailable:
    allow_request

The default must be deny.

43. Logging

Security-relevant authorization events should contain:

request_id
principal_id
action
resource_type
resource_id
decision
reason/category
timestamp

Do not log:

raw evidence
access tokens
passwords
secret keys
presigned URLs
sensitive citizen data

Use the existing secure logging/request-ID infrastructure from BE-001.

44. Audit Requirements

BE-015 remains the authoritative audit ledger.

BE-016 must not create a second audit system.

Authorization-related administrative changes should emit audit events through the existing BE-015 service.

Examples:

USER_CREATED
ROLE_ASSIGNED
ROLE_REVOKED
SCOPE_ASSIGNED
SCOPE_REVOKED
ORGANIZATION_CREATED
ORGANIZATIONAL_UNIT_CREATED

Exact vocabulary may be defined during implementation.

45. API Documentation

All authorization-aware endpoints must expose:

authentication requirements
required permissions
possible 401 response
possible 403 response
resource scope behavior

OpenAPI documentation must remain accurate.

46. Backward Compatibility

Existing BE-001 through BE-015 functionality must remain operational.

Do not:

rewrite the fusion engine
rewrite the graph
rewrite the audit ledger
rewrite evidence ingestion
alter analysis semantics
alter review case lifecycle
alter evidence request lifecycle

Authorization is an enforcement layer around existing domain behavior.

47. Data Migration Safety

Existing development data must remain usable.

Migration requirements:

no destructive deletion
no recreation of existing projects
no loss of evidence
no loss of graph relationships
no loss of fusion history
no loss of review cases
no loss of evidence requests
no loss of audit events

If existing projects require ownership, introduce a deterministic development organization rather than deleting records.

48. Definition of Done

BE-016 is complete only when all of the following are true:

Database
 Authentication/authorization tables exist
 Foreign keys are enforced
 Uniqueness constraints exist
 Scope indexes exist
 Migration is reversible
 Exactly one Alembic head exists
Authentication
 Principal abstraction exists
 FastAPI authentication dependency exists
 Development authentication mechanism is explicit
 /auth/me works
 Disabled users cannot authenticate
Authorization
 Central can(...) decision service exists
 Permissions are explicit
 Roles map to permissions
 Role assignments are scoped
 Organization scope works
 Project scope works
 Cross-project access is denied by default
 Cross-organization access is denied by default
 Authorization fails closed
Existing systems
 Projects enforce authorization
 Evidence enforces authorization
 Review Cases enforce authorization
 Evidence Requests enforce authorization
 Audit access enforces authorization
 Evidence storage URLs require authorization
Security
 Horizontal privilege escalation tested
 Vertical privilege escalation tested
 Cross-project isolation tested
 Cross-organization isolation tested
 Forged scope tested
 Disabled account tested
 Administrator/substantive authority separation tested
Audit
 Security-sensitive authorization changes emit BE-015 audit events
 No second audit system created
 Sensitive values are not logged
Regression
 Full unit suite passes
 Full integration suite passes
 Alembic upgrade passes
 Alembic downgrade passes
 Alembic upgrade after downgrade passes
 Existing BE-001 → BE-015 tests remain green
49. Verification Commands

The implementation must be verified with the project's existing environment.

At minimum:

pytest -q
alembic heads
alembic upgrade head
alembic downgrade <BE-015 revision>
alembic upgrade head

Run targeted tests for:

tests/unit/test_authorization.py
tests/integration/test_authorization.py

Exact test file naming may follow repository conventions.

50. Anti-Shortcut Gates

The following are explicit failure conditions.

Gate 1 — No fake authentication

Do not treat:

X-User-ID

or similar arbitrary headers as production authentication.

A development authentication adapter may use deterministic headers only when explicitly configured for development/testing.

Gate 2 — No role-only authorization

This is insufficient:

user.role == "REVIEWER"

Authorization must consider scope.

Gate 3 — No frontend-only authorization

Frontend hiding of buttons is not authorization.

Backend enforcement is mandatory.

Gate 4 — No global-admin bypass

Do not implement:

if admin:
    allow everything

unless the permission is explicitly granted.

Administrator does not automatically equal substantive reviewer authority.

Gate 5 — No project-ID trust

Never trust:

project_id
organization_id
role
permission

provided by the client as proof of authorization.

Resolve relationships server-side.

Gate 6 — No cross-project leakage

Graph relationships, duplicate matches, fusion signals, and other intelligence MUST NOT bypass resource authorization.

Gate 7 — No authorization via LLM

Do not use an LLM to determine whether an actor can access a resource.

Gate 8 — No authorization via ML

Do not use predictive models for authorization.

Gate 9 — No audit replacement

Do not replace BE-015 with ordinary application logs.

Gate 10 — Fail closed

If authorization cannot be evaluated reliably:

DENY

Never:

ALLOW
51. Architectural Boundary

BE-016 establishes:

WHO ARE YOU?
        ↓
WHAT ARE YOU ALLOWED TO DO?
        ↓
WHERE ARE YOU ALLOWED TO DO IT?
        ↓
IS THIS ACTION AUTHORIZED?

It does NOT establish:

WHO IS TELLING THE TRUTH?

It does NOT establish:

IS THIS EVIDENCE FRAUDULENT?

It does NOT establish:

WHICH PROJECT IS RISKIEST?

It does NOT establish:

WHO SHOULD WIN A DISPUTE?

Those remain outside the scope of authentication and authorization.

52. Relationship to Previous Milestones
BE-001
  ↓
BE-002
  ↓
BE-003
  ↓
BE-004
  ↓
BE-005
  ↓
BE-006
  ↓
BE-007
  ↓
BE-008
  ↓
BE-009
  ↓
BE-010
  ↓
BE-011
  ↓
BE-012
  ↓
BE-013
  ↓
BE-014
  ↓
BE-015
  ↓
BE-016
  Authentication &
  Authorization

BE-016 does not replace any previous milestone.

It adds the security boundary around the existing domain.

53. Expected Implementation Structure

Recommended:

backend/
├── services/
│   └── authorization.py
│
├── repositories/
│   └── authorization.py
│
├── schemas/
│   └── authorization.py
│
├── api/
│   └── v1/
│       └── endpoints/
│           ├── auth.py
│           └── authorization.py
│
├── db/
│   └── models.py
│
└── security/
    ├── authentication.py
    └── authorization.py

The exact folder structure may be adapted to the existing repository conventions.

54. Recommended Commit

Implementation commit:

BE-016: implement authentication and authorization foundation

Completion/finalization commit:

be-016 complete

Do not combine unrelated frontend, ML, notification, or dashboard work into this milestone.

55. Final Scope Statement

BE-016 establishes the backend security boundary for Proof-of-Action.

After BE-016:

Unauthenticated
      ↓
Authentication
      ↓
Principal
      ↓
Roles + Permissions
      ↓
Organization / Project Scope
      ↓
Contextual Authorization
      ↓
Authorized Domain Action
      ↓
Audit

The implementation must remain deterministic, backend-enforced, fail-closed, scope-aware, and compatible with future OIDC/OAuth2 integration.

No authentication or authorization mechanism introduced in this milestone may override the existing substantive human-decision architecture.


### BE-016 boundary

The important part is that we're **not jumping straight into the frontend or SSO**. After BE-015, this gives PoA the security layer needed before we start exposing the system to different actors.

The sequence becomes:

**BE-015 → Audit Ledger ✅ → BE-016 Auth/AuthZ → BE-017 likely Retention & Data Governance → later operational/frontend work.**

I would keep **BE-016 exactly this focused**: identity abstraction + RBAC + resource/org/project scope + backend enforcement + audit integration.