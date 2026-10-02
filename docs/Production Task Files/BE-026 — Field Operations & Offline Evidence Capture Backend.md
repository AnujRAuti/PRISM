BE-026 — Field Operations & Offline Evidence Capture Backend
Mission

Implement and fully verify BE-026: Field Operations & Offline Evidence Capture for Proof-of-Action.

The objective is to establish the backend foundation required for field officers to execute assigned activities, capture evidence while offline, and synchronize that work safely when connectivity returns.

This milestone must implement the backend/API/domain side only.

Do not build the frontend/PWA in BE-026.

The backend must support:

Assignment
→ Field Activity
→ Offline Capture
→ Local Client Identity
→ Deferred Synchronization
→ Server Validation
→ Evidence Ingestion
→ Provenance Preservation
→ Conflict Handling
→ Idempotent Completion
→ Audit

The existing Evidence pipeline remains authoritative.

Do not create a second evidence-ingestion system.

1. Non-negotiable operating rules
Reconnaissance before implementation.
Do not modify production code during reconnaissance.
Read the locked architecture and existing implementation before designing.
Reuse existing Project, Activity, Claim, Evidence, authorization, audit, storage, notification, and idempotency infrastructure.
Do not redesign existing authorization.
Backend authorization is authoritative.
Never trust client-provided authorization claims.
Never silently fall back to unrestricted access.
Preserve organization/project/activity assignment boundaries.
Preserve evidence immutability.
Preserve original evidence bytes and cryptographic identity.
Preserve capture time, queue time, upload time, and server processing time separately.
Never invent missing GPS or timestamps.
Missing GPS/time must remain explicitly unknown where appropriate.
Offline synchronization must be idempotent.
Duplicate synchronization must not create duplicate evidence.
Conflicts must be explicit and auditable.
Do not silently overwrite conflicting server state.
Audit ledger remains append-only and tamper-evident.
Never delete, truncate, or update audit ledger records.
Preserve the BE-023 audit guard.
Use TEST_DATABASE_URL.
Never fall back to pofa_dev.
Python 3.12 remains authoritative.
No new AI/ML functionality.
No fake offline behavior.
No frontend/PWA implementation.
No native mobile implementation.
No unrelated BE-024/BE-025 cleanup.
No destructive Git operations.
No force push.
Never use git add . or git add -A.
2. Locked architecture requirements

The architecture defines offline field operation as:

PWA offline-first for assigned work
sync assignments
capture GPS/time
capture notes
local validation
secure local queue
deferred synchronization
stable client IDs
idempotent sync
preservation of:
capture timestamp
queue timestamp
upload timestamp
server timestamp
explicit conflict handling

BE-026 must implement the backend contracts required to support those semantics.

Do not implement the browser's IndexedDB/local encryption/offline UI in this milestone.

3. Stage A — Reconnaissance

Before writing production code, inspect:

Existing domain
Project
Activity
Claim
Evidence
Evidence metadata
Evidence provenance
assignments
users
roles
organizations
organizational units
Existing APIs

Inspect all relevant:

project endpoints
activity endpoints
claim endpoints
evidence endpoints
upload endpoints
analysis/job endpoints
audit endpoints
notification endpoints
authorization endpoints
Existing infrastructure

Inspect:

Principal
require()
require_target()
idempotency implementation
audit service
storage service
evidence ingestion service
analysis jobs
Redis
database transactions
request IDs
error handling
Existing tests

Search for:

activity assignment
evidence ownership
duplicate uploads
idempotency
authorization
audit
timestamps
GPS/location
offline
synchronization
conflict handling

Determine whether any offline/sync functionality already exists.

Produce:

docs/BE-026 Stage A Reconnaissance.md

Include:

existing field/activity model
existing assignment model
existing evidence pipeline
existing provenance capabilities
existing idempotency mechanisms
existing audit mechanisms
missing backend capabilities
required schema changes
required APIs
security risks
testing gaps
proposed implementation plan
explicit out-of-scope items

STOP after Stage A.

Do not implement yet.

4. Stage B — Domain and synchronization design

After reconnaissance approval, design the minimum backend model necessary for offline field synchronization.

