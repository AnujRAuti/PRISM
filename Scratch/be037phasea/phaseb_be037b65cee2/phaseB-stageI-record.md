# BE-037 Phase B — Stage I record: operational and failure checks

Run: `be037b_20261013T062257Z_65cee2` (disposable stack, prefix `be037b65cee2`)
Executed: 2026-10-13, 08:42 – 09:07 UTC, on the disposable containers only.
Protected resources (`pofa_dev`, `pofa_test`, `pofa_db`, `pofa_redis`, `pofa_minio`,
their volumes) were not touched by this stage; the closing re-verification is Stage 12.

Verdict for this stage: **the integrated system recovers correctly from a PostgreSQL
outage and from an object-storage outage, but it does NOT survive a Redis outage: the
analysis queue consumer dies and never comes back by itself.** Ten findings, one of
them High. Nothing was fixed here — Stage I reports.

---

## 1. What was tested, and with what evidence

| # | Test | Result | Evidence file |
|---|---|---|---|
| 0 | Idle baseline: resources, restart counts, PID-1 signal masks | measured | `stageI-00-baseline.txt` |
| 1 | Idle CPU cost of the four workers | measured (finding I2) | `stageI-01-worker-cpu.txt` |
| 2 | Cold application import cost per process | 1.81 – 2.57 s (finding I2) | `stageI-02-import-cost.txt` |
| 3 | Total PostgreSQL outage (34 s) + recovery | PASS with finding I7 | `stageI-03-pg-outage.txt` |
| 4 | Health/readiness endpoint ownership attribution | corrected, see §4 | `stageI-12-endpoint-attribution.txt` |
| 5 | Total Redis outage + recovery | **FAIL — finding I1 (High)** | `stageI-04-redis-outage.txt` |
| 6 | Recovery of the stranded queue message by restarting the worker | PASS (manual) | `stageI-05-stranded-queue-recovery.txt` |
| 7 | Total MinIO / object-storage outage + recovery | PASS with I3, I4, I5 | `stageI-06-minio-outage.txt` |
| 8 | Presigned download URL during a storage outage | 200 + unusable URL (I3) | `stageI-07-presigned-during-outage.txt` |
| 9 | API SIGTERM stop + start, recovery timing, ledger continuity | PASS | `stageI-08-api-restart.txt` |
| 10 | SIGTERM stop/start of each worker container and the client | mixed, I8 | `stageI-09-worker-sigterm-matrix.txt` |
| 11 | Secret leakage in container logs (9 containers x 5 secrets + patterns) | PASS, zero hits | `stageI-10-log-hygiene.txt` |
| 12 | Closing consistency after every failure injection | PASS | `stageI-11-closing-state.txt` |
| 13 | Loop workers through the DB outage (crash + continuation) | PASS | `stageI-13-workers-through-db-outage.txt` |

Probes used: `probe_i_ready.py`, `probe_i_redis.py`, `probe_i_minio.py`,
`probe_i_dl.py`. All outages were created with `docker stop -t 2` / `docker start`
against **this run's own** containers, and every one was restored and re-verified
before the next test.

---

## 2. Proven facts

**PostgreSQL outage (34 s, 08:42:52 – 08:43:26).**
`/ready` returned 503 `{"status":"unhealthy",…,"checks":…}` for every poll in the
window and 200 again at 08:43:29 — the API self-recovered ~3 s after the database
came back with **no process restart and `restarts=0`**. `/health` returned 200 the
whole time. The audit chain stayed `valid:true` at 89 events; live worker appends
resumed correctly afterwards. An authenticated read that needs the database returned
**401 "Invalid credentials"** rather than a 5xx (finding I7).

