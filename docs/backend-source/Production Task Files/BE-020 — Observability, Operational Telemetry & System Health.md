# BE-020 — Observability, Operational Telemetry & System Health

## 1. Objective

Implement the production observability layer for Proof-of-Action (PoA) so that operators can reliably understand system health, API behavior, background processing, storage/database performance, integration delivery, and failure conditions.

BE-020 establishes **technical observability**, not business analytics.

The milestone must provide:

- structured application metrics
- distributed/request tracing
- worker/job telemetry
- database and Redis health telemetry
- storage telemetry
- webhook/integration delivery telemetry
- correlation through request IDs and trace IDs
- health/readiness checks suitable for production deployment
- Prometheus-compatible metrics
- OpenTelemetry instrumentation
- operationally useful dashboards/queries
- failure visibility without leaking sensitive evidence or credentials

BE-020 MUST NOT implement business analytics, fraud analytics, review-priority analytics, ML monitoring, or citizen-facing dashboards.

---

# 2. Architectural Boundary

BE-020 consumes existing behavior from:

- BE-001 — API foundation
- BE-002 — storage abstraction
- BE-005 — async analysis jobs
- BE-006 — duplicate intelligence
- BE-008 — temporal intelligence
- BE-009 — vision analysis
- BE-010 — evidence graph
- BE-011 — fusion engine
- BE-012 — explainability
- BE-013 — review cases
- BE-014 — evidence requests
- BE-015 — audit ledger
- BE-016 — authentication/authorization
- BE-017 — retention/governance
- BE-018 — notifications/event delivery
- BE-019 — external integrations/API clients/webhooks

BE-020 observes these systems.

It MUST NOT change their substantive domain behavior.

---

# 3. Core Principle

Observability answers:

> "Is the system working correctly, how is it behaving, and where is it failing?"

It does NOT answer:

> "Is the evidence truthful?"
> "Is a project fraudulent?"
> "Which project is suspicious?"
> "Which reviewer is performing best?"
> "Which claim should be decided?"

Those remain domain/intelligence/review concerns.

---

# 4. Required Technology

Use the locked architecture stack:

- OpenTelemetry
- Prometheus
- Grafana
- Python FastAPI instrumentation
- SQLAlchemy instrumentation where appropriate
- Redis instrumentation where appropriate
- structured logging
- existing request-ID infrastructure
- OpenTelemetry trace/span IDs

Do not introduce a second observability framework.

---

# 5. Observability Architecture

Implement:

```text
HTTP Request
    |
    +--> Request ID
    |
    +--> Trace ID
    |
    +--> FastAPI Span
            |
            +--> DB Span
            |
            +--> Redis Span
            |
            +--> Storage Span
            |
            +--> External Integration Span
            |
            +--> Worker/Background Span

Metrics:

Application
    |
    +--> Prometheus
            |
            +--> Grafana

Logs:

Application / Worker
        |
        +--> Structured JSON Logs
                |
                +--> request_id
                +--> trace_id
                +--> service/component
                +--> event
                +--> severity
6. Metrics

Implement Prometheus-compatible metrics.

6.1 HTTP Metrics

Track:

request count
request duration
response status
request method
route
error count

Required metric concepts:

http_requests_total
http_request_duration_seconds
http_errors_total

Labels MUST remain bounded.

Allowed examples:

method
route
status_code

Do NOT use:

evidence UUID
user UUID
project UUID
claim UUID
API credential
arbitrary request parameters

as metric labels.

7. Database Metrics

Track:

connection pool usage
connection acquisition failures
query latency where instrumentation is available
transaction failures
database connectivity state

Do not log raw SQL containing:

secrets
credentials
evidence metadata
personally identifiable information

Avoid excessive per-query application logging.

8. Redis Metrics

Track:

connection failures
command latency where practical
queue/stream processing failures
worker backlog where measurable
retry/dead-letter conditions if applicable

Do not expose Redis credentials through telemetry.

9. Background Worker Metrics

Instrument existing background workers.

At minimum cover:

analysis worker
webhook worker
notification/event worker where applicable
retention worker where applicable

Track:

worker_jobs_started_total
worker_jobs_completed_total
worker_jobs_failed_total
worker_job_duration_seconds
worker_retry_total
worker_backlog

Labels should use bounded values such as:

worker
job_type
status

Do not use:

evidence_id
project_id
user_id
claim_id

as metric labels.

10. Analysis Pipeline Observability

Observe the existing analysis lifecycle:

QUEUED
→ RUNNING
→ COMPLETED

and:

QUEUED
→ RUNNING
→ FAILED

Track:

analysis jobs created
jobs completed
jobs failed
retry counts
execution duration
abandoned-job recovery
job type

Examples:

analysis_jobs_total
analysis_job_duration_seconds
analysis_job_failures_total
analysis_job_retries_total

Do NOT modify analysis semantics.

BE-020 must not introduce:

new scoring
new vision analysis
new duplicate logic
new temporal logic
new fusion logic
11. Webhook / Integration Observability

Instrument BE-019 webhook delivery.

Track:

events created
deliveries attempted
deliveries succeeded
deliveries failed
retries
subscription suspension
delivery latency
HTTP response classes

Example metrics:

webhook_events_total
webhook_delivery_attempts_total
webhook_delivery_success_total
webhook_delivery_failures_total
webhook_delivery_duration_seconds
webhook_retries_total
webhook_subscriptions_suspended_total

Do not expose:

webhook secret
API credential
HMAC secret
authorization header
raw external payload
12. Storage Observability

Instrument the BE-002 storage abstraction.

Track:

upload attempts
upload success/failure
download attempts
download success/failure
copy/promote operations
delete operations
storage latency
storage errors

Example:

storage_operations_total
storage_operation_duration_seconds
storage_operation_errors_total

Labels should remain bounded:

operation
provider
status

Never expose object keys containing sensitive identifiers through metrics.

13. Health Checks

Implement production-oriented health endpoints.

Existing health/readiness behavior from BE-001 must be preserved.

Extend readiness checks to verify required dependencies.

Minimum checks:

PostgreSQL
Redis
Storage

Optional dependency checks should distinguish:

required dependency unavailable
optional dependency unavailable

Health endpoints MUST NOT:

expose credentials
expose environment variables
expose connection strings
expose database schema details
expose internal secrets
perform expensive analysis
14. Liveness vs Readiness

Clearly separate:

Liveness

Answers:

"Is this application process alive?"

It must not fail merely because PostgreSQL or Redis is temporarily unavailable.

Readiness

Answers:

"Can this instance safely receive work?"

Readiness may fail when required dependencies are unavailable.

Do not combine these semantics.

15. Structured Logging

Implement structured JSON logging for application and worker processes.

Minimum fields:

timestamp
level
service
component
event
message
request_id
trace_id
span_id

Where applicable:

route
method
status_code
duration_ms
job_type
worker
error_type

Do not log:

passwords
API secrets
webhook secrets
bearer tokens
storage credentials
raw evidence contents
raw EXIF
sensitive citizen data
full external payloads
authorization headers
16. Request Correlation

Every HTTP request must preserve the existing request ID behavior.

Add OpenTelemetry correlation:

request_id
trace_id
span_id

Logs generated during a request must contain the appropriate correlation identifiers.

Background jobs should preserve useful parent/correlation information where available.

Do not create fake trace relationships when no valid parent context exists.

17. Error Instrumentation

Centralize error telemetry without changing existing error responses.

Capture:

exception type
component
route/operation
trace ID
request ID
timestamp

Do not expose internal stack traces to API clients.

Stack traces may exist in protected server-side logs when appropriate.

18. Sensitive Data Redaction

Create one reusable telemetry redaction mechanism.

It must protect at minimum:

password
secret
token
access_token
refresh_token
authorization
api_key
credential
webhook_secret
signature

Redaction must apply recursively to structured dictionaries where appropriate.

Do not rely on individual endpoints remembering to redact fields.

19. OpenTelemetry

Implement OpenTelemetry tracing with:

FastAPI request spans
database spans where supported
Redis spans where supported
worker spans
storage operation spans
webhook delivery spans

Use configurable exporters.

Development may use a console exporter.

Production must support OTLP-compatible export.

Telemetry export failure MUST NOT bring down the application.

20. Sampling

Tracing must support configurable sampling.

Provide configuration such as:

OTEL_ENABLED
OTEL_SERVICE_NAME
OTEL_EXPORTER_OTLP_ENDPOINT
OTEL_TRACE_SAMPLE_RATE

Do not hard-code production sampling assumptions.

21. Prometheus Endpoint

Expose a Prometheus-compatible metrics endpoint.

It must:

be lightweight
avoid authentication secrets in output
expose bounded labels
not perform database scans for every scrape
not expose evidence contents
not expose user/project identifiers

If the existing authentication model protects operational endpoints, follow the established authorization architecture rather than creating a second security mechanism.

22. Grafana Dashboard Definitions

Create dashboard configuration suitable for development/production deployment.

Minimum dashboard views:

API Health

Show:

request rate
error rate
latency
status-code distribution
Background Processing

Show:

queue/backlog
jobs completed
jobs failed
retry activity
execution duration
Database / Redis

Show:

availability
connection failures
latency indicators
resource pressure where available
Integrations

Show:

webhook delivery rate
failures
retries
suspended subscriptions
delivery latency
Storage

Show:

operation rate
failures
latency
provider status

Do not create business dashboards.

23. Alert Rules

Provide baseline operational alert definitions.

Examples:

API error spike

Trigger when the HTTP error rate exceeds a configurable threshold for a sustained period.

API latency

Trigger when request latency exceeds a configurable threshold.

Database unavailable

Trigger when readiness/database connectivity remains unavailable.

Redis unavailable

Trigger when required Redis connectivity remains unavailable.

Worker failure spike

Trigger when worker failures exceed a configurable threshold.

Webhook failure spike

Trigger when webhook delivery failures exceed a configurable threshold.

Queue backlog

Trigger when background processing backlog remains above a configurable threshold.

Thresholds must be configuration, not hard-coded domain decisions.

24. Audit Boundary

Observability is NOT the audit ledger.

BE-015 remains the authoritative tamper-evident audit mechanism for auditable domain/security actions.

BE-020 telemetry:

may reference audit events
may contain operational logs
must not replace audit events
must not mutate audit records
must not create a second audit ledger

Do not emit duplicate domain audit records merely for telemetry.

25. Authorization Boundary

Use BE-016 authorization.

Operational telemetry must not bypass authorization.

Sensitive operational endpoints must be protected according to existing permission/scope rules.

Do not invent a second RBAC system.

26. Privacy Boundary

Telemetry must follow the same security/privacy principles established by the architecture.

Do not treat:

trace_id
request_id
metric labels
logs

as permission to expose domain data.

Telemetry should identify the operation, not reproduce the underlying evidence.

27. Failure Semantics

Observability failures must be non-fatal.

If:

OpenTelemetry exporter unavailable

the API must continue operating.

If:

Prometheus scrape fails

the application must continue operating.

If:

Grafana unavailable

the application must continue operating.

Telemetry is secondary to domain execution.

28. Configuration

Add environment configuration with safe defaults.

Examples:

OTEL_ENABLED=false
OTEL_SERVICE_NAME=poa-backend
OTEL_EXPORTER_OTLP_ENDPOINT=
OTEL_TRACE_SAMPLE_RATE=0.1

PROMETHEUS_ENABLED=true

OBSERVABILITY_LOG_FORMAT=json
OBSERVABILITY_REDACT_SENSITIVE=true

Exact names may be adapted to the existing configuration conventions.

Secrets must never have insecure production defaults.

29. Testing Requirements
Unit Tests

Test:

metric registration
bounded labels
structured log fields
sensitive-data redaction
recursive redaction
trace/request correlation
configuration parsing
invalid sampling values
disabled telemetry behavior
exporter failure behavior
Integration Tests

Test:

/health
/ready
Prometheus metrics endpoint
PostgreSQL readiness
Redis readiness
storage readiness
request ID propagation
trace context propagation
worker telemetry
webhook telemetry
storage telemetry
Regression

Run the entire existing backend suite.

No existing milestone behavior may regress.

30. Security Tests

Explicitly test that telemetry does NOT expose:

bearer tokens
API client secrets
webhook secrets
passwords
authorization headers
storage credentials
raw evidence payloads
sensitive EXIF
private object-storage keys

Also test that metric labels cannot be influenced into high-cardinality identifiers.

31. Performance Requirements

Observability must introduce bounded overhead.

Measure:

API request overhead
metrics collection overhead
logging overhead
tracing overhead
worker overhead

Telemetry export must be asynchronous/non-blocking where supported.

Do not perform expensive synchronous telemetry operations inside critical request paths.

32. Docker / Local Development

Update development infrastructure where appropriate to support:

Backend
PostgreSQL/PostGIS
Redis
MinIO
Prometheus
Grafana

Optional OpenTelemetry collector support may be provided.

Do not make Grafana/Prometheus mandatory for the backend to boot in the default minimal development environment unless explicitly configured.

33. API Contract

Document new operational endpoints through FastAPI/OpenAPI.

Potential endpoints:

GET /health
GET /ready
GET /metrics

Preserve existing endpoint contracts.

Do not expose arbitrary internal debugging endpoints.

34. Files

Expected implementation areas:

backend/
├── observability/
│   ├── __init__.py
│   ├── metrics.py
│   ├── tracing.py
│   ├── logging.py
│   ├── redaction.py
│   └── health.py
│
├── core/
│   └── config.py
│
├── api/
│   └── ...
│
├── workers/
│   └── ...
│
tests/
├── unit/
│   └── test_observability.py
│
└── integration/
    └── test_observability.py

Adapt paths to the existing repository structure instead of blindly creating duplicate infrastructure.

35. Database Migration

BE-020 should NOT require a database migration unless implementation demonstrates a concrete need.

Do not create telemetry tables merely to make observability work.

Prometheus/OpenTelemetry are the primary telemetry stores.

Existing domain and audit tables remain authoritative for persistent application history.

36. No Scope Creep

BE-020 MUST NOT implement:

business analytics
project analytics
reviewer analytics
fraud detection
authenticity detection
deepfake detection
ML monitoring
model evaluation
fusion changes
evidence graph changes
review-case policy changes
citizen dashboards
reviewer dashboards
notification workflow changes
authentication redesign
authorization redesign
retention policy changes
external integration redesign
new evidence-processing capabilities

Those belong to other milestones.

37. Anti-Shortcut Requirements

The implementation MUST NOT:

fake metrics
return hard-coded health status
fabricate worker backlog
log sensitive data for debugging
use unbounded UUID labels
expose secrets in Prometheus
swallow application errors merely to make telemetry appear healthy
create a second audit system
replace request IDs with trace IDs
require Grafana for backend correctness
require OpenTelemetry infrastructure for basic application startup
add observability code that changes business behavior
silently modify existing API contracts
remove existing tests
weaken authorization to expose metrics
disable security checks for monitoring convenience
38. Verification Checklist

Before completion, verify:

Code
 OpenTelemetry integrated
 Prometheus metrics implemented
 Structured logging implemented
 Sensitive-data redaction implemented
 Request/trace correlation implemented
 Health/readiness semantics verified
 Worker telemetry implemented
 Storage telemetry implemented
 Webhook/integration telemetry implemented
 Bounded metric labels verified
 Configuration documented
Security
 No credentials in logs
 No credentials in metrics
 No raw evidence in telemetry
 No bearer tokens in telemetry
 No webhook secrets in telemetry
 Operational endpoints follow BE-016 authorization
 No second audit system introduced
Testing
 Unit tests pass
 Integration tests pass
 Security/redaction tests pass
 Full regression suite passes
 Health checks verified against live dependencies
 Prometheus endpoint verified
 Worker telemetry verified
 Webhook telemetry verified
 No high-cardinality labels detected
Performance
 API overhead measured
 Worker overhead measured
 Telemetry exporter failure tested
 Logging overhead measured
 No blocking telemetry dependency introduced
Git

Implementation commit:

BE-020: implement observability and system telemetry

Completion commit:

BE-020 Complete

Both commits should be pushed to:

origin/Backend

Do not rewrite history, force-push, reset, rebase, or delete existing branches.

39. Definition of Done

BE-020 is complete only when:

OpenTelemetry tracing is operational.
Prometheus metrics are operational.
Structured logs contain request/trace correlation.
Sensitive telemetry data is centrally redacted.
API, database, Redis, storage, worker, and integration behavior has operational telemetry.
Health and readiness semantics are correct.
Metrics use bounded labels.
Worker and webhook failures are observable.
Telemetry failure cannot take down the application.
Operational endpoints respect existing authorization.
No second audit mechanism has been introduced.
Grafana dashboard definitions are provided.
Baseline alert definitions are provided.
Unit tests pass.
Integration tests pass.
Full regression suite passes with zero regressions.
Security tests confirm secrets and sensitive evidence are not leaked.
Performance overhead has been measured.
No BE-021+ scope has leaked into the implementation.
Changes are committed and pushed to origin/Backend.
40. Final Architectural Boundary

After BE-020:

BE-001 → API Foundation
BE-002 → Storage
BE-003 → Evidence Ingestion
BE-004 → Fingerprinting
BE-005 → Async Analysis
BE-006 → Duplicate Intelligence
BE-007 → Projects / Claims / Spatial Context
BE-008 → Temporal Intelligence
BE-009 → Vision Intelligence
BE-010 → Evidence Graph
BE-011 → Fusion Engine
BE-012 → Explainability
BE-013 → Review Cases
BE-014 → Evidence Requests
BE-015 → Audit Ledger
BE-016 → Authentication / Authorization
BE-017 → Retention / Governance
BE-018 → Notifications / Event Delivery
BE-019 → External Integrations / API Clients
BE-020 → Observability / System Health

BE-020 provides the operational foundation required before exposing PoA as a production-grade platform.

The milestone must leave the existing domain semantics unchanged.