# Object Storage Foundation

The backend uses one `StorageService` abstraction backed by an S3-compatible client:

```text
Application -> StorageService -> MinIO locally / Amazon S3 in production
```

## Local setup

From the repository root:

```bash
docker compose up -d
```

The Compose stack starts PostgreSQL and MinIO. An idempotent initialization container creates the private buckets:

- `pofa-quarantine`
- `pofa-evidence`

MinIO's API is available on `localhost:9000` and its console on `localhost:9001`. The persistent `minio_data` volume keeps objects across container restarts.

## Configuration

Set these variables in the untracked `.env` file. `.env.example` contains safe local placeholders:

```text
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_REGION=us-east-1
S3_USE_SSL=false
S3_QUARANTINE_BUCKET=pofa-quarantine
S3_EVIDENCE_BUCKET=pofa-evidence
MAX_UPLOAD_SIZE=10485760
```

For production, point `S3_ENDPOINT` and credentials at the selected S3-compatible provider and set `S3_USE_SSL=true`.

## Object keys

The service generates keys from trusted evidence identifiers:

```text
quarantine/{evidence_id}/original
evidence/{evidence_id}/original
evidence/{evidence_id}/derived/{artifact}
```

The storage layer provides presigned upload and download URLs, object existence and metadata checks, server-side copy/promotion, and deletion. It keeps buckets private and does not implement upload validation or evidence processing.

## Evidence upload

`POST /api/v1/evidence` accepts a multipart form field named `file`. The endpoint supports JPEG, PNG, and WebP images up to `MAX_UPLOAD_SIZE` bytes (10 MiB by default). It verifies that the content is a readable image, stores the original in `pofa-quarantine` under `quarantine/{evidence_id}/original`, and creates an `uploaded_quarantine` Evidence record.

The response contains the generated `evidence_id`, the `uploaded` response status, the quarantine `storage_key`, the validated `content_type`, and the byte `size`. Client filenames are retained only as metadata and never control object keys.

## Evidence fingerprints

BE-004 processes the original quarantine object bytes and persists three independent signals:

- `Evidence.sha256` stores the complete lowercase SHA-256 digest for exact byte identity.
- `Evidence.phash` stores the deterministic perceptual hash for visual comparison foundations.
- `EvidenceMetadata.metadata` stores extracted EXIF values and an explicit EXIF status. Images without EXIF use `no_metadata`; they are not treated as invalid.

Fingerprinting does not alter the original object, make duplicate or fraud decisions, validate GPS or timestamps, or start background jobs.

## Asynchronous analysis jobs

BE-005 adds Redis-backed asynchronous execution for the existing BE-004 fingerprinting operation. Start the local infrastructure with `docker compose up -d`, then run the worker with:

```text
python -m backend.workers.analysis_worker
```

Create a job with `POST /api/v1/analysis/jobs` and a JSON body containing `evidence_id`. Retrieve its PostgreSQL-backed state with `GET /api/v1/analysis/jobs/{job_id}`. Jobs move through `queued`, `running`, `completed`, or `failed`; processing retries up to `ANALYSIS_MAX_ATTEMPTS` (3 by default). Redis carries only the job ID, while PostgreSQL remains authoritative for state and results.

The worker invokes the existing BE-004 fingerprinting service and persists the real SHA-256, pHash, and EXIF status in `AnalysisResult`. It does not perform duplicate, fraud, risk, or other later-milestone analysis.

### Redis outages and tuning

Redis carries job IDs only; PostgreSQL stays authoritative for job state. That
division decides what "surviving an outage" means for the worker: it keeps the
process alive, stops touching the queue for a while, and re-checks for work left
behind once the connection works again. It never exits because Redis is down,
because exiting would strand the jobs that are already sitting in Redis.

All of the settings below are seconds and are read once at worker start.