**Redis outage (~4 s window, 08:50:46 – 08:50:49).**
`/ready` → 503 with the redis check unhealthy, correctly. `POST /api/v1/analysis/jobs`
→ **503 `{"detail":"Unable to enqueue analysis job"}`** and the job row was written as
`status='failed', error='Unable to enqueue analysis job'`; `SELECT count(*) … status='queued'`
returned **0** — the enqueue path leaves no stranded row (positive result, by design at
`backend/services/analysis_jobs.py:30-34`). Liveness stayed 200. Reads that do not need
Redis (`/api/v1/audit/verify`) stayed 200.
The consumer, however, died: the analysis container was `state=exited exit=1`, and the
message enqueued after Redis returned sat in `pofa:analysis:jobs` (llen=1) with its row
`queued` for 36+ s until the container was started by hand.

**Object-storage outage (~25 s, 08:57:34 – 08:57:58; re-run 08:59:20 – 08:59:37).**
`/ready` → 503 with `storage` unhealthy, api log:
`Storage health check failed: Could not connect to the endpoint URL: "http://minio:9000/"`.
`POST /api/v1/evidence` → **500 `{"detail":"internal server error"}`**, and the failed
upload left **no orphan `evidence` row and no audit event** — storage is written before
the DB (verified: the newest-4 row list contains no id for the rejected upload).
Metadata reads (DB only) kept working. After `docker start`, uploads returned 201 again
within one poll and the presigned download fetched the correct bytes.

**API restart.** SIGTERM produced a full graceful sequence
(`Shutting down` → `Waiting for application shutdown.` → `Application shutdown complete.`
→ `application.shutting_down` → `Finished server process [1]`), **exit code 0**, 1.90 s
wall. From `docker start` to the first successful `/ready` 200: **6.83 s**, of which
~4.5 s is cold import before uvicorn binds. Ledger: 91 events before, 92 after one real
app-path append, `valid:true`, no gap, no sequence reset, `restarts=0`.

**Ledger and data integrity after everything** (outages, a crashed consumer, three
SIGKILL-forced worker stops): 92 rows, sequences dense `1..92`, `/audit/verify`
`valid:true failures:[]`, Redis queue `0/0`, **no `analysis_jobs` left in `queued` or
`running`**, evidence 11 rows all `uploaded_quarantine`, notification outbox 3,
webhook deliveries 2 `RETRYING` (unchanged from Stage G).

**Log hygiene: clean.** For each of the five disposable secret values (owner password,
runtime password, MinIO root user, MinIO root password, JWT secret) across all nine
containers: **0 hits**. Credential-bearing DSN pattern (`scheme://user:pass@host`):
0 hits. JWT-shaped strings (`eyJ…`): 0 hits. `dev-user-` token strings in the API log:
0 hits — the API logs `principal=USER:<uuid>`, an identifier, not a credential. The only
URLs ever logged are `http://minio:9000/...` object paths (no signature query string) and
`http://0.0.0.0:8000`.

---

## 3. Findings (reported, not fixed)

### BE-037B-I1 — High — the analysis queue consumer cannot survive a Redis outage
`run_worker()` loops on `queue.dequeue(timeout=5)` with **no exception handling**
(`backend/workers/analysis_worker.py:197-224`, dequeue at `:213`), and `__main__` catches only
`KeyboardInterrupt` (`:226-232`). A `redis.exceptions.ConnectionError` therefore escapes
the loop and kills the process: measured `state=exited exit=1` with a full
`redis/connection.py … raise ConnectionError(SERVER_CLOSED_CONNECTION_ERROR)` traceback
within ~1 s of Redis disappearing. Consequences, all measured:
* work already accepted by the API (HTTP 202) is **not processed** until a human restarts
  the container — one job stayed `queued` with its payload sitting in Redis;
* `recover_abandoned()` only inspects the *processing* list, so a message that never left
  the main queue is not "recovered" — it simply waits;
* restarting the consumer did pick the message up (llen 1 → 0, `attempt_count` 0 → 3,
  row `failed` for the pre-existing `ObjectNotFoundError` reason), so nothing is lost,
  but only because a person intervened.

