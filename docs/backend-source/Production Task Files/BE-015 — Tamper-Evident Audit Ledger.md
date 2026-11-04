BE-015 — Tamper-Evident Audit Ledger

Production Task File
Milestone: BE-015
Status: Ready for implementation
Depends on: BE-001 → BE-014
Primary dependencies: BE-013 Review Cases, BE-014 Evidence Requests, existing domain models
Recommended commit: BE-015: implement tamper-evident audit ledger

1. Objective

Implement the dedicated append-only, tamper-evident audit ledger defined by the frozen architecture.

The audit ledger records security- and governance-relevant actions across the system and provides cryptographic continuity between audit events.

The architectural distinction is critical:

Domain history
    ↓
BE-013 Review Case Events
BE-014 Evidence Request Events
etc.

Audit Ledger
    ↓
independent tamper-evident record

Workflow history answers:

What happened to this particular domain object?

The audit ledger answers:

What security/governance-relevant action occurred, who performed it, when did it occur, and can the historical sequence be shown to have been altered?

2. Architectural Boundary

BE-015 introduces the dedicated audit ledger.

It must:

be append-only;
preserve event ordering;
record actor/action/resource context;
contain cryptographic chaining;
detect modification/removal/reordering;
preserve historical event payloads;
be independent from ordinary domain history;
support verification.

It must not become:

a replacement for domain history;
a general event-sourcing system;
a message queue;
an analytics database;
an authorization system;
an authentication system.
3. Core Principle

The audit ledger records actions and security-relevant events.

It does not determine whether the underlying action was substantively correct.

For example:

AUDIT:
Reviewer X recorded decision Y on Case Z.

does not mean:

Decision Y is correct.

Similarly:

AUDIT:
Evidence A was uploaded.

does not mean:

Evidence A is authentic.
4. Audit Event Model

Create:

audit_events

Minimum fields:

Identity
id
UUID primary key
monotonically ordered database identifier or equivalent ordering field
Event identity
event_type
action
resource_type
resource_id
Actor
actor_id
nullable for explicitly system-generated events
Scope
organization_id if the existing architecture supports it
project_id where applicable

Do not introduce the full Organization model merely for BE-015 if it does not yet exist.

5. Event Payload

Store:

payload
metadata

Use JSONB.

The payload must contain structured facts relevant to the event.

Do not store arbitrary sensitive request bodies by default.

Avoid:

passwords;
tokens;
secrets;
raw authentication credentials;
unnecessary PII;
complete evidence contents.
6. Request Context

Where available, preserve:

request ID;
correlation ID;
source/service;
API route;
client type;
IP address if permitted by the privacy model;
user agent if permitted.

Sensitive infrastructure information must not be logged indiscriminately.

7. Timestamp

Each event must contain:

created_at

Use timezone-aware UTC timestamps.

Do not accept arbitrary client-provided timestamps as the authoritative audit timestamp.

The server/database determines the authoritative event time.

8. Hash Chain

Each event must cryptographically reference the previous event.

Suggested fields:

previous_hash
event_hash

Conceptually:

Event N
    previous_hash = hash(Event N-1)
    event_hash = H(canonical(Event N))

The event hash must cover the important immutable fields, including:

event ID;
sequence;
event type;
actor;
resource;
payload;
timestamp;
previous hash.
9. Canonicalization

Hash generation must use deterministic canonical serialization.

Equivalent payloads must generate equivalent canonical representations.

Requirements:

deterministic key ordering;
deterministic encoding;
explicit null handling;
UTF-8;
stable number representation;
stable timestamp representation.

Do not hash Python's default repr().

Do not hash unordered data structures directly.

10. Hash Algorithm

Use a modern cryptographic hash:

SHA-256

Do not implement a custom cryptographic algorithm.

The algorithm/version must be represented in the ledger metadata so future migration can be distinguished.

Example:

hash_algorithm = SHA-256
ledger_version = audit-v1
11. Append-Only Requirement

