# BE-005 — Async Analysis Jobs

## 1. Objective

Introduce the asynchronous analysis-job infrastructure for Proof-of-Action (PoA).

BE-004 currently performs evidence fingerprinting synchronously. From BE-005 onward, evidence analysis must be capable of running through a persistent job system rather than blocking an API request.

The goal of BE-005 is **not to add new analysis intelligence**.

The goal is to establish a reliable execution layer that future analysis engines can use.

After BE-005, the architecture should support:

```text
Evidence Upload
      ↓
Create Analysis Job
      ↓
Queue Job
      ↓
Worker
      ↓
Execute Analysis Pipeline
      ↓
Persist Result
      ↓
Update Job Status
```

BE-005 should provide the infrastructure required for BE-006 and later analysis milestones.

---

# 2. Engineering Integrity / Anti-Shortcut Gate

> **Do not interpret "make it work" as "make a convincing demo."**
>
> Every implemented capability must perform the real underlying operation it claims to perform. Do not use fake values, hardcoded results, placeholder confidence scores, simulated analysis, mocked success paths, or fabricated evidence.
>
> If a capability cannot genuinely be implemented yet, fail clearly or mark it as unavailable rather than pretending it succeeded.
>
> Do not implement future milestone functionality early.
>
> Prefer deterministic, measurable operations over AI-generated assertions.
>
> Tests must verify actual behavior and outputs, not merely that a function was called.
>
> Never weaken validation or correctness simply to make tests pass.
>
> Do not hide errors, suppress failures, or convert unsuccessful operations into successful responses.
>
> Preserve completed milestones unless a genuine blocker requires a minimal compatibility fix.

---

# 3. Copilot Implementation Discipline

Before changing code:

1. Inspect the existing `Backend` branch.
2. Understand BE-001 through BE-004 contracts.
3. Inspect:
   - `AnalysisJob`
   - `AnalysisResult`
   - `Evidence`
   - `StorageService`
   - `fingerprinting.py`
   - API routing
   - database session
   - existing tests
   - existing configuration
4. Reuse existing abstractions.
5. Do not create duplicate storage, database, or configuration systems.
6. Do not refactor unrelated code.
7. Do not modify completed milestones unless required for compatibility with BE-005.
8. Do not introduce speculative architecture.
9. Do not add ML or analysis intelligence.
10. Do not add frontend functionality.
11. Execute the relevant tests after implementation.

Do not claim completion based solely on static inspection.

---

# 4. Scope

BE-005 includes:

- Redis-backed job queue infrastructure.
- Analysis job creation.
- Worker execution.
- Persistent job status.
- Job lifecycle handling.
- Retry-safe execution.
- Failure handling.
- Analysis result persistence.
- Basic job status API.
- Configuration for queue/worker infrastructure.
- Integration tests using real infrastructure.

BE-005 does **not** include new intelligence engines.

---

# 5. Explicitly Out of Scope

Do NOT implement:

- Embeddings.
- CLIP.
- SigLIP.
- Semantic similarity.
- Duplicate detection.
- SIFT.
- ORB.
- Geo validation.
- Temporal analysis.
- Vision detection.
- Manipulation detection.
- Authenticity scoring.
- Evidence Graph.
- Fusion engine.
- Risk scoring.
- Integrity scoring.
- Explainability engine.
- Human review workflow.
- ML models.
- Fraud classification.
- AI-generated conclusions.
- LLM analysis.
- Authentication.
- RBAC.
- Frontend.
- Blockchain.
- C2PA.
- External authenticity APIs.
- Production cloud deployment.
- Kubernetes.
- Distributed worker orchestration.

The worker infrastructure must exist so those capabilities can be added later.

It must not implement them now.

---

# 6. Architecture

Use the following architecture:

```text
                 ┌─────────────────────┐
                 │   FastAPI API       │
                 │                     │
                 │ Create Analysis Job │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ PostgreSQL          │
                 │                     │
                 │ analysis_jobs       │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Redis               │
                 │                     │
                 │ Job Queue           │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Analysis Worker     │
                 │                     │
                 │ Execute Job         │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Analysis Pipeline   │
                 │                     │
                 │ BE-004 fingerprint  │
                 │ processing           │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ PostgreSQL          │
                 │                     │
                 │ analysis_results    │
                 │ analysis_jobs       │
                 └─────────────────────┘
```

Redis is the transport/queue.

PostgreSQL remains the source of truth for job state and results.

Do not use Redis as the authoritative database for analysis-job state.

---

# 7. Queue Technology

Use the existing Redis dependency.