Scope caveat, stated precisely: this stack runs `restart: "no"` (my Stage B choice, so no
container could ever be recreated). The shipped `docker-compose.yml:146` uses
`restart: unless-stopped`, where the identical defect appears as a **crash-loop** that
self-heals when Redis returns. That shipped configuration was **NOT RUN** here — it would
require the protected stack. Either way the product behaviour is the same: an unhandled
dependency exception is used as the shutdown mechanism.

### BE-037B-I2 — Medium — the shell-supervisor workers burn a core while idle
`sh -c "while true; do python -m backend.workers.<x> …; sleep 15; done"` re-imports the
whole application every pass: measured cold import **1.81 – 2.57 s** per process
(`stageI-02`), samplers caught **39 – 99 % of a core** on an otherwise idle stack
(`stageI-01`). The observed pass cadence (08:42:51 → 08:43:26 → 08:43:43 → 08:44:01,
≈17.5 s) is 15 s sleep + ~2.5 s import, which corroborates the cost independently.
Retention's 3600 s interval makes it negligible; the long-lived analysis worker holds
~76 – 446 MiB resident depending on whether a vision pass has run.
This loop shape is also what makes the notification/webhook workers resilient to the DB
outage (§2, `stageI-13`): a failed pass prints a traceback, exits, and the next pass runs
15 s later. So the finding is a cost/observability issue, not a reliability one.

### BE-037B-I3 — Medium — a presigned download URL is issued even when storage is dead
During a total storage outage `GET /api/v1/evidence/{id}/download` returned **HTTP 200 with
a well-formed URL** (`http://minio:9000/be037b65cee2-quarantine/...`) twice; the client's
fetch then failed in 2 ms with `URLError: [Errno -3] Temporary failure in name resolution`.
The endpoint (`backend/api/v1/endpoints/evidence.py:76`) only signs locally, so the response
is not an availability signal even though `/ready` was simultaneously reporting storage
unhealthy. A caller that trusts the 200 sees a phantom success.

### BE-037B-I4 — Low/Medium — dependency outages are mapped to 500 on one path, 503 on another
Storage outage → evidence upload **500** (`StorageConnectionError` is unmapped; it reaches
`generic_exception_handler` at `backend/app/main.py:72`). Redis outage → analysis job **503**
(`backend/api/v1/endpoints/analysis.py:28` maps `RuntimeError`). Same class of failure,
different HTTP semantics, and 500 tells a client not to retry.

### BE-037B-I5 — Low — readiness probes get slow exactly when they matter
`/ready` answers 503 in **10.08 s**, then **3.89 s** during a storage outage
(botocore endpoint retries against an unresolvable host; the check is uncached and runs
all required dependencies per request), versus 50 ms during a DB outage and ~50 ms when
healthy. An orchestrator with a probe timeout under ~10 s would log a timeout rather than
the intended 503.

### BE-037B-I6 — Low (by design, recorded so it is not mistaken for a defect)
The api container healthcheck (`compose.disposable.yml:112-117`) polls `/health`, which is
the BE-020 **liveness** endpoint and is deliberately dependency-agnostic
(`backend/observability/health.py:1-6`). The container therefore stayed `healthy` through a
34 s total database outage while `/ready` correctly returned 503. Reasonable for avoiding
restart storms, but Docker-level health carries no readiness information here.

### BE-037B-I7 — Low — an infrastructure outage is reported as an authentication failure
During the DB outage, an authenticated request returned **401 "Invalid credentials"**,
because validating a dev token requires a database read. Operators reading a 401 will
debug auth while the actual fault is the database.