| Variable | Default | What it controls |
| --- | --- | --- |
| `ANALYSIS_RETRY_BACKOFF_BASE_SECONDS` | `1.0` | The exponential term's starting point. For the Nth consecutive failure the term is `min(max, base * 2 ** (N - 1))`, and the wait slept is half of that term plus a uniform draw of the other half — so the first wait of an outage falls between `base/2` and `base`, the next between `base` and `2 * base`, and so on. With the default `base` of `1.0` and this run's `base` of `5`, the observed first waits were 3.4–4.9 s out of the possible 2.5–5 s band. |
| `ANALYSIS_RETRY_BACKOFF_MAX_SECONDS` | `60.0` | The ceiling on the term, hence on any single wait: once `base * 2 ** (N - 1)` reaches it the outage settles at a steady poll rate between `max/2` and `max` instead of growing further. Nothing validates the pair, so a `base` above `max` is accepted and simply starts every wait at the ceiling. |
| `ANALYSIS_SHUTDOWN_POLL_SECONDS` | `0.5` | How finely a backoff wait is sliced. It bounds SIGTERM latency only while the worker is waiting out a backoff; while it is parked in a blocked dequeue the bound is `ANALYSIS_DEQUEUE_BLOCK_SECONDS` (see "Shutdown latency" below). |
| `ANALYSIS_REDIS_SOCKET_TIMEOUT_SECONDS` | `30.0` | Read deadline on the queue connection. |
| `ANALYSIS_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS` | `10.0` | Deadline for establishing the TCP connection. |
| `ANALYSIS_REDIS_HEALTH_CHECK_INTERVAL_SECONDS` | `15.0` | Reuse-check frequency for an idle connection. |
| `ANALYSIS_DEQUEUE_BLOCK_SECONDS` | `5` | How long the blocking dequeue waits for a message before returning "nothing". |
| `ANALYSIS_ABANDONED_TIMEOUT_SECONDS` | `300` | Age past which a `running` job's processing-list entry counts as abandoned. |
| `ANALYSIS_MAX_ATTEMPTS` | `3` | Delivery attempts before a job is settled as `failed`. |

**How these values reach the process.** `Settings` (Pydantic) reads the process
environment, with `.env` as a fallback file. For a worker started directly with
`python -m backend.workers.analysis_worker` in the repository root, that means
the `.env` entries above apply as documented. For the Compose stack it does not,
as measured against the current files: the shared environment block the worker
service inherits (`x-app-environment` in `docker-compose.yml`) is an explicit
list and forwards none of the `ANALYSIS_*` names, and `.dockerignore` excludes
`.env` from the image. A containerised worker therefore runs on the compiled
defaults in `backend/core/config.py` regardless of what the host `.env` says,
until the variable is also added to that block (or to a per-service
`env_file:`). Tuning an outage's poll rate or the socket deadline on a deployed
worker is a compose-file change plus a redeploy, not an `.env` edit — the
defaults are chosen so that doing nothing is the safe option.

**Backoff shape.** A single consecutive failure yields
`min(MAX, BASE * 2 ** (failures - 1))`, and the worker sleeps half of that plus a
random draw of the other half. With the defaults, the waits cluster around 1s,
2s, 4s, 8s… and then hold between 30 and 60 seconds for the rest of a long
outage. The random half exists so several workers that lost Redis at the same
instant do not all come back on the same tick; it means the waits are not
exactly those numbers, and you should not read an individual interval as a
guarantee. Raising `BASE` lengthens every wait; raising `MAX` only postpones the
point where the poll rate flattens out; lowering either makes the worker notice
recovery sooner at the cost of more connection attempts.

**Validation.** There is exactly one rule the code enforces in this group:
`ANALYSIS_REDIS_SOCKET_TIMEOUT_SECONDS` must be strictly greater than
`ANALYSIS_DEQUEUE_BLOCK_SECONDS`. An idle blocking dequeue is *supposed* to end
on the server side with "no message"; a socket deadline at or below it would
report every idle poll as an outage, so the queue raises `ValueError` at
construction and the worker refuses to start. Nothing else in the group is range
or bounds-validated: the values are passed through as floats, and setting the
backoff base to `0` removes the wait entirely, which turns a Redis outage into a
tight reconnect loop. Keep them positive and treat the defaults as the reviewed
configuration. `ENVIRONMENT=production` triggers the separate security fail-fast
in `backend/core/config.py` (JWT secret, `AUTH_MODE`, dev tokens, wildcard
CORS); it does not check any of these timing values.

**Why the socket timeout is the important one.** Measured against a disposable
Redis with the redis-py 4.6.0 defaults these settings replace (all three
bounds unset): a server that stops answering *without* closing the connection —
the shape a frozen container, a network blackhole, or a pause produces — left
`ping` and the blocking `brpoplpush` hanging well past a 45-second budget. A
worker inside that hang reaches neither the outage handler nor its shutdown
check, so the difference between "backing off" and "apparently alive but doing
nothing" is whether the read itself has a deadline. `health_check_interval`
complements it rather than replacing it: redis-py checks the socket *before*
issuing the next command, never mid-reply, so it catches a silently dead idle
connection and cannot help a read already in flight.

**Shutdown latency.** Two different waits, two different costs — both measured
with the worker as container PID 1 (image `poa-backend:be037final`, `docker
stop`, each grace period set far above the observed latency so no case was
decided by SIGKILL):

