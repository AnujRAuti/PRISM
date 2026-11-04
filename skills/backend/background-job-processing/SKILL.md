---
name: background-job-processing
description: Build reliable background workers—job schemas, at-least-once execution, idempotency, retries and backoff, scheduling, concurrency limits, and graceful shutdown.
metadata:
  domain: backend
  version: 1.0.0
  risk: high
---

# Background Job Processing

## 1. Purpose

Run work outside the request cycle without losing it, duplicating it, or starving the database. Background jobs are where "the email was never sent", "the invoice was charged twice", and "the worker ate all the connections" happen. This skill covers job design, dispatch guarantees, idempotency, retry policy, scheduling and cron correctness, concurrency and rate control, graceful shutdown, and observability.

**Scope:** your own workers and queues. Jobs often hold elevated privileges (mail, payments, deletions); each job must re-check authorization and must not accept parameters that grant more access than the requester had.

## 2. Activation Conditions

- Work takes longer than a request budget (exports, encoding, syncs).
- Periodic tasks (cleanup, reconciliation, digests).
- Retries needed for unreliable external services.
- Need to fan out work across workers.
- Keywords: Celery, RQ, BullMQ, Sidekiq, Dramatiq, arq, worker, cron, scheduler, retry, backoff, idempotency, visibility timeout, graceful shutdown, concurrency.

## 3. When Not to Use

- Work that must complete before the response (keep it synchronous and fast).
- Sub-millisecond work where queue overhead dominates.
- Continuous stream processing (use a stream processor, not a job queue).

## 4. Required Context

1. Queue/broker in use and its delivery semantics.
2. Job inventory: inputs, side effects, expected duration, failure modes.
3. Schedule requirements and timezone.
4. Concurrency limits (database connections, third-party rate limits).
5. Deployment model (containers, autoscaling, rolling updates).

## 5. Operating Procedure

1. **Model jobs as small, explicit units** with a typed payload: `{job_type, version, idempotency_key, params}`. Keep payloads small — pass IDs, fetch state inside the job.
2. **Assume at-least-once delivery** and make every job idempotent: a unique constraint on `(job_type, idempotency_key)` or a business-level guard.
3. **Enqueue with the transaction** that creates the obligation (outbox), not before it commits.
4. **Classify failures**: transient (retry with exponential backoff + jitter), permanent (no retry, route to a dead/error queue, alert), and unknown (limited retries).
5. **Set time limits** per job (soft timeout to clean up, hard timeout to kill) and ensure the worker can't hold a database transaction for the job's full duration.
6. **Bound concurrency**: per-queue worker counts, plus per-resource concurrency if a downstream API has limits.
7. **Schedule with explicit timezones and missed-run policy**: what happens if the scheduler was down for an hour? Use distributed locks so cron runs once across instances.
8. **Shut down gracefully**: stop accepting, finish in-flight jobs within a deadline, then exit; re-deliver unfinished work.
9. **Record every attempt**: attempt count, last error class, duration, and a correlation ID propagated to logs and downstream calls.
10. **Alert on queue age, failure rate, and staleness of periodic jobs** (a missed nightly job is an outage even if no errors appear).

## 6. Tools and Technologies

| Stack | Options |
|---|---|
| Python | Celery, RQ, Dramatiq, arq, Huey |
| Node/TS | BullMQ, Graphile Worker, Agenda |
| Ruby | Sidekiq |
| Scheduling | Celery beat, APScheduler, cron + supervisor, Kubernetes CronJob |
| Durable workflows | Temporal, Inngest, Restate |
| Locks | Redis `SET NX PX`, Postgres advisory locks |
| Observability | Flower, Bull Board, OpenTelemetry spans per job |

## 7. Practical Implementation

**Job table for dedupe and audit (works with any queue):**

```sql
CREATE TABLE job_run (
  id               bigserial PRIMARY KEY,
  job_type         text        NOT NULL,
  idempotency_key  text        NOT NULL,
  status           text        NOT NULL CHECK (status IN ('queued','running','succeeded','failed','dead')),
  attempts         int         NOT NULL DEFAULT 0,
  last_error       text,
  payload          jsonb       NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  started_at       timestamptz,
  finished_at      timestamptz,
  UNIQUE (job_type, idempotency_key)
);
CREATE INDEX job_run_stale ON job_run (job_type, finished_at) WHERE status = 'running';
```

**Enqueue inside the business transaction (outbox), then dispatch:**

