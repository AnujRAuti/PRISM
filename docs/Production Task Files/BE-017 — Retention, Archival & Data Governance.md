# BE-017 — Retention, Archival & Data Governance

## Status

PLANNED

## Milestone

BE-017

## Title

Retention, Archival & Data Governance

## Depends On

- BE-001 — Database/API Foundation
- BE-002 — Storage
- BE-003 — Evidence Ingestion
- BE-004 — Fingerprinting
- BE-005 — Async Analysis
- BE-006 — Duplicate Intelligence
- BE-007 — Projects, Claims & Geospatial Context
- BE-008 — Temporal Intelligence
- BE-009 — Vision
- BE-010 — Evidence Graph
- BE-011 — Fusion Engine
- BE-012 — Explainability
- BE-013 — Review Cases
- BE-014 — Evidence Requests
- BE-015 — Tamper-Evident Audit Ledger
- BE-016 — Authentication & Authorization

---

# 1. Objective

Implement the retention, archival, legal-hold, supersession, and controlled-deletion foundation for Proof-of-Action.

The purpose of BE-017 is to establish a policy-driven lifecycle for stored evidence and related domain/intelligence data.

The system must be able to answer:

> How long should this data be retained?

> Why is it still being retained?

> Is it eligible for archival?

> Is it currently protected by a hold?

> Can it be deleted?

> Who authorized the deletion?

> What dependent records are affected?

Retention MUST be policy-driven.

Retention MUST NOT be implemented as a simple:

```text
created_at + fixed number of days = delete

rule.

The system must account for:

retention policies
resource type
project scope
evidence lifecycle
review cases
disputes
holds
supersession
dependencies
archival
deletion authorization
auditability
2. Architectural Requirement

The implementation MUST conform to:

docs/Final Architecture.md

Relevant architectural decisions:

Retention is configurable and policy-driven.
Holds prevent deletion.
Controlled deletion is required.
Deletion is auditable.
Archive/cold storage may be used.
Evidence originals are immutable during normal operation.
Corrections create new versions/evidence.
Derived intelligence is recomputable/versioned.
Human decisions are append-only.
Withdrawal/supersession must be supported.
Dependency-aware propagation is required.
Reprocessing creates new analysis runs.
Raw evidence and derived intelligence have different lifecycle considerations.
The audit ledger remains separate from domain history.
Authorization from BE-016 is authoritative.
3. Scope
IN SCOPE

BE-017 implements:

retention policy model
retention policy versions
resource retention state
retention evaluation
retention schedules
legal/administrative holds
hold lifecycle
archival eligibility
archive state
controlled deletion requests
deletion authorization checks
dependency checks
supersession-aware retention
retention execution service
dry-run retention evaluation
retention audit events
authorization integration
retention APIs
background retention jobs
retention tests
storage lifecycle integration
database migration
4. OUT OF SCOPE

The following MUST NOT be implemented in BE-017:

external cold-storage provider migration beyond the existing storage abstraction
blockchain anchoring
external audit anchoring
automatic evidence truth determination
fraud detection
authenticity detection
deepfake detection
ML-based retention decisions
LLM-based retention decisions
notifications
email workflows
SMS
chat
frontend retention dashboard
full government records-management integration
external legal-system integration
OIDC changes
MFA
SSO
policy engines such as OPA
new fusion logic
new graph intelligence
new review-case scoring
new evidence analysis
analytics dashboards

BE-017 is a lifecycle/governance milestone.

5. Core Principle

Retention MUST NOT mean:

DELETE AFTER N DAYS

Instead:

Resource
    ↓
Retention Policy
    ↓
Retention Schedule
    ↓
Hold / Dispute / Dependency Evaluation
    ↓
Eligible for Archive?
    ↓
Eligible for Deletion?
    ↓
Authorized Action
    ↓
Audit Ledger
6. Resource Lifecycle

Introduce an explicit retention state separate from domain state.

Recommended lifecycle:

ACTIVE
ELIGIBLE_FOR_ARCHIVE
ARCHIVED
ELIGIBLE_FOR_DELETION
DELETION_PENDING
DELETED

Additional states may be introduced where required.

Retention state MUST NOT replace:

Evidence state
Analysis state
Review Case state
Fusion state
Human decision state

Each state machine remains independent.

7. Retention Policy

Create a versioned retention policy.

Conceptually:

RetentionPolicy
├── id
├── name
├── description
├── resource_type
├── scope
├── retention_period
├── archive_after
├── deletion_behavior
├── version
├── status
├── effective_from
├── effective_until
├── created_by
├── created_at
└── updated_at

Policies MUST be versioned.

Existing policies MUST NOT be silently modified after activation.

A changed policy creates a new version.

8. Resource Types

At minimum support policies for:

EVIDENCE
ANALYSIS_RESULT
FUSION_RUN
REVIEW_CASE
EVIDENCE_REQUEST
AUDIT_LEDGER_EVENT

However, BE-017 MUST NOT automatically delete audit ledger events.

Audit ledger retention requires a separate governance decision and MUST preserve the tamper-evident chain.

If audit retention is configurable, deletion/compaction must preserve the architectural integrity guarantees of BE-015.

9. Policy Scope

Retention policies may apply at:

GLOBAL
ORGANIZATION
ORGANIZATIONAL_UNIT
PROJECT

This must use the scope model introduced in BE-016.

A project-specific policy must override a broader policy only according to deterministic precedence.

Recommended precedence:

PROJECT
    ↓
ORGANIZATIONAL_UNIT
    ↓
ORGANIZATION
    ↓
GLOBAL

If no applicable policy exists:

DO NOT DELETE

Fail closed.

10. Policy Versioning

A policy version must contain:

policy_id
version
rules
effective_from
effective_until
status
created_by
created_at

Recommended statuses:

DRAFT
ACTIVE
SUPERSEDED
RETIRED

Only one applicable active version should exist for a given policy scope/resource combination unless explicit priority resolution is implemented.

11. Retention Clock

The retention clock MUST be explicit.

Do not assume:

database.created_at

is always the correct retention start.

Possible retention anchors include:

INGESTED_AT
CAPTURED_AT
PROJECT_COMPLETED_AT
CASE_RESOLVED_AT
REQUEST_FULFILLED_AT
DECISION_AT
SUPERSEDED_AT
CUSTOM_POLICY_EVENT

The policy must specify the anchor.

Example:

EVIDENCE
retention_anchor = INGESTED_AT
retention_period = 365 days

Another policy may use:

REVIEW_CASE
retention_anchor = RESOLVED_AT
retention_period = 7 years

Missing anchors MUST NOT be invented.

If the required anchor is unavailable:

retention evaluation = UNKNOWN
deletion = NOT ELIGIBLE
12. Retention Evaluation

Create:

backend/services/retention.py

The service should expose a deterministic evaluator conceptually:

evaluate_retention(resource, policy, context)

Result:

RetentionEvaluation
├── eligible
├── state
├── anchor
├── anchor_timestamp
├── expiry_timestamp
├── policy_id
├── policy_version
├── blocking_reasons
└── evaluated_at

The evaluator MUST NOT delete anything.

Evaluation and execution must remain separate.

13. Blocking Conditions

Deletion must be blocked by any applicable hold or dependency.

Potential blocking reasons:

ACTIVE_HOLD
OPEN_REVIEW_CASE
ACTIVE_DISPUTE
UNRESOLVED_REQUEST
ACTIVE_DEPENDENCY
SUPERSEDED_RESOURCE_REQUIRED
LEGAL_HOLD
RETENTION_PERIOD_NOT_REACHED
MISSING_RETENTION_ANCHOR
UNAUTHORIZED_REQUEST
POLICY_INACTIVE

The exact vocabulary may be refined.

Blocking reasons must be structured.

Do not return only a free-text message.

14. Legal / Administrative Holds

Implement first-class holds.

Conceptually:

RetentionHold
├── id
├── scope
├── resource_type
├── resource_id
├── reason
├── authority
├── status
├── created_by
├── created_at
├── released_by
├── released_at
└── release_reason

A hold MUST prevent deletion.

A hold may also prevent archival if policy requires active availability.

15. Hold States

Recommended:

ACTIVE
RELEASED
EXPIRED
CANCELLED

The implementation must preserve hold history.

Do not delete hold records.

Release/cancellation must be auditable.

16. Hold Scope

Supports:

RESOURCE
PROJECT
CASE
CLAIM
ORGANIZATION

A scoped hold may protect multiple dependent resources.

Example:

Project A hold

may prevent deletion of:

evidence
analysis results
review cases
evidence requests

that belong to Project A.

The dependency resolution must be deterministic.

17. Review Case Interaction

Open Review Cases MUST be considered by retention.

Recommended rule:

OPEN
ASSIGNED
INVESTIGATING
DECISION_PENDING
ESCALATED

→ block deletion of directly relevant evidence.

Resolved cases may permit retention evaluation according to policy.

Do not modify BE-013 case lifecycle.

Retention only reads the existing case state.

18. Evidence Request Interaction

Open Evidence Requests MUST be considered.

If evidence is actively requested:

OPEN
ACKNOWLEDGED
PARTIALLY_FULFILLED

retention should not delete the relevant requested evidence unless an explicit policy permits it.

Do not modify BE-014 workflow semantics.

19. Evidence Supersession

Evidence itself is immutable.

Corrections must create new evidence/version relationships rather than modifying the original.

Retention must understand supersession.

Example:

Evidence A
    ↓
SUPERSEDED_BY
    ↓
Evidence B

Evidence A must not automatically become deletable merely because Evidence B exists.

Retention policy must determine when superseded evidence may be removed.

20. Dependency Graph

Retention must account for dependent records.

Examples:

Evidence
    ↓
Analysis Result
    ↓
Fusion Run
    ↓
Review Case

and:

Evidence
    ↓
Evidence Request

and:

Evidence
    ↓
Graph Relationship

Before deletion, determine whether dependent records still require the resource.

Do not silently orphan domain/intelligence records.

21. Derived Intelligence

Derived data includes:

fingerprints
duplicate matches
vision detections
graph relationships
fusion signals
fusion runs
explanations
review priority outputs

Retention MUST distinguish raw evidence from derived intelligence.

Derived intelligence may be recomputable.

However, deletion MUST NOT assume that recomputability means immediate deletion is safe.

The applicable policy and dependency state remain authoritative.

22. Archive

Implement archive eligibility.

Archive is NOT deletion.

Conceptually:

ACTIVE
   ↓
ELIGIBLE_FOR_ARCHIVE
   ↓
ARCHIVED

An archived resource remains logically retained.

Archived resources may be moved to a lower-cost storage tier later.

BE-017 may implement logical archival without introducing a new storage provider.

23. Storage Abstraction

Reuse the existing BE-002 storage abstraction.

Do not create a second storage system.

Archive operations must use:

StorageService

or the repository abstraction already established by BE-002.

Do not directly manipulate MinIO/S3 from retention business logic.

24. Archive Integrity

Archiving MUST preserve:

SHA-256
original evidence identity
evidence ID
provenance
storage identity
metadata required for restoration
audit lineage

Archiving MUST NOT alter the original cryptographic identity.

25. Archive Restoration

If archival storage is implemented, support restoration.

Conceptually:

restore(resource)

Restoration must:

verify resource identity
verify integrity
preserve evidence identity
preserve provenance
emit an audit event

Restoration MUST NOT silently create a new evidence item.

26. Deletion

Deletion must be explicit and controlled.

Recommended process:

Retention Evaluation
        ↓
Eligible
        ↓
Deletion Request
        ↓
Authorization
        ↓
Dependency Re-check
        ↓
Deletion
        ↓
Audit Event

Do not directly expose:

DELETE /evidence/{id}

for arbitrary authenticated users.

Deletion is a governance operation.

27. Deletion Authorization

Deletion MUST require an explicit permission.

Recommended permission:

retention.delete

Additional administrative permissions may be required.

Possession of:

evidence.delete

must not automatically imply:

retention.delete

unless explicitly designed that way.

BE-016 authorization remains authoritative.

28. Two-Phase Safety

Deletion should use a two-phase model.

Phase 1 — Evaluation

Determine:

eligible = true/false
Phase 2 — Execution

Immediately before deletion:

re-evaluate

This prevents:

evaluation at 10:00
hold created at 10:01
deletion at 10:02

from incorrectly deleting held evidence.

29. Race Protection

Retention execution must protect against concurrent lifecycle changes.

At minimum protect against:

hold creation
hold release
case reopening
policy change
resource supersession
duplicate deletion

The final deletion decision must be made using current transactional state.

Database constraints should prevent duplicate deletion operations.

30. Dry Run

Implement a dry-run retention evaluation.

Example:

POST /api/v1/retention/evaluate

or equivalent.

Dry-run MUST NOT modify resources.

It should return:

eligible
blocked
archive_candidate
deletion_candidate
unknown

with structured reasons.

31. Retention APIs

Recommended APIs:

GET /api/v1/retention/policies
POST /api/v1/retention/policies

GET /api/v1/retention/policies/{id}
GET /api/v1/retention/policies/{id}/history

POST /api/v1/retention/evaluate

GET /api/v1/retention/resources/{type}/{id}

GET /api/v1/retention/holds
POST /api/v1/retention/holds
GET /api/v1/retention/holds/{id}
POST /api/v1/retention/holds/{id}/release

POST /api/v1/retention/archive/{type}/{id}
POST /api/v1/retention/restore/{type}/{id}

POST /api/v1/retention/delete/{type}/{id}

Exact endpoint structure may follow existing conventions.

All APIs must enforce BE-016 authorization.

32. Retention Resource Endpoint

A resource retention endpoint should expose:

resource_type
resource_id
retention_state
policy
policy_version
anchor
anchor_timestamp
expiry_timestamp
hold_status
blocking_reasons
archive_eligible
deletion_eligible
last_evaluated_at

Do not expose sensitive evidence content through retention APIs.

33. Retention Repository

Create:

backend/repositories/retention.py

Responsibilities:

retention policy persistence
policy version lookup
retention state lookup
hold persistence
deletion request persistence
archive state persistence
dependency lookup
retention execution support

The repository must not contain authorization policy.

34. Retention Schemas

Create:

backend/schemas/retention.py

Schemas should cover:

RetentionPolicy
RetentionPolicyVersion
RetentionEvaluation
RetentionHold
RetentionState
ArchiveOperation
DeletionOperation

Use Pydantic validation.

All timestamps must be timezone-aware.

Naive timestamps MUST be rejected.

35. Database Model

Recommended tables:

retention_policies
retention_policy_versions
retention_states
retention_holds
retention_operations

Additional tables may be introduced where required.

Use UUID primary keys.

Use foreign keys wherever domain relationships are stable.

Use appropriate indexes for:

resource type
resource ID
project
organization
policy
status
expiry
hold status
36. Migration

Create one Alembic migration.

Recommended revision:

j0e1f2g3h017_be017_retention_governance.py

Parent:

i9d0e1f2g016

Requirements:

alembic heads

must show exactly one head.

Test:

alembic upgrade head
alembic downgrade <BE-016 revision>
alembic upgrade head

Never modify previous migrations.

37. Background Processing

Retention evaluation may eventually be scheduled.

Create a reusable service suitable for a worker.

Conceptually:

RetentionWorker
    ↓
find candidates
    ↓
evaluate
    ↓
archive/delete where authorized
    ↓
audit

The worker MUST NOT bypass authorization.

System execution must use an explicit SYSTEM principal.

38. Worker Safety

A worker must not blindly delete everything older than a threshold.

Every deletion must:

load current resource state
load active policy
evaluate retention
check holds
check dependencies
check authorization/system capability
execute deletion transactionally
emit audit event
39. Audit Ledger Integration

BE-015 remains the authoritative audit ledger.

Retention events should include:

RETENTION_POLICY_CREATED
RETENTION_POLICY_ACTIVATED
RETENTION_HOLD_CREATED
RETENTION_HOLD_RELEASED
RETENTION_EVALUATED
RESOURCE_ARCHIVED
RESOURCE_RESTORED
DELETION_REQUESTED
RESOURCE_DELETED
DELETION_BLOCKED

Do not create a second audit mechanism.

Audit events must contain sufficient lineage to identify:

actor
resource
policy
policy version
operation
reason
timestamp
40. Audit Chain Preservation

Retention MUST NOT casually delete audit ledger events.

If audit records become subject to retention policy in the future, that implementation must preserve the cryptographic chain semantics of BE-015.

BE-017 should therefore default to:

Audit ledger events = retained

unless an explicit policy has been implemented and cryptographically safe compaction/archival semantics are established.

41. Authorization Integration

All retention administrative operations must use BE-016.

Minimum permissions:

retention.read
retention.manage_policy
retention.manage_hold
retention.archive
retention.restore
retention.delete

Scope must be respected.

A project-scoped retention administrator must not manage another project.

Global retention administrators may operate across scopes only where explicitly permitted.

42. Separation of Duties

Retention policy management and deletion authority should be separately permissionable.

For example:

retention.manage_policy

does not automatically imply:

retention.delete

Likewise:

retention.read

does not imply:

retention.manage_hold

The exact organizational separation may be configured later.

43. Deletion Semantics

Deletion must distinguish:

logical deletion

from:

physical object deletion

If a resource is logically deleted:

its identity must not be silently reused
audit history remains
references must be handled according to dependency policy
restoration behavior must be explicit

If physical evidence objects are deleted:

the database must not retain misleading "available" storage references
deletion must be recorded
provenance must indicate deletion where required
44. Referential Integrity

Do not use cascading deletes for sensitive evidence dependencies unless explicitly justified.

Prefer:

RESTRICT

for relationships where deleting a parent could destroy important provenance.

Deletion should be dependency-aware.

No orphaned:

evidence metadata
analysis results
graph nodes
review cases
evidence requests
audit references

may be created.

45. Graph Interaction

BE-010 graph relationships must be considered before deletion.

If deleting an evidence record would leave graph relationships invalid:

do not blindly delete

Possible behavior:

invalidate/supersede relationship

may be required according to the graph semantics.

Do not silently rewrite graph history.

Graph provenance must remain consistent.

46. Fusion Interaction

BE-011 fusion history is append-only.

Retention MUST NOT modify:

fusion calculations
historical fusion runs
historical signal values
assessment history

If an underlying evidence resource becomes unavailable/deleted, the existing fusion run must retain its historical provenance.

New evaluations may correctly report missing/unavailable inputs according to existing semantics.

47. Review Case Interaction

Retention MUST NOT:

automatically resolve cases
automatically reopen cases
modify human decisions
modify decision rationale
replace reviewer authority

If a case blocks deletion:

retention system
→ reports blocking condition

It does not alter the case.

48. Evidence Request Interaction

Retention MUST NOT:

fulfill requests
reject requests
decline requests
cancel requests
modify requested evidence

It only considers the request lifecycle when evaluating deletion eligibility.

49. Unknown Handling

Missing information MUST NOT be interpreted as permission to delete.

Examples:

missing retention anchor
unknown dependency state
unknown hold state
missing policy
unknown project scope

must result in:

NOT ELIGIBLE

or:

UNKNOWN / BLOCKED

not:

DELETE
50. Policy Conflict

If multiple policies apply and precedence cannot be deterministically resolved:

do not delete

Return:

POLICY_CONFLICT

and preserve the evaluation.

No implicit "latest policy wins" behavior unless explicitly encoded by policy semantics.

51. Test Requirements
Unit Tests

Minimum coverage:

Policy
policy creation
policy versioning
activation
supersession
scope precedence
conflicting policies
Retention
anchor resolution
expiry calculation
missing anchor
retention period not reached
eligible resource
ineligible resource
Holds
active hold blocks deletion
released hold permits re-evaluation
expired hold behavior
project-scoped hold
resource-scoped hold
Dependencies
open case blocks deletion
unresolved request blocks deletion
active dependency blocks deletion
resolved dependency behavior
Security
unauthorized deletion denied
unauthorized hold creation denied
project scope enforced
organization scope enforced
global permission behavior
52. Integration Tests

Run against real PostgreSQL and real storage infrastructure.

Minimum scenarios:

Policy
create policy
activate policy
evaluate resource
Retention
resource inside retention period
→ not eligible

resource past retention period
→ eligible
Hold
resource eligible
→ create hold
→ deletion blocked

release hold
→ re-evaluate
→ eligibility restored
Review Case
open case
→ evidence deletion blocked

resolve case
→ retention evaluated again
Evidence Request
active request
→ relevant evidence deletion blocked
Authorization
Project A retention admin
→ can manage Project A

Project A retention admin
→ cannot manage Project B
Concurrent deletion
10 concurrent deletion attempts

Expected:

exactly one successful deletion operation
remaining operations become idempotent/already-completed/blocked
Archive
archive
→ resource remains logically retained

restore
→ resource becomes available
Audit

Every administrative lifecycle operation produces the expected BE-015 ledger event.

53. Storage Tests

Verify:

archive preserves SHA-256
restore preserves SHA-256
deleted object is no longer accessible
stale storage references are not exposed
presigned URLs cannot be issued after deletion
archive does not create a duplicate evidence record
54. Concurrency Requirements

Retention operations must be safe under concurrent execution.

Test concurrent:

hold creation
deletion
archive
restore

The implementation must prevent race conditions where:

hold created

but a concurrent deletion still succeeds incorrectly.

Use database transactions/locking where necessary.

Do not rely on Python process-local locks.

55. Idempotency

Retention operations must be idempotent where practical.

Examples:

archive already archived
→ no duplicate archive

restore already restored
→ no duplicate restoration

delete already deleted
→ deterministic already-completed result

Repeated administrative requests must not create inconsistent lifecycle states.

56. Performance

Retention candidate discovery should be indexed.

Queries must not perform:

full table scan

for every resource on every evaluation where indexed candidate selection is possible.

Indexes should support:

retention state
expiry
policy
resource type
project
organization
hold status

Do not introduce premature distributed caching.

57. Observability

Retention operations should expose:

evaluation duration
resources evaluated
eligible resources
blocked resources
archived resources
deleted resources
failure count

Do not log sensitive evidence content.

Use existing request IDs and structured logging.

58. Failure Handling

If archival or deletion fails:

DO NOT report success

The operation must persist a failure state where appropriate.

Partial deletion must be handled carefully.

For storage + database operations, the implementation must define which operation is authoritative and provide recovery behavior.

Never silently swallow storage deletion errors.

59. Data Safety

BE-017 MUST NOT delete data merely because:

it is old
it has low integrity
it has a negative fusion signal
it has a low review priority
it has a duplicate match
it was contradicted
a model produced an observation

Retention is independent from evidence truth and risk assessment.

60. No Automatic Truth-Based Deletion

This is explicitly forbidden:

IF integrity_score < threshold
THEN delete evidence

Also forbidden:

IF fraud suspicion high
THEN delete evidence

The retention layer must remain independent of analytical conclusions.

61. Definition of Done

BE-017 is complete only when:

Database
 Retention policies exist
 Policy versions exist
 Retention state exists
 Holds exist
 Retention operations exist
 Foreign keys are enforced
 Required indexes exist
 Migration is reversible
 Exactly one Alembic head exists
Policy
 Policies are versioned
 Scope precedence is deterministic
 Retention anchors are explicit
 Missing anchors fail closed
 Conflicting policies fail closed
Holds
 Holds are first-class
 Holds block deletion
 Hold release is auditable
 Hold history is preserved
Archive
 Archive uses BE-002 storage abstraction
 SHA-256 is preserved
 Provenance is preserved
 Restoration works
 Archive is distinct from deletion
Deletion
 Deletion requires explicit authorization
 Eligibility is rechecked immediately before deletion
 Dependencies are checked
 Concurrent deletion is safe
 Deletion is audited
 Unauthorized deletion is denied
Existing systems
 Review Cases are considered
 Evidence Requests are considered
 Graph dependencies are considered
 Fusion history is preserved
 Audit ledger integrity is preserved
 Evidence storage remains consistent
Security
 BE-016 authorization enforced
 Project scope enforced
 Organization scope enforced
 Global permissions explicitly handled
 No role-only bypass
 No frontend-only security
Testing
 Unit suite passes
 Integration suite passes
 Full regression suite passes
 Alembic upgrade passes
 Alembic downgrade passes
 Alembic upgrade after downgrade passes
 Concurrent operations tested
 Storage operations tested
62. Verification Commands

At minimum:

pytest -q

alembic heads

alembic upgrade head

alembic downgrade <BE-016 revision>

alembic upgrade head

Run targeted tests:

tests/unit/test_retention.py

tests/integration/test_retention.py

Exact commands may follow the repository's existing test conventions.

63. Anti-Shortcut Gates
Gate 1 — No fixed global deletion timer

Do not implement one hard-coded deletion period for everything.

Gate 2 — No deletion without policy

If no applicable retention policy exists:

DENY DELETION
Gate 3 — No deletion through direct endpoint

Do not expose unrestricted:

DELETE /evidence/{id}
Gate 4 — No hold bypass

An active hold always blocks deletion.

Gate 5 — No stale evaluation

A previously successful retention evaluation cannot be treated as permanent authorization to delete.

Gate 6 — No cascading evidence destruction

Do not use careless cascading deletes for evidence/intelligence relationships.

Gate 7 — No audit destruction

BE-015 audit integrity must not be weakened to make retention easier.

Gate 8 — No truth-based retention

Fusion, vision, duplicate detection, or review priority must not directly determine deletion eligibility.

Gate 9 — No LLM/ML retention decisions

Retention eligibility must be deterministic and policy-based.

Gate 10 — Fail closed

If policy, hold, dependency, authorization, or lifecycle state cannot be reliably determined:

DO NOT DELETE
64. Recommended Implementation Structure
backend/
├── services/
│   └── retention.py
│
├── repositories/
│   └── retention.py
│
├── schemas/
│   └── retention.py
│
├── api/
│   └── v1/
│       └── endpoints/
│           └── retention.py
│
├── workers/
│   └── retention_worker.py
│
└── db/
    └── models.py

Exact structure may follow existing repository conventions.

65. Recommended Commit

Implementation:

BE-017: implement retention and data governance

Completion:

be-017 complete

66. Architectural Boundary

BE-017 answers:

HOW LONG SHOULD THIS RESOURCE BE RETAINED?

and:

IS THIS RESOURCE CURRENTLY ELIGIBLE FOR ARCHIVE OR DELETION?

It does NOT answer:

IS THIS EVIDENCE TRUE?

It does NOT answer:

IS THIS EVIDENCE FRAUDULENT?

It does NOT answer:

WHICH CASE SHOULD A REVIEWER DECIDE?

It does NOT answer:

WHICH PROJECT IS RISKIEST?

Those remain separate domain and intelligence concerns.

67. Final Architecture Flow

After BE-017, the relevant lifecycle becomes:

Authentication
→ Authorization
→ Resource Access
→ Evidence / Domain Processing
→ Intelligence
→ Human Review
→ Audit
→ Retention Evaluation
→ Hold / Dependency Check
→ Archive or Controlled Deletion

Retention remains independent of the substantive truth/decision layer.

The final human decision remains authoritative.

No retention operation may rewrite historical analytical or human-decision records.


### Current milestone chain

You are now effectively at:

**BE-001 → BE-015 ✅ → BE-016 ✅ → BE-017 next**

And the GitHub verification confirms that **BE-016 really is pushed**, with `fc9275a` as the current remote HEAD.