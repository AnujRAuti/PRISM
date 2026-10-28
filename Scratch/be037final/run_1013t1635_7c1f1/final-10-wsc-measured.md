# BE-037 FINAL — WS-C / WS-D / WS-E measured results

Run id `be037fin7c1f1`, disposable stack only. Every number below is read back from
the JSON in `evidence/`, not from an expectation in the code. Nothing in this file
was executed against `pofa_dev` / `pofa_test` / `pofa_db` / `pofa_redis` / `pofa_minio`.

Code under test is at HEAD `d3764806`; the WS-A and WS-C implementation and their
unit tests are already committed (`tests/unit/test_be037g5_reprocessing_hook.py`,
`tests/unit/test_be037c_analysis_queue_timeouts.py`, `tests/unit/test_be037a_analysis_worker_shutdown.py`,
`tests/unit/test_be037i1_analysis_worker_redis_outage.py` all appear in `git ls-files`).
The two integration modules added by this run are still untracked.

---

## WS-C — the hung-connection question, answered by measurement

### The three questions §6 asked

| Question | Answer | Evidence |
|---|---|---|
| Does the blocking dequeue have a finite socket timeout? | **Not before this run.** `AnalysisQueue` built a bare `redis.Redis.from_url(...)`. It does now: `_bounded_client()` at `backend/services/analysis_queue.py:24-56` passes `socket_timeout`, `socket_connect_timeout`, `health_check_interval`. | `final-07-wsc-baseline-frozen-redis.json` (pre-fix): a frozen Redis left `brpoplpush` unanswered for the whole 45 s probe budget, no reply, no exception, worker never reached its shutdown check. |
| Does `health_check_interval` fix a frozen connection? | **No.** It pings an idle connection *between* commands; a reply that never arrives is not "between commands". | S4/S3: with `health_check_interval` configured, the blackhole still had to be broken by the socket deadline. `ANALYSIS_REDIS_HEALTH_CHECK_INTERVAL_SECONDS` is documented as a helper, never as the bound. |
| Can a network blackhole block indefinitely? | **Yes, pre-fix** (`docker pause` = the socket stays open, no RST, no reply). Post-fix the stall ends at the socket deadline: freeze→warning **8.23 s** with `socket_timeout 8.0`. | `sc4_blackhole_during_idle_dequeue.json`: `freeze_at_worker_clock_s 4.91`, first warning at `13.14`, `seconds_freeze_to_warning 8.23`, worker alive after the warning. |

The exception set the handler treats as an outage is `redis.exceptions.ConnectionError`
and `redis.exceptions.TimeoutError` (`backend/workers/analysis_worker.py:32-45`). The
comment block records the measurement that made it necessary: the two are **siblings**
under `RedisError`, so catching `ConnectionError` alone never covered a socket timeout,
and `AuthenticationError` is the trap because it *does* subclass `ConnectionError`.
`ResponseError` / `DataError` stay outside the set on purpose — S7 proves they still
propagate.

### The validator

`_bounded_client` raises `ValueError` at construction when
`socket_timeout <= dequeue_block` (`analysis_queue.py:41-49`), i.e. the worker refuses
to start. The requirement is derived from client semantics, not from a test: a healthy
idle `brpoplpush` is *supposed* to end server-side with "no message", and a deadline at
or below the block turns every idle poll into a reported outage. Harness settings used
socket 8 / block 3 throughout; the container cases used socket 30 / block 20 or 1.

### Host harness: 11 scenarios (S1–S10, plus the S3 re-run)

`wsc_scenarios.py`, real Redis for this run (`be037fin7c1f1_redis`, AOF always), real
PostgreSQL for this run, real worker process, synthetic fixtures in this run's MinIO.