```python
async def request_export(session: AsyncSession, principal: Principal, report_id: str) -> None:
    async with session.begin():
        await session.execute(
            """INSERT INTO job_run (job_type, idempotency_key, status, payload)
               VALUES ('report.export', :key, 'queued', :payload)
               ON CONFLICT (job_type, idempotency_key) DO NOTHING""",
            {"key": f"report:{report_id}:{principal.user_id}",
             "payload": {"report_id": report_id, "tenant_id": principal.tenant_id,
                         "requested_by": principal.user_id}},
        )
        await session.execute(
            "INSERT INTO outbox (aggregate_id, event_type, payload) VALUES (:id, 'job.dispatch', :p)",
            {"id": report_id, "p": {"job_type": "report.export", "key": f"report:{report_id}:{principal.user_id}"}},
        )
```

**Idempotent worker with claim-and-run semantics:**

```python
import asyncio, logging
from sqlalchemy import text

log = logging.getLogger(__name__)

async def run_job(session_factory, job_type: str, key: str) -> None:
    async with session_factory() as session, session.begin():
        claimed = (await session.execute(text("""
            UPDATE job_run SET status = 'running', attempts = attempts + 1, started_at = now()
            WHERE job_type = :t AND idempotency_key = :k
              AND status IN ('queued','failed')
            RETURNING id, payload, attempts
        """), {"t": job_type, "k": key})).first()

    if claimed is None:
        log.info("job already handled", extra={"job_type": job_type, "key": key})
        return

    job_id, payload, attempt = claimed
    try:
        await HANDLERS[job_type](payload)
    except TransientJobError as exc:
        await mark_failed(session_factory, job_id, str(exc), retry_in=backoff_seconds(attempt))
        raise                                   # let the broker schedule the retry
    except Exception as exc:
        await mark_dead(session_factory, job_id, repr(exc))
        log.exception("job failed permanently", extra={"job_id": job_id})
    else:
        await mark_succeeded(session_factory, job_id)
```

**Backoff with jitter and a cap:**

```python
import random

def backoff_seconds(attempt: int, base: float = 5.0, cap: float = 900.0) -> float:
    return min(cap, base * 2 ** (attempt - 1)) * random.uniform(0.5, 1.5)
```

**Celery configuration with limits, acks-late, and prefetch:**

```python
from celery import Celery

app = Celery("worker", broker=settings.broker_url, backend=settings.result_backend)

app.conf.update(
    task_acks_late=True,                    # ack only after success
    task_reject_on_worker_lost=True,        # requeue if the worker dies
    worker_prefetch_multiplier=1,           # no hoarding by one worker
    task_time_limit=600,                    # hard kill
    task_soft_time_limit=540,               # raises SoftTimeLimitExceeded for cleanup
    worker_max_tasks_per_child=200,         # bound memory growth from leaks
    broker_transport_options={"visibility_timeout": 3600},
)

@app.task(bind=True, name="report.export", max_retries=5,
          autoretry_for=(TransientJobError,), retry_backoff=True, retry_jitter=True)
def export_report(self, payload: dict) -> None:
    handle_export(payload)
```

**BullMQ equivalent (Node/TS):**

```ts
import {Queue, Worker} from "bullmq";

export const exportQueue = new Queue("reports", {connection});

export const worker = new Worker(
  "reports",
  async (job) => {
    await handleExport(job.data);
  },
  {
    connection,
    concurrency: 10,
    lockDuration: 60_000,
    attempts: 5,
    backoff: {type: "exponential", delay: 5_000},
    removeOnComplete: {age: 86_400, count: 5_000},
    removeOnFail: false,
  },
);
```

**Single-run cron across instances (advisory lock):**

```python
async def run_daily_reconciliation(session_factory) -> None:
    async with session_factory() as session:
        got = (await session.execute(
            text("SELECT pg_try_advisory_lock(hashtext('daily-reconciliation'))")
        )).scalar()
        if not got:
            return                                  # another instance is running it
        try:
            await reconcile(session)
        finally:
            await session.execute(text("SELECT pg_advisory_unlock(hashtext('daily-reconciliation'))"))
```

**Missed-run policy for schedulers:**

```python
# Run the digest for yesterday only if it has not already been recorded
async def digest_job(session):
    target_day = (datetime.now(tz=ZoneInfo("Asia/Kolkata")) - timedelta(days=1)).date()
    if await already_ran(session, "daily.digest", target_day):
        return
    await send_digests(session, target_day)
    await record_run(session, "daily.digest", target_day)
```