Do not introduce Celery/Dramatiq unless the existing project architecture genuinely requires it.

For BE-005, prefer a lightweight Python-native queue implementation using the existing Redis package.

The implementation must provide:

- enqueue
- dequeue
- acknowledgement
- retry handling
- worker execution
- failure handling

Keep the queue abstraction behind a service/interface so that the transport can be replaced later without rewriting the API or analysis pipeline.

---

# 8. Job Lifecycle

Define explicit job states.

Minimum states:

```text
queued
running
completed
failed
```

A job must never silently disappear.

Expected lifecycle:

```text
queued
   ↓
running
   ↓
completed
```

Failure:

```text
queued
   ↓
running
   ↓
failed
```

If retryable failure handling is implemented:

```text
queued
   ↓
running
   ↓
retry
   ↓
queued
```

Do not invent additional states unless they are required by the actual implementation.

---

# 9. AnalysisJob

Reuse the existing `AnalysisJob` database model.

Current BE-001 model:

```python
class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    evidence_id = Column(
        UUID(as_uuid=False),
        ForeignKey("evidence.id"),
        nullable=False,
    )
    status = Column(String(50), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
```

Inspect the current implementation before modifying it.

If BE-005 requires additional fields, add only fields necessary for reliable job execution.

Potential fields include:

```text
started_at
completed_at
attempt_count
error
```

Do not add speculative fields merely because they might be useful later.

If fields are added, create a proper reversible Alembic migration.

---

# 10. Job Identity

Every job must have a unique ID.

Do not use:

- evidence filename
- storage key
- SHA-256
- timestamp alone
- Redis task ID as the database primary key

The PostgreSQL `AnalysisJob.id` remains the canonical job identity.

---

# 11. Queue Payload

The queue payload should contain enough information to identify the job.

Prefer:

```json
{
  "job_id": "..."
}
```

The worker should retrieve the authoritative job from PostgreSQL using the job ID.

Do not put the entire evidence object into Redis.

Do not put image bytes into Redis.

Do not duplicate database state unnecessarily in Redis.

---

# 12. Job Creation

Create a service responsible for creating analysis jobs.

Expected flow:

```text
API request
    ↓
Validate evidence exists
    ↓
Create AnalysisJob(status="queued")
    ↓
Commit PostgreSQL transaction
    ↓
Enqueue job_id
    ↓
Return job information
```

The database record must exist before the queue message references it.

Do not enqueue an unknown job ID.

---

# 13. Queue Failure Handling

The API must not report a successfully queued job if the queue operation actually failed.

For example:

```text
PostgreSQL INSERT succeeds
Redis enqueue fails
```

must not become:

```text
HTTP 202
status = queued
```

with no recovery mechanism.

Implement a clear consistency strategy.

A minimal acceptable strategy for this milestone is:

1. Create the job.
2. Commit it.
3. Attempt queue enqueue.
4. If enqueue fails:
   - mark the job as failed or otherwise explicitly unavailable for processing,
   - persist the error,
   - return an appropriate error response.

Do not silently swallow Redis failures.

Do not fabricate successful queueing.

If a stronger transactional-outbox design is implemented, keep it minimal and document it. Do not turn BE-005 into a general distributed-systems redesign.

---

# 14. Worker

Create a worker entry point capable of running independently from FastAPI.

Example conceptual interface:

```text
python -m backend.workers.analysis_worker
```

The exact module path should follow the existing project structure.

The worker must:

1. Receive a `job_id`.
2. Retrieve the job from PostgreSQL.
3. Verify the job exists.
4. Verify the associated evidence exists.
5. Transition the job to `running`.
6. Execute the configured analysis pipeline.
7. Persist the analysis result.
8. Transition the job to `completed`.

On failure:

```text
running
   ↓
failed
```

with the failure persisted.

The worker must not report success when processing failed.

---

# 15. What the Worker Actually Executes

BE-005 must prove the worker can execute a **real existing analysis operation**.

Use BE-004 fingerprint processing as the initial worker operation.

The worker should invoke the existing fingerprinting service rather than duplicate its implementation.

Conceptually:

```text
Worker
  ↓
process_evidence(job.evidence_id)
  ↓
SHA-256
EXIF
pHash
  ↓
persist existing BE-004 results
  ↓
persist AnalysisResult
```

Do not rewrite BE-004 inside the worker.

Do not create fake analysis output simply to demonstrate asynchronous execution.

The worker must operate against actual stored evidence.

---

# 16. AnalysisResult

Reuse the existing `AnalysisResult` model.

Current structure includes:

```python
class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    job_id = Column(
        UUID(as_uuid=False),
        ForeignKey("analysis_jobs.id"),
        nullable=False,
    )
    result = Column(JSONB)
    embedding = Column(ARRAY(Float))
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
```

The existing `embedding` field is a future placeholder.

**Do not populate it in BE-005.**

For BE-005, `result` should contain the actual output generated by the executed BE-004 processing.

For example, conceptually:

```json
{
  "sha256": "...",
  "phash": "...",
  "exif_status": "success",
  "phash_status": "success"
}
```

Use the actual `FingerprintResult` output.

Do not fabricate values.

Do not add confidence scores.

Do not add integrity scores.

Do not add risk scores.

---

# 17. Idempotency

The worker must be safe against duplicate delivery.

Redis queue delivery and worker crashes can result in the same job being encountered more than once.

The implementation must prevent uncontrolled duplicate `AnalysisResult` records.

Before creating a result, determine whether the job already has a successful result.

A completed job should not be processed again simply because a duplicate queue message exists.

Do not delete duplicate queue messages blindly if the job state proves they are stale.

---

# 18. Worker Crash Safety

Consider this sequence:

```text
worker receives job
       ↓
job = running
       ↓
worker crashes
```

The database must not falsely claim:

```text
completed
```

when no result exists.

At minimum:

- only set `completed` after successful result persistence;
- only acknowledge the queue message after successful job handling;
- leave enough persisted state to diagnose a worker failure.

Do not claim full distributed exactly-once processing.

The target is **safe, observable, retry-aware execution**, not mathematically perfect exactly-once semantics.

---

# 19. Retry Policy

Implement a small bounded retry policy if supported by the chosen queue design.

For example:

```text
maximum attempts = configurable
```

The exact default should be reasonable and documented.

Do not retry permanent errors indefinitely.

Do not retry validation errors endlessly.

Do not create infinite retry loops.

If retry behavior is implemented, persist the attempt count.

After retry exhaustion:

```text
status = failed
```

and persist a useful error description.

---

# 20. Error Handling

Errors must remain visible.

Persist enough information to understand why a job failed.

Do not store:

- secrets
- credentials
- full image contents
- unnecessary EXIF data
- authorization tokens

Error messages should be concise and operationally useful.

Example:

```text
Failed to retrieve evidence object
```

is preferable to dumping an entire internal traceback into an API response.

Detailed tracebacks may remain in server logs where appropriate.

---

# 21. API

Add a minimal API for job creation/status.

Suggested endpoints:

```text
POST /api/v1/analysis/jobs
GET  /api/v1/analysis/jobs/{job_id}
```

### POST

Input:

```json
{
  "evidence_id": "..."
}
```

Expected behavior:

1. Validate evidence exists.
2. Create a queued job.
3. Persist job.
4. Enqueue job.
5. Return job ID and status.

Suggested response:

```json
{
  "job_id": "...",
  "evidence_id": "...",
  "status": "queued"
}
```

Use the project's existing Pydantic/FastAPI conventions.

Do not expose internal Redis implementation details.

---

# 22. GET Job Status

The status endpoint should retrieve the job from PostgreSQL.

Example:

```json
{
  "job_id": "...",
  "evidence_id": "...",
  "status": "completed"
}
```

For completed jobs, it may expose the persisted result if that follows the existing API conventions.

For failed jobs, expose a safe error description.

Do not expose internal stack traces.

---

# 23. API Status Codes

Use appropriate HTTP semantics.

At minimum:

```text
201 / 202 → job successfully created/queued
200       → job status retrieved
404       → job/evidence not found
4xx       → invalid request
5xx       → infrastructure failure
```

Choose the exact status codes based on the existing API conventions.

Do not return HTTP 200 for an operation that actually failed.

---

# 24. Redis Configuration

Add Redis configuration only if it does not already exist.

BE-001 already defines:

```text
redis_url
```

Reuse it.

Do not create another Redis URL setting.

The worker and API must use the same configured Redis endpoint.

Local development should continue using the existing Docker Compose Redis infrastructure if already present; if Redis is missing from the current Compose configuration, add the minimal Redis service required by BE-005.

Do not add unrelated infrastructure.

---

# 25. Docker Compose

If Redis is not already present, add:

```text
redis
```

to `docker-compose.yml`.

Keep it minimal.

The objective is local development/testing.

Do not add:

- Kubernetes
- Redis Sentinel
- Redis Cluster
- monitoring stacks
- distributed orchestration
- unnecessary containers

Verify that the actual Redis container is reachable from the backend/worker.

---

# 26. Service Boundaries

Recommended structure:

```text
backend/
├── api/
│   └── analysis.py
│
├── services/
│   ├── analysis_jobs.py
│   └── fingerprinting.py
│
├── workers/
│   └── analysis_worker.py
│
└── ...
```

The exact structure should follow the existing repository conventions.

Possible responsibilities:

### Analysis Job Service

```text
create_job()
enqueue_job()
get_job()
```

### Queue Service

```text
enqueue()
dequeue()
acknowledge()
retry()
```

### Worker

```text
consume queue
→ load job
→ execute processing
→ persist result
→ update status
```

Keep queue-specific code out of the API endpoint wherever practical.

---

# 27. Transaction Boundaries

Be deliberate about database transactions.

Recommended sequence:

```text
Create job
→ commit
→ enqueue
```

Worker:

```text
Load job
→ mark running
→ commit

Execute analysis

Persist result
→ mark completed
→ commit

Acknowledge queue message
```

Do not hold one PostgreSQL transaction open while processing an image.

Do not hold database locks during analysis.

---

# 28. Concurrency

The implementation should tolerate multiple workers processing different jobs.

A worker must not blindly take ownership of a job already marked `running`, `completed`, or `failed`.

Use an atomic/state-aware transition where practical.

At minimum:

```text
queued → running
```

must be guarded so two workers do not both execute the same job under normal duplicate-delivery conditions.

Do not claim perfect distributed locking unless actually implemented and tested.

---

# 29. Tests

Tests are mandatory.

They must test actual behavior.

## Unit Tests

Test:

1. Queue enqueue/dequeue.
2. Job state transitions.
3. Invalid job IDs.
4. Missing evidence.
5. Successful worker execution.
6. Failed worker execution.
7. Retry behavior.
8. Duplicate job delivery/idempotency.
9. Result persistence.
10. No false completion.

---

# 30. Integration Tests

Use real:

```text
PostgreSQL
Redis
MinIO
```

where infrastructure-dependent behavior is being tested.

Do not replace the complete queue/database/storage flow with mocks.

At minimum verify:

### Test 1 — Job creation

```text
POST job
→ PostgreSQL job exists
→ status = queued
→ Redis message exists
```

### Test 2 — Worker execution

```text
queued job
→ worker
→ actual BE-004 fingerprinting
→ AnalysisResult persisted
→ status = completed
```

### Test 3 — Real evidence

Use actual evidence bytes stored in MinIO.

Verify the resulting SHA-256/pHash correspond to the actual evidence.

Do not hardcode expected values unless the fixture's known bytes make those values independently verifiable.

### Test 4 — Failure

Cause a real processing failure.

Verify:

```text
status = failed
```

and no false successful result is created.

### Test 5 — Duplicate delivery

Deliver the same job more than once.

Verify that processing does not create uncontrolled duplicate successful results.

### Test 6 — Worker/API separation

Verify that creating the job does not perform the full analysis synchronously inside the API request.

The API should create/enqueue the job; the worker performs processing.

---

# 31. Test Integrity

Do not write tests such as:

```python
mock_worker.assert_called_once()
```

as the primary proof that asynchronous processing works.

Tests must verify actual outcomes:

```text
job state
Redis queue state
database result
real evidence fingerprint
```

Mocks may be used for narrow unit tests of failure boundaries, but the critical end-to-end path must use real infrastructure.

---

# 32. BE-004 Compatibility

Do not break BE-004.

The existing synchronous fingerprinting service should remain usable.

BE-005 should call it rather than replacing it.

The following must remain true:

```text
SHA-256 = actual stored evidence bytes
EXIF = actual image metadata
pHash = actual image perceptual hash
```

No changes should weaken BE-004 validation or persistence.

---

# 33. Documentation

Update the relevant backend documentation.

Document:

- Redis requirement.
- Worker startup command.
- Job lifecycle.
- API endpoints.
- Local development setup.
- Retry behavior.
- Failure behavior.

Do not create a huge architecture document unless the repository structure requires it.

Keep documentation focused on BE-005.

---

# 34. Dependencies

Reuse existing dependencies whenever possible.

Existing relevant dependency:

```text
redis
```

Do not add Celery/Dramatiq/RQ/etc. unless inspection shows the project already depends on one.

Do not add ML dependencies.

Do not add unnecessary infrastructure dependencies.

If a dependency is genuinely required, pin it consistently with the existing project dependency strategy.

---

# 35. Migration

If the existing `analysis_jobs` / `analysis_results` schema requires changes:

Create a new reversible Alembic migration.

Example:

```text
alembic/versions/<revision>_be005_async_analysis_jobs.py
```