| # | Scenario | Observed |
|---|---|---|
| S1 | Redis unavailable **before** worker start | worker stayed alive, 3 backoff warnings with stated delays 3.9 / 5.5 / 14.0 s (consecutive failures 1→3, base 4.0 max 20.0), then completed the job at 109.45 s, `attempt_count 1`, `result_rows 1`, lists 0/0. |
| S2 | Clean disconnect (`docker stop`) during a blocked dequeue | stop→warning in **0.17 s** (worker clock 4.97 → 5.14), stated delay 2.5 s, recovered and completed at 88.55 s, lists 0/0. |
| S3 | `docker pause` **across the acknowledgement** (no clean disconnect) | DB committed while frozen at 74.06 s; frozen 20 s past the commit; socket deadline fired → warning 3.9 s at 88.06; after thaw, recovery requeued 1 abandoned job (94.25), job completed at 95.14 with `attempt_count 2`, `result_rows 1`, final lists 0/0. **Nothing lost.** |
| S3a | Same, thaw **before** the abandoned-retry deadline | frozen 12 s (> socket 8); ack succeeded silently after thaw — 0 backoff warnings, no "recovered" line, completion at 69.31, `attempt_count 2`, lists 0/0. |
| S4 | Blackhole during the **idle** blocking dequeue | see table above: 8.23 s freeze→warning, worker alive, job completed after restore. |
| S5 | Restore with jobs already queued | 3 queued pre-outage, 1 backoff warning (3.0 s), all 3 completed after restore (70.52 / 71.25 / 72.03), all `attempt_count 1` `result_rows 1`, lists 0/0. Survived because this run's Redis has AOF on. |
| S6 | Four repeated outage cycles | 8 warnings, stated consecutive failures 1→8, stated delays 2.2 / 5.2 / 11.6 / 17.5 / 11.0 / 12.0 / 11.6 / 14.6 s against base 4.0 max 20.0 — bounded, never exceeding max, and the counter restarts after each recovery. Measured inter-warning intervals 4.29 … 25.92 s. Worker never exited; job completed at 168.34. |
| S7 | Unrelated Redis error (queue name points at a string key) | **0 backoff warnings**, traceback present, `WRONGTYPE Operation against a key holding the wrong kind of value`, **exit code 1**. Genuine errors are not swallowed by the outage handler. |
| S8 | Malformed payload | `ValueError: Invalid analysis queue payload` from `analysis_queue.py:67`, traceback, **exit code 1**, the bad entry left in the processing list (main 0 / processing 1). Recorded as an observation, not a fix: §6 mandates propagating invalid data rather than discarding it, but a single poison message still kills the consumer. |
| S9 | Reprocessing hook on the real worker (WS-A) | unlinked job: `DEBUG ... no reprocessing request delegates job_id=...; governance hook skipped`, **0** `linkage_lookup_failed` lines, **0** ERROR lines, **0** tracebacks, 1 DEBUG line, job completed `attempt_count 1 result_rows 1`. Linked job: `reprocessing_requests` reached `COMPLETED`, 1 `INTELLIGENCE_REPROCESS_COMPLETED` audit event. |
| S10 | Recovery classification (5 planted processing entries) | 1 recovered-and-reprocessed (stale running → completed at 49.80), corrupt + missing-job + terminal entries discarded, fresh `queued` entry left untouched in processing; `recovered 1 abandoned job(s)` logged; final lists main 0 / processing 1. All 8 classification booleans true. |

S3/S3a are the scenarios that prove the §6 ordering rule held under a stall: the
database commit happened *before* the acknowledgement was ever attempted, and when the
ack could not complete the job was re-run from `recover_abandoned` rather than being
lost or double-acked.

### Real-Redis integration module

`tests/integration/test_be037c_redis_timeout_integration.py` — **5 passed, 1 warning in
15.20 s** (`evidence/wsc_integration.pytest.log`, rc 0), against this run's Redis only.

### Container PID-1 SIGTERM cases (the Windows host cannot send SIGTERM)

Image `poa-backend:be037final`, containers named `be037fin7c1f1_wsig_*`, `docker stop`
as the signal source. **Capture lesson: `logging.basicConfig(level=logging.INFO)` at
`analysis_worker.py:378` has no stream argument, so every worker line goes to stderr;
reading `docker logs` stdout alone silently produced an empty evidence set on the first
attempt.** `container_logs()` merges both streams; the four cases below are the re-run.

| Case | Configured | Observed stop latency | Notes |
|---|---|---|---|
| SIGTERM during a backoff wait | base 40, max 60, poll 0.5, Redis `redis://redis:6399/0` (closed port) | **1.25 s** | warning said 35.6 s delay, 15.8–33.6 s of it still to sleep → the poll loop sliced it. exit 0, RestartCount 0, both stop lines logged. |
| SIGTERM during a blocked dequeue | block 20, socket 30, poll 0.5 | **18.62 s** | the `brpoplpush` is one unsliceable read: the poll interval cannot cut it. |
| same, contrast | block 1 | **1.5 s** | the knob that matters for an idle worker is `ANALYSIS_DEQUEUE_BLOCK_SECONDS`. |
| SIGTERM while a job is genuinely running | 42 MB synthetic fixture, block 3, `-t 200` | **10.91 s** | job picked up at 5.64 s, state `running attempt_count 1` at stop; log order is `analysis job completed` → `worker stopping` → `worker stopped`; after stop `status completed`, `attempt_count 1`, `result_rows 1`, lists 0/0. A mid-job SIGTERM does **not** abort the job or the commit. |