- A **backoff wait** is slept in slices of `ANALYSIS_SHUTDOWN_POLL_SECONDS`,
  checking for the SIGTERM flag between slices (a single `time.sleep` would not
  be interruptible: CPython resumes the remaining time after the handler
  returns). With a 35.6 s wait already in progress, `docker stop` returned in
  **1.25 s** and the worker exited 0 — the cost is the poll interval, not the
  rest of the wait.
- A **blocked dequeue** is one unsliceable `brpoplpush` read: the flag is only
  checked when the read returns, so stopping an idle worker waits for the rest
  of `ANALYSIS_DEQUEUE_BLOCK_SECONDS`. Measured **18.62 s** at a 20 s block
  versus **1.5 s** at a 1 s block, exit 0 in both.

So `ANALYSIS_DEQUEUE_BLOCK_SECONDS`, not the poll interval, is the knob that
decides how long an idle worker takes to stop; keep it well inside the
deployment's `stop_grace_period` while still strictly below the socket timeout.
Ctrl-C takes the same path. All cases exited 0 with `RestartCount` 0 after
logging `analysis worker stopping; releasing queue and database resources` and
`analysis worker stopped`, i.e. the queue connection and the pooled DB
connections are released rather than dropped.

**Diagnosing repeated Redis disconnections.** The worker's own log lines
distinguish the cases:

- `redis unavailable; backing off <n>s (consecutive failures <k>)` (WARNING) —
  one counted failure, whatever transient error produced it. Isolated lines that
  reset to `failures 1` are brief blips, which is normal churn.
- `redis reachable again after <k> backoff(s)` (INFO) — the end of an outage
  streak; the failure counter and the recovery pass are keyed to this. Any
  dequeue that returns ends the streak, including one that returns no payload,
  so an idle queue proves reachability just as a delivered message does. A
  worker that logs this repeatedly is losing an established connection, not
  failing to start one.
- `analysis worker recovered <n> abandoned job(s)` (INFO) — after reconnecting,
  the first thing the loop does is reclassify processing-list entries using
  PostgreSQL state (terminal or unknown jobs are discarded, `queued`/stale
  `running` ones are requeued, a fresh `running` job is left with its live
  worker). Repeated non-zero counts alongside backoff warnings mean deliveries
  are being interrupted mid-flight.

The one Redis error the worker deliberately does **not** wait out is
`AuthenticationError` (bad credentials, or a `REDIS_URL` pointing somewhere that
isn't Redis). It catches the same class as connection errors, so a misconfigured
deployment would otherwise be indistinguishable from an outage and would poll
quietly forever; instead it propagates, the process exits, and the container
restart is a real signal. Corollary for operators: a worker that restarts in a
loop is *not* showing the backoff behaviour — look for the exception in its last
log lines. Conversely, "the worker is up but jobs are not moving" is the outage
path, and the checks are `LLEN <queue>` / `LLEN <queue>:processing` plus whether
the WARNING lines are growing.

**Consequences for latency.** An outage delays delivery, never discards it:
messages stay in the main list, and an interrupted delivery stays in the
processing list until a recovery pass requeues it, so a job's end-to-end delay
is bounded by the current backoff wait plus the recovery pass it lands in, and a
duplicate delivery is possible (handled idempotently by the completed/failed
guards). Recovery only runs while the worker is up and Redis answers, so a job
abandoned by a crashed worker waits for `ANALYSIS_ABANDONED_TIMEOUT_SECONDS`
before another worker may take it. There is no dead-letter queue and no
independent watchdog: if the last worker exits while Redis is down, the work
waits for a worker to start again.

## Duplicate intelligence

BE-006 preserves duplicate signals independently. Exact candidates use equality of persisted SHA-256 values; perceptual candidates use the Hamming distance between persisted pHash values and `PHASH_MAX_HAMMING_DISTANCE` (8 by default). Candidate pairs are stored symmetrically and idempotently in `duplicate_matches` with signal provenance.

The embedding schema is PostgreSQL `VECTOR(512)` and the configured real model is `openai/clip-vit-base-patch32`, with normalized cosine-compatible vectors. Semantic search uses the latest persisted embedding per evidence, excludes the current evidence/job, and persists `embedding_similarity = 1 - cosine_distance` in `duplicate_matches`. Embedding generation is explicit: when a compatible `torch` and `transformers` runtime is installed, the worker computes and persists the real image embedding; otherwise the result records `embedding_status=unavailable` and no vector or semantic similarity is claimed. No fabricated vectors or scores are used.