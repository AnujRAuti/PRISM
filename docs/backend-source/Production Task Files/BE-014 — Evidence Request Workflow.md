BE-014 — Evidence Request Workflow

Production Task File
Milestone: BE-014
Status: Ready for implementation
Depends on: BE-001 → BE-013
Primary dependencies: BE-007 Project/Claim/Evidence, BE-011 Fusion, BE-012 Explainability, BE-013 Review Cases
Recommended commit: BE-014: implement evidence request workflow

1. Objective

Implement the backend Evidence Request workflow defined by the frozen architecture.

An Evidence Request allows an authorized workflow participant to request additional evidence needed to investigate a claim, activity, evidence item, or review case.

The central principle is:

A Review Case identifies work that requires human investigation. An Evidence Request records a specific, auditable request for additional evidence needed during that investigation.

BE-014 must not create new analytical intelligence.

The workflow becomes:

Evidence / Claim / Intelligence
          ↓
BE-011 Fusion
          ↓
BE-012 Explanation
          ↓
BE-013 Review Case
          ↓
BE-014 Evidence Request
          ↓
Additional Evidence
          ↓
Existing Evidence Ingestion Pipeline

The newly submitted evidence must enter the existing BE-003 → BE-010 → BE-011 pipeline rather than bypassing it.

2. Architectural Boundary

The frozen architecture defines Evidence Request as a first-class auditable object with:

requester;
recipient;
scope;
instructions;
due date;
priority;
lifecycle;
linked evidence.

BE-014 implements that domain object and its lifecycle.

It does not implement:

email;
SMS;
push notifications;
chat;
citizen messaging;
authentication;
RBAC;
organization authorization;
reviewer UI;
mobile UI;
new evidence analysis;
new scoring;
fraud detection.

Those belong to later milestones.

3. Core Principles
3.1 Request ≠ Evidence

An Evidence Request is not itself evidence.

Evidence Request
    ↓
asks for evidence

The request must never be inserted into the evidence table.

3.2 Requested Evidence Is Not Automatically Trusted

When requested evidence is submitted:

request
    ↓
submission
    ↓
existing evidence ingestion
    ↓
validation
    ↓
quarantine
    ↓
trusted storage
    ↓
analysis

The fact that evidence was submitted in response to an official request does not establish truth, authenticity, or correctness.

3.3 Request Fulfillment ≠ Positive Outcome

A fulfilled request does not mean:

claim supported

Likewise:

request expired

does not mean:

claim contradicted

Absence of requested evidence must remain distinct from negative evidence.

4. Evidence Request Model

Create:

evidence_requests

Minimum fields:

Identity
id
UUID primary key
Case relationship
review_case_id
required for review-driven requests
Scope

Nullable references as appropriate:

project_id
activity_id
claim_id
evidence_id

The request must identify what investigation context it belongs to.

Do not allow arbitrary cross-project references without validating domain consistency.

5. Requester and Recipient

Store:

requester_id
recipient_id

These are identity references.

BE-014 must treat them as opaque identifiers.

Do not implement identity management or authentication in this milestone.

6. Request Instructions

Required:

instructions

The instructions describe what evidence is being requested.

Example:

Provide a photograph showing the completed installation
from the western entrance, including the surrounding area.

Do not automatically convert instructions into a canonical Claim.

Do not use an LLM to generate instructions.

7. Due Date

Optional:

due_at

Requirements:

timezone-aware;
normalized internally;
cannot silently invent a timezone;
explicit timestamp semantics.

A missing due date means no deadline was configured.

It does not mean the request has no lifecycle.

8. Priority

Store request priority independently from BE-011 Review Priority.

Suggested enum:

LOW
NORMAL
HIGH
URGENT

This is an operational urgency field for the request.

It must not be confused with:

Review Priority

from BE-011.

No calculation should derive one from the other unless explicitly configured in a future milestone.

9. Request Lifecycle

Use an explicit state machine.

Minimum lifecycle:

DRAFT
OPEN
ACKNOWLEDGED
FULFILLED
PARTIALLY_FULFILLED
DECLINED
EXPIRED
CANCELLED

Meaning:

DRAFT

Request has been created but not issued.

OPEN

Request has been issued and awaits a response.

ACKNOWLEDGED

Recipient has acknowledged receipt.

FULFILLED

Requested evidence has been submitted and linked successfully.

PARTIALLY_FULFILLED

Some requested material was supplied but the request remains incomplete.