All four: `docker stop` rc 0, state exited, `exit_code 0`, `oom_killed false`,
`RestartCount 0`.

These four measurements are what forced the WS-B documentation correction: the old
`docs/storage.md` text promised poll-interval shutdown for every case, which the
block-20 case (18.62 s) disproves. `.env.example` and `docs/storage.md` now state both
costs with these numbers.

---

## WS-D — reproducible bootstrap and schema drift

Fresh second boot: `be037fin7c1f1_db2` (same image as `_db`, `garapadev/postgres-postgis-pgvector:15-stable`,
host port 15433, DB `be037fin7c1f1_app2`), created with `docker run` — rc 0.
`evidence/wsd_second_boot.json`:

- bare `docker run` has **no healthcheck** (`none`) where the compose-created DB has one
  (`defined`) — recorded as a bootstrap difference, not repaired.
- initdb scripts that ran: `/docker-entrypoint-initdb.d/init.sql`. No `initdb trust` warning.
- extensions after first boot: `plpgsql 1.0`, `postgis 3.4.2`, `vector 0.7.4`.
- `public` relations after first boot: **1** — `spatial_ref_sys`. **`exemplo_dados` is absent**
  on this run's second boot; the schema-drift baseline exception was **not** widened.
- `alembic upgrade head` rc 0, chain ends `… -> t0u1v2w3x030` (BE-030 enforcement + event-type CHECK);
  `alembic_version = t0u1v2w3x030`; **73 tables**; `search_path = "$user", public`;
  **15** baseline registry rows.
- extension-owned object, with owner recorded: `spatial_ref_sys`, owner `postgres`, kind `r`.
- drift gate on the clean DB: `tests/integration/test_schema_drift_gate.py` → **24 passed, 1 skipped,
  1 warning in 65.83 s** (gate rc 0).
- deliberate app-owned drift: created a manual table → drift test **failed rc 1** and named it
  (`test_drift_is_exactly_the_documented_baseline`), `alembic check` rc **-1** mentioning the manual
  table; after removing it, the drift test **passed rc 0** (15.95 s). So detection is live in both
  directions, and the baseline was not edited to accommodate the object.

### Protected-target refusal, now proven over a real connection

The §7 refactor is the opt-in probe in
`tests/integration/test_be029_database_safety_guard.py::test_verification_refusal_also_holds_over_a_real_connection`
(`POA_PROTECTED_NAME_PROBE_DATABASE_URL`), and `wsd_protected_probe.py` supplied a
target that is genuinely disposable: **a database named `pofa_dev` created on this run's own
server** (`127.0.0.1:15433`, container `89aeb7ec998a…`), not the protected cluster.

- Provenance recorded so the two cannot be confused: `inet_server_addr 172.19.0.5/32`,
  `inet_server_port 5432`, `current_setting('port') = 5432` (the *guest* port — the host
  mapping 15433 is not visible to the server, which is itself a provenance trap).