Once an audit event is created:

UPDATE → forbidden
DELETE → forbidden

through the application layer.

Do not provide an endpoint that edits audit events.

Do not provide an endpoint that deletes audit events.

Historical corrections require a new audit event.

12. Database Protection

Application-level append-only behavior is insufficient.

Use database protections where practical.

The implementation must prevent normal application roles from:

updating audit events;
deleting audit events.

If the current development database role architecture cannot enforce separate database privileges without introducing unrelated infrastructure, document the limitation and ensure the application repository exposes no mutation path.

Do not introduce a large database privilege-management system solely for this milestone.

13. Sequence Ordering

The ledger must provide deterministic ordering.

Use a database-generated sequence or equivalent mechanism.

Recommended:

sequence_number

must be unique and monotonically increasing.

The chain is based on this ordering.

Do not use timestamps alone to establish event order.

14. Concurrency

Concurrent audit writes must remain chain-consistent.

Example:

10 concurrent audit writes
        ↓
10 unique sequence numbers
        ↓
valid chain

The implementation must prevent:

Event A → previous_hash = X
Event B → previous_hash = X

where both are incorrectly treated as consecutive events.

Use an appropriate database transaction/locking strategy.

Do not rely on Python process locks.

15. Audit Writer

Create:

backend/services/audit_ledger.py

Responsibilities:

canonicalize event;
determine sequence;
retrieve previous chain state;
calculate hash;
persist event atomically;
verify event integrity;
expose safe query methods.

The service must not contain domain-specific business decisions.

16. Repository

Create:

backend/repositories/audit_ledger.py

Responsibilities:

append;
fetch;
query;
verify;
retrieve latest sequence;
retrieve chain ranges.

There must be no public repository method for modifying or deleting an existing event.

17. Schemas

Create:

backend/schemas/audit_ledger.py

Include:

AuditEventResponse
AuditEventListResponse
AuditVerificationResponse
AuditVerificationFailure

Do not expose internal database mutation fields unnecessarily.

18. API

Implement:

Get audit event
GET /api/v1/audit/events/{event_id}
List audit events
GET /api/v1/audit/events

Support filters:

event type;
action;
actor;
resource type;
resource ID;
project;
time range;
sequence range.

Pagination must be deterministic.

Verify ledger
GET /api/v1/audit/verify

This must verify:

sequence continuity;
previous-hash continuity;
event hashes;
canonical representation;
expected ordering.

Return a structured result.

Example conceptual response:

{
  "valid": true,
  "checked_events": 150,
  "first_sequence": 1,
  "last_sequence": 150
}

Do not return a political/subjective interpretation; this is a cryptographic integrity result.

19. Verification Range

Support bounded verification:

GET /api/v1/audit/verify?from_sequence=...&to_sequence=...

The implementation must correctly account for the previous event outside the requested range when necessary.

Example:

verify 100–200

must verify that event 100 correctly references event 99.

20. Audit Event Vocabulary

Create an explicit event vocabulary.

Initial events should cover important existing workflows.

Examples:

EVIDENCE_CREATED
EVIDENCE_UPLOADED
EVIDENCE_CONTEXT_UPDATED
EVIDENCE_LOCATION_UPDATED

ANALYSIS_STARTED
ANALYSIS_COMPLETED
ANALYSIS_FAILED

FUSION_RUN_CREATED

EXPLANATION_GENERATED

REVIEW_CASE_CREATED
REVIEW_CASE_ASSIGNED
REVIEW_CASE_DECISION_RECORDED
REVIEW_CASE_ESCALATED
REVIEW_CASE_RESOLVED
REVIEW_CASE_REOPENED

EVIDENCE_REQUEST_CREATED
EVIDENCE_REQUEST_ISSUED
EVIDENCE_REQUEST_ACKNOWLEDGED
EVIDENCE_REQUEST_FULFILLED
EVIDENCE_REQUEST_DECLINED
EVIDENCE_REQUEST_CANCELLED
EVIDENCE_REQUEST_EXPIRED