**Graceful shutdown:**

```python
import signal, asyncio

stop = asyncio.Event()

def _handle(*_):
    stop.set()

signal.signal(signal.SIGTERM, _handle)
signal.signal(signal.SIGINT, _handle)

async def main() -> None:
    worker_task = asyncio.create_task(consume())
    await stop.wait()
    log.info("shutting down: finishing in-flight jobs")
    await asyncio.wait_for(worker_task, timeout=25)     # Kubernetes default grace is 30 s
```

**Per-resource concurrency (respect a downstream rate limit):**

```python
semaphores = {"payments-api": asyncio.Semaphore(5)}

async def call_payments(fn, *args):
    async with semaphores["payments-api"]:
        return await fn(*args)
```

**Metrics that matter:**

```text
job_queue_age_seconds{queue}             -> alert if p95 > 300
job_failures_total{job_type,error_class} -> alert on rate spike
job_dead_total{job_type}                 -> alert on any increase
cron_last_success_timestamp{name}        -> alert if older than 2× interval
job_duration_seconds{job_type}           -> p99 tracking
```

## 8. Quality Standards

- Every job is idempotent and safe to run twice.
- Jobs are enqueued with the committing transaction (no lost work on crash).
- Retry classification is explicit per job; permanent failures do not retry.
- Timeouts exist at soft and hard levels; jobs never hold DB transactions across external calls.
- Concurrency is bounded per queue and per downstream dependency.
- Scheduled jobs are safe with multiple instances (advisory lock or leader election) and have a missed-run policy.
- Shutdown drains in-flight work within the platform's grace period.
- Attempt history, error class, and duration are recorded.

## 9. Verification and Testing

- Run the same job twice with the same idempotency key; assert one side effect.
- Kill a worker mid-job; the job is retried and completes once.
- Force a transient error three times, then success; assert backoff delays increase with jitter and the job succeeds.
- Send a poison payload; it lands in `dead` without endless retries.
- Cron test: run two scheduler instances concurrently; exactly one executes.
- Graceful shutdown test: send SIGTERM during a long job; it finishes or is re-delivered, never half-committed.
- Load test: enqueue 10k jobs, verify queue age returns to baseline.

## 10. Security Considerations

- Job payloads must not carry long-lived credentials or full PII; pass IDs and re-authorize inside the job.
- A job runs with system privileges—validate that the original actor was entitled to the action, and record the actor for audit.
- Deserialize payloads with explicit schemas; never `pickle`/`eval` job bodies from the broker.
- Broker credentials are high-value: a compromised queue can trigger arbitrary privileged jobs. Use per-queue ACLs and rotation.
- Jobs that delete or export data must enforce tenant scoping and quotas.
- Retries must not replay a payment without an idempotency key at the provider.
- Dead-letter payloads may contain sensitive data; restrict access and set retention.

## 11. Failure Handling

- **Duplicate emails/charges:** the job was not idempotent or acked before completion; ack late and dedupe with a key.
- **Job runs forever:** no timeout, or a blocking call without a deadline; add timeouts and propagate cancellation.
- **Queue age grows during deploys:** workers restart and lose prefetched jobs; use acks-late with requeue-on-worker-lost.
- **Database connection exhaustion:** too many worker processes; size pools as `workers × pool_size + API pools < max_connections`, or use PgBouncer.
- **Missed nightly job silently:** no freshness alert; add `cron_last_success_timestamp` monitoring.
- **Retry storm after an outage:** retries all fire at once; exponential backoff with jitter plus a global rate limit.

## 12. Expected Deliverables

1. Job inventory with payload schemas and side effects.
2. Idempotency strategy per job.
3. Retry/backoff/DLQ policy and error classification.
4. Timeout and concurrency configuration.
5. Schedule table with timezones and missed-run behavior.
6. Graceful shutdown procedure.
7. Metrics, alerts, and runbook for dead jobs.

## 13. References

- Celery documentation — https://docs.celeryq.dev/en/stable/
- Celery task retries and acks_late — https://docs.celeryq.dev/en/stable/userguide/tasks.html#task-options
- BullMQ documentation — https://docs.bullmq.io/
- Sidekiq best practices (reliability) — https://github.com/sidekiq/sidekiq/wiki/Best-Practices
- PostgreSQL advisory locks — https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS
- Kubernetes pod lifecycle / graceful termination — https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
- Temporal (durable workflows) — https://docs.temporal.io/
- RQ documentation — https://python-rq.org/docs/