- Before creation: `existing_protected_named_databases = 1` (only this run's probe-less state),
  then `CREATE DATABASE "pofa_dev"` on the disposable server.
- Test result: **1 passed, rc 0, 4.09 s** — `ProtectedDatabaseError` raised, and
  `server_database_name(probe) != own_name` holds over a real connection, which is what the
  guard actually keys on (the name the *server* reports, not the DSN text).
- After: database dropped, `remaining_protected_named_databases = 0`, 1 database left on the
  disposable server. The live `pofa_dev` was never contacted by this script.

No baseline exception was added anywhere in WS-D.

---

## WS-E — storage isolation and the ledger under three identities

### E1: `tests/integration/test_storage.py:77` no longer depends on `pofa_minio`

`DISPOSABLE_MINIO_CONTAINER_ENV = "POA_DISPOSABLE_MINIO_CONTAINER"`; the test binds the armed
container name to the configured `S3_ENDPOINT` host port before restarting anything, and skips
with an explicit reason when unarmed.

| Run | Command shape | Result |
|---|---|---|
| Unarmed (`RUN_SUITE_WITHOUT=POA_DISPOSABLE_MINIO_CONTAINER`) | `run_suite.py wse1_storage_unarmed tests/integration/test_storage.py` | **rc 0 — 6 passed, 1 skipped, 1 warning in 3.54 s.** Skip reason quotes `test_storage.py:138`: "POA_DISPOSABLE_MINIO_CONTAINER is not set, so there is no MinIO this test owns. Restarting the shared compose stack from a test is not allowed…". Proves the default test run cannot bounce the shared stack. |
| Armed | `run_suite.py wse1_storage_armed tests/integration/test_storage.py` | **rc 0 — 7 passed, 1 warning in 7.59 s**, restart-persistence included, against this run's `be037fin7c1f1_minio` only. |

`pofa_minio` was never restarted, recreated, or reconfigured by this run (see
`final-09-wse1-minio-restart-forensics.txt` for the read-only investigation of the earlier
restarts: cause **not established**, reported as unresolved, not attributed to this run).

### E2: the ledger under three identities

- Identity matrix: `tests/integration/test_be037e2_ledger_identity_matrix.py` →
  **7 passed in 19.42 s** (`evidence/wse2_identity.pytest.log`) — app runtime role, disposable
  owner, insufficient-permission role, on this run's DBs only. No owner, grant, or role of
  `pofa_dev` / `pofa_test` was modified.
- Owner-side transcript: `wse2_owner_transcript.py` → **rc 0**, `evidence/wse2_owner_transcript.json`.
  It lives in Scratch because `tests/audit_guard.py` makes ledger UPDATE/DELETE/TRUNCATE text an
  unconditional violation inside the test tree with no allowlist; the refusal words therefore have
  to be captured outside it.

Measured, as the disposable cluster owner (`current_user postgres`, `rolsuper true`,
grants update/delete/truncate all **true**):

| Step | Observed |
|---|---|
| Chain built by the app's own append path | rows 3, min 1, max 3, `verify_chain valid true checked_events 3`; tail hash `bcc421d5…`, tail previous hash `68798906…` (the out-of-band anchor) |
| Catalog | one trigger `trg_audit_ledger_append_only`, `tgtype 27` → row-level true, fires_on_update true, fires_on_delete true, **fires_on_truncate false** |
| Owner UPDATE of the tail row | refused, **SQLSTATE 42501**, message `append-only enforcement refuses UPDATE on the audit ledger` |
| Owner DELETE of the tail row | refused, 42501, `append-only enforcement refuses DELETE on the audit ledger` |
| `SET LOCAL poa.ledger_mutation_exception = 'true'` + UPDATE | **succeeded** — and `verify_chain` then reported `valid false`, failure `event_hash mismatch at sequence 3` |
| `TRUNCATE audit_ledger_events` | **succeeded** in 0.03 s (statement-level; the row trigger never runs) |
| In-database verdict after the wipe | `ledger_checkpoint` rows 0 / min null / max null / hashes null; `verify_chain valid true checked_events 0`; anchored verify identical |
| External digest | `external_digest_disagrees true` |

Threat-model statement (this is the distinction §8 demands, not a claim that an
application-level trigger defeats a database owner): grants refuse the owner nothing, so the
**trigger** is what stops row-level UPDATE/DELETE, and it does stop the owner. The sanctioned
`SET LOCAL` hatch is *permitted*, not *invisible* — verification still reports the hash mismatch.
**TRUNCATE bypasses the row trigger entirely and is detectable only from the checkpoint digest
published outside the database**; from inside a wiped ledger the database looks valid and empty,
indistinguishable from a fresh one (`audit_ledger.py:344-347` returns `valid=True` over zero
rows). The control that closes that hole is operational (digest published/kept out-of-band, plus
the F-05 non-owner role that denies TRUNCATE), not a row trigger.

### WS-C/WS-D/WS-E defect register

| Ref | Status |
|---|---|
| WS-C socket deadline + validator | Implemented, 11 scenarios + 5 integration tests + 4 container cases measured |
| WS-D second fresh bootstrap, extension ownership, deliberate drift detection | Executed, no baseline exception added |
| WS-D protected-target refusal | Was a skip, now executed and passing over a real connection |
| WS-E1 shared-MinIO dependency | Removed; both shapes (unarmed skip, armed pass) proven |
| WS-E2 owner-DSN / identity integrity | Matrix + live transcript, threat-model distinction documented |
| S8 poison message kills the consumer | **Observation, not fixed** (mandated propagation makes it a design call for the owner) |
| `exemplo_dados` absent on this run's boot | Fact recorded; the exception remains documented where it came from, no new exception added |
| bare `docker run` DB has no healthcheck | Observation |