DECLINED

Recipient explicitly declined.

EXPIRED

Due date passed without fulfillment.

CANCELLED

Authorized workflow action cancelled the request.

10. State Machine

Implement explicit transition validation.

Recommended transitions:

DRAFT
  ↓
OPEN
  ↓
ACKNOWLEDGED
  ↓
FULFILLED

ACKNOWLEDGED
  ↓
PARTIALLY_FULFILLED
  ↓
FULFILLED

OPEN
  ↓
DECLINED

ACKNOWLEDGED
  ↓
DECLINED

OPEN
  ↓
EXPIRED

ACKNOWLEDGED
  ↓
EXPIRED

DRAFT → CANCELLED
OPEN → CANCELLED
ACKNOWLEDGED → CANCELLED
PARTIALLY_FULFILLED → CANCELLED

Invalid transitions must:

return a structured error;
leave the database unchanged;
create no event.
11. Request History

Create:

evidence_request_events

This is workflow history.

Fields:

id
request_id
event_type
from_status
to_status
actor_id
metadata
created_at

Events should include:

REQUEST_CREATED
REQUEST_ISSUED
REQUEST_ACKNOWLEDGED
EVIDENCE_LINKED
PARTIAL_FULFILLMENT
FULFILLED
DECLINED
EXPIRED
CANCELLED

History must be append-only.

Do not overwrite historical events.

This is not the future cryptographic audit ledger.

12. Requested Evidence Links

A request may require more than one evidence item.

Do not model this as a single evidence_id.

Create:

evidence_request_items

Fields:

id
request_id
evidence_id
item_status
linked_at
linked_by
notes

Suggested item states:

REQUESTED
RECEIVED
ACCEPTED_FOR_REQUEST
REJECTED_FOR_REQUEST

Important:

ACCEPTED_FOR_REQUEST means the evidence fulfills the request item operationally.

It does not mean the evidence is truthful or authentic.

13. Multiple Evidence Items

One request may be fulfilled by multiple evidence items:

Evidence Request
    ├── Evidence A
    ├── Evidence B
    └── Evidence C

A single evidence item may also be linked to multiple requests where appropriate.

Therefore:

Evidence ↔ Evidence Request

is many-to-many.

Do not impose a one-to-one relationship.

14. Evidence Provenance

When evidence is linked to a request, preserve request provenance.

The system must be able to answer:

Why was this evidence submitted?

At minimum, the evidence-request link must preserve:

request ID;
request item ID;
actor;
timestamp.

Do not modify the immutable original evidence provenance.

Instead, represent the request relationship separately.

15. Existing Evidence Pipeline Integration

BE-014 must use the existing evidence ingestion APIs/services.

Conceptually:

POST evidence
      ↓
BE-003 validation
      ↓
BE-004 fingerprint
      ↓
BE-005 async processing
      ↓
BE-006 duplicate intelligence
      ↓
BE-008 temporal intelligence
      ↓
BE-009 vision
      ↓
BE-010 graph
      ↓
BE-011 fusion

BE-014 must not create a second upload pipeline.

16. Linking Existing Evidence

A request should support linking an already-existing evidence item where authorized.

Example:

POST /api/v1/evidence-requests/{request_id}/evidence/{evidence_id}

Before linking:

evidence must exist;
request must exist;
project/scope consistency must be checked;
request must be in a linkable state;
duplicate links must be prevented.

Do not copy evidence files.

17. New Evidence Submission

For V1, support linking newly created evidence through an explicit workflow.

The implementation may expose:

POST /api/v1/evidence-requests/{request_id}/submissions

The endpoint must use the existing evidence creation service.

It must not implement a parallel storage or validation mechanism.

If the existing upload endpoint already supports the necessary provenance/context mechanism, reuse that service rather than duplicating the upload logic.

18. Request Scope Validation

A request may reference:

Project
Activity
Claim
Evidence
Review Case

Scope consistency must be enforced.

Examples:

request.project_id = Project A
request.claim_id → Claim belonging to Project A

Valid.

But:

request.project_id = Project A
request.claim_id → Claim belonging to Project B

must be rejected.

Similarly, if a request is linked to a Review Case:

case.project_id

must be consistent with:

request.project_id

No silent cross-project association.

19. Review Case Integration

A Review Case may have multiple evidence requests.

Therefore:

Review Case
    ├── Evidence Request 1
    ├── Evidence Request 2
    └── Evidence Request 3

