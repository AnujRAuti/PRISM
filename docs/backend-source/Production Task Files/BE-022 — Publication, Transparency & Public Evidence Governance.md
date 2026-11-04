# BE-022 — Publication, Transparency & Public Evidence Governance

## 1. Objective

Implement the controlled publication and transparency layer for Proof-of-Action (PoA).

PoA currently contains:

- evidence
- projects
- activities
- claims
- evidence relationships
- analysis results
- fusion assessments
- explanations
- review cases
- human decisions
- disputes
- corrections
- retention policies
- authorization
- audit history
- external assertions

BE-022 introduces the governed mechanism for determining:

> What information may be exposed publicly, what remains private/internal, who can publish it, what version is published, and how publication/revocation history is preserved.

The public transparency layer MUST NOT expose the internal intelligence system directly.

Publication is a controlled projection of authorized information.

---

# 2. Core Principle

The system must distinguish:

```text
INTERNAL DOMAIN DATA
        |
        ↓
AUTHORIZATION
        |
        ↓
PUBLICATION POLICY
        |
        ↓
RELEASABILITY EVALUATION
        |
        ↓
PUBLICATION VERSION
        |
        ↓
PUBLIC PUBLICATION

Publication does NOT mean:

"the evidence is true"

Publication means:

"this specific information has been authorized for public visibility."

These concepts MUST remain separate.

3. Architectural Boundary

BE-022 integrates with:

BE-003 — Evidence Ingestion
BE-007 — Projects / Claims / Activities
BE-010 — Evidence Graph
BE-011 — Fusion Engine
BE-012 — Explainability
BE-013 — Review Cases
BE-015 — Audit Ledger
BE-016 — Authentication / Authorization
BE-017 — Retention / Governance
BE-018 — Notifications
BE-019 — External Integrations
BE-020 — Observability
BE-021 — Dispute / Correction / Invalidation

BE-022 MUST reuse these systems.

Do not create:

a second authorization system
a second audit ledger
a second evidence store
a second graph
a second notification system
a second retention system
4. Publication Model

Introduce a first-class publication model.

A publication represents a governed public representation of a PoA object.

Possible publication targets:

PROJECT
ACTIVITY
CLAIM
EVIDENCE
REVIEW_CASE
FUSION_ASSESSMENT

Not every target type must be publicly publishable.

The implementation must define an explicit allowlist.

Do NOT expose:

credentials
internal permissions
internal audit data
private citizen identity
private EXIF
storage keys
internal graph traversal
security telemetry
internal risk/review prioritization data
confidential reviewer information
private evidence
unapproved intelligence
5. Public vs Internal Representation

The public representation MUST be a projection.

Example:

Internal Evidence
    |
    +-- storage_key
    +-- EXIF
    +-- internal metadata
    +-- analysis lineage
    +-- graph relationships
    +-- reviewer information
    +-- security metadata
    |
    ↓
PUBLIC EVIDENCE PROJECTION
    |
    +-- public ID
    +-- approved metadata
    +-- approved media derivative
    +-- publication timestamp
    +-- publication status

Never serialize the internal ORM object directly as the public response.

Create explicit public schemas.

6. Publication Status

Implement a controlled lifecycle.

Minimum states:

DRAFT
PENDING_REVIEW
APPROVED
PUBLISHED
UNPUBLISHED
REJECTED

Suggested lifecycle:

DRAFT
  → PENDING_REVIEW
  → REJECTED

PENDING_REVIEW
  → APPROVED
  → REJECTED

APPROVED
  → PUBLISHED

PUBLISHED
  → UNPUBLISHED

A published item may NOT silently return to an editable published state.

A new publication version must be created for material changes.

7. Publication Versioning

Publication is versioned.

Example:

Project P1

Publication v1
    ↓
published
    ↓
material correction
    ↓
Publication v2
    ↓
published

Historical publication versions remain queryable.

Never overwrite the historical public representation.

Each version must contain:

publication ID
target
version number
publication snapshot
publication status
created timestamp
approved timestamp
published timestamp
unpublished timestamp where applicable
actor metadata
policy version
source version references
8. Publication Snapshot

A publication version must contain a deterministic snapshot of the information approved for public exposure.

The snapshot MUST NOT contain:

raw storage credentials
storage keys
authentication data
authorization data
internal audit payloads
private citizen information
internal review-priority values
internal security telemetry
secrets
hidden graph relationships

The snapshot should reference public-safe identifiers where necessary.

Do not rely on reconstructing historical publication output from mutable domain records.

9. Publication Policy

Create versioned publication policies.

A policy defines:

what target types may be published
which fields are public
which fields are prohibited
whether evidence media may be exposed
whether derived intelligence may be exposed
whether review outcomes may be exposed
minimum authorization level
required approvals
retention/publication duration
geographic/privacy restrictions
redaction requirements

Policy versions are immutable.

Changing policy creates a new version.

10. Default Visibility Classes

Respect the architecture's existing visibility concepts:

PUBLIC
CITIZEN_OWNED_PRIVATE
OPERATIONAL
INTELLIGENCE_INTERNAL
ADMINISTRATIVE_SECURITY

Only PUBLIC content may be returned through public endpoints.

Do not infer public visibility merely because a user has permission to read the internal object.

11. Releasability Evaluation

Implement a deterministic publication eligibility check.

Potential blockers:

UNAUTHORIZED
NOT_PUBLISHABLE_TYPE
PRIVATE_VISIBILITY
ACTIVE_DISPUTE
UNRESOLVED_CORRECTION
RETENTION_RESTRICTION
LEGAL_HOLD
MISSING_REQUIRED_APPROVAL
SENSITIVE_DATA_PRESENT
SOURCE_RESTRICTION
UNAVAILABLE_PUBLIC_DERIVATIVE

The system must return structured reasons.

Do not collapse every failure into:

NOT_ALLOWED

Do not treat:

LOW_INTEGRITY
HIGH_REVIEW_PRIORITY

as automatic publication blockers unless explicitly configured by policy.

Publication governance is separate from truth determination.

12. Dispute / Correction Interaction

Integrate with BE-021.

If a published object becomes disputed:

do NOT silently delete it
preserve publication history
surface governed status where policy permits
prevent inappropriate new publication versions
require appropriate review before republication

If a published object is corrected:

PUBLICATION v1
       ↓
source corrected
       ↓
v1 remains historical
       ↓
releasability re-evaluated
       ↓
PUBLICATION v2

The system must not mutate v1.

13. Retention Interaction

Integrate with BE-017.

Publication MUST NOT bypass retention policies.

If a source object is subject to:

legal hold
retention restriction
controlled deletion
archival restriction

publication behavior must follow the applicable governance policy.

A public publication must not become a mechanism for bypassing controlled deletion rules.

If an already-published object is later removed from public visibility due to retention/governance rules, record the unpublication event.

14. Authorization

Use BE-016.

Suggested permissions:

publication.create
publication.read
publication.review
publication.approve
publication.publish
publication.unpublish
publication.policy.manage

Authorization must consider:

actor
role
organization
organizational unit
project scope
target resource
publication action

Administrators must NOT automatically receive substantive publication authority unless explicitly granted.

15. Approval Separation

Where configured by policy:

REQUESTER
    ≠
APPROVER

A user who creates a publication request should not automatically approve their own request.

For high-sensitivity publication policies, support:

REVIEWER
→ SUPERVISOR APPROVAL
→ PUBLISH

Do not hard-code a single approval hierarchy into every publication.

16. Public Identifier

Do not expose internal UUIDs unnecessarily.

Create a stable public identifier for published objects.

Example:

POA-PROJ-000001
POA-EVD-000001
POA-CLAIM-000001

Requirements:

unique
non-sensitive
stable across publication versions
not derived from secrets
not a sequential internal database primary key unless explicitly acceptable

Internal IDs may remain available to authorized internal APIs.

17. Public API

Create public, read-only endpoints.

Suggested endpoints:

GET /api/v1/public/projects
GET /api/v1/public/projects/{public_id}
GET /api/v1/public/projects/{public_id}/activities
GET /api/v1/public/projects/{public_id}/claims
GET /api/v1/public/projects/{public_id}/evidence
GET /api/v1/public/evidence/{public_id}
GET /api/v1/public/publications/{publication_id}

Public endpoints MUST NOT require internal authentication for genuinely public content.

They MUST still enforce publication state.

A PUBLISHED publication is the source of truth for public output.

Do not dynamically expose unpublished internal domain records.

18. Internal Publication API

Create authenticated governance endpoints.

Suggested:

POST /api/v1/publications
GET /api/v1/publications/{publication_id}
GET /api/v1/publications
GET /api/v1/publications/{publication_id}/history

POST /api/v1/publications/{publication_id}/submit-review
POST /api/v1/publications/{publication_id}/approve
POST /api/v1/publications/{publication_id}/reject
POST /api/v1/publications/{publication_id}/publish
POST /api/v1/publications/{publication_id}/unpublish

GET /api/v1/publications/{publication_id}/eligibility

Exact route structure may follow existing endpoint conventions.

19. Public Evidence Media

If evidence media is approved for publication:

NEVER expose internal object-storage keys
use a public-safe derivative
preserve original evidence immutability
apply configured redaction/transformation
use BE-002 storage abstraction
respect retention policy
preserve lineage

Public media must be explicitly approved.

A private/internal evidence object must never become publicly accessible merely because a URL is known.

20. Media Derivatives

Where public media requires transformation, create a derived object.

Example:

ORIGINAL EVIDENCE
       |
       +--> PUBLIC DERIVATIVE

The original remains unchanged.

The derivative must have provenance identifying:

source evidence
transformation
transformation version
creation timestamp
publication version

Do not modify original evidence bytes.

21. PII / Sensitive Data Protection

Publication must include deterministic protection for sensitive information.

At minimum consider:

citizen identity
phone numbers
email addresses
exact private addresses
private GPS coordinates
EXIF
internal user IDs
reviewer identity where restricted
storage keys
authentication data
internal notes
private evidence-request instructions

Do not introduce facial recognition or ML-based PII detection.

V1 should use explicit field-level publication policies.

22. Location Privacy

Public publication must support location precision policies.

Possible policies:

EXACT
APPROXIMATE
AREA
HIDDEN

For example:

Internal:
18.5984, 73.7898

Public:
Hinjewadi Phase 1

The transformation must be deterministic and policy-controlled.

Never expose precise private citizen location by default.

23. Public Claims

Claims may be published only when their publication state is explicitly approved.

Public claim output should contain:

public claim ID
public project ID
approved claim statement
relevant publication-safe dates
publication status
supporting public evidence references where approved

Do not expose internal fusion signals unless policy explicitly allows them.

24. Public Assessments

If policy allows publication of assessment outcomes, expose only approved public vocabulary.

Do not expose:

internal weighted signal values
internal priority score
model internals
internal graph conflicts
reviewer-only notes
security metadata

If the human decision is public, clearly distinguish:

AUTOMATED SIGNAL

from:

HUMAN DECISION

Never imply that an automated signal is a final government determination.

25. Provenance

Public outputs should preserve useful provenance without exposing sensitive internals.

Possible public provenance:

publication version
source category
publication timestamp
human approval status
evidence collection date where approved

Do not expose:

private credentials
internal worker details
storage paths
secret IDs
security telemetry
private audit payloads
26. Audit Integration

Every publication governance mutation must emit BE-015 audit events.

Minimum events:

PUBLICATION_CREATED
PUBLICATION_REVIEW_STARTED
PUBLICATION_APPROVED
PUBLICATION_REJECTED
PUBLICATION_PUBLISHED
PUBLICATION_UNPUBLISHED
PUBLICATION_POLICY_CREATED
PUBLICATION_POLICY_UPDATED
PUBLICATION_ELIGIBILITY_FAILED
PUBLIC_PUBLICATION_VERSION_CREATED

Do not create another audit store.

Audit payloads must contain bounded metadata only.

27. Notification Integration

Use BE-018.

Potential notifications:

PUBLICATION_SUBMITTED
PUBLICATION_APPROVED
PUBLICATION_REJECTED
PUBLICATION_PUBLISHED
PUBLICATION_UNPUBLISHED
PUBLICATION_REQUIRES_REVIEW

Do not implement direct email delivery.

Use the existing notification/outbox infrastructure.

28. External Integration

Integrate with BE-019.

Published information may be exposed through approved external APIs/webhooks.

Do not automatically publish every external assertion.

External source restrictions must remain authoritative.

Publication must not silently modify external systems.

29. Search / Listing

Public listing endpoints should support safe filters such as:

project
publication_status
published_at
region
category

Do not allow arbitrary internal filters.

Do not expose internal UUID filtering publicly.

Pagination is mandatory.

Avoid unbounded public queries.

30. Caching

Public published representations may be cacheable.

Internal/unpublished information MUST NOT accidentally become publicly cached.

If caching is implemented:

cache only published representations
invalidate cache on unpublish
invalidate cache when a new publication version becomes current
never cache private/internal responses under public keys

Do not introduce Redis caching unless it is actually required.

31. Database

Create only tables required for publication.

Potential tables:

publication_policies
publications
publication_versions
publication_events
public_identifiers
public_media_derivatives

All persistent publication records must include:

UUID primary key
timezone-aware timestamps
controlled status fields
target references
appropriate indexes
restrictive historical FKs
policy version references

Publication versions MUST be immutable after publication.

32. Snapshot Storage

Choose an explicit persistence mechanism for publication snapshots.

The snapshot must be:

deterministic
versioned
immutable
reproducible
independent of future internal field changes

JSONB may be used for structured snapshots where appropriate.

Do not store complete raw evidence files inside PostgreSQL.

Media belongs in BE-002 storage.

33. Migration

Create exactly one Alembic migration.

Recommended revision:

n4o5p6q7r022

Parent MUST be the current BE-021 migration head.

Before implementation:

alembic heads
alembic current

must be checked.

There must remain exactly one Alembic head.

Verify:

alembic upgrade head
alembic downgrade -1
alembic upgrade head

Do not modify historical migrations.

34. Repository / Service Architecture

Follow existing patterns.

Suggested structure:

backend/
├── services/
│   ├── publication.py
│   └── publication_policy.py
│
├── repositories/
│   ├── publication.py
│   └── publication_policy.py
│
├── schemas/
│   ├── publication.py
│   └── public.py
│
└── api/v1/endpoints/
    ├── publication.py
    └── public.py

Adapt names to repository conventions.

Do not duplicate existing authorization, audit, storage, notification, retention, or governance services.

35. Observability

Integrate BE-020 telemetry.

Track:

publications_created_total
publications_approved_total
publications_published_total
publications_unpublished_total
publication_eligibility_failures_total
public_publication_requests_total
public_publication_errors_total
publication_operation_duration_seconds

Metric labels MUST remain bounded.

Never use:

user_id
project_id
evidence_id
claim_id
publication_id
public_id

as Prometheus labels.

36. Security

Explicitly test:

unpublished objects cannot be retrieved publicly
rejected objects cannot be retrieved publicly
internal-only evidence cannot be published without authorization
cross-project publication isolation works
citizen-private information cannot leak
storage keys cannot leak
EXIF cannot leak unless explicitly allowed
internal audit data cannot leak
reviewer-only data cannot leak
internal fusion signals cannot leak
private GPS cannot leak
unpublish immediately removes public availability
public APIs cannot access arbitrary internal IDs
public endpoints cannot be used for enumeration beyond intended public identifiers
37. Publication Immutability Tests

Verify:

Publication v1
    ↓
published

After internal source mutation:

Publication v1

must remain unchanged.

A new version must be created.

Test:

snapshot immutability
version ordering
historical retrieval
current-version resolution
unpublish behavior
new-version publication
38. Testing
Unit Tests

Test:

Policy
policy creation
policy versioning
immutable versions
target allowlist
field allowlist
prohibited field detection
Publication
lifecycle transitions
invalid transitions
version creation
snapshot generation
public identifier generation
eligibility evaluation
Privacy
prohibited fields
private GPS
EXIF
citizen identity
storage keys
internal IDs
reviewer-only information
Public API
only published records visible
pagination
safe filtering
unpublished hidden
rejected hidden
39. Integration Tests

Use live PostgreSQL and existing infrastructure.

At minimum test:

create publication policy
create publication request
eligibility evaluation
publication review
approval
publication
public retrieval
public listing
public pagination
rejected publication inaccessible publicly
unpublished publication inaccessible publicly
cross-project isolation
evidence public derivative
original evidence remains immutable
publication version creation
historical version retrieval
correction interaction
dispute interaction
retention interaction
private GPS protection
EXIF protection
storage-key protection
audit event creation
notification event creation
authorization enforcement
public identifier stability
concurrent publication attempts
duplicate publication requests
public cache invalidation if caching exists
observability metrics
40. Regression Testing

Run:

pytest tests/ -q

No existing tests may be deleted, weakened, or skipped to make BE-022 pass.

Any regression must be investigated.

41. Performance

Measure:

publication creation latency
eligibility evaluation latency
public retrieval latency
public listing latency
publication version creation latency
concurrent publish behavior

Public listing queries must use appropriate indexes.

No unbounded joins.

No loading of entire evidence datasets into application memory.

42. Integrity Verification

Verify:

0 orphaned publication rows
0 orphaned publication versions
0 invalid publication states
0 duplicate active publication versions
0 duplicate public identifiers
0 unpublished data publicly accessible
0 private data exposed publicly
0 storage keys exposed
0 EXIF leaks
0 internal UUID enumeration paths
0 broken publication lineage
0 unauthorized cross-project access
0 multiple Alembic heads
43. Anti-Shortcut Requirements

The implementation MUST NOT:

expose internal ORM objects directly
make every internal object public automatically
equate publication with truth
expose internal fusion scores
expose review-priority scores
expose internal graph traversal
expose private EXIF
expose storage keys
expose citizen identity without explicit policy
modify original evidence
overwrite publication history
delete publication history
bypass retention
bypass authorization
create a second audit system
create a second notification system
create a second storage system
use ML to determine publication eligibility
use an LLM to determine publication eligibility
introduce arbitrary public SQL filters
use high-cardinality Prometheus labels
modify historical migrations
weaken existing tests
introduce BE-023+ scope
44. Required Final Verification Report

Before declaring BE-022 complete, produce:

Implementation
Files created:
Files modified:
Files deleted:
Migration:
API endpoints:
Permissions:
Publication policies:
Audit events:
Notification events:
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
Publication Verification
Policy versioning:
Eligibility:
Publication lifecycle:
Public visibility:
Unpublication:
Versioning:
Snapshot immutability:
Public identifier stability:
Privacy
Citizen data protection:
GPS protection:
EXIF protection:
Storage-key protection:
Internal-ID protection:
Reviewer-data protection:
Fusion-data protection:
Governance
BE-021 dispute interaction:
BE-021 correction interaction:
BE-017 retention interaction:
BE-016 authorization:
BE-015 audit:
BE-018 notifications:
BE-019 integrations:
BE-020 telemetry:
Performance
Publication creation:
Eligibility evaluation:
Public retrieval:
Public listing:
Concurrent publication:
45. Git

Implementation commit:

BE-022: implement publication and transparency governance

Completion commit:

BE-022 Complete

Push both to:

origin/Backend

Do NOT:

force push
reset
rebase
delete branches
rewrite history
discard unrelated changes
46. Definition of Done

BE-022 is complete only when:

Publication is a first-class governed domain concept.
Publication policies are versioned.
Publication versions are immutable.
Public representations are explicit projections.
Internal ORM objects are never exposed directly.
Public identifiers are stable and non-sensitive.
Publication eligibility is deterministic.
Authorization is enforced through BE-016.
Public endpoints expose only published representations.
Unpublished/rejected/private information is inaccessible publicly.
Public media uses the BE-002 storage abstraction.
Original evidence remains immutable.
Publication snapshots are historically stable.
Dispute interaction with BE-021 is implemented.
Correction interaction with BE-021 is implemented.
Retention interaction with BE-017 is implemented.
Audit events use BE-015.
Notifications use BE-018.
External publication uses BE-019 where applicable.
Observability uses BE-020.
Sensitive information cannot leak through public APIs.
Cross-project authorization is enforced.
Concurrent publication operations are database-safe.
Idempotent publication requests are supported.
Unit tests pass.
Integration tests pass.
Full regression suite passes with zero regressions.
Alembic upgrade/downgrade/re-upgrade succeeds.
Exactly one Alembic head exists.
No historical publication version is silently modified.
No second audit/storage/notification/authorization system exists.
No BE-023+ scope has leaked into the implementation.
47. Final Architectural Boundary

After BE-022:

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
BE-022  Publication / Transparency Governance

BE-022 establishes the controlled boundary between PoA's internal intelligence system and its public transparency layer.

The resulting architecture becomes:

                         INTERNAL SYSTEM
                              |
                              ↓
Evidence → Analysis → Graph → Fusion → Review
                              |
                              ↓
                    Human / Governance Layer
                              |
             ┌────────────────┴────────────────┐
             ↓                                 ↓
       Dispute / Correction              Authorization
             ↓                                 ↓
       Invalidation                    Publication Policy
             └────────────────┬────────────────┘
                              ↓
                    PUBLICATION SNAPSHOT
                              ↓
                     PUBLIC TRANSPARENCY

The public layer must expose only explicitly authorized publication snapshots.

Publication is not truth.
Publication is not approval of the underlying evidence.
Publication is a governed visibility decision.

BE-022 must implement that distinction throughout the database, services, APIs, security model, audit trail, and tests.