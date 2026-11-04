# BE-018 — Notifications & Event Delivery

## Status

PLANNED

## Milestone

BE-018

## Title

Notifications & Event Delivery

## Depends On

- BE-001 — Database/API Foundation
- BE-013 — Review Cases
- BE-014 — Evidence Requests
- BE-015 — Tamper-Evident Audit Ledger
- BE-016 — Authentication & Authorization
- BE-017 — Retention & Data Governance

---

# 1. Objective

Implement the notification and event-delivery foundation for Proof-of-Action.

The system must be able to inform authorized actors when important workflow events occur without coupling domain services directly to email, push, SMS, or frontend-specific delivery mechanisms.

BE-018 establishes:

- notification events
- notification records
- recipient resolution
- notification preferences
- delivery states
- idempotent delivery
- retry handling
- in-app notifications
- optional email delivery abstraction
- event-driven delivery architecture
- authorization-aware notification visibility
- audit integration

The notification system is a delivery mechanism.

It MUST NOT become a second workflow engine.

---

# 2. Architectural Requirement

The implementation MUST conform to:

`docs/Final Architecture.md`

Relevant decisions:

- Notifications are workflow-focused.
- V1 supports in-app notifications and optional email.
- Push/SMS are deferred.
- There is no chat/messaging system.
- Notifications must respect authorization and project/organization scope.
- Domain workflow remains authoritative.
- Notifications must not modify domain decisions.
- Notification delivery must be auditable.
- External delivery failures must not corrupt domain transactions.

---

# 3. Scope

## IN SCOPE

BE-018 implements:

- notification domain model
- notification event model
- recipient resolution
- notification preferences
- in-app notification inbox
- notification read/unread state
- delivery status
- email provider abstraction
- asynchronous notification delivery
- Redis Streams integration
- retry handling
- idempotency
- authorization-aware recipient filtering
- notification APIs
- notification audit events
- worker implementation
- notification templates
- notification tests

---

# 4. OUT OF SCOPE

The following MUST NOT be implemented:

- SMS
- push notifications
- WhatsApp
- chat
- direct messaging
- email campaign system
- marketing notifications
- bulk promotional messaging
- notification-based workflow decisions
- LLM-generated mandatory notifications
- automatic case decisions
- automatic review decisions
- new fusion logic
- new risk scoring
- new evidence intelligence
- frontend notification UI beyond API compatibility
- external event bus such as Kafka
- separate message broker
- workflow engine

Redis Streams remains the event-delivery mechanism.

---

# 5. Core Architecture

The notification architecture must be:

```text
Domain Event
    ↓
Notification Event
    ↓
Recipient Resolution
    ↓
Notification Record
    ↓
Redis Stream
    ↓
Notification Worker
    ↓
Delivery Provider
    ↓
Delivery Result

Domain services MUST NOT directly send email.

6. Domain Event Separation

A domain action is not itself a notification.

Example:

Review Case assigned

creates a domain event.

The notification subsystem may transform that into:

You have been assigned Review Case #123

The notification must not modify the Review Case.

7. Notification Types

Implement a controlled notification vocabulary.

Initial types:

REVIEW_CASE_ASSIGNED
REVIEW_CASE_ESCALATED
REVIEW_CASE_DECISION_PENDING
REVIEW_CASE_REOPENED

EVIDENCE_REQUEST_ISSUED
EVIDENCE_REQUEST_ACKNOWLEDGED
EVIDENCE_REQUEST_PARTIALLY_FULFILLED
EVIDENCE_REQUEST_FULFILLED
EVIDENCE_REQUEST_DECLINED
EVIDENCE_REQUEST_EXPIRED

RETENTION_HOLD_CREATED
RETENTION_HOLD_RELEASED

SYSTEM_SECURITY_EVENT

Additional types may be introduced only when tied to a real workflow.

Do not create generic notification types for every database mutation.

8. Notification Model

Create a first-class notification record.

Conceptually:

Notification
├── id
├── recipient_id
├── organization_id
├── project_id
├── notification_type
├── title
├── body
├── resource_type
├── resource_id
├── severity
├── status
├── created_at
├── read_at
└── expires_at

Notification content should be generated from structured event data.

9. Delivery Model

Separate:

Notification

from:

NotificationDelivery

A notification may have multiple delivery channels.

Example:

Notification
    ├── IN_APP
    └── EMAIL

Conceptually:

NotificationDelivery
├── id
├── notification_id
├── channel
├── status
├── attempts
├── provider
├── provider_message_id
├── last_error
├── next_attempt_at
├── created_at
└── delivered_at
10. Delivery Channels

V1:

IN_APP
EMAIL

Push and SMS remain future channels.

The system should be designed so new channels can be added without changing domain services.

11. Notification Status

Recommended notification state:

UNREAD
READ

Delivery state:

PENDING
PROCESSING
DELIVERED
FAILED
RETRYING
CANCELLED

Notification read state and delivery state MUST remain separate.

12. Recipient Resolution

Recipient resolution must be deterministic.

Examples:

Review Case assignment
Case assigned
    ↓
assigned user
    ↓
notification
Escalation
Case escalated
    ↓
authorized supervisor(s)
    ↓
notification
Evidence Request
Request issued
    ↓
recipient
    ↓
notification

Do not notify users merely because they belong to the same organization.

Recipient selection must follow the actual workflow relationship.

13. Authorization

BE-016 remains authoritative.

Before creating/delivering a notification, verify that the recipient is allowed to know about the referenced resource.

A notification must never leak:

unauthorized project IDs
private evidence information
citizen identity
internal intelligence
restricted case information

If recipient authorization cannot be established:

DO NOT DELIVER
14. Cross-Project Isolation

A notification referencing Project A must not expose Project A information to a user authorized only for Project B.

Example:

Project A Case
    ↓
Assigned Reviewer A
    ↓
Notification

Reviewer B must not receive it.

Cross-project graph relationships do not create notification authority.

15. In-App Inbox

Implement:

GET /api/v1/notifications

with:

pagination
unread filter
notification type filter
project filter
date filtering

Additional:

GET /api/v1/notifications/{id}

POST /api/v1/notifications/{id}/read

POST /api/v1/notifications/read-all

Only the recipient may modify read state.

16. Notification Preferences

Implement basic user preferences.

Conceptually:

NotificationPreference
├── user_id
├── notification_type
├── in_app_enabled
├── email_enabled
└── updated_at

Defaults should be deterministic.

Critical security/workflow notifications may be non-disableable if required by policy.

Do not create complex notification preference rules in V1.

17. Email Provider Abstraction

Create:

backend/services/notification.py

and a provider abstraction.

Conceptually:

NotificationProvider
    ├── InAppProvider
    └── EmailProvider

The email provider should expose:

send(notification, recipient)

Application services must not call SMTP/SendGrid/etc. directly.

18. Development Email Provider

A development provider may:

log messages
persist test delivery records
avoid sending real email

Production email provider configuration must be explicit.

Never silently send production email using development configuration.

19. Templates

Notification templates must be versioned.

Example:

REVIEW_CASE_ASSIGNED
template_version = 1

Template inputs should be structured.

Example:

{
    "case_id": "...",
    "project_name": "...",
    "priority_band": "HIGH"
}

Do not construct notification content from arbitrary database strings without validation.

20. LLM Boundary

An LLM MUST NOT be required to generate notifications.

Default:

structured event
    ↓
deterministic template
    ↓
notification

Optional future behavior:

structured notification
    ↓
LLM language rendering

If an LLM is introduced later, it must not invent:

case IDs
project names
decisions
priorities
deadlines
evidence claims

Structured event data remains authoritative.

21. Redis Streams

Reuse the existing Redis Streams infrastructure.

Notification events should be published to a dedicated stream.

Example:

notifications

Conceptually:

FastAPI
    ↓
Notification event
    ↓
Redis Stream
    ↓
Notification worker

Do not introduce Kafka or another message broker.

22. Worker

Create:

backend/workers/notification_worker.py

Responsibilities:

read stream event
resolve delivery
create/update delivery record
send through provider
record result
retry failures
acknowledge stream message

The worker must be safe to restart.

23. Idempotency

Notification delivery MUST be idempotent.

Use a deterministic event/delivery identity.

Example:

notification_event_id
+
recipient_id
+
channel

Repeated processing must not create duplicate notifications.

24. Retry Policy

Transient failures should retry.

Recommended initial policy:

attempt 1 → immediate
attempt 2 → short delay
attempt 3 → longer delay
attempt 4 → longer delay

Exact delays may be configurable.

Permanent failures should stop retrying.

Store:

attempt_count
last_error
next_attempt_at
25. Dead-Letter Handling

Failed notifications that exceed retry limits should become:

FAILED

and remain queryable.

Do not silently discard failed deliveries.

A dead-letter stream may be used if necessary, but a second messaging system must not be introduced.

26. Domain Integration

Integrate with existing workflows.

At minimum:

BE-013
case assignment
escalation
decision pending
reopening
BE-014
request issued
acknowledgment
partial fulfillment
fulfillment
decline
expiration
BE-017
retention hold creation
retention hold release

Do not modify the underlying workflow state machines.

27. Transaction Boundary

Notification creation must not corrupt domain transactions.

Where possible:

Domain transaction
    ↓
Persist domain event
    ↓
Persist notification event
    ↓
Commit
    ↓
Publish/deliver asynchronously

If external delivery fails:

domain transaction remains successful

The notification failure is independent.

28. Outbox Requirement

Implement a lightweight transactional event/outbox mechanism if required to guarantee:

database commit
+
notification event persistence

are atomic.

Do not rely solely on:

DB commit
→ Redis publish

because Redis publication may fail after the database transaction succeeds.

The outbox should be persisted in PostgreSQL.

29. Outbox Model

Recommended:

notification_outbox
├── id
├── event_type
├── aggregate_type
├── aggregate_id
├── payload
├── status
├── attempts
├── created_at
├── processed_at
└── last_error

Use a unique event identity.

The outbox worker publishes events to Redis Streams.

30. Audit Integration

BE-015 remains the authoritative audit ledger.

Notification administration events may be audited.

Examples:

NOTIFICATION_PREFERENCE_CHANGED
NOTIFICATION_DELIVERY_FAILED
NOTIFICATION_DELIVERY_SUCCEEDED

Routine notification creation does not need to produce a ledger entry for every in-app message unless required by policy.

Do not create a second audit system.

31. Security

Never store:

access tokens
passwords
SMTP credentials
API secrets

inside notification records.

Email content must not contain sensitive evidence unless explicitly authorized.

Presigned storage URLs should generally not be embedded in notifications.

Instead:

notification
    ↓
authorized application link
    ↓
fresh authorization check
32. API Authorization

Recommended permissions:

notification.read
notification.mark_read
notification.manage_preferences
notification.admin

Users can read their own notifications.

Administrators should not automatically be able to read everyone's private notification inbox unless explicitly permitted.

33. Database

Recommended tables:

notifications
notification_deliveries
notification_preferences
notification_outbox

Use:

UUID primary keys
foreign keys
unique constraints
indexes on recipient/status/created_at
indexes on delivery status/next_attempt_at
project scope indexes
34. Migration

Create one Alembic migration.

Recommended revision:

k1f2g3h4i018_be018_notifications.py

Parent:

j0e1f2g3h017

Requirements:

alembic heads

must report exactly one head.

Test:

alembic upgrade head
alembic downgrade <BE-017 revision>
alembic upgrade head
35. Repository

Create:

backend/repositories/notification.py

Responsibilities:

notification persistence
delivery persistence
preferences
outbox
inbox queries
unread counts
delivery status

Do not put provider logic in repositories.

36. Schemas

Create:

backend/schemas/notification.py

Schemas should cover:

notification
notification delivery
notification preference
notification event
outbox event
pagination/filtering
37. Service

Create:

backend/services/notification.py

Responsibilities:

create notification events
resolve recipients
render templates
apply preferences
create outbox events
manage delivery state
enforce notification invariants

Do not place FastAPI-specific logic in this service.

38. Endpoints

Create:

backend/api/v1/endpoints/notification.py

Minimum:

GET  /api/v1/notifications
GET  /api/v1/notifications/{id}
POST /api/v1/notifications/{id}/read
POST /api/v1/notifications/read-all

GET   /api/v1/notifications/preferences
PATCH /api/v1/notifications/preferences

Administrative delivery inspection may be added if required.

39. Testing
Unit

Test:

notification creation
recipient resolution
preference handling
template rendering
notification status
delivery state
retry calculation
idempotency
authorization
cross-project isolation
Integration

Test against real PostgreSQL and Redis:

case assignment notification
evidence request notification
retention notification
outbox persistence
Redis publication
worker processing
retry
duplicate event
concurrent delivery
unread/read state
project isolation
unauthorized recipient
failed provider
40. Concurrency

Test:

10 concurrent identical notification events

Expected:

exactly one notification

and:

10 concurrent delivery attempts

must not create duplicate provider deliveries where idempotency can be guaranteed.

Use database constraints, not Python locks.

41. Failure Handling

If Redis is unavailable:

domain operation MUST NOT silently fail

if the outbox transaction has already safely persisted the notification event.

The event can be published later.

If email provider fails:

notification remains
delivery = RETRYING / FAILED

The user must still retain the in-app notification when applicable.

42. Performance

Notification inbox queries must be indexed.

Primary query:

recipient_id
+
created_at

must be efficient.

Unread counts must not require loading the entire inbox.

Notification creation must not synchronously wait for email delivery.

43. Observability

Expose:

notifications created
notifications delivered
delivery failures
retry count
queue lag
worker processing duration
provider latency

Use the existing:

OpenTelemetry
Prometheus
Grafana

stack.

Do not introduce another monitoring system.

44. Definition of Done

BE-018 is complete only when:

Database
 Notifications table exists
 Delivery table exists
 Preferences table exists
 Outbox exists
 Constraints exist
 Indexes exist
 Migration reversible
 Single Alembic head
Notifications
 In-app notifications work
 Read/unread state works
 Recipient resolution is deterministic
 Notification types are controlled
 Templates are versioned
Delivery
 Redis Streams integrated
 Worker exists
 Email abstraction exists
 Retry handling works
 Failed delivery is preserved
 Idempotency works
 Outbox protects DB/event consistency
Security
 BE-016 authorization enforced
 Cross-project isolation enforced
 Unauthorized recipients blocked
 Sensitive information is not leaked
 Tokens/secrets are never stored in notifications
Integration
 Review Case events integrated
 Evidence Request events integrated
 Retention events integrated
 Existing workflows remain unchanged
Audit
 Required administrative notification events audited
 BE-015 remains authoritative
 No second audit system
Testing
 Unit tests pass
 Integration tests pass
 Full regression suite passes
 Concurrent delivery tested
 Redis failure tested
 Provider failure tested
 Migration upgrade tested
 Migration downgrade tested
45. Anti-Shortcut Gates
Gate 1 — No direct email from domain services

Domain services must never call an email provider directly.

Gate 2 — No synchronous email delivery

A review-case assignment must not wait for an SMTP/API provider.

Gate 3 — No duplicate notifications

Retries must be idempotent.

Gate 4 — No notification-based authorization

Receiving a notification does not grant access to the referenced resource.

Gate 5 — No cross-project leakage

Notifications must respect BE-016 scope.

Gate 6 — No chat system

Notifications are one-way workflow communication.

Gate 7 — No Kafka

Redis Streams remains the event transport.

Gate 8 — No LLM dependency

Notifications must work without an LLM.

Gate 9 — No workflow mutation

Notifications must never automatically:

resolve cases
approve evidence
decide claims
fulfill requests
delete resources
Gate 10 — No silent failure

Failed delivery must remain observable and retryable.

46. Recommended Implementation Structure

backend/
├── services/
│ └── notification.py
│
├── repositories/
│ └── notification.py
│
├── schemas/
│ └── notification.py
│
├── api/
│ └── v1/
│ └── endpoints/
│ └── notification.py
│
├── workers/
│ └── notification_worker.py
│
└── db/
└── models.py

47. Recommended Commit

Implementation:

BE-018: implement notifications and event delivery

Completion:

BE-018 Complete

48. Architectural Boundary

BE-018 answers:

How does PoA inform an authorized actor that something important happened?

It does NOT answer:

What decision should be made?

It does NOT answer:

Is evidence truthful?

It does NOT answer:

Is a project fraudulent?

It does NOT answer:

Who should win a dispute?

Notifications communicate existing system events.

They do not create new intelligence or decision authority.

49. Final Flow
Domain Workflow
      ↓
Domain Event
      ↓
Transactional Outbox
      ↓
Redis Streams
      ↓
Notification Worker
      ↓
Recipient Authorization
      ↓
Notification
      ├── In-App
      └── Email

The domain remains authoritative.

The notification system remains asynchronous, idempotent, authorization-aware, auditable, and independently recoverable.