GRAPH_RELATIONSHIP_CREATED
GRAPH_RELATIONSHIP_INVALIDATED
GRAPH_RELATIONSHIP_SUPERSEDED

The exact vocabulary may be implemented incrementally, but it must be explicit rather than arbitrary strings scattered throughout the code.

21. Integration With Existing Workflows

BE-015 should integrate audit emission into the existing services.

Examples:

Evidence upload
    ↓
domain operation
    ↓
audit event
Review Case decision
    ↓
decision persisted
    ↓
audit event
Evidence Request fulfilled
    ↓
request state changed
    ↓
audit event

Audit failure semantics must be carefully defined.

For security-critical actions, the preferred behavior is:

domain mutation
+
audit event
=
same transaction

where technically possible.

The system must not report a successful audited action if the audit record failed to persist.

22. Transaction Boundary

For database-backed operations:

BEGIN
    domain mutation
    audit event
COMMIT

If the transaction fails:

domain mutation → rollback
audit event → rollback

Do not create an audit event describing an operation that was rolled back.

For asynchronous operations, audit the actual lifecycle event that occurred rather than claiming completion prematurely.

23. Domain History vs Audit History

Do not duplicate entire workflow histories unnecessarily.

For example:

review_case_events

remains responsible for case-specific workflow history.

The audit ledger records the security/governance event:

REVIEW_CASE_DECISION_RECORDED

The audit event may reference the case event ID where useful.

This creates:

Domain Event
    ↕
Audit Event

without making one table replace the other.

24. Audit Provenance

Audit events should preserve enough context to answer:

who;
what;
when;
which resource;
which project/scope;
request/correlation ID;
relevant domain event;
method/version where analytical execution is involved.

For analysis events, include the corresponding:

analysis run ID;
capability;
method;
method version.

Do not copy complete analytical outputs into the audit ledger.

25. Failed Actions

Do not only record successful actions.

Where security/governance relevance warrants it, support:

ACTION_ATTEMPTED
ACTION_REJECTED

Examples:

INVALID_STATE_TRANSITION
UNAUTHORIZED_ACTION
INVALID_UPLOAD

However, BE-015 must not implement authorization itself.

It may record an authorization failure emitted by a future authorization layer.

26. Sensitive Data

Audit events must avoid storing:

passwords;
JWTs;
API keys;
access tokens;
signed object URLs;
raw evidence binaries;
full multipart payloads.

For evidence operations, store identifiers and metadata rather than file contents.

27. Retention Boundary

Do not implement the complete retention engine in BE-015.

The audit ledger must nevertheless be designed so that future retention policies can distinguish audit data from ordinary domain data.

Do not automatically delete audit events.

Any future deletion/archival must be governed by the dedicated retention milestone.

28. External Anchoring

External anchoring is explicitly deferred.

Do not implement:

blockchain;
public timestamping service;
external notarization;
distributed ledger.

BE-015 only creates the internal cryptographic chain.

29. Tests

Create:

tests/unit/test_audit_ledger.py
tests/integration/test_audit_ledger.py
Unit tests

At minimum:

canonical serialization;
deterministic hash;
hash changes when protected fields change;
previous-hash calculation;
sequence validation;
valid chain verification;
broken previous hash detection;
broken event hash detection;
deterministic payload ordering;
timestamp normalization;
sensitive-field filtering;
event schema validation.
30. Integration Tests

Use real PostgreSQL.

Test:

Basic append
event 1
→ valid
Chain
event 1
→ event 2
→ event 3

Verify every event references the correct predecessor.

Verification

Verify complete chain returns:

valid = true
Tampering

Modify an event directly in a controlled test transaction or test fixture.

Verification must detect:

event_hash mismatch

Do not modify production/development data outside the test fixture.

Deletion

Attempt to delete an audit row through the application layer.