The design must answer:

What is a field session?

A field session should represent an authorized field officer's execution context for assigned work.

It must remain associated with:

user
organization
project
activity
assignment

where applicable.

What is an offline capture?

An offline capture represents a client-generated capture that may later become a canonical Evidence record.

It must have a stable client-generated identity.

Do not use timestamps alone as identifiers.

What is synchronization?

Synchronization must be idempotent.

The same client operation submitted repeatedly must produce the same logical server outcome.

What is a conflict?

A conflict must represent an actual incompatible state transition.

Examples:

assignment revoked while device was offline
activity closed while offline work was captured
evidence client ID already exists with different payload identity
conflicting metadata update
synchronization against superseded state

Do not classify ordinary duplicate requests as conflicts.

5. Client identity

Every offline operation must have a stable client-generated identifier.

At minimum support:

client_id
client_operation_id

Where appropriate preserve:

device/session identifier
client-generated capture identifier

The backend must never generate a new logical operation merely because the same client operation was retried.

6. Timestamp semantics

Do not collapse timestamps.

Preserve separate timestamps where available:

Capture timestamp

When the evidence was actually captured on the field device.

Queue timestamp

When the client placed the capture into its offline synchronization queue.

Upload timestamp

When the client successfully transmitted the payload.

Server ingestion timestamp

When PoA received the operation.

Processing timestamp

When backend processing occurred.

Domain event timestamp

When the corresponding domain action occurred.

Known timestamps must be normalized appropriately.

Unknown timestamps must remain unknown.

Never fabricate a timestamp from another timestamp merely to fill a field.

7. GPS semantics

Field capture may contain:

latitude
longitude
capture accuracy
altitude where supported
source timestamp

Preserve the source information.

Do not silently treat missing GPS as zero coordinates.

Do not treat GPS presence as proof of evidence truth.

Do not automatically reject evidence solely because GPS is unavailable unless an existing activity policy explicitly requires it.

Existing PostGIS semantics remain authoritative.

8. Assignment enforcement

A field officer must only synchronize field work they were authorized to perform.

Verify:

user is authenticated
user belongs to correct organization
user is assigned to activity/project as required
assignment is active
assignment has not expired/revoked
activity is valid
project is valid

An offline client must not gain authority merely because it possesses an old assignment snapshot.

At synchronization time, the backend must re-evaluate current authorization.

9. Evidence ingestion integration

Do not bypass BE-003.

Offline synchronization must ultimately reuse the existing evidence ingestion/storage pipeline.

Conceptually:

Offline capture
→ sync request
→ authorization
→ idempotency
→ validation
→ existing evidence ingestion
→ quarantine
→ validation
→ trusted storage
→ fingerprinting
→ analysis

Do not create a second upload validator.

Do not create a second SHA-256 implementation.

Do not create a second EXIF parser.

Do not create a second pHash implementation.

Reuse existing services.

10. Idempotent synchronization

This is a core BE-026 requirement.

Test:

First synchronization

Client operation does not exist.

→ operation executes.

Exact retry

Same client operation submitted again.

→ no duplicate operation/evidence.

Retry after timeout

Client does not know whether server completed.

→ same logical result is returned/recovered.

Same client ID, different payload

→ deterministic conflict.

Never silently accept a different payload under an existing client operation identity.

11. Synchronization response

The API must provide a deterministic synchronization result.

Where appropriate distinguish:

accepted
already synchronized
rejected
conflict
authorization denied
validation failed
temporarily unavailable

Do not collapse all failures into HTTP 500.

Do not expose internal stack traces.

Use the project's existing structured error conventions.

12. Conflict handling

Conflicts must be first-class and auditable.

A conflict should preserve enough information to explain:

client operation
affected resource
server state
reason
timestamp
actor/client
resolution status

Do not silently overwrite server state.

Do not automatically choose client state over server state.

Do not automatically choose server state over client state when the conflict requires human resolution.

Where deterministic resolution is safe, document the rule.

13. Offline assignment synchronization

Provide an API allowing an authorized field client to retrieve the current assigned work necessary for offline operation.

The returned data must be authorization-filtered.

Do not expose:

unrelated projects
unrelated activities
internal intelligence
unauthorized claims
other users' private evidence
administrative/security information

The client must receive enough information to perform assigned field work but no more.

14. Security requirements

Explicitly test:

Field Officer

Can:

retrieve assigned field work
synchronize their authorized captures
access permitted activity context

Cannot:

synchronize another officer's assignment
modify another organization's work
create unauthorized assignments
submit evidence against unauthorized projects
access reviewer/admin intelligence
Reviewer

Must retain existing reviewer semantics.

Supervisor

Must retain existing supervisor semantics.

Administrator

Must retain existing administrative semantics.

Citizen

Must not gain field-officer synchronization authority.

API Client

Must require explicit appropriate scopes.

Unauthenticated

Must be rejected.

15. Offline evidence provenance

Offline synchronization must preserve provenance showing that the evidence originated from a field capture workflow.

Where available preserve:

capture source
client identity
field session
activity
user
device/session metadata
capture timestamp
queue timestamp
upload timestamp
server ingestion timestamp
transformations

Provenance is not truth.

Do not convert successful synchronization into an authenticity claim.

16. Audit requirements

Audit all security-sensitive synchronization operations.

At minimum cover:

field session creation/activation where applicable
offline sync accepted
duplicate sync
sync rejection
conflict
evidence association
assignment access
assignment-related security failures

Do not place:

raw image bytes
secrets
access tokens
credentials

into the audit ledger.

After synchronization tests, verify the audit chain.

17. API requirements

Use existing:

/api/v1

REST conventions.

Possible API areas, subject to reconnaissance:

/api/v1/field/assignments
/api/v1/field/sessions
/api/v1/field/sync

These are examples only.

Do not blindly create these paths if existing conventions provide a better location.

The actual API design must come from reconnaissance.

OpenAPI must accurately describe:

authentication
authorization
request schemas
response schemas
conflict responses
validation errors
pagination
idempotency requirements
18. Pagination

Any assignment/list endpoint must have bounded pagination.

Verify:

stable ordering
maximum page size
authorization filtering
no cross-organization leakage
no unauthorized count leakage
deterministic results
19. Database and migration requirements

Only introduce a migration if required.

Before creating one:

inspect current schema
inspect existing assignment structures
inspect existing evidence metadata/provenance
inspect existing idempotency tables
inspect existing audit relationships
determine whether existing tables can support BE-026

Do not duplicate existing concepts.

If migration is necessary:

linear Alembic migration
upgrade verified
downgrade verified where applicable
from-scratch migration verified
existing database upgrade verified
no historical migration modification
20. Testing requirements

Create a focused BE-026 suite.

Assignment
authorized assignment retrieval
unauthorized assignment retrieval
cross-org denial
revoked assignment
expired assignment
pagination
Offline capture
valid capture
malformed capture
missing optional GPS
valid GPS
missing timestamp
known timestamp preservation
multiple timestamps preserved
Synchronization
first sync
exact duplicate
retry after timeout simulation
same operation ID with different payload
concurrent sync
partial failure
retry after failure
Evidence
existing ingestion pipeline reused
SHA-256 preserved
storage state correct
evidence relationship correct
no duplicate evidence
Authorization
field officer
reviewer
supervisor
administrator
citizen
API client
unauthenticated
Conflict
assignment revoked offline
activity state changed offline
duplicate client identity
payload mismatch
explicit conflict result
Audit
expected events
correct actor
correct resource
chain valid
no sensitive data leakage
21. Stage C — Implementation

After Stage A/B approval:

Implement the minimum required backend changes.

Potential categories:

domain models
synchronization service
schemas
APIs
provenance
conflict handling
authorization integration
audit events
migration
tests

Do not implement frontend.

Do not implement browser storage.

Do not implement native mobile.

Do not add ML.

Do not redesign Evidence.

Do not redesign Authorization.

Do not redesign Audit.

22. Stage D — Runtime verification

Use:

TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test

Verify against real:

PostgreSQL
PostGIS
pgvector
Redis
MinIO
Python 3.12

Run real HTTP/API tests.

Verify the complete path:

Assigned Activity
→ Field Session
→ Offline Capture Representation
→ Synchronization
→ Evidence Ingestion
→ Evidence Association
→ Provenance
→ Audit

Do not claim end-to-end success based only on unit tests.

Produce:

docs/BE-026 Stage D Runtime Results.md

Record exact commands/results.

23. Stage E — Hardening

Test:

duplicate synchronization
concurrent synchronization
timeout/retry
conflicting client payload
revoked assignment
expired assignment
activity closure
malformed IDs
malformed payloads
oversized evidence
missing GPS
missing timestamp
database outage
Redis outage where applicable
MinIO outage
partial evidence-ingestion failure
rollback
authorization bypass attempts
cross-organization access
audit integrity

Do not fake unavailable dependency tests.

Restore infrastructure after fault injection.

24. Stage F — Full verification

Run:

BE-026 targeted tests
affected integration tests
full unit suite
full integration suite
migration verification
from-scratch migration
BE-023 preflight
authorization regression
audit-chain verification
repeated/idempotency verification

The existing baseline should remain intact.

Expected:

no unexplained failures
no authorization regression
no duplicate evidence
no audit corruption
no migration drift
no pofa_dev contamination
25. Documentation

Create:

docs/BE-026 Stage A Reconnaissance.md

docs/BE-026 Stage B Design.md

docs/BE-026 Stage C Implementation Summary.md

docs/BE-026 Stage D Runtime Results.md

docs/BE-026 Stage E Hardening Results.md

docs/BE-026 Final Acceptance Report.md

Preserve all historical findings.

Use:

FOUND → FIXED → VERIFIED

Do not rewrite previous defects out of history.

26. BE-025 regression protection

BE-026 must not regress:

organization administration
role assignment
project ownership
project/team assignment
API client authorization
audit
publication authorization
dispute authorization
retention governance
evidence ingestion
existing idempotency

Run the existing BE-025-related tests.

If a regression appears:

STOP → CLASSIFY → REPORT.

Do not weaken existing tests.

27. Known existing findings

Do not silently fix unrelated findings from previous milestones.

In particular, preserve:

DF-SD-02
DF-SE-01
DF-SE-02
P15 publication-test fixture leak
MinIO host restart environmental issue

If BE-026 is genuinely affected by one of them, document the dependency rather than quietly modifying unrelated code.

28. Scope exclusions

Explicitly out of scope:

PWA frontend
IndexedDB implementation
browser offline UI
native Android/iOS
push notifications
SMS
chat
new ML models
fraud detection
authenticity detection
deepfake detection
OCR
face recognition
Evidence Graph redesign
Fusion redesign
Review Case redesign
Publication redesign
Organization/RBAC redesign
OIDC implementation
cloud migration
Kubernetes
fixing unrelated BE-024/BE-025 findings
29. Final acceptance gate

BE-026 may only be declared:

PASS / ACCEPTED

when all of the following are verified:

reconnaissance completed
design completed
implementation completed
assigned field work authorization verified
offline operation contract verified
stable client IDs verified
idempotent synchronization verified
duplicate synchronization verified
conflicting payload behavior verified
evidence pipeline reused
provenance preserved
timestamps preserved correctly
GPS semantics verified
authorization boundaries verified
organization isolation verified
audit events verified
audit chain valid
concurrency verified
retry behavior verified
partial failures verified
migration verified
full unit suite passes
full integration suite passes
BE-025 regression passes
BE-023 isolation remains intact
final Git state intentional and synchronized

If any requirement fails, do not claim PASS.

FIRST ACTION — DO NOT IMPLEMENT

Start with Stage A reconnaissance only.

Do not write production code.

Do not create migrations.

Do not create APIs.

Do not commit anything.

Return exactly:

Existing field/activity architecture
Existing assignment architecture
Existing evidence/provenance capabilities
Existing idempotency infrastructure
Existing authorization mechanisms
Existing audit mechanisms
Existing offline/sync functionality, if any
Missing capabilities
Required schema changes
Required APIs
Security risks
Testing gaps
Proposed BE-026 implementation plan
Explicit out-of-scope confirmation
Whether a migration is actually required

STOP after Stage A. Wait for approval before implementing anything.