The migration must support:

```text
upgrade
downgrade
```

Do not modify historical migrations.

Do not manually alter the database outside Alembic.

---

# 36. Security

Ensure:

- Redis credentials/configuration come from configuration.
- No credentials are logged.
- Job IDs are validated.
- Evidence IDs are validated.
- Internal Redis errors are not exposed unnecessarily.
- Worker exceptions do not leak sensitive data.
- Image bytes never enter Redis.
- EXIF data is not unnecessarily logged.
- Queue payloads contain only required identifiers.

Authentication/RBAC is future scope and must not be implemented here.

---

# 37. Performance

The worker should not unnecessarily download the same evidence multiple times.

BE-004 already retrieves the evidence object for fingerprinting.

Reuse that implementation.

Do not optimize prematurely.

Do not add distributed caching.

Do not add GPU infrastructure.

Do not add batch processing.

---

# 38. Observability

Provide useful logs for:

```text
job created
job queued
job started
job completed
job failed
job retried
```

Include the job ID where useful.

Do not log:

- image contents
- secrets
- credentials
- unnecessary EXIF
- authorization tokens

Preserve the existing request-ID/logging behavior.

Do not perform unrelated logging refactors.

---

# 39. Definition of Done

BE-005 is complete only when all applicable items are true:

- [ ] Redis queue is operational.
- [ ] Queue abstraction exists.
- [ ] Analysis jobs can be created.
- [ ] Jobs are persisted in PostgreSQL.
- [ ] Jobs can be enqueued.
- [ ] Independent worker can consume jobs.
- [ ] Worker retrieves jobs from PostgreSQL.
- [ ] Worker executes the real BE-004 fingerprinting operation.
- [ ] SHA-256 remains based on actual evidence bytes.
- [ ] EXIF remains based on actual image metadata.
- [ ] pHash remains based on actual image content.
- [ ] AnalysisResult is persisted.
- [ ] Job transitions to `completed` only after successful processing.
- [ ] Failed jobs become `failed`.
- [ ] Queue/worker failures are not silently converted into success.
- [ ] Duplicate delivery does not create uncontrolled duplicate successful results.
- [ ] Retry behavior is bounded if implemented.
- [ ] Job status API works.
- [ ] Real PostgreSQL integration tests pass.
- [ ] Real Redis integration tests pass.
- [ ] Real MinIO-backed evidence processing passes.
- [ ] Full existing test suite passes.
- [ ] Alembic migration, if required, upgrades successfully.
- [ ] Alembic downgrade works.
- [ ] Documentation is updated.
- [ ] No fake/demo analysis results exist.
- [ ] No BE-006+ functionality was implemented.

---

# 40. Required Verification

Run:

```bash
python -m alembic upgrade head
```

Then:

```bash
python -m pytest -q
```

Also run focused BE-005 tests.

If Docker infrastructure is required:

```bash
docker compose up -d
```

Verify Redis is actually reachable.

Verify MinIO is actually reachable.

Verify PostgreSQL is actually reachable.

Verify the worker can process a real evidence object.

Do not claim success from static code inspection.

---

# 41. Final Copilot Response

When implementation is complete, report exactly:

### 1. Files changed

List every modified/created file.

### 2. BE-005 functionality

Briefly explain:

- queue
- job creation
- worker
- state transitions
- result persistence
- retry/failure handling

### 3. Database changes

List:

- migrations
- model changes
- new indexes/fields if any

### 4. Infrastructure

Report:

- Redis status
- PostgreSQL status
- MinIO status
- worker startup/verification

### 5. Tests executed

List the exact commands.

### 6. Test results

Report exact numbers.

Example:

```text
Focused BE-005 tests: X passed
Full suite: X passed
```

### 7. Warnings

List warnings without hiding them.

### 8. Blockers

State:

```text
None
```

if genuinely none exist.

### 9. Confirmation

Explicitly confirm:

- real Redis queue used;
- real PostgreSQL job state used;
- real worker executed;
- real MinIO evidence processed;
- real BE-004 fingerprinting executed;
- AnalysisResult persisted;
- failed jobs are not reported as successful;
- duplicate processing is controlled;
- no fake/demo values were introduced;
- no BE-006+ functionality was implemented.

If any of these are not true, state the limitation instead of claiming completion.

---

# 42. Milestone Boundary

BE-005 ends here.

The next milestone is:

```text
BE-006 — Embeddings + Duplicate Intelligence
```

BE-006 will build actual duplicate/semantic similarity capabilities on top of the asynchronous execution infrastructure established here.

Do not implement BE-006 during BE-005.