It must be unavailable.

Update

Attempt to mutate an existing audit row through the application layer.

It must be unavailable.

Concurrent writes

Run at least:

10 concurrent audit writes

Verify:

unique sequence numbers;
no duplicate sequence;
valid hash chain.
Transaction rollback

Cause the domain operation to fail.

Verify no successful audit event remains for the rolled-back operation.

Workflow integration

Verify representative:

Review Case
Evidence Request
Evidence
Analysis

operations emit appropriate audit events.

31. Integrity Tests

After test execution verify:

0 duplicate sequence numbers
0 chain breaks
0 invalid hashes
0 orphaned resource references where references are required
32. Performance

Measure:

Single append

At least:

n >= 50

Report:

average;
minimum;
maximum.
Verification

Measure:

n >= 100

events.

Report:

total verification time;
average per event.

Do not invent numbers.

33. Migration

Create:

alembic/versions/h8c9d0e1f015_be015_audit_ledger.py

Parent:

g7b8c9d0e014

Requirements:

single Alembic head;
upgrade tested live;
downgrade tested live;
appropriate indexes;
unique sequence constraint;
immutable hash fields;
JSONB payload/metadata.
34. Suggested Indexes

At minimum:

audit_events(sequence_number)
audit_events(created_at)
audit_events(actor_id)
audit_events(event_type)
audit_events(resource_type, resource_id)
audit_events(project_id)
audit_events(request_id)

The exact indexes should follow measured/query requirements rather than indiscriminately indexing every column.

35. Explicit Non-Goals

BE-015 does not implement:

authentication;
RBAC;
authorization;
Organization model;
retention engine;
external anchoring;
blockchain;
notifications;
dashboards;
analytics;
ML;
LLM;
fraud detection;
authenticity detection;
deepfake detection;
new fusion logic;
reviewer workflow;
citizen workflow.
36. Anti-Shortcut Gates

BE-015 is not complete if it:

uses timestamps as the chain;
hashes non-canonical data;
allows existing audit events to be updated;
allows existing audit events to be deleted;
relies only on application code for sequence uniqueness;
uses Python locks for concurrency;
replaces domain history;
stores raw evidence;
stores passwords/tokens/secrets;
automatically determines substantive decisions;
introduces blockchain;
introduces a new event-sourcing architecture;
implements authentication/RBAC;
modifies BE-001 → BE-014 semantics unnecessarily.
37. Required Files
Create
backend/services/audit_ledger.py
backend/repositories/audit_ledger.py
backend/schemas/audit_ledger.py
backend/api/v1/endpoints/audit_ledger.py

alembic/versions/h8c9d0e1f015_be015_audit_ledger.py

tests/unit/test_audit_ledger.py
tests/integration/test_audit_ledger.py
Modify
backend/db/models.py
backend/api/v1/router.py

Plus the minimal existing service integrations required to emit audit events.

Delete
none
38. Completion Contract

BE-015 is complete only when:

audit events are append-only;
sequence ordering is deterministic;
SHA-256 hash chaining works;
canonical serialization is deterministic;
concurrent writes produce a valid chain;
verification detects tampering;
normal application code cannot mutate/delete existing audit events;
relevant BE-013/BE-014/domain actions emit audit events;
domain history remains separate;
audit events do not contain secrets or raw evidence;
transaction boundaries do not produce false successful audit records;
external anchoring is not introduced;
retention is not prematurely implemented;
Alembic upgrade/downgrade succeeds;
unit tests pass;
integration tests pass against real PostgreSQL;
full regression passes;
runtime API verification succeeds;
performance is measured rather than invented;
no BE-016+ scope leaks into the implementation.
39. Final Architectural Boundary

BE-013 records human-review workflow. BE-014 records requests for additional evidence. BE-015 records security/governance-relevant actions in an independent tamper-evident ledger. The audit ledger records what happened; it does not determine whether the underlying action or evidence was substantively correct.