### BE-037B-I8 — Low — only the API and the analysis worker stop cleanly
`docker stop -t 15` results: analysis **exit 0** (graceful "worker stopping / stopped"),
api **exit 0** (graceful, 1.9 s); notification, webhook, retention and client all
**exit 137** — SIGKILL after the grace period expired, i.e. SIGTERM did not stop the
`sh -c` loop in 15 s (`stageI-09`). PID-1 masks read from `/proc/1/status` for the three
loop workers are `SigIgn: 0000000000000000`, `SigCgt: 0000000000010002` (SIGINT+SIGCHLD
caught, SIGTERM neither caught nor ignored), so the exact reason the shell outlives
SIGTERM is **not established by this measurement** — recorded as an open question rather
than explained. Practical consequence: production shutdown of these three is unclean and
any in-flight pass can be cut mid-way. In this run no data was damaged (§2 integrity).
This also **corrects the Phase A prediction recorded earlier**: the observed outcome is
137, matching what Phase A predicted, not the 143 I reasoned from the signal masks.

### BE-037B-I9 — Low — the shutdown log does not distinguish a clean stop from a crash
On the fatal Redis path the worker still printed
`analysis worker stopping; releasing queue and database resources` /
`analysis worker stopped` (the `finally:` block runs during unwinding). Only the exit
code separates the two. Anything keying off that log line will read a crash as a stop.

### BE-037B-I10 — inherited, re-confirmed — BE-037B-G5 is still live
The completed job at 08:50 again emitted, immediately before
`analysis job completed`, an ERROR plus traceback:
`reprocessing completion hook failed job_id=6e02a5ae… LookupError: Reprocessing request not found`
(`backend/workers/analysis_worker.py:55` → `backend/services/governance.py:684`).
Unchanged from Stage G: an ERROR+traceback for every successful job.

---

## 4. Attribution correction made during this stage

`backend/api/v1/endpoints/health.py` (the trivial `{"status":"ok"}` `/health` and
`SELECT 1` `/ready`) is **not** what the mounted probes answer. Live measurement plus
`backend/app/main.py:78-102` establishes: `/health` → BE-020 liveness, `/ready` → BE-020
readiness (application + postgresql + redis + storage, three of them `required=True` at
`observability/health.py:75,115,144`), `/healthz` → combined snapshot, and the trivial
router is reachable only at `/api/v1/health` and `/api/v1/ready`. Earlier session notes
that described `/health` as "static, no dependency checks" were about the legacy router;
the correct statement is that root `/health` *is* dependency-agnostic **on purpose**.
Recorded in `stageI-12-endpoint-attribution.txt`.

---

## 5. NOT RUN (and why)

* **Shipped-config behaviour under the Redis outage** (`restart: unless-stopped`,
  crash-loop cadence, whether `recover_abandoned()` then repairs the processing list):
  requires the protected `pofa_*` containers or a compose run — both forbidden. Would
  need a second disposable stack with `restart:` set; not built.
* **Vision/temporal inference through an outage** — model weights are absent locally
  (inherited hazard), so inference paths were exercised only for fingerprint jobs.
* **Two simultaneous queue consumers / Redis failover under load** — the image ships one
  analysis worker; no second consumer existed to test handover.
* **Sustained-load failure behaviour, queue backpressure, and DB pool exhaustion** — no
  load generator was authorized in this stage.
* **Orchestrator reaction to I5** (probe timeout vs 503) — Docker Compose healthcheck here
  targets `/health`, so the situation cannot arise in this stack; Kubernetes-style probe
  tuning is out of scope.
* **Anything resembling production recovery** — no PITR, no backup-restore rehearsal, no
  multi-node failover. None of these checks support a production-acceptance claim, and
  none is being made.

---

## 6. Safety posture during this stage

Only containers named `be037b65cee2_*` were stopped, started or restarted; every stop was
paired with a start and a `/ready` re-verification before the next test. Writes went only
to the disposable database and this run's disposable buckets, through the real API path
with an authorized disposable principal. Every read-only DB probe ran inside
`rollback()`. No repo file was modified, staged, committed or pushed. Secrets were
handled by count-only scans; no secret value appears in any Stage I file or in this
document, and the only tokens that appear anywhere are the disposable dev tokens
(`dev-user-<uuid>`) that this throwaway database issues for its own throwaway users.
