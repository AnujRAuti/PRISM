# BE-019 — External Integrations & API Client Platform

## Status

PLANNED

## Milestone

BE-019

## Title

External Integrations & API Client Platform

## Depends On

- BE-001 — Database/API Foundation
- BE-007 — Projects, Claims & Geospatial Context
- BE-010 — Evidence Graph
- BE-011 — Fusion Engine
- BE-013 — Review Cases
- BE-014 — Evidence Requests
- BE-015 — Tamper-Evident Audit Ledger
- BE-016 — Authentication & Authorization
- BE-017 — Retention & Data Governance
- BE-018 — Notifications & Event Delivery

---

# 1. Objective

Implement the external integration and API-client foundation for Proof-of-Action.

PoA is designed to operate beside existing government and organizational systems rather than replacing them.

BE-019 establishes the secure API boundary through which authorized external systems can:

- submit evidence
- submit structured project data
- import claims
- retrieve authorized intelligence
- retrieve review status
- retrieve evidence-request status
- receive event notifications
- synchronize external identifiers
- perform idempotent operations

The goal is to make PoA usable as an **Evidence Intelligence Platform / API layer** for existing systems.

---

# 2. Architectural Principle

PoA MUST remain:

> A system that integrates with existing systems rather than requiring them to be replaced.

External systems are first-class sources.

External data MUST preserve:

- source system identity
- external identifier
- ingestion timestamp
- provenance
- synchronization metadata
- source assertions
- processing history

External data MUST NOT automatically become PoA's internal truth.

---

# 3. Scope

## IN SCOPE

BE-019 implements:

- external API client model
- API credentials
- API scopes
- API client lifecycle
- credential hashing/storage
- credential rotation
- credential revocation
- external system registration
- external identifiers
- idempotency keys
- inbound API authentication
- scoped API authorization
- external evidence ingestion
- external structured-data ingestion
- external claim import
- external project/activity references
- outbound webhook foundation
- webhook delivery
- webhook retry
- webhook signing
- webhook idempotency
- integration event model
- integration audit events
- API versioning rules
- integration tests

---

# 4. OUT OF SCOPE

The following MUST NOT be implemented:

- replacing government systems
- government SSO implementation
- citizen identity provider implementation
- MFA
- SMS
- WhatsApp
- Kafka
- enterprise ESB
- custom workflow engine
- automatic cross-system reconciliation decisions
- ML-based integration mapping
- LLM-based integration mapping
- automatic fraud decisions
- automatic authenticity decisions
- blockchain integration
- frontend integration dashboard
- arbitrary database synchronization
- direct database access for external systems

External systems MUST interact through explicit APIs.

---

# 5. External System Model

Create a first-class external system representation.

Conceptually:

```text
ExternalSystem
├── id
├── organization_id
├── name
├── code
├── system_type
├── status
├── description
├── created_at
├── updated_at
└── metadata

System types may include:

GOVERNMENT_PORTAL
FIELD_SYSTEM
PROJECT_MANAGEMENT
DOCUMENT_SYSTEM
INSPECTION_SYSTEM
DATA_PLATFORM
OTHER

The vocabulary may be expanded later.

6. External System Lifecycle

Recommended states:

ACTIVE
SUSPENDED
DISABLED

A disabled external system MUST NOT be able to authenticate.

Existing historical data associated with a disabled system MUST remain intact.

7. API Client

API clients represent machine actors.

Conceptually:

APIClient
├── id
├── external_system_id
├── name
├── client_identifier
├── status
├── created_at
├── updated_at
└── last_used_at

The client MUST map into the BE-016:

Principal
    ↓
API_CLIENT

model.

8. API Credentials

Credentials MUST NOT be stored in plaintext.

Store:

credential_id
client_id
credential_hash
created_at
expires_at
revoked_at
last_used_at

Only the credential hash should be persisted.

If a secret is shown to the caller during creation, it must not be recoverable later.

9. Credential Rotation

Support:

create credential
revoke credential
rotate credential

Rotation should permit controlled overlap where necessary.

Example:

Old Credential
       ↓
Rotation
       ↓
Old + New temporarily valid
       ↓
Old revoked
       ↓
New active

The exact overlap duration must be configurable.

10. Credential Revocation

Revocation must be immediate from the authorization perspective.

A revoked credential:

authentication → denied

The client itself may remain active if another credential exists.

11. API Scopes

API clients MUST use explicit scopes from BE-016.

Examples:

evidence.read
evidence.write

project.read
project.write

claim.read
claim.write

analysis.read
fusion.read

graph.read

review_case.read

evidence_request.read
evidence_request.write

notifications.read

webhooks.manage

A client with:

evidence.read

must not be able to:

review_case.decide

unless explicitly assigned.

12. Resource Scope

API clients must support:

GLOBAL
ORGANIZATION
ORGANIZATIONAL_UNIT
PROJECT

scope.

Example:

External System A
    ↓
API Client
    ↓
Project 123

must not automatically access:

Project 456
13. Backend Authorization

Every external API request must pass through BE-016 authorization.

Conceptually:

Credential
    ↓
API Client
    ↓
Principal
    ↓
Permission
    ↓
Scope
    ↓
Resource
    ↓
Authorization

Do not create a parallel authorization mechanism.

14. External Identifiers

External systems will have their own IDs.

Create a mapping model:

ExternalReference
├── id
├── external_system_id
├── resource_type
├── resource_id
├── external_id
├── external_version
├── first_seen_at
└── last_seen_at

A resource may have multiple external references.

Example:

PoA Project
    ├── Government System A: PROJECT-92831
    └── Department System B: WORK-1827
15. External Reference Uniqueness

Prevent duplicate mappings for the same source:

external_system_id
+
resource_type
+
external_id

must be unique.

Do not assume external IDs are globally unique across systems.

16. External Assertions

External systems may provide assertions.

Example:

Government System
    ↓
"Activity completed on 2026-09-20"

PoA must preserve this as an external assertion.

It must NOT silently convert the assertion into:

PoA truth

External assertions should retain:

source_system
external_id
source_timestamp
ingested_at
payload
17. External Project Integration

Support external project references.

An external project may map to:

PoA Project

without requiring the external system to use PoA's internal UUID.

Mapping must be explicit.

Do not create projects automatically from arbitrary inbound payloads unless the API operation explicitly requests project creation.

18. External Activity Integration

Support external activity references.

External activities may map to existing PoA activities.

The system must preserve:

external_activity_id
source_system
PoA activity ID
19. External Claim Import

External systems may submit claims/assertions.

Claims must preserve provenance:

Claim
├── source = EXTERNAL
├── external_system_id
├── external_reference
└── imported_at

Imported claims remain claims.

They must not automatically receive human approval.

20. Evidence Ingestion

External systems must be able to submit evidence through the existing BE-003 ingestion pipeline.

Do NOT create a second evidence-upload implementation.

The flow must remain:

External API
    ↓
BE-016 authentication
    ↓
BE-019 authorization
    ↓
BE-003 ingestion
    ↓
Quarantine
    ↓
Validation
    ↓
Trusted storage
    ↓
Existing async analysis

External source metadata must be attached as provenance.

21. External Evidence Requirements

External evidence requests must support:

external system ID
external evidence ID
original filename where available
declared media type
capture metadata where supplied
source timestamps
external project/activity/claim references
source provenance

Do not overwrite PoA-generated:

SHA-256
pHash
analysis results
storage identity

with external values.

22. External Metadata Trust

External metadata must be treated as:

SOURCE ASSERTION

not automatically verified fact.

For example:

external_capture_time

must remain distinguishable from:

EXIF_capture_time

and:

server_ingestion_time
23. Idempotency

All mutating external APIs MUST support idempotency.

Example header:

Idempotency-Key

The server must persist sufficient information to determine whether an operation has already been executed.

Repeated requests with the same key and compatible request body must return the original result.

24. Idempotency Safety

The implementation must detect:

same key
+
different request body

and reject it.

Recommended response:

409 Conflict

Do not silently execute a different operation under an existing key.

25. Idempotency Scope

Idempotency keys must be scoped to the API client.

This prevents:

Client A
Idempotency-Key = 123

from interfering with:

Client B
Idempotency-Key = 123
26. Webhook System

Implement outbound webhooks.

Conceptually:

PoA Event
    ↓
Webhook Subscription
    ↓
Webhook Delivery
    ↓
External System
27. Webhook Subscription

Create:

WebhookSubscription
├── id
├── external_system_id
├── endpoint_url
├── status
├── subscribed_events
├── secret_hash/reference
├── created_at
├── updated_at
└── last_delivery_at

Webhook URLs must be validated.

28. Webhook Events

Initial events:

review_case.created
review_case.assigned
review_case.escalated
review_case.resolved

evidence_request.issued
evidence_request.fulfilled
evidence_request.declined
evidence_request.expired

fusion.completed

retention.archived
retention.deleted

Only meaningful integration events should be exposed.

Do not expose every internal database mutation.

29. Webhook Payload

Webhook payloads must contain structured information.

Example:

{
  "event_id": "...",
  "event_type": "review_case.assigned",
  "event_version": 1,
  "occurred_at": "...",
  "resource_type": "REVIEW_CASE",
  "resource_id": "...",
  "project_id": "...",
  "data": {...}
}

Do not expose unauthorized fields.

30. Webhook Signing

Every webhook must be cryptographically signed.

Recommended:

HMAC-SHA256

Headers should contain:

X-PoA-Event-ID
X-PoA-Event-Type
X-PoA-Timestamp
X-PoA-Signature

The external system can verify authenticity.

31. Webhook Replay Protection

Include an event timestamp.

External consumers should be able to reject stale events.

PoA should generate unique event IDs.

Do not reuse event IDs across deliveries.

32. Webhook Delivery State

Recommended:

PENDING
PROCESSING
DELIVERED
RETRYING
FAILED
DISABLED

Store:

attempt_count
last_status_code
last_error
next_attempt_at
delivered_at
33. Webhook Retry

Transient HTTP failures should retry.

Examples:

408
429
500
502
503
504

Permanent failures should eventually become:

FAILED

Repeated failures may disable the subscription after a configurable threshold.

34. Webhook Idempotency

Webhook delivery must be safe to retry.

Every event has:

event_id

and every delivery has:

delivery_id

The receiver can use event_id to deduplicate.

35. Webhook Security

Webhook endpoints MUST NOT be allowed to receive arbitrary internal credentials.

Do not include:

JWTs
API secrets
database credentials
presigned URLs unless explicitly required and short-lived
internal authorization data
36. SSRF Protection

Webhook endpoints create an outbound network boundary.

Validate destination URLs.

Block:

localhost
loopback addresses
private IP ranges
link-local addresses
cloud metadata endpoints

DNS resolution must also be considered.

Do not rely solely on string validation.

37. Redirect Handling

Webhook delivery should NOT blindly follow redirects.

If redirects are supported, revalidate the destination.

The safest V1 behavior is:

redirects disabled
38. Outbound Event Architecture

Reuse the notification/outbox principles from BE-018.

Recommended:

Domain Event
    ↓
Transactional Outbox
    ↓
Integration Event
    ↓
Redis Streams
    ↓
Webhook Worker
    ↓
Signed HTTP Request

Do not publish webhooks synchronously from domain transactions.

39. Integration Event Store

Create a durable integration event record.

Conceptually:

IntegrationEvent
├── id
├── event_type
├── event_version
├── aggregate_type
├── aggregate_id
├── project_id
├── payload
├── created_at
└── status

Historical event identity must remain stable.

40. API Versioning

External APIs must use:

/api/v1/

as the canonical version.

Do not introduce:

/api/

without a version.

Breaking API changes require a new version.

41. External API Error Contract

All external APIs must use the existing structured error model.

Errors should contain:

code
message
request_id
details

Do not expose:

stack traces
SQL errors
internal filesystem paths
secrets
authorization internals
42. Rate Limiting

External API clients must support configurable rate/resource limits.

At minimum define:

requests per minute
upload limits
payload size limits
concurrent operations

The implementation may use application-level controls initially.

Do not introduce a separate API gateway solely for BE-019.

43. Request Correlation

External requests must preserve:

request_id
client_id
external_system_id

through:

API
→ services
→ workers
→ audit
→ webhook delivery

Use the existing request-ID infrastructure.

44. Audit Integration

BE-015 remains authoritative.

Add integration audit events such as:

API_CLIENT_CREATED
API_CLIENT_DISABLED
API_CREDENTIAL_CREATED
API_CREDENTIAL_REVOKED
EXTERNAL_SYSTEM_CREATED
EXTERNAL_REFERENCE_CREATED
WEBHOOK_CREATED
WEBHOOK_DISABLED
WEBHOOK_DELIVERY_FAILED
WEBHOOK_DELIVERY_SUCCEEDED

Do not create a second audit system.

45. Authorization

Use BE-016.

Recommended permissions:

integration.read
integration.manage
api_client.manage
credential.manage
external_data.read
external_data.write
webhook.manage
webhook.read

Scope must be enforced at:

GLOBAL
ORGANIZATION
ORGANIZATIONAL_UNIT
PROJECT
46. Credential Security

Secrets must:

never appear in logs
never appear in API responses after creation
never be stored plaintext
never be included in audit payloads
never be included in webhook payloads

Credential comparison must use secure hashing.

47. Database

Recommended tables:

external_systems
api_clients
api_credentials
external_references
external_assertions
idempotency_keys
webhook_subscriptions
webhook_events
webhook_deliveries
integration_events

Exact decomposition may be adjusted if an existing model already satisfies the requirement.

48. Migration

Create one Alembic migration.

Recommended revision:

l2g3h4i5j019_be019_external_integrations.py

Parent:

k1f2g3h4i018

Requirements:

alembic heads

must report exactly one head.

Test:

alembic upgrade head
alembic downgrade <BE-018 revision>
alembic upgrade head

Never modify previous migrations.

49. Repository

Create:

backend/repositories/integration.py

Responsibilities:

external systems
API clients
credentials
references
assertions
idempotency
webhooks
integration events
50. Schemas

Create:

backend/schemas/integration.py

Schemas must cover:

external system
API client
credential
external reference
external assertion
webhook
webhook event
integration event
idempotency response
51. Services

Create:

backend/services/integration.py
backend/services/webhook.py

Responsibilities:

Integration Service
external system management
client management
credential lifecycle
external references
external assertions
idempotency
Webhook Service
subscriptions
event creation
payload generation
signing
delivery
retry
failure handling
52. API Endpoints

Recommended:

GET    /api/v1/integrations/systems
POST   /api/v1/integrations/systems

GET    /api/v1/integrations/clients
POST   /api/v1/integrations/clients
GET    /api/v1/integrations/clients/{id}

POST   /api/v1/integrations/clients/{id}/credentials
POST   /api/v1/integrations/credentials/{id}/revoke

GET    /api/v1/integrations/references
POST   /api/v1/integrations/references

POST   /api/v1/integrations/evidence
POST   /api/v1/integrations/claims

GET    /api/v1/integrations/webhooks
POST   /api/v1/integrations/webhooks
PATCH  /api/v1/integrations/webhooks/{id}

GET    /api/v1/integrations/events

Exact endpoints must follow existing API conventions.

53. External Evidence Endpoint

External evidence submission MUST reuse:

BE-003 evidence ingestion

and must preserve:

source = EXTERNAL
external_system_id
external_reference

Do not duplicate validation/storage logic.

54. External Claim Endpoint

Claims imported through the integration API must preserve external provenance.

They may later participate in:

Evidence Graph
Temporal Engine
Fusion Engine

but BE-019 must not alter their analytical semantics.

55. External Data Validation

Validate all inbound payloads with Pydantic.

Reject:

malformed UUIDs
invalid timestamps
invalid coordinates
oversized payloads
unsupported content types
invalid external IDs
duplicate conflicting mappings

Never trust external JSON blindly.

56. Timestamp Handling

External timestamps must:

be timezone-aware
preserve original source timestamp
record ingestion timestamp separately
never silently replace missing timezone information

Use existing BE-008 temporal conventions.

57. External Source Provenance

Every imported external object should preserve:

source_system
external_id
source_version
source_timestamp
ingested_at
request_id
api_client_id

Provenance does not imply truth.

58. Synchronization Semantics

BE-019 must distinguish:

CREATE
UPDATE
REPLAY
DUPLICATE
CONFLICT

External updates must not silently overwrite protected PoA history.

Where a conflict exists:

do not silently choose a winner

Persist the conflict for later handling.

59. No Automatic Reconciliation

This is explicitly forbidden:

External System says X
PoA says Y
↓
LLM decides X is correct

or:

External System says X
PoA says Y
↓
latest timestamp automatically wins

Conflicting source assertions remain distinguishable.

60. Testing
Unit Tests

Test:

credential hashing
credential revocation
credential rotation
API scope evaluation
resource scope
external reference uniqueness
idempotency
webhook signing
webhook payload versioning
retry calculation
SSRF protection
URL validation
timestamp validation
61. Integration Tests

Run against real PostgreSQL, Redis, and storage.

Minimum scenarios:

API Client
create client
create credential
authenticate
authorize
revoke credential
authentication denied
Scope
Project A client
→ Project A allowed
→ Project B denied
External Evidence
external submission
→ BE-003 pipeline
→ provenance preserved
→ normal analysis path
Idempotency
same request
same key
→ one operation

and:

same key
different body
→ 409
Webhook
event
→ outbox
→ Redis
→ worker
→ signed HTTP delivery
Retry
500
→ retry

200
→ delivered
Security
private IP webhook
→ rejected

metadata endpoint
→ rejected

unauthorized project
→ denied
62. Concurrent Tests

Test:

10 concurrent identical API operations

Expected:

exactly one effective operation

Test:

10 concurrent webhook deliveries

Expected:

no duplicate event identity

Use database uniqueness constraints.

Do not use Python process-local locks.

63. Performance

External API operations should be bounded.

At minimum measure:

authentication
authorization
idempotency lookup
external reference lookup
evidence submission
webhook enqueue

Webhook delivery must never block API requests.

64. Observability

Expose:

external API request count
authentication failures
authorization failures
idempotency conflicts
webhook queue depth
webhook delivery latency
webhook failures
retry count
external ingestion failures

Use:

OpenTelemetry
Prometheus
Grafana
65. Failure Handling

If external webhook delivery fails:

domain transaction remains successful

and:

delivery = RETRYING / FAILED

If an external evidence upload fails:

do not create a trusted evidence record

Reuse BE-003 failure semantics.

If Redis is unavailable:

persist integration event/outbox

and deliver later.

66. Definition of Done

BE-019 is complete only when:

External Systems
 External systems exist
 Lifecycle exists
 Organization scope enforced
API Clients
 API clients exist
 Credentials are hashed
 Credential revocation works
 Credential rotation works
 API scopes enforced
 Resource scope enforced
External Data
 External references work
 External assertions preserve provenance
 External claims work
 External evidence reuses BE-003
 No duplicate ingestion pipeline exists
Idempotency
 Idempotency keys work
 Same key/same body is idempotent
 Same key/different body returns conflict
 Client-scoped idempotency exists
Webhooks
 Webhook subscriptions work
 Events are versioned
 Payloads are signed
 Delivery is asynchronous
 Retries work
 Failures are persisted
 SSRF protection exists
 Webhook authorization works
Security
 BE-016 is reused
 Secrets are never stored plaintext
 Secrets never appear in logs
 Cross-project isolation works
 Unauthorized resources return appropriate errors
 Private webhook destinations are blocked
Audit
 Integration administration is audited
 Credential lifecycle is audited
 Webhook failures are auditable
 BE-015 remains authoritative
Testing
 Unit tests pass
 Integration tests pass
 Full regression suite passes
 Migration upgrade passes
 Migration downgrade passes
 Concurrent operations tested
 Failure/retry paths tested
 SSRF security tests pass
67. Anti-Shortcut Gates
Gate 1 — No plaintext API secrets

Never store API credentials in plaintext.

Gate 2 — No second authorization system

Reuse BE-016.

Gate 3 — No second evidence pipeline

Reuse BE-003.

Gate 4 — No synchronous webhooks

Domain requests must not wait for external HTTP delivery.

Gate 5 — No unbounded retries

Every delivery must have a retry policy and terminal failure state.

Gate 6 — No SSRF

Webhook URLs must be protected against internal-network access.

Gate 7 — No automatic conflict resolution

Conflicting external assertions must remain distinguishable.

Gate 8 — No LLM reconciliation

LLMs must not decide which external source is correct.

Gate 9 — No direct database integration

External systems use the API, never PoA's database directly.

Gate 10 — No cross-project leakage

External API clients are subject to BE-016 scope.

68. Recommended Implementation Structure

backend/
├── services/
│ ├── integration.py
│ └── webhook.py
│
├── repositories/
│ └── integration.py
│
├── schemas/
│ └── integration.py
│
├── security/
│ └── authentication.py
│
├── api/
│ └── v1/
│ └── endpoints/
│ └── integration.py
│
├── workers/
│ └── webhook_worker.py
│
└── db/
└── models.py

69. Recommended Commit

Implementation:

BE-019: implement external integrations and API client platform

Completion:

BE-019 Complete

70. Architectural Boundary

BE-019 answers:

How can authorized external systems securely communicate with PoA?

It does NOT answer:

Which external system is telling the truth?

It does NOT answer:

Is the evidence authentic?

It does NOT answer:

Is the project fraudulent?

It does NOT answer:

Which conflicting source should win?

External systems are sources and integration partners.

PoA preserves their assertions, provenance, and identity while keeping its own analytical and human-decision layers independent.

71. Final Integration Flow
External Government / Organization System
                  ↓
             OAuth/API
                  ↓
          API Client Principal
                  ↓
       BE-016 Authorization
                  ↓
        BE-019 Integration Layer
          ↙                 ↘
   Inbound Data          Outbound Events
        ↓                       ↓
 Evidence / Claims         Transactional Outbox
        ↓                       ↓
 Existing PoA Pipeline     Redis Streams
                                ↓
                         Webhook Worker
                                ↓
                         Signed Webhook
                                ↓
                      External System

The integration layer must remain secure, asynchronous, idempotent, provenance-preserving, and independent of substantive evidence decisions.