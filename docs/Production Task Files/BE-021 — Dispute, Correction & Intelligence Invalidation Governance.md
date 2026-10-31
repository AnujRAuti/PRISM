# BE-021 — Dispute, Correction & Intelligence Invalidation Governance

## 1. Objective

Implement the production-grade dispute, correction, invalidation, and supersession framework for Proof-of-Action (PoA).

The system already preserves immutable evidence, analytical runs, graph relationships, fusion assessments, review cases, audit events, retention policies, and external assertions.

BE-021 adds the governance layer required when previously submitted information is:

- disputed
- corrected
- withdrawn
- invalidated
- superseded
- discovered to contain incorrect metadata/context
- determined to require reprocessing

The core principle is:

> Raw evidence and historical decisions are never silently rewritten. Corrections create new state/version lineage, invalidate or supersede affected derived intelligence, and preserve the complete historical record.

BE-021 MUST NOT directly decide whether evidence is fraudulent, authentic, truthful, or false.

It provides the controlled mechanism through which authorized users can challenge or correct information and propagate the resulting state changes through dependent intelligence.

---

# 2. Architectural Boundary

BE-021 consumes and integrates with:

- BE-003 — Evidence Ingestion
- BE-004 — Fingerprinting
- BE-005 — Async Analysis
- BE-006 — Duplicate Intelligence
- BE-008 — Temporal Intelligence
- BE-009 — Vision Intelligence
- BE-010 — Evidence Graph
- BE-011 — Fusion Engine
- BE-012 — Explainability
- BE-013 — Review Cases
- BE-014 — Evidence Requests
- BE-015 — Audit Ledger
- BE-016 — Authentication / Authorization
- BE-017 — Retention / Governance
- BE-018 — Notifications / Event Delivery
- BE-019 — External Integrations
- BE-020 — Observability

BE-021 MUST preserve the existing architecture.

It MUST NOT replace existing services with a second implementation.

---

# 3. Core Governance Principle

PoA must distinguish between:

```text
CORRECTION
    |
    +--> new authoritative version/context
    |
    +--> previous state preserved
    |
    +--> dependent intelligence becomes stale
    |
    +--> authorized reprocessing may occur

and:

INVALIDATION
    |
    +--> previous assertion/relationship/intelligence is no longer valid
    |
    +--> historical record remains preserved
    |
    +--> downstream outputs are marked stale/invalidated

and:

SUPERSESSION
    |
    +--> newer information replaces applicability
    |
    +--> previous information remains historically queryable

and:

DISPUTE
    |
    +--> authorized challenge is recorded
    |
    +--> existing evidence is NOT automatically deleted
    |
    +--> outcome requires appropriate human authority
4. What BE-021 Must NOT Do

BE-021 MUST NOT:

automatically label evidence as fraudulent
automatically label evidence as authentic
automatically resolve disputes
automatically overturn human decisions
rewrite historical evidence
rewrite audit events
delete evidence because it is disputed
change fusion formulas
introduce new fraud scoring
introduce authenticity scoring
introduce deepfake detection
introduce ML-based truth determination
use an LLM to decide disputes
silently modify historical analysis runs
silently modify historical human decisions
bypass authorization
bypass retention holds
create a second audit ledger
5. Domain Concepts

Implement the following first-class governance concepts.

5.1 Dispute

A dispute represents an authorized challenge against an object or assertion.

Possible targets:

Evidence
Evidence-Claim relationship
Claim
External Assertion
Fusion Assessment
Review Case outcome where permitted by governance rules

A dispute must contain:

unique ID
target type
target ID
project scope where applicable
initiator
reason
description
status
created timestamp
updated timestamp
resolution metadata where resolved

Do not store arbitrary raw payloads unnecessarily.

6. Dispute Status

Implement a controlled lifecycle.

Minimum states:

OPEN
UNDER_REVIEW
RESOLVED
REJECTED
WITHDRAWN
ESCALATED

Transitions must be explicitly validated.

Suggested lifecycle:

OPEN
  → UNDER_REVIEW
  → RESOLVED
  → REJECTED
  → ESCALATED
  → WITHDRAWN

Escalation may return to:

UNDER_REVIEW

Do not permit arbitrary state mutation.

7. Dispute Resolution

Resolution must be human-governed.

Required resolution vocabulary:

UPHELD
REJECTED
INCONCLUSIVE
INSUFFICIENT_EVIDENCE

A resolution requires:

authorized actor
resolution value
non-empty rationale
timestamp

Do not add:

FRAUD
AUTHENTIC
FAKE
TRUE
FALSE

as automatic resolution vocabulary.

Those terms improperly collapse the distinction between evidence state and human governance.

8. Correction

Implement controlled corrections.

A correction may apply to mutable contextual information associated with evidence, such as:

project association
claim association
activity association
location context
contextual metadata
authorized descriptive fields

The original evidence bytes and cryptographic identity remain immutable.

If a correction affects the actual evidence file itself:

OLD EVIDENCE
    |
    +--> SUPERSEDED
    |
    +--> NEW EVIDENCE

The new evidence must pass through the normal ingestion pipeline.

Never overwrite the original object.

9. Evidence Version Lineage

Create explicit lineage between versions.

Use the existing graph model where appropriate.

Required relationship:

NEW_EVIDENCE
    -- DERIVED_FROM / SUPERSEDES -->
OLD_EVIDENCE

Choose the existing relationship vocabulary consistently with BE-010 and extend it only if a genuinely new relationship type is required.

Do not duplicate graph relationships in a second unrelated lineage system.

10. Correction Requests

Implement a first-class correction workflow.

A correction request should contain:

target type
target ID
requested change
reason
requester
status
created timestamp
resolution timestamp
resolver
rationale

Suggested lifecycle:

REQUESTED
→ UNDER_REVIEW
→ APPROVED
→ APPLIED

Alternative terminal states:

REJECTED
CANCELLED

Approval and application must remain distinct.

11. Authorization

Integrate completely with BE-016.

Introduce narrowly scoped permissions.

Suggested permissions:

dispute.create
dispute.read
dispute.review
dispute.resolve

correction.create
correction.read
correction.approve
correction.apply

intelligence.invalidate
intelligence.reprocess

Use the existing authorization service.

Do NOT implement a second permission system.

12. Role Separation

Maintain separation between:

Requester
Reviewer
Approver
Resolver
Administrator

Do not automatically allow the person who created a correction request to approve/apply it unless existing authorization policy explicitly permits it.

Administrators must not automatically become substantive decision-makers.

13. Dependency Invalidation

This is the most important BE-021 capability.

When a governed correction/invalidation occurs, determine affected derived information.

Potential dependency chain:

Evidence
   ↓
Analysis Run
   ↓
Vision / Duplicate / Temporal Observations
   ↓
Graph Relationships
   ↓
Fusion Run
   ↓
Explanation
   ↓
Review Case

Affected outputs must be marked appropriately as stale/invalidated.

Do NOT delete them.

14. Staleness Semantics

Introduce an explicit concept of stale derived intelligence.

Possible state:

CURRENT
STALE
INVALIDATED
SUPERSEDED

Do not overload existing domain statuses if doing so would break their established semantics.

Where possible, use the existing Analysis Run / graph / assessment lifecycle rather than inventing duplicate state machines.

15. Dependency Propagation

Example:

Evidence E1
    ↓
Analysis Run A1
    ↓
Graph Relationship G1
    ↓
Fusion Run F1
    ↓
Explanation X1

If E1 is materially corrected:

E1
 ↓
A1 → STALE
 ↓
G1 → STALE/INVALIDATED
 ↓
F1 → STALE/INVALIDATED
 ↓
X1 → STALE

The system must preserve the original records.

A new processing cycle creates new runs:

A2
F2
X2

Historical A1/F1/X1 remain queryable.

16. Dependency Graph

Use BE-010's Evidence Graph as the primary relationship source.

Do not implement a separate graph database.

Dependency traversal must:

be deterministic
be bounded
preserve provenance
preserve historical relationships
respect authorization
avoid infinite cycles
prevent duplicate processing

Use PostgreSQL recursive queries or bounded iterative traversal as appropriate.

17. Reprocessing

BE-021 may request reprocessing.

It MUST NOT directly duplicate BE-005 worker logic.

Instead:

Governance Event
    ↓
Invalidate/Stale existing intelligence
    ↓
Create reprocessing request/job
    ↓
Existing analysis pipeline
    ↓
New Analysis Run

Every new analysis execution must follow BE-005's existing lifecycle.

No historical run is modified.

18. Fusion Interaction

BE-021 must integrate with BE-011.

If evidence used by a fusion run becomes stale/invalidated:

existing fusion run remains historical
it must no longer be treated as current
dependent assessment/priority must reflect stale lineage
a new fusion run may be generated after valid reprocessing

BE-021 MUST NOT alter the fusion algorithm.

Do not recalculate fusion merely to mark something stale.

19. Explainability Interaction

BE-012 explanations must preserve historical lineage.

Historical explanations must remain retrievable.

If their source fusion run becomes stale/invalidated:

historical explanation = preserved
current explanation = stale/invalidated

A new explanation must reference the new fusion run.

Do not mutate historical explanation content.

20. Review Case Interaction

If a review case references intelligence that becomes stale:

do not automatically resolve the case
do not automatically reopen a resolved case without explicit governance policy
record that dependent intelligence changed
create an auditable event
allow authorized reviewers to determine next action

For open/investigating cases, optionally surface a governance warning.

For resolved cases, preserve the original decision.

Any reopening must use the existing BE-013 lifecycle.

21. Human Decision Preservation

Human decisions are append-only historical records.

BE-021 MUST NOT:

overwrite a previous decision
rewrite rationale
silently replace decision vocabulary
delete previous decisions

A subsequent decision must create a new event/version according to the existing review governance model.

22. External Assertions

Integrate with BE-019 external assertions.

External assertions may be:

disputed
superseded
invalidated
corrected through a new external assertion

Never rewrite the original external assertion.

Preserve:

source
external reference
received timestamp
original payload/provenance

where already supported by BE-019.

23. Audit Integration

Every governance action must emit BE-015 audit events.

Minimum events:

DISPUTE_CREATED
DISPUTE_REVIEW_STARTED
DISPUTE_ESCALATED
DISPUTE_RESOLVED
DISPUTE_WITHDRAWN

CORRECTION_REQUESTED
CORRECTION_APPROVED
CORRECTION_REJECTED
CORRECTION_APPLIED

INTELLIGENCE_INVALIDATED
INTELLIGENCE_REPROCESS_REQUESTED
INTELLIGENCE_REPROCESS_COMPLETED

Do not create another audit store.

Sensitive data must follow existing audit payload scrubbing.

24. Notifications

Integrate with BE-018.

Potential notifications:

dispute created
dispute assigned
dispute escalated
dispute resolved
correction approved
correction rejected
correction applied
intelligence invalidated
reprocessing completed

Notifications must not contain sensitive evidence contents.

Use the existing notification/event delivery infrastructure.

Do not create direct email logic.

25. External Integration Interaction

If a governed object originated from an external system:

preserve the external reference
preserve source provenance
record the correction/invalidation locally
do not silently mutate external source data
optionally emit outbound integration events where BE-019 permits

Do not automatically reconcile external systems.

26. Retention Interaction

Integrate with BE-017.

Disputed or invalidated evidence:

must not bypass retention policy
must not bypass legal holds
must not be automatically deleted
must preserve governance history

If deletion is requested while a dispute/hold/dependency exists, existing retention rules remain authoritative.

27. API

Implement REST endpoints under:

/api/v1/disputes
/api/v1/corrections
/api/v1/governance

Suggested endpoints:

POST   /api/v1/disputes
GET    /api/v1/disputes/{dispute_id}
GET    /api/v1/disputes
POST   /api/v1/disputes/{dispute_id}/start-review
POST   /api/v1/disputes/{dispute_id}/escalate
POST   /api/v1/disputes/{dispute_id}/resolve
POST   /api/v1/disputes/{dispute_id}/withdraw
GET    /api/v1/disputes/{dispute_id}/history

Correction:

POST   /api/v1/corrections
GET    /api/v1/corrections/{correction_id}
GET    /api/v1/corrections
POST   /api/v1/corrections/{correction_id}/approve
POST   /api/v1/corrections/{correction_id}/reject
POST   /api/v1/corrections/{correction_id}/apply
GET    /api/v1/corrections/{correction_id}/history

Dependency inspection:

GET /api/v1/governance/{target_type}/{target_id}/dependencies

Reprocessing:

POST /api/v1/governance/{target_type}/{target_id}/reprocess

Exact endpoint structure may be adapted to existing API conventions.

28. Idempotency

Governance mutations must be safe under retries.

Use existing BE-019 idempotency infrastructure where appropriate.

Examples:

duplicate dispute creation
duplicate correction approval
duplicate invalidation request
duplicate reprocessing request

Repeated identical requests must not create unintended duplicate state transitions.

29. Concurrency

Protect against:

two reviewers resolving the same dispute
two users approving the same correction
correction application racing with another correction
multiple invalidation operations
duplicate reprocessing requests

Use PostgreSQL transactions and appropriate row-level locking/constraints.

Do not rely on Python locks.

30. Database

Add only the tables genuinely required.

Potential tables:

disputes
dispute_events

correction_requests
correction_events

intelligence_invalidations
reprocessing_requests

All tables must have:

UUID primary keys
timezone-aware timestamps
appropriate foreign keys
CHECK constraints
indexes for operational queries
restrictive FK behavior where historical records must be preserved

Do not store duplicated evidence data.

31. Migration

Create one Alembic migration.

Recommended revision:

m3n4o5p6q021

Parent must be the current BE-020 migration head.

Before implementation:

alembic heads
alembic current

must be checked.

There must remain exactly one Alembic head.

Verify:

upgrade
→ downgrade
→ upgrade

against live PostgreSQL.

Do not modify historical migrations.

32. Repository / Service Architecture

Follow the existing architecture:

backend/
├── services/
│   ├── dispute.py
│   ├── correction.py
│   └── governance.py
│
├── repositories/
│   ├── dispute.py
│   ├── correction.py
│   └── governance.py
│
├── schemas/
│   ├── dispute.py
│   ├── correction.py
│   └── governance.py
│
└── api/v1/endpoints/
    ├── dispute.py
    ├── correction.py
    └── governance.py

Adapt names to repository conventions.

Do not duplicate existing graph, audit, authorization, notification, or analysis services.

33. Observability

Integrate BE-020 telemetry.

Track:

disputes_created_total
disputes_resolved_total
correction_requests_total
corrections_applied_total
intelligence_invalidations_total
reprocessing_requests_total
reprocessing_failures_total
governance_operation_duration_seconds

Metric labels MUST remain bounded.

Never use:

user_id
project_id
evidence_id
claim_id
dispute_id

as Prometheus labels.

Structured logs should contain correlation IDs.

34. Security

Test:

unauthorized users cannot create/read/resolve disputes outside scope
users cannot modify another organization's governance state
correction approval requires appropriate permission
administrators cannot bypass substantive authority
cross-project dependency traversal respects authorization
sensitive evidence is not returned through governance endpoints
audit payloads are scrubbed
retention holds cannot be bypassed
historical decisions cannot be overwritten

Use BE-016 as the authoritative authorization layer.

35. Testing
Unit Tests

Minimum coverage:

Disputes
creation
lifecycle transitions
invalid transitions
resolution vocabulary
rationale validation
withdrawal
escalation
authorization
Corrections
request creation
approval
rejection
application
invalid transitions
immutable evidence protection
version lineage
Invalidation
dependency discovery
bounded traversal
stale propagation
invalidation propagation
duplicate dependency handling
cycle protection
Reprocessing
request creation
idempotency
duplicate prevention
existing pipeline delegation
36. Integration Tests

Use live PostgreSQL and existing infrastructure.

Test at minimum:

create dispute
review dispute
resolve dispute
dispute audit events
create correction
approve correction
apply correction
original evidence remains unchanged
new evidence version has lineage
dependent analysis becomes stale
dependent graph relationships become stale/invalidated
dependent fusion becomes stale/invalidated
historical explanation remains available
new reprocessing creates a new analysis run
review case is preserved
human decision is preserved
authorization isolation
concurrent resolution
concurrent correction application
retention hold interaction
external assertion invalidation
notification integration
observability telemetry
37. Regression Testing

Run the complete existing test suite.

Expected result:

ALL TESTS PASS
0 REGRESSIONS

Do not delete, weaken, skip, or rewrite existing tests merely to make BE-021 pass.

If an existing test conflicts with the architecture, stop and investigate the conflict rather than silently changing behavior.

38. Performance

Measure:

dispute creation latency
correction creation latency
dependency traversal latency
invalidation propagation latency
governance list/query latency
concurrent resolution behavior

Dependency traversal must remain bounded.

Do not perform unbounded graph traversal.

Use appropriate indexes.

39. Integrity Verification

After implementation, verify:

0 orphaned governance rows
0 invalid lifecycle states
0 duplicate active corrections
0 duplicate active disputes where prohibited
0 broken evidence lineage
0 overwritten historical evidence
0 overwritten historical decisions
0 unauthorized cross-project access
0 invalid graph relationships
0 multiple Alembic heads

Verify that stale/invalidated intelligence remains historically queryable.

40. Anti-Shortcut Requirements

The implementation MUST NOT:

mark evidence as fake because it is disputed
delete disputed evidence
overwrite evidence files
overwrite historical analysis
overwrite fusion results
overwrite explanations
overwrite human decisions
use an LLM for dispute decisions
use ML for dispute decisions
invent truth/fraud probabilities
bypass authorization
bypass retention
create a second audit ledger
create a second graph
duplicate the analysis worker
duplicate notification delivery
duplicate external integration logic
use Python locks for concurrency
perform unlimited recursive traversal
expose sensitive evidence through governance APIs
use high-cardinality Prometheus labels
modify historical Alembic migrations
weaken existing tests
introduce BE-022+ functionality
41. Definition of Done

BE-021 is complete only when:

Disputes are first-class domain objects.
Dispute lifecycle is explicitly validated.
Human resolution is required.
Correction requests are first-class domain objects.
Evidence bytes remain immutable.
Evidence corrections create explicit version lineage.
Dependency discovery uses the Evidence Graph.
Derived intelligence can become STALE/INVALIDATED without deletion.
Historical analysis runs remain queryable.
Historical fusion results remain queryable.
Historical explanations remain queryable.
Human review decisions remain preserved.
Reprocessing creates new analysis runs.
BE-011 fusion logic remains unchanged.
BE-012 explanation logic remains unchanged.
BE-013 review lifecycle remains authoritative.
BE-015 audit ledger records governance actions.
BE-016 authorization protects governance operations.
BE-017 retention/holds remain authoritative.
BE-018 notifications are reused.
BE-019 external assertions are supported.
BE-020 telemetry is emitted.
Concurrency is database-safe.
Idempotency is enforced.
Unit tests pass.
Integration tests pass.
Full regression suite passes with zero regressions.
Alembic upgrade/downgrade/upgrade succeeds.
Exactly one Alembic head exists.
No sensitive data leaks through governance endpoints or telemetry.
No historical data is silently rewritten.
No BE-022+ scope has leaked into the implementation.
42. Required Final Verification Report

Before declaring completion, produce a report containing:

Implementation
files created
files modified
files deleted
migration revision
API endpoints
permissions
audit events
notification events
Tests
Unit:
Integration:
Full suite:
Failures:
Skipped:
Database
Alembic head:
Upgrade:
Downgrade:
Re-upgrade:
Orphan check:
Constraint check:
Governance Verification
Dispute lifecycle:
Correction lifecycle:
Evidence immutability:
Version lineage:
Dependency propagation:
Fusion invalidation:
Explanation preservation:
Review-case preservation:
Human-decision preservation:
Reprocessing:
Security
Authorization:
Cross-project isolation:
Retention interaction:
Sensitive-data exposure:
Audit integrity:
Performance
Dispute creation:
Correction creation:
Dependency traversal:
Invalidation propagation:
Concurrent mutation:
Git

Implementation commit:

BE-021: implement dispute and correction governance

Completion commit:

BE-021 Complete

Push both to:

origin/Backend

Do NOT:

force push
reset
rebase
delete branches
rewrite history
discard unrelated changes
43. Final Architectural Boundary

After BE-021:

BE-001  API / DB Foundation
BE-002  Storage
BE-003  Evidence Ingestion
BE-004  Fingerprinting
BE-005  Async Analysis
BE-006  Duplicate Intelligence
BE-007  Projects / Claims / Spatial
BE-008  Temporal Intelligence
BE-009  Vision Intelligence
BE-010  Evidence Graph
BE-011  Fusion Engine
BE-012  Explainability
BE-013  Review Cases
BE-014  Evidence Requests
BE-015  Audit Ledger
BE-016  Authentication / Authorization
BE-017  Retention / Governance
BE-018  Notifications / Event Delivery
BE-019  External Integrations / API Clients
BE-020  Observability / System Health
BE-021  Dispute / Correction / Intelligence Invalidation

BE-021 completes the governance feedback loop:

EVIDENCE
   ↓
ANALYSIS
   ↓
GRAPH
   ↓
FUSION
   ↓
EXPLANATION
   ↓
REVIEW
   ↓
HUMAN DECISION
   ↓
DISPUTE / CORRECTION
   ↓
INVALIDATION / SUPERSESSION
   ↓
REPROCESSING
   ↓
NEW ANALYSIS RUN
   ↓
NEW FUSION
   ↓
NEW EXPLANATION

The historical chain must remain intact at every stage.

BE-021 is a governance and lineage milestone, NOT a new intelligence engine.