Add:

review_case_id

to the request.

The case must not automatically change state when a request is created.

For example:

OPEN
+
request created
=
OPEN

not:

INVESTIGATING

unless an explicit human workflow action performs that transition.

20. Case Resolution Interaction

A case must not be automatically resolved because all evidence requests are fulfilled.

Likewise:

all requests fulfilled

must not automatically create a decision.

The human reviewer remains responsible for deciding the case.

21. Expiration

Implement deterministic expiration handling.

A request becomes eligible for expiration when:

status ∈ {OPEN, ACKNOWLEDGED}
AND due_at < current_time

Expiration must not happen merely because a request was created long ago if no due_at exists.

V1 may expose an explicit endpoint:

POST /api/v1/evidence-requests/{request_id}/expire

or an internal service method.

If a background scheduler is not yet part of the architecture, do not introduce one solely for BE-014.

Explicit expiration is acceptable for V1.

22. Partial Fulfillment

If a request contains multiple request items:

2 of 3 items received

the request should become:

PARTIALLY_FULFILLED

rather than FULFILLED.

When all required items are fulfilled:

FULFILLED

The calculation must be deterministic.

Do not treat rejected request items as fulfilled.

23. Required vs Optional Items

evidence_request_items should include:

required

Boolean.

Example:

Item A → required
Item B → required
Item C → optional

Request fulfillment requires all required items to reach an acceptable fulfillment state.

Optional items do not block fulfillment.

24. Item Status

Suggested transitions:

REQUESTED
    ↓
RECEIVED
    ↓
ACCEPTED_FOR_REQUEST

RECEIVED
    ↓
REJECTED_FOR_REQUEST

A rejected evidence item remains a valid evidence object.

Its rejection means only:

It did not satisfy this particular request item.

It does not imply fraud or invalidity of the evidence globally.

25. Request Completion Rules

A request becomes FULFILLED when:

all required request items
have at least one
ACCEPTED_FOR_REQUEST evidence link

A request becomes PARTIALLY_FULFILLED when:

at least one item is fulfilled
but at least one required item remains unresolved

A request with no fulfilled items remains:

OPEN / ACKNOWLEDGED

unless another lifecycle action occurs.

26. Request Configuration

Do not create a complex policy engine.

The request itself stores its:

priority;
due date;
instructions;
required items.

Future notification scheduling may use these fields.

BE-014 does not implement notification policy.

27. API

Create:

Create request
POST /api/v1/evidence-requests

Required:

review case;
recipient;
instructions;
at least one request item.

Optional:

due date;
priority;
project/activity/claim/evidence scope.
Get request
GET /api/v1/evidence-requests/{request_id}
List requests
GET /api/v1/evidence-requests

Filters:

project_id
review_case_id
status
priority
requester_id
recipient_id
due_before
due_after

Use deterministic pagination.

Request history
GET /api/v1/evidence-requests/{request_id}/history
Acknowledge
POST /api/v1/evidence-requests/{request_id}/acknowledge
Link existing evidence
POST /api/v1/evidence-requests/{request_id}/evidence/{evidence_id}
Submit evidence
POST /api/v1/evidence-requests/{request_id}/submissions

Must reuse the existing evidence ingestion service.

Decline
POST /api/v1/evidence-requests/{request_id}/decline

Required:

reason
Cancel
POST /api/v1/evidence-requests/{request_id}/cancel
Expire
POST /api/v1/evidence-requests/{request_id}/expire
28. Schemas

Create:

backend/schemas/evidence_request.py

Include:

EvidenceRequestCreate
EvidenceRequestResponse
EvidenceRequestListResponse
EvidenceRequestItemCreate
EvidenceRequestItemResponse
EvidenceRequestHistoryResponse
EvidenceRequestDeclineRequest
EvidenceRequestResponseAction
EvidenceRequestLinkResponse

Use strict enums.

Reject invalid lifecycle/item states.

29. Service Layer

Create:

backend/services/evidence_request.py

Responsibilities:

request creation;
scope validation;
item creation;
lifecycle transitions;
evidence linking;
fulfillment calculation;
expiration;
decline/cancel;
history;
request provenance;
integration with existing evidence service.

The service must not contain:

fusion logic;
scoring;
vision inference;
duplicate detection;
temporal analysis;
geospatial calculations;
LLM calls.
30. Repository Layer

Create:

backend/repositories/evidence_request.py

Responsibilities:

request CRUD;
item CRUD;
event persistence;
deterministic list queries;
evidence-link lookup;
duplicate-link prevention;
lifecycle-safe queries.
31. Database Models

Modify:

backend/db/models.py

Add:

EvidenceRequest
EvidenceRequestItem
EvidenceRequestEvent

Use deliberate FK behavior.

Historical request data must not disappear merely because an upstream object changes state.

Do not cascade-delete request history.

32. Migration

Create:

alembic/versions/g7b8c9d0e014_be014_evidence_requests.py

Parent:

f6a7b8c9d013

Requirements:

single Alembic head;
upgrade verified live;
downgrade verified live;
indexes;
CHECK constraints;
FK constraints;
uniqueness constraints.
33. Suggested Indexes

At minimum:

evidence_requests(project_id)
evidence_requests(review_case_id)
evidence_requests(status)
evidence_requests(priority)
evidence_requests(requester_id)
evidence_requests(recipient_id)
evidence_requests(due_at)

evidence_request_items(request_id)
evidence_request_items(evidence_id)

evidence_request_events(request_id, created_at)

Prevent duplicate request-item/evidence links with a database constraint.

34. Concurrency

Concurrent evidence linking must be safe.

Example:

10 concurrent
POST /evidence-requests/{id}/evidence/{same_evidence}

Expected:

1 link
9 idempotent/existing responses

Database uniqueness must enforce this.

Do not rely on Python locks.

35. Idempotency

Repeated lifecycle actions must behave deterministically.

Examples:

ACKNOWLEDGED → ACKNOWLEDGED

must not generate ten acknowledgement events.

Repeated evidence linking must not create duplicate link rows.

Repeated fulfillment processing must not duplicate events.

36. Request History Semantics

Every meaningful state transition creates exactly one event.

Example:

OPEN
 ↓
ACKNOWLEDGED

creates:

REQUEST_ACKNOWLEDGED

An invalid transition creates:

no event

and:

no database mutation
37. Provenance Requirements

For each linked evidence item, retain:

request_id
request_item_id
linked_by
linked_at

If evidence was uploaded specifically through a request, the request relationship must be recoverable later.

Do not modify original evidence timestamps.

The system must continue preserving:

capture timestamp;
upload timestamp;
ingestion timestamp;
processing timestamp;

according to the existing architecture.

38. Cross-Project Safety

Test:

Request Project A
+
Evidence Project B

must be rejected when scope is incompatible.

Likewise:

Review Case Project A
+
Request Project B

must be rejected.

No request may be used to bypass existing project boundaries.

Do not add RBAC.

39. Integration With BE-011 / BE-012 / BE-013

BE-014 should expose enough lineage for:

Evidence Request
    ↓
Review Case
    ↓
Fusion Run
    ↓
Explanation

but it must not modify:

fusion results;
assessments;
review priorities;
explanations.

If new evidence later triggers analysis, that creates new analytical runs according to existing architecture.

BE-014 does not mutate historical analytical runs.

40. Tests

Create:

tests/unit/test_evidence_request.py
tests/integration/test_evidence_request.py
Unit tests

At minimum:

request creation;
required fields;
priority validation;
lifecycle validation;
scope validation;
case/project consistency;
item creation;
required/optional item semantics;
acknowledgement;
decline;
cancellation;
expiration;
partial fulfillment;
complete fulfillment;
invalid transitions;
duplicate evidence link;
idempotent linking;
decision/case independence;
request does not create analytical judgments;
timezone-aware due dates.
41. Integration Tests

Use real PostgreSQL.

Test:

Creation
POST request
→ request persisted
→ items persisted
→ OPEN/DRAFT state correct
Lifecycle

Verify:

OPEN
→ ACKNOWLEDGED
→ PARTIALLY_FULFILLED
→ FULFILLED
Decline

Verify:

OPEN
→ DECLINED
Expiration

Verify:

OPEN + past due_at
→ EXPIRED
Cancellation

Verify cancellation rules.

Evidence linking

Verify:

request
→ evidence
→ request item
Existing evidence

Verify an existing evidence object can be linked without copying its file.

New evidence

Verify request submission uses the existing evidence ingestion path.

Duplicate links

Verify database uniqueness.

Concurrent links

Run multiple concurrent requests and verify exactly one link.

Scope isolation

Verify cross-project evidence cannot be linked.

History

Verify every valid transition creates exactly one event.

Invalid transitions

Verify:

no mutation
no event
Case lineage

Verify:

request
→ case
→ fusion
→ explanation
42. Full Regression

Required:

pytest

Expected:

0 failed

Run:

alembic upgrade head

Then downgrade to the previous revision and upgrade again.

Verify:

single Alembic head

No existing BE-001 → BE-013 tests may regress.

43. Runtime Verification

Verify against the actual stack:

PostgreSQL
PostGIS
Redis
MinIO
FastAPI

Verify:

request creation;
lifecycle transitions;
evidence linking;
evidence submission;
duplicate protection;
concurrent linking;
history;
expiration;
filters;
pagination.

Mock-only verification is insufficient.

44. Performance

Measure live:

Request creation

At least:

n >= 20

Report:

average;
minimum;
maximum;
database time if separately measured.
Evidence linking

Measure at least:

n >= 20
Concurrent duplicate-link test

Use 10 concurrent requests.

Do not invent numbers.

45. Data Integrity Checks

After integration testing verify:

0 orphaned evidence requests
0 orphaned request items
0 orphaned request events
0 invalid request states
0 invalid item states
0 duplicate evidence-request links
0 invalid cross-project links
0 request events without valid requests

Also verify:

FULFILLED

requests actually satisfy all required items.

Verify:

PARTIALLY_FULFILLED

requests have fulfilled evidence but unresolved required items.

46. Anti-Shortcut Gates

BE-014 is not complete if it:

creates a second evidence-upload implementation;
bypasses BE-003 validation;
bypasses quarantine/trusted storage;
marks requested evidence as automatically trusted;
treats fulfillment as proof;
treats non-fulfillment as contradiction;
creates fusion scores;
changes integrity assessments;
changes review priority;
automatically resolves review cases;
automatically creates human decisions;
invokes an LLM;
adds ML;
adds fraud/deepfake/authenticity detection;
adds RBAC;
adds authentication;
adds notifications;
adds chat;
creates an audit ledger;
modifies completed BE-001 → BE-013 analytical semantics;
relies only on Python for uniqueness;
deletes request history.
47. Explicit Non-Goals

BE-014 does not implement:

reviewer dashboard;
supervisor dashboard;
citizen portal;
email;
SMS;
push notifications;
chat;
notification scheduler;
RBAC;
authentication;
organization authorization;
offline PWA;
ML;
LLM;
fraud detection;
authenticity detection;
deepfake detection;
new fusion signals;
new scoring;
analytics;
audit ledger;
public publication.
48. Required Files
Create
backend/services/evidence_request.py
backend/repositories/evidence_request.py
backend/schemas/evidence_request.py
backend/api/v1/endpoints/evidence_request.py

alembic/versions/g7b8c9d0e014_be014_evidence_requests.py

tests/unit/test_evidence_request.py
tests/integration/test_evidence_request.py
Modify
backend/db/models.py
backend/api/v1/router.py
Delete
none
49. Completion Contract

BE-014 is complete only when:

Evidence Request is a first-class domain object.
Requests have explicit lifecycle states.
Request items support multiple evidence objects.
Required and optional items are supported.
Request history is append-only.
Existing evidence can be linked.
New evidence uses the existing ingestion pipeline.
Evidence request provenance is preserved.
Cross-project scope violations are rejected.
Duplicate evidence links are database-protected.
Concurrent duplicate linking is safe.
Fulfillment is deterministic.
Partial fulfillment is supported.
Expiration is deterministic.
Decline/cancel behavior is explicit.
Request creation does not create analytical judgments.
Fulfillment does not automatically resolve a case.
Fulfillment does not automatically create a human decision.
BE-011 outputs remain unchanged.
BE-012 explanations remain unchanged.
BE-013 case lifecycle remains unchanged except for explicit human actions.
Alembic upgrade/downgrade succeeds.
Unit tests pass.
Integration tests pass against real PostgreSQL.
Full regression passes.
Runtime API verification succeeds.
Data integrity checks pass.
No BE-015+ scope has leaked into the implementation.
Git history remains untouched except for the final BE-014 commit.
50. Recommended Commit
BE-014: implement evidence request workflow
Final Architectural Boundary

BE-011 calculates intelligence. BE-012 explains intelligence. BE-013 creates human-review cases. BE-014 creates auditable requests for additional evidence within those investigations. Requested evidence enters the existing evidence pipeline and remains subject to the same validation, provenance, and analytical rules as every other evidence item.