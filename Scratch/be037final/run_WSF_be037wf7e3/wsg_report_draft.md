# BE-037 — Final Backend Completion and Acceptance Report (run `be037wf7e3`)

Milestone: BE-037 (final planned backend milestone; no BE-038 is created).
Task executed: `docs/Production Task Files/BE-037 — FINAL BACKEND MILESTONE.md` as
extended by the "FINAL BACKEND COMPLETION AND ACCEPTANCE" workstreams A–G.
Report written 2026-10-15 against repository HEAD `d3764806`, branch `Backend`.

Every number below was read back from the evidence files listed in §16, produced by
commands run during this session. Nothing here is a restatement of an expectation in
the code.

## 1. Executive summary

This task executed the remaining BE-037 workstreams (A–G of "FINAL BACKEND
COMPLETION AND ACCEPTANCE") against a purpose-built, uniquely named disposable
stack, and then cleaned that stack up. The headline results:

- **The test tree is green and complete.** 930 passed, 1 skipped, 0 failed
  (`pytest tests`, rc 0) on this run's disposable suite database — 540 unit plus
  390 integration. The single skip is an inverse guard in `test_preflight.py`
  (it skips when the ML stack is genuinely importable). The four integration
  obligations that are armed by environment all ran rather than silently
  skipping: zero skips in the integration directory (§14).
- **Both inherited High findings are closed with real evidence.** G1 (the
  analysis endpoints had no authorization at all) is now a verified 23-case +
  14-case matrix with HTTP status *and* database side effects checked: every
  expectation met, 0 rows written by any rejected request (§12). I1 (loss of
  Redis killed the analysis consumer) is now a bounded, logged, recovering
  backoff, proven across 11 host-injected scenarios, 4 container PID-1 signal
  cases and a 9-case outage matrix on this run's own stack — including a
  `docker pause` blackhole that ends at the socket deadline (8.23 s) instead of
  hanging forever (§8).
- **G5 is fixed and proved non-vacuously.** An unlinked reprocessing job is a
  DEBUG no-op with no traceback; a genuine hook failure still logs ERROR once;
  neither escapes the worker, and the job still completes (§6).
- **The documentation now matches the implementation** for worker tuning:
  `.env.example` and `docs/storage.md` describe the real defaults, the actual
  jittered formula, the one validator that exists, the two that do not, and the
  measured shutdown latency for each waiting state (§7).
- **Bootstrap is reproducible and drift is detected in both directions.** Two
  independently created disposable databases from the same tree reach the same
  73-table schema at `t0u1v2w3x030`; a deliberately injected app-owned table was
  caught by both the drift gate and `alembic check`, and no baseline exception
  was added, widened or removed (§9).
- **Audit-ledger integrity is characterized precisely, not oversold.** The
  append-only trigger refuses row mutation for *every* identity including the
  cluster owner (SQLSTATE 42501 from the trigger body); grants alone stop the
  runtime role from UPDATE/DELETE/TRUNCATE; TRUNCATE bypasses row triggers, so
  an owner-level wipe is only detectable from a digest held outside the database
  (§11). This run's acceptance ledger chain verifies `valid=true` over 23 events
  as the runtime role.
- **Cleanup is proven, and protected resources provably did not move.** 7
  containers, 7 volumes, 2 networks and 4 credential-bearing files created by
  this task are gone; all 11 host ports are free again; nothing was deleted on a
  name pattern (§16). `pofa_dev` (6023 ledger rows) and `pofa_test` (53316) are
  byte-for-byte the same on every read-only field as the task's opening baseline,
  and the three protected containers keep their original IDs, creation times and
  `RESTARTS=0` (§17).
- **Two real limitations remain and are not presented as passes.** Production
  acceptance cannot be measured here: there is no approved production target and
  no production secret store (verified by enumeration, §18.2). And containerised
  inference ran *degraded, not fabricated* — no model weights were downloaded
  (that needs owner approval), so the embedding column is `null` with
  `embedding_status "unavailable"` and semantic similarity is unverified in this
  environment (§13).

No code was changed by this task; its five changed files are documentation and
tests (§5). Nothing was staged, committed or pushed (§20).

## 2. Final verdict

**CONDITIONAL PASS — acceptance achieved against a disposable isolated
environment; NOT cleared for production.**

### 2.1 What the PASS part covers (accepted)

| Scope item | Status |
| --- | --- |
| BE-037 workstream A (G5 reprocessing hook) | Passed — unit + real-worker evidence, vacuity check |
| BE-037 workstream B (worker configuration documentation) | Passed — `.env.example` and `docs/storage.md` corrected to measured behaviour |
| BE-037 workstream C (Redis outage / hung-connection handling) | Passed — 11 host scenarios + 4 container signal cases + this run's 9-case matrix, all executed |
| BE-037 workstream D (container database bootstrap, schema drift) | Passed — reproducible twice, drift detected both directions, protected-target refusal tested |
| BE-037 workstream E1 (storage test isolation) | Passed — armed and unarmed shapes both run; no dependency on the shared `pofa_minio` |
| BE-037 workstream E2 (owner-DSN / runtime-role integrity) | Passed — identity matrix + owner transcript, disposable DBs and roles only |
| G1 authorization matrix (F1) | Passed — 23 + 14 cases, status and side effects verified |
| End-to-end synthetic evidence flow (F3) | Passed **with the stated inference limitation** — real upload → queue → worker → result → signed download, embeddings unavailable by design here |
| Unit + integration + full suite (F4) | Passed — 930 / 1 skip / 0 failures, all rc 0 |
| Production-fail-fast, redirect SSRF gate, ledger posture, image provenance, secret hygiene (F5) | Passed — with the deviations and corrections listed in §15 |
| Disposable-resource cleanup and protected-resource verification (G) | Passed — positive identification only, before/after evidence captured |

### 2.2 What the CONDITIONAL part means (not accepted, with reason)

1. **No production target and no production secret store.** Production
   acceptance, deployment, live cutover proof and live health/integrity
   verification are therefore **Blocked — not run**, and cannot be closed by any
   amount of isolated testing (§18.2).
2. **Semantic inference is unverified.** It requires an approved outbound model
   weight download or weights baked into the image. Until then the acceptance
   covers the plumbing, not the vector (§13, §15).
3. **Open owner decisions, deliberately not fixed here:** D2 (empty
   authorization catalogue on a fresh deploy), WSF-OBS-1 (intake credential needs
   GLOBAL scope), NEW-1 (idle-worker recovery log + backoff counter never reset),
   NEW-2 (the analysis lifecycle writes no audit event at all), S8 (a single
   poison message stops the consumer — propagate-and-restart is what the task
   mandates), the TRUNCATE residual control, OQ-3 (`external_subject`), G4/G6/G7
   and I5–I9 (§18.1).
4. **Dependency debt recorded, not fixed:** the two deprecation families behind
   all 10 warnings (FastAPI `on_event` lifespan migration, `HTTP_422` constant)
   require a code change no workstream in this task was authorized to make (§15).
5. **Ledger history on `pofa_dev` is still `known_historical_only`** with 7
   gap-only failures and 0 hash mismatches (inherited; §18.2). Repair is barred by
   BE-032R §3.2, so this is a reconciliation-register decision, not a defect.

Per the task's own rule — *"Even if all isolated tests pass, do not declare PoA
production-ready"* — the correct statement of this run's outcome is:
**the backend is functionally complete and verified in isolation; production
readiness is a separate milestone that has not been reached and has no target to
be reached on.**

## 3. Initial and final Git HEAD

| Point | Value |
| --- | --- |
| Branch at start and at end | `Backend` |
| HEAD at start of this task | `d3764806` — "docker #2 complete" (authored 2026-10-14 16:03 IST) |
| HEAD at end of this task | `d3764806` (identical; no commit was created) |
| Commits made by this task | none |
| Pushes made by this task | none |

## 4. Initial and final working-tree status

Status recorded at the start of this session's work and re-verified at the end
(`git status --short`), before this report file itself was written:

```
 M .env.example
 M docs/storage.md
 M tests/integration/test_storage.py
?? tests/integration/test_be037c_redis_timeout_integration.py
?? tests/integration/test_be037e2_ledger_identity_matrix.py
```

Writing this report adds exactly one further untracked path and changes nothing
else:

```
?? docs/BE-037 Final Backend Completion and Acceptance Report.md
```

It is a **new** file: no existing report was overwritten (§10 of Workstream G).

Nothing is staged (`git diff --cached` is empty), nothing was committed, nothing was
pushed. The two commits that predate this session on the branch
(`c2702588` "BE-037 Complete BACKEND", `7bd315f0` "be-037 error handling", plus
`d3764806`) are the user's own; the user's deletions of the previous BE-031…BE-037
result reports and the deferred-fixes backlog in `52084de7` ("done with auditing")
were preserved untouched — that is why this document is a new file rather than an
update to an existing report (§10 of the task's Workstream G).

## 5. Exact files changed and reason for each

### 5.1 Committed before this session's edits (the user's own commits, already at HEAD)

| File | Reason |
| --- | --- |
| `backend/workers/analysis_worker.py` | WS-A (G5 reprocessing hook no longer logs ERROR/traceback for an unlinked job), WS-C (outage exception set, bounded backoff, recovery pass after reconnect), WS-B (reads the three worker tuning settings). |
| `backend/services/analysis_queue.py` | WS-C: `_bounded_client()` builds the queue connection with `socket_timeout` / `socket_connect_timeout` / `health_check_interval` and raises `ValueError` when `socket_timeout <= dequeue_block`. |
| `backend/core/config.py` | WS-B/WS-C defaults (`ANALYSIS_RETRY_BACKOFF_BASE/MAX_SECONDS`, `ANALYSIS_SHUTDOWN_POLL_SECONDS`, the four Redis socket/block knobs) and the extended production fail-fast (`auth_mode`, dev tokens, CORS, JWT length). |
| `backend/api/v1/endpoints/analysis.py`, `backend/services/authorization.py` | G1: the analysis endpoints are authorized (permission + scoped resource checks), inherited from Phase B remediation. |
| `docker/pg-init/init.sql` | WS-D: container first-boot extension setup (postgis/pgvector) without vendor demo data. |
| `tests/unit/test_be037g5_reprocessing_hook.py` (7 tests) | WS-A obligations: no-op at DEBUG, successful hook, genuine failure observable, idempotence, no duplicate logging. |
| `tests/unit/test_be037c_analysis_queue_timeouts.py` (6) | WS-C unit layer: timeout configuration, validator, exception classification. |
| `tests/unit/test_be037i1_analysis_worker_redis_outage.py` (18) | WS-C/I1 worker behaviour across outages. |
| `tests/unit/test_be037a_analysis_worker_shutdown.py` (7) | Shutdown responsiveness during retry waits. |
| `tests/integration/test_be037g1_analysis_auth.py` (13) | G1 authorization matrix at integration level. |
| `tests/integration/test_be029_database_safety_guard.py` | WS-D refactor: the protected-target refusal is testable without writing to a protected database (opt-in probe). |
| `.env.example` | WS-B: the three settings documented in the canonical example config. |

### 5.2 Modified by this task and left unstaged

| File | Diff | Reason |
| --- | --- | --- |
| `.env.example` | +13/−4 | WS-B correction after measurement: the backoff term is `min(max, BASE * 2**(N-1))` with half-jitter (not "roughly half" of a bare exponential), `ANALYSIS_SHUTDOWN_POLL_SECONDS` bounds SIGTERM latency **only while backing off**, the idle case is bounded by `ANALYSIS_DEQUEUE_BLOCK_SECONDS`, and a note that the Compose environment block forwards none of the `ANALYSIS_*` names so a containerised worker stays on compiled defaults. |
| `docs/storage.md` | +135/−0 | WS-B: the operator-facing "Redis outages and tuning" walkthrough — purpose, real defaults, the base/max relation as implemented, the validator that exists (`socket_timeout > dequeue_block`), the absence of validators on base/max/poll, diagnosing repeated disconnections, and the measured shutdown latency (18.41 s at a 20 s block vs 1.75 s at a 1 s block on this run's stack). No invented ranges. |
| `tests/integration/test_storage.py` | +89/−5 | WS-E1: the restart-persistence case no longer depends on the shared `pofa_minio`; it is gated on `POA_DISPOSABLE_MINIO_CONTAINER`, binds the armed name to the configured endpoint, and skips with an explicit reason when unarmed. |
| `tests/integration/test_be037c_redis_timeout_integration.py` (new, 266 lines) | WS-C: real isolated-Redis measurements (hung/blackholed connection) — 5 tests, skipped unless `POA_DISPOSABLE_REDIS_URL`/`..._CONTAINER` are armed. |
| `tests/integration/test_be037e2_ledger_identity_matrix.py` (new, 363 lines) | WS-E2: the ledger under the app runtime role, a privileged disposable owner and an insufficient-permission role, disposable DBs/roles only. |
| `docs/BE-037 Final Backend Completion and Acceptance Report.md` (new) | — | WS-G: this report. Written as a new file because the user's `52084de7` commit deleted the previous BE-031…BE-037 result reports; nothing was overwritten. |

No production code was modified by this task; all six files above are
documentation and tests.

## 6. G5 behaviour and test evidence (Workstream A)

**Decision taken (and implemented at HEAD):** an absent reprocessing linkage is an
*expected no-op*. It is logged at `DEBUG`, not `ERROR`, and produces no traceback.
A genuine fault inside the hook stays at `ERROR` with a traceback. Neither case
propagates out of the worker, because the job's database outcome is already
committed and the acknowledgement must not depend on governance bookkeeping.

Implementation: `backend/workers/analysis_worker.py:138-181`
(`_complete_reprocessing_hook`) — it checks
`governance_repo.lock_pending_reprocessing_for_job(db, str(job.id))` first;
`request is None` → `logger.debug("no reprocessing request delegates job_id=%s;
governance hook skipped")` and return; a linkage-query exception →
`logger.exception("reprocessing linkage lookup failed …")`; a
`complete_reprocessing` rejection → `logger.exception("reprocessing completion hook
failed …")`. The `LookupError` raised by `complete_reprocessing` for an unlinked job
is no longer the thing being caught.

Vacuity check (`run_1013t1635_7c1f1/final-01-g5-vacuity.txt`) — proves the new
assertion is not vacuous:

```
OLD hook (unlinked job): records=1 levels=['ERROR'] errors=1 with_traceback=1
NEW hook (unlinked job): records=1 levels=['DEBUG'] errors=0 with_traceback=0
```

Unit layer: `tests/unit/test_be037g5_reprocessing_hook.py`, 7 tests —
quiet no-op, DEBUG level carries the job id, linkage measured with the job id as a
string, linked job completes the delegating request, completion failure logged
**once** with a traceback, linkage-query failure logged and completion skipped,
repeated hook calls stay quiet and idempotent.

Real-worker layer (`evidence/sc9_reprocessing_hook.json`, this session's run):

| Observation | Unlinked job | Linked job |
| --- | --- | --- |
| `ERROR` lines | 0 | — |
| traceback lines | 0 | — |
| `linkage_lookup_failed` lines | 0 | — |
| DEBUG no-op lines | 1 | — |
| Job outcome | `completed`, `attempt_count 1`, 1 result row | `completed`, `attempt_count 1`, 1 result row |
| Governance state | — | `reprocessing_requests.status = COMPLETED`, 1 `INTELLIGENCE_REPROCESS_COMPLETED` audit event |
| Queue lists after | main 0 / processing 0 | main 0 / processing 0 |

Worker did not exit; completion, transaction, audit, retry and acknowledgement
semantics are unchanged (`db.commit()` → hook → `queue.acknowledge(message)` →
`logger.info("analysis job completed …")`, `analysis_worker.py:262-268`).

## 7. Worker configuration documentation changes (Workstream B)

Both existing documents were updated in place; no competing document was created.

| Setting | Documented default | What the documentation now states that the code actually does |
| --- | --- | --- |
| `ANALYSIS_RETRY_BACKOFF_BASE_SECONDS` | `1.0` | The exponential term is `min(max, base * 2 ** (N-1))`; the slept wait is half of that term plus a uniform draw over the other half, so wait N falls in `[term/2, term]`. With base 5 the observed first waits were 3.4–4.9 s inside the 2.5–5 s band. |
| `ANALYSIS_RETRY_BACKOFF_MAX_SECONDS` | `60.0` | Ceiling per wait; once the term reaches it the outage settles at a steady poll between `max/2` and `max`. Nothing validates the pair, so a base above the max is accepted and simply starts every wait at the ceiling. |
| `ANALYSIS_SHUTDOWN_POLL_SECONDS` | `0.5` | Slices the backoff sleep, so it bounds SIGTERM latency **only while backing off** (measured 0.97 s and 1.25 s). While parked in a blocked dequeue the bound is `ANALYSIS_DEQUEUE_BLOCK_SECONDS` (measured 18.41 s at block 20 vs 1.75 s at block 1). |
| `ANALYSIS_REDIS_SOCKET_TIMEOUT_SECONDS` | `30.0` | The load-bearing bound: the read deadline that ends a stall when a peer stops answering without sending an RST. Validated to be strictly greater than the dequeue block. |
| `ANALYSIS_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS` | `10.0` | Bounds only connection establishment. |
| `ANALYSIS_REDIS_HEALTH_CHECK_INTERVAL_SECONDS` | `15.0` | Reuse check between commands; documented explicitly as never bounding an in-flight read. |
| `ANALYSIS_DEQUEUE_BLOCK_SECONDS` | `5` | Idle blocking-dequeue window and, because that read is unsliceable, the real stop latency for an idle worker. |

Validation behaviour documented as implemented: one validator exists on this family
(`socket_timeout > dequeue_block`, enforced with `ValueError` in
`analysis_queue._bounded_client`, i.e. the worker refuses to start);
`ANALYSIS_RETRY_BACKOFF_BASE/MAX_SECONDS` and `ANALYSIS_SHUTDOWN_POLL_SECONDS` have
no validators, and the documentation says so rather than inventing ranges.

## 8. Redis outage and hung-connection behaviour (Workstream C)

### 8.1 The three questions, answered by measurement

| Question | Answer | Evidence |
| --- | --- | --- |
| Did the blocking dequeue have a finite socket timeout before the fix? | **No** — `AnalysisQueue` built a bare `redis.Redis.from_url(...)`. A frozen peer left `brpoplpush` unanswered for the whole 45 s probe window with no reply and no exception. | `final-07-wsc-baseline-frozen-redis.json` |
| Does `health_check_interval` fix a frozen connection? | **No.** It pings an *idle* connection between commands; a read already in flight is not "between commands". | S3/S4 re-measured after the fix |
| Can a network blackhole block indefinitely? | Yes pre-fix (`docker pause`: socket open, no RST, no reply). Post-fix the stall ends at the socket deadline — freeze→warning in **8.23 s** with `socket_timeout 8.0`. | `sc4_blackhole_during_idle_dequeue.json` |

The outage exception set is `redis.exceptions.ConnectionError` **and**
`redis.exceptions.TimeoutError` — they are siblings under `RedisError`, so catching
`ConnectionError` alone never covered a socket timeout, and `AuthenticationError` is
the trap because it *does* subclass `ConnectionError`. `ResponseError`/`DataError`
stay outside on purpose: S7 measured a `WRONGTYPE` against a string key producing 0
backoff warnings, a traceback and **exit code 1**, and S8 measured an invalid
payload raising `ValueError` from `analysis_queue.py:67` with **exit code 1**.
Programming errors and invalid replies still propagate.

### 8.2 Eleven required failure scenarios — all executed

Host harness `wsc_scenarios.py` against this session's own Redis/PostgreSQL/MinIO
(run `be037fin7c1f1`), plus four container PID-1 cases:

| # | Scenario | Observed |
| --- | --- | --- |
| S1 | Redis unavailable before worker start | stayed alive, warnings stated 3.9/5.5/14.0 s (failures 1→3, base 4 max 20), job completed at 109.45 s, `attempt_count 1`, 1 result row, lists 0/0 |
| S2 | Clean disconnect during blocked dequeue | stop→warning **0.17 s**, stated delay 2.5 s, recovered and completed at 88.55 s, lists 0/0 |
| S3 | `docker pause` across the acknowledgement | DB committed while frozen; socket deadline ended the stall (warning 3.9 s); recovery requeued 1 abandoned job; completed with `attempt_count 2`, 1 result row; lists 0/0 — **nothing lost, no double ack** |
| S3a | Same, thaw before the abandoned-retry deadline | silent ack success: 0 warnings, no recovery line, completed `attempt_count 2`, lists 0/0 |
| S4 | Blackhole during idle dequeue | 8.23 s freeze→warning, worker alive, job completed after restore |
| S5 | Restore with jobs already queued | 3 queued pre-outage, 1 warning (3.0 s), all 3 completed after restore, each `attempt_count 1` |
| S6 | Four repeated outage cycles | 8 warnings, failures 1→8, stated 2.2/5.2/11.6/17.5/11.0/12.0/11.6/14.6 s — bounded by max, counter reset after each recovery |
| S7 | Unrelated Redis error (`WRONGTYPE`) | 0 warnings, traceback, **exit 1** |
| S8 | Malformed payload | `ValueError`, traceback, **exit 1**, poison entry left in processing (main 0 / processing 1) — recorded as an observation, not silently discarded |
| S9 | Reprocessing hook (§6) | see §6 |
| S10 | Recovery classification of 5 planted processing entries | 1 recovered and reprocessed, corrupt/missing/terminal discarded, fresh `running` left untouched, `recovered 1 abandoned job(s)` logged, all 8 classification booleans true |

Container cases (image `poa-backend:be037final`, worker as PID 1, `docker stop` as
the signal source): SIGTERM during a backoff → 1.25 s; during a blocked dequeue →
18.62 s (block 20) and 1.5 s (block 1); while a job runs → 10.91 s with the job
completing (`status completed`, `attempt_count 1`, 1 result row, lists 0/0). All
four: stop rc 0, `exit_code 0`, `oom_killed false`, `RestartCount 0`.

Capture lesson recorded: `logging.basicConfig(level=logging.INFO)` at
`analysis_worker.py:378` has no `stream`, so all worker lines go to stderr; reading
`docker logs` stdout alone silently produced an empty evidence set on the first
attempt. Both streams are merged by the harnesses now.

### 8.3 This acceptance run's own outage matrix (F2, run `be037wf7e3`)

Configurations differ per case (base/max/block are set explicitly); the stated
delay is what the worker logged, the measured interval is the wall gap between
consecutive warnings.

| Case | Setup | Measured |
| --- | --- | --- |
| C1 | Redis down before start, 3 jobs queued (base 10, max 60) | first warning 8.36 s after start; stated 4.6 s, 9.0 s; measured warning-to-warning 8.61 s (≈ stated + the failed attempt's own duration); recovery logged **15.12 s** after restore because the worker was mid-sleep; all 3 jobs `completed`, `attempt_count 1`, 1 result each; lists 0/0; exit 0, restarts 0 |
| C2 | Disconnect while parked in `BRPOPLPUSH` | first warning **0.14 s** after `docker stop`; stated 3.4 s, 10.0 s; `recovery_log_line: null` (see §15 finding); job enqueued after restore completed (`attempt_count 1`, 1 result) |
| C3 | Redis lost while a 42 MB job is in flight | job picked up at 4.34 s; by the time the outage was measured the job had **already committed** (`completed`, 1 result) — commit-before-ack held; 1 warning (4.2 s); recovery line 6.55 s after restore; lists drained 0.48 s later; final `attempt_count 2` with still exactly 1 result row (duplicate *work*, idempotent storage) |
| C4 | Three 22 s outage/restore cycles, queue empty | 6 warnings; stated 4.0, 8.5, 12.8, 15.1, 14.4, 12.5 s (failures 1→6 — the counter never reset while idle); **no recovery line in any cycle**; worker `running`, restart_count 0, exit 0 |
| C5 | SIGTERM during a backoff wait | first warning stated 22.7 s; `docker stop` returned in **0.97 s**; exit 0 |
| C6 | SIGTERM during a blocked dequeue (block 20) | stop latency **18.41 s**; exit 0 |
| C7 | SIGTERM during a blocked dequeue (block 1) | stop latency **1.75 s**; exit 0 |
| C8 | SIGTERM while a 42 MB job is running | job completed after the signal (`attempt_count 1`, 1 result); lists 0/0; stop 12.12 s; exit 0 |
| C9 | Three 30 s outages + 45 s idle windows, queue empty (base 5, max 600) | cumulative stated delays **3.7, 6.5, 14.0, 22.6, 40.2, 151.9 s**; `recovery_lines_logged_while_idle = []`; the job enqueued at the end completed 74.17 s later and only then logged `redis reachable again after 6 backoff(s)`; lists 0/0; exit 0 |

C9 is the runtime proof of the idle-recovery finding: with the queue empty the only
successful Redis call is a blocking dequeue that returns no message, and in
`run_worker` both the recovery log line and the reset of the consecutive-failure
counter sit *after* that path's `continue` (`analysis_worker.py:347`, `:364-366`).
Consequences measured on this run: no observability that Redis came back, and a
backoff that keeps growing across independent outages (an idle worker slept 151.9 s
straight through a restore). A fourth outage's first wait would fall in the
160–320 s band — that last figure is **derived from the measured formula, not
observed**.

## 9. Database bootstrap and schema-drift findings (Workstream D)

### 9.1 Reproducible bootstrap, measured twice

| Step | Container first boot (`docker/pg-init/init.sql`) | Alembic | Result |
| --- | --- | --- | --- |
| Fresh cluster (this acceptance stack, `be037wf7e3_db`) | extensions after first boot `plpgsql 1.0`, `postgis 3.4.2`, `vector 0.7.4`; public relations: **1** (`spatial_ref_sys`); **no `exemplo_dados`** | `alembic upgrade head` rc 0 → `t0u1v2w3x030`, **73 base tables** (75 non-catalog relations counting the two PostGIS views `geography_columns`, `geometry_columns`) | `alembic check` rc 0 with only the four logged suppressions of the known `uq_user_role_scoped` nulls-not-distinct autogenerate artifact |
| Second fresh disposable DB (WS-D, `be037fin7c1f1_db2`) | identical extension versions; 1 public relation; no vendor demo | same head, 73 tables, `search_path = "$user", public`, **15** baseline registry rows | drift gate 24 passed / 1 skipped |

The acceptance and suite databases of this run were compared object-by-object at the
end (`information_schema.tables`, both schemas): 75 vs 75, **no difference** — so
two independently created disposable databases built from the same tree reach the
same schema.

Extension-owned objects: `spatial_ref_sys` (owner `postgres`, kind `r`, created by
`postgis`), plus the `geography_columns`/`geometry_columns` PostGIS views. Their
provenance is the extension's own script, verified by creating a database with no
repo involvement and observing them after `CREATE EXTENSION`. The vendor demo table
`exemplo_dados` — the reason a baseline exception exists — was **absent** on both of
this session's boots; **no baseline exception was added, widened, or removed.**

Deliberate app-owned drift was injected (a manual table) and detected:
`test_drift_is_exactly_the_documented_baseline` failed rc 1 naming it,
`alembic check` exited non-zero mentioning it, and after removing the object the
same test passed rc 0. Detection works in both directions.

### 9.2 Bootstrap gap that is a product decision, not a defect

`roles` / `permissions` / `role_permissions` are Python constants seeded by
`backend/services/authorization.py::ensure_default_catalogue`, which **has no
production caller** — not the app startup, not any migration (grep-verified, and
re-verified by measuring the tables empty before a manual seed: `before=(0,0,0)` →
`after=(6, 69, 131)`). A freshly deployed database therefore boots with an empty
authorization catalogue. This run seeded it explicitly in both its databases. The
finding (inherited as D2) remains open for the owner.

### 9.3 Protected-target refusal, testable without touching a protected DB

`tests/integration/test_be029_database_safety_guard.py::test_verification_refusal_also_holds_over_a_real_connection`
is armed by `POA_PROTECTED_NAME_PROBE_DATABASE_URL`. The probe target is genuinely
disposable: a database *named* `pofa_dev` created inside this run's own Postgres
container. Measured: 1 passed rc 0 — `ProtectedDatabaseError` raised, and
`server_database_name(probe) != own_name` holds over a live connection, which is
what the guard keys on (the name the **server** reports, not the DSN text). The
live `pofa_dev` was never contacted. The probe was dropped afterwards.

## 10. Storage test isolation and the MinIO anomaly (Workstream E1)

`tests/integration/test_storage.py:77`'s restart-persistence case no longer depends
on the shared `pofa_minio`. Both shapes were executed:

| Shape | Result |
| --- | --- |
| Unarmed (default developer run) | **rc 0 — 6 passed, 1 skipped, 1 warning in 3.54 s.** Skip reason quotes `test_storage.py:138`: "POA_DISPOSABLE_MINIO_CONTAINER is not set, so there is no MinIO this test owns. Restarting the shared compose stack from a test is not allowed…" |
| Armed with this run's `be037fin7c1f1_minio` | **rc 0 — 7 passed, 1 warning in 7.59 s**, restart-persistence included |

The protection is bidirectional: the test cannot bounce a stack it does not own, and
this run never pointed its storage suites at the protected endpoint.

**The earlier `pofa_minio` restart question: cause established for the class of
event, still not attributed to any operator action.** Read-only inspection at
2026-10-14T14:50:31Z (`final-09-wse1-minio-restart-forensics.txt`) found
`pofa_minio` `Created 2026-09-13T13:33:00Z`, `StartedAt 2026-10-14T14:30:56Z`,
`FinishedAt 2026-10-14T14:30:54Z`, `RestartCount 0`, policy `unless-stopped`, and
`docker events` (not persistent) empty. This session then captured a directly
comparable event with a known cause: at 2026-10-15T02:44Z **all three** protected
containers and **all four** of the previous run's containers went to
`exited (255)` within the same second boundary while none of this run's acceptance
containers did, the engine's npipe was unreachable and no Docker processes existed
(`evidence/wsf-06-environment-event.json`). That signature — simultaneous daemon-wide
exit, `restart_count` still 0, restart only after the daemon came back on the
`unless-stopped` policy — is a Docker Desktop VM lifecycle event, not a container
restart issued by anyone. Conclusion: the protected MinIO was never restarted,
recreated or reconfigured by this task; the observed restarts are consistent with a
daemon-lifecycle event, and no evidence exists that this run caused them. This run
issued no command against the protected containers other than read-only
`docker inspect` and read-only `psql` inside `pofa_db`.

## 11. Owner-DSN / runtime-role integrity findings (Workstream E2)

Executed only against disposable databases and disposable roles. No owner, grant or
role of `pofa_dev` / `pofa_test` was modified.

Identity matrix (`tests/integration/test_be037e2_ledger_identity_matrix.py`,
7 passed in 19.42 s) covers the app runtime role, a privileged disposable owner and
an insufficient-permission role. The owner-side transcript
(`wse2_owner_transcript.py`, rc 0) measured, as the disposable cluster owner
(`current_user postgres`, `rolsuper true`, grants update/delete/truncate all
**true**):

| Step | Observed |
| --- | --- |
| Chain built through the app's own `append_event` | 3 rows, seq 1–3, `verify_chain valid true checked_events 3`; tail hash `bcc421d5…`, tail previous hash `68798906…` (out-of-band anchor) |
| Trigger catalog | `trg_audit_ledger_append_only`, `tgtype 27` → row-level, fires on UPDATE and DELETE, **fires_on_truncate false** |
| Owner UPDATE of the tail row | refused, **SQLSTATE 42501**, "append-only enforcement refuses UPDATE on the audit ledger" |
| Owner DELETE of the tail row | refused, 42501, "…refuses DELETE…" |
| Sanctioned hatch: `SET LOCAL poa.ledger_mutation_exception = 'true'` + UPDATE | **succeeded** — and `verify_chain` then reported `valid false`, `event_hash mismatch at sequence 3` |
| `TRUNCATE audit_ledger_events` | **succeeded** in 0.03 s (row triggers do not fire on TRUNCATE) |
| In-database verdict after the wipe | 0 rows, min/max null, `verify_chain valid true checked_events 0` |
| External digest | `external_digest_disagrees true` |

The distinction §8 requires, stated plainly rather than oversold: an
application-level trigger does **not** defeat a database owner in general. What it
does defeat is *any* identity's row-level mutation, including the owner's, because
the refusal lives in the trigger and grants cannot bypass it. TRUNCATE bypasses row
triggers by design; the F-05 non-owner runtime role is denied TRUNCATE, so the
application identity cannot reach the hole, while a cluster owner can. Detecting an
owner-level wipe requires the checkpoint digest published **outside** the database
(`audit_ledger.py:344-347` returns `valid=True` over zero rows, so an emptied
ledger looks identical to a fresh one from inside). That control is operational,
not a row trigger, and it is still an owner decision.

## 12. G1 authorization matrix results (F1)

Run against this acceptance stack's own API container in `AUTH_MODE=enforcing`, with
API-client bearer credentials and with development user tokens, in two shapes. HTTP
status **and** database side effects were verified for every case.

| Shape | Cases | All expectations met | Rejected requests that still created a row |
| --- | --- | --- | --- |
| dev tokens **off** (API clients only) | 23 | `true` | 0 (14 rejected cases, `analysis_jobs`/`evidence`/`audit` counts unchanged before vs after each) |
| dev tokens **on** (development user tokens) | 14 | `true` | 0 (`cross_org_row_created: 0`) |

Representative verified rows (observed = expected in every case):

- anonymous `POST /api/v1/analysis/jobs` → **401** "Authentication required";
  invalid bearer → 401; dev-user token while dev tokens disabled → 401; client with
  an unknown secret → 401.
- client lacking `intelligence.reprocess` → **403**; dev-user CITIZEN → 403.
- cross-organisation client (org B acting on A's evidence) → **404** (not 403), and
  no row created — the leak-free "does not exist" answer.
- malformed job id → **422** "Invalid resource identifier"; valid-UUID absent job →
  **404**; malformed evidence id in the body → 422 "Invalid evidence ID"; invalid
  `job_type` literal → 422 with the pydantic literal_error detail.
- authorized enqueue → **202** with `job_status queued`; authorized read → **200**;
  owner-scope read of its own job 200 vs cross-org read of the same job 404.
- dev bypass limited: dev-user tokens resolve only to seeded users and inherit the
  same permission/scope evaluation (ADMINISTRATOR 200, CITIZEN 403 on anchored
  verify).
- API-client contract: `POST /api/v1/evidence` 201, context PATCH governed by
  `evidence.update_context`, anchored verify requires global-scope `audit.read`
  (project-scope holder → 403), `/health`, `/ready`, `/openapi.json` reachable.
- cross-org isolation measured with the catalogue as seeded:
  `evidence.update_context` is held **only** by `FIELD_OFFICER`;
  `intelligence.reprocess` by `FIELD_OFFICER, SUPERVISOR`; `audit.read` by
  `ADMINISTRATOR, REVIEWER, SUPERVISOR`.

**Observation WSF-OBS-1 (product-shape, not a security defect):** an
API-client-driven ingestion needs a **GLOBAL** grant to complete the
upload→context step, because `resolve_resource_scope()` reports no project for an
unprojected evidence (`authorization.py:1003`), `can()` answers
`RESOURCE_UNSCOPEABLE`, and `enforce()` maps that to 404. Measured in both shapes:
an ORG-scope client gets 404 on its own just-uploaded evidence, a project-scoped
client gets 404, a client without `evidence.update_context` gets 403, and only a
GLOBAL-scope intake identity (a `FIELD_OFFICER`, not an ADMINISTRATOR — the seeded
catalogue grants `evidence.update_context` only to FIELD_OFFICER) gets 200. The
deployment consequence: machine intake needs a paired GLOBAL FIELD_OFFICER
credential, since `POST /api/v1/evidence` accepts no project of its own.

## 13. End-to-end synthetic evidence flow results (F3)

Fully synthetic JPEG (3,984 bytes) generated locally, uploaded through the real API
against this run's disposable MinIO — no endpoint invented, no authorization
bypassed, no fixture faked:

| Step | Observed |
| --- | --- |
| `POST /api/v1/evidence` | 201, `status uploaded`, `storage_key quarantine/a75a3d32-…/original`, `size 3984`, `content_type image/jpeg` |
| Object actually stored | bucket `be037wf7e3-quarantine`, `content_length 3984`, bytes **identical** to the local file, sha256 `190812dba57251a8aafd82fe7a0ed2e3d28a624126573690fd24aef83ff46b2c` equal to the local hash |
| Context attach | 200 → evidence projected onto project `c2e97af6-…` |
| `POST /api/v1/analysis/jobs` | 202, `job_status queued`, job `c3149df0-…` |
| Worker (container of this run, rc 0, restarts 0) | status sequence seen through the API: `queued → running → completed` |
| Final job via API | 200, `completed`, `attempt_count 1`, `error null`, result present, `completed_at 2026-10-14T17:30:26Z` |
| Final job in database | `completed`, `attempt_count 1`, `error null`, 1 result row |
| Stored `AnalysisResult` | `sha256` equals the uploaded bytes' hash (`sha256_matches_local_bytes true`), `phash 907355f348275675` with `phash_status success`, EXIF handled, `embedding_column_null true` with `embedding_status "unavailable"` and the loader error recorded verbatim |
| Duplicate matching | `semantic_matches 0`, `perceptual_matches 0` (single object in an empty corpus) |
| Signed download endpoint | 200 with a URL issued, `expires_in 900`, evidence id matches |
| Evidence row | `uploaded_quarantine`, the storage key above, sha256, 3984, `image/jpeg`, project id |
| Queue lengths after | main 0 / processing 0 |
| Ledger side effects | the flow appended **no** analysis-lifecycle event (see §15) |

**Honest limitation, stated as the task requires:** the inference step is
*degraded, not fabricated*. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are set
on every container this run starts and the image contains no model weights
(`docker inspect`/`find` probe: `weight_files_found: []`), so the embedding path
takes its documented "unavailable" branch and the stored result records the loader
failure instead of inventing a vector. **No model-weight download was performed,
because that requires explicit owner approval.** Full semantic inference therefore
remains unverified in this environment; closing it needs an approved outbound
weight fetch (or weights baked into the image) and a re-run of this flow.

## 14. Unit and integration suite totals

All nine categories were run by one harness (`wsf_f4_suites.py`) against **one**
target: the disposable suite database `be037wf7e3_suite` on this run's own Postgres
container, migrated to `t0u1v2w3x030` with `postgis 3.4.2` / `vector 0.7.4`, and
seeded with the permission catalogue (`CATALOGUE before=(0, 0, 0) after=(6, 69, 131)`).
Interpreter: `backend/.venv312_repro`. No category was pointed at `pofa_test` or
`pofa_dev` (`protected_targets_used: []`), and the acceptance database
`be037wf7e3_app` was recorded as untouched by the suites
(`acceptance_database_untouched_by_suites: true`).

| Category | Command | rc | Result line | Wall |
| --- | --- | --- | --- | --- |
| `unit_all` | `python -m pytest tests/unit -q -p no:cacheprovider` | 0 | 540 passed, 1 skipped, 6 warnings in 53.82s | 59.0 s |
| `integration_all` | `python -m pytest tests/integration -q -rs -p no:cacheprovider` | 0 | 390 passed, 10 warnings in 835.87s | 844.2 s |
| `authorization` | `python -m pytest tests/unit/test_authorization.py tests/integration/test_authorization.py -q` | 0 | 34 passed, 6 warnings in 44.52s | 48.5 s |
| `worker` | 7-module selection (see below) | 0 | 68 passed, 6 warnings in 75.59s | 81.7 s |
| `storage` | `python -m pytest tests/integration/test_storage.py -q -rs` | 0 | 7 passed, 1 warning in 5.50s | 8.2 s |
| `migration` | `python -m pytest tests/unit/test_migrations.py tests/integration/test_migration_and_crud.py -q` | 0 | 10 passed, 1 warning in 6.23s | 9.0 s |
| `schema_drift` | `python -m pytest tests/integration/test_schema_drift_gate.py -q` | 0 | 6 passed, 1 warning in 13.61s | 16.5 s |
| `be037_final` | 4-module BE-037 selection (see below) | 0 | 63 passed, 7 warnings in 58.52s | 62.2 s |
| `full_suite` | `python -m pytest tests -q -rs -p no:cacheprovider` | 0 | **930 passed, 1 skipped, 10 warnings in 590.47s** | 600.2 s |

**Totals reconciliation.** The tree total is exactly the two directory totals:
540 unit + 390 integration = 930 passed, and the single skip is the one unit skip.
The other six categories are *subsets* of those two directories, not additional
tests, so they must not be added to 930.

The two targeted selections, per file (several modules are parametrised, so the
collected count is not the number of `def test_` lines):

- `worker` = 68 → `tests/unit/test_be037a_analysis_worker_shutdown.py` 7,
  `tests/unit/test_be037c_analysis_queue_timeouts.py` 6,
  `tests/unit/test_be037i1_analysis_worker_redis_outage.py` 18,
  `tests/unit/test_be037g5_reprocessing_hook.py` 9,
  `tests/integration/test_be036_webhook_worker.py` 12,
  `tests/integration/test_be037c_redis_timeout_integration.py` 5,
  `tests/integration/test_analysis_jobs.py` 11.
- `be037_final` = 63 → `tests/unit/test_be037_webhook_redirect_ssrf.py` 24,
  `tests/integration/test_be037g1_analysis_auth.py` 13,
  `tests/integration/test_be037e2_ledger_identity_matrix.py` 7,
  `tests/integration/test_be029_database_safety_guard.py` 19.

**Zero skips in the integration tree.** `integration_all` reported no skip at all,
which is the point: four obligations in that directory are armed by environment and
skip silently otherwise. The harness armed all five variables for the whole matrix —
`POA_DISPOSABLE_MINIO_CONTAINER`, `POA_DISPOSABLE_REDIS_URL`,
`POA_DISPOSABLE_REDIS_CONTAINER`, `POA_DISPOSABLE_OWNER_DATABASE_URL`,
`POA_PROTECTED_NAME_PROBE_DATABASE_URL` — each pointing at this run's own container,
database or the disposable probe database named `pofa_test` that lived **inside**
this run's cluster (§16).

**Reconciliation with an earlier milestone number.** The WS-D evidence
(`run_1013t1635_7c1f1/evidence/wsd_second_boot.json`) records
`gate_summary: "24 passed, 1 skipped"` and separately `drift_test_clean: 1 passed`.
That 24 is not a different drift suite: it was a **combined selection** of
`test_schema_drift_gate.py` (6, as re-measured here) plus
`test_be029_database_safety_guard.py` (18–19 depending on arm state, 1 skip when the
protected-name probe is unarmed). 6 + 18/19 reproduces 24/1 exactly, so nothing has
regressed between the two runs and the two numbers describe the same tests counted
differently.

## 15. Every failure, skip, warning, and deviation

**Failures: 0.** Every one of the nine categories exited 0 and no category recorded a
`failed_tests` entry, including the full tree (930 passed). Nothing was re-run to
obtain that result, and no test was weakened, skipped out, or deleted to get it.

**Skips: exactly 1, in the whole tree.**

- `tests/unit/test_preflight.py:117` — "ML stack genuinely installed in this
  environment", inside `test_ml_missing_never_becomes_available_without_importer`.
  It is the *inverse* guard: it skips when the ML stack really is importable, because
  its subject is the behaviour of a missing stack. It is not an armed-by-environment
  obligation and it is not new in this run.

**Warnings: 10 in the integration and full-suite runs, 6–7 in the narrower
selections.** All are dependency deprecations, none is emitted by this project's own
assertions, and the set is identical (deduplicated) across runs:

1. `fastapi/testclient.py:1` — `StarletteDeprecationWarning`: using `httpx` with
   `starlette.testclient` is deprecated; install `httpx2` instead.
2. `pydantic/_internal/_config.py:323` — `PydanticDeprecatedSince20`: class-based
   `config` is deprecated, use `ConfigDict` (removed in V3.0).
3. `backend/app/main.py:121` — `on_event("startup")` is deprecated, use lifespan
   handlers.
4. `backend/app/main.py:135` — the same for `on_event("shutdown")`.
5. `fastapi/applications.py:4681` — the FastAPI-internal `on_event` forwarder.
6. `backend/security/authorization.py:84` — `HTTP_422_UNPROCESSABLE_ENTITY` constant
   deprecation.
7. `fastapi/routing.py:352` and `anyio/_backends/_asyncio.py:1100` — the same
   constant seen through the request path, counted per site.

Items 3–5 and 6–7 are the two open dependency-debt tasks (FastAPI lifespan migration,
`HTTP_422` constant rename). They are recorded, not fixed: fixing them is a code
change no workstream in this task was authorised to make.

**Deviations from the intended procedure during this run.** Each was corrected and
re-measured; none is hidden behind a passing number.

*Suite execution (F4)*
- The first F4 launch died immediately because Git Bash was handed a relative
  interpreter path; it was relaunched with the absolute
  `backend/.venv312_repro/Scripts/python.exe` path. The recorded numbers are from the
  relaunched process. The first launch produced no test data.
- During the matrix the host Docker Desktop engine stopped and auto-restarted at
  `2026-10-15T02:44:48Z` (`evidence/wsf-06-environment-event.json`): every container,
  including the protected `pofa_*` trio, shows `exited (255)` at one timestamp with
  `restart_count 0`, which is engine death rather than a restart of any one service.
  This run's containers were recovered by starting them again; the incident is the
  reason the integration timings are long (835 s) and it is why §17 quotes a
  `STARTED` value identical across the protected trio.

*Safeguards harness (F5), five fixes found by measurement*
- The redirect sink was unreachable because the probe URL used the name `sink`
  without a network alias; `--network-alias sink` was added and the step re-run.
  Without it the probe would have measured a DNS failure and reported it as a
  redirect decision.
- The probe container raised `AttributeError` from
  `__import__('urllib.request').Request` (that returns the top-level `urllib`);
  replaced with an explicit import, and exception *messages* are now recorded, not
  just type names.
- The SSRF-gate bypass stub originally answered the first DNS lookup with `8.8.8.8`,
  which would have put a real Google IP into a live socket path. It now answers
  `192.0.2.1` (TEST-NET-1), and the module docstring records the substitution and why
  no outbound traffic was involved.
- The first ledger measurement was **vacuous** (see the next bullet).
- The harness writes its evidence by rewriting the whole JSON, so re-running a single
  step dropped the sections another process had recorded. `main()` now merges the
  existing file before recording; the affected sections (`production_fail_fast`,
  `ledger_posture`, `secret_scan`) were **re-measured**, not restored from a backup.

*Ledger posture: from vacuous to non-vacuous*
- The first measurement reported the owner-shaped `UPDATE` as `ok`. It was not a
  finding about the trigger: this run's own integration suite had truncated the
  disposable `be037wf7e3_suite` ledger, so the statement matched **zero rows**. The
  harness now seeds that ledger through the application's own `append_event` path
  (3 rows, `max(sequence_number) = 3`) before each attempt and records the row count
  on both sides. Two seed attempts failed first and are part of the record:
  `append_event` rejected `resource_id='f5-seed-0'` because `_require_uuid` demands a
  UUID (`audit_ledger.py:98-105`), then the inline script raised `NameError` for a
  missing `import uuid`. With rows present, the same attempts produce the real
  answer: owner `UPDATE` and `DELETE` are refused by
  `audit_ledger_refuse_mutation()` ("append-only enforcement refuses UPDATE/DELETE on
  the audit ledger", hint `SET LOCAL poa.ledger_mutation_exception`), and 3 rows were
  still in the table afterwards. Owner `TRUNCATE` then succeeded (3 → 0), which is the
  documented residual. Incidentally, the suite's own ability to empty that disposable
  ledger is the same TRUNCATE bypass, observed from inside the test path.
- Seeding was deliberately confined to the disposable suite database. The acceptance
  database's ledger (23 rows, the artifact §11 quotes) was never written to by this
  step; only the runtime identity, which holds no UPDATE/DELETE/TRUNCATE grant, was
  aimed at it, and `acceptance_ledger_preserved: true` (23 before, 23 after) confirms
  it.

*Provenance artifact*
- The image-vs-HEAD comparison first read as "4 of 5 files match HEAD". Measured
  against three serialisations instead of one, the truth is narrower and cleaner:
  4/5 are **byte-identical** to the HEAD blob and 5/5 are byte-identical to the
  working tree and content-equal to HEAD after line-ending normalisation. The single
  byte mismatch is `backend/services/analysis_queue.py` — 0 CRLF pairs in the blob,
  154 in the checkout — because `core.autocrlf = true` on this machine and the build
  context is the working tree. It is a checkout artifact, not a code difference.

*Cleanup harness (WS-G)*
- `file_scrub()` existed but was never called by `main()`, so no credential-bearing
  file would have been removed; it is now run in the verify step, after the docker
  teardown has been verified.
- The same whole-file-rewrite bug as F5: a step run as its own process started from an
  empty `OUT`. `main()` now merges the existing evidence and keeps the original
  `started_at`.
- The compose-label rule alone could not justify removing `be037fin7c1f1_db2`, which
  was started with `docker run` and therefore carries no
  `com.docker.compose.project` label. The rule did its job — it refused, and the
  container and its volume survived the first pass. A second, equally positive
  identification path was added (the creating literal in `wsd_second_boot.py`, the
  recorded container name and `docker_run_rc = 0` in that run's own
  `wsd_second_boot.json`, and the live ID/creation timestamp read back from docker);
  with that proof the container was removed by name and its volume followed. Nothing
  was ever deleted on a name pattern.
- A second teardown pass **overwrote** the first pass's per-item record in
  `wsg-07-cleanup.json` (the same single-process-state defect, one level up). The
  console log of the first pass is quoted in §16 for those values, and a `merge_tear()`
  helper now unions repeat passes instead of replacing them. Consequence of the same
  bug: the post-hoc `pg_database` listing for `be037fin7e3_db` is not in the JSON
  either; the databases that lived in that cluster are named in §16 from the console
  read taken at 09:25:21 before removal and from the creation-time evidence.
- `cluster_databases()` could not read the sibling run's databases because those
  containers were already `exited (255)` from the engine incident, and a stopped
  container cannot be `docker exec`'d. Reported as a gap, filled from that run's own
  creation-time evidence rather than guessed.

*Secret hygiene*
- The evidence scan was originally narrower than the task requires (one run's
  throwaway values, one directory). It now covers every file under the BE-037 final
  scratch root against 12 credential shapes, and it is not the only check: a separate
  shape sweep (`wsf_g_secret_sweep.py`) looks for presigned-object URLs, credential
  scopes in query strings, bearer JWTs, run-derived passwords and DSNs with inline
  secrets without ever printing a match.
- Those two scans found two files that should not have held a value: an early run's
  botocore debug log (S3 access key inside the recorded request URLs, 4 occurrences,
  with signatures) and this run's `wsf_env_event.py` (the owner password written as a
  literal instead of derived). Both were redacted in place and both scans re-run: the
  value scan is now **clean over 114 files**, and the shape sweep's only remaining
  matches are 11 harness-source DSN *templates* (`...://postgres:{RUN_ID}pw@...`),
  which contain no secret.
- A final scan of exactly the files that leave the scratch tree — this report plus
  every repo file the task touched — against both mechanisms (`wsf_g_final_report_scan.py`,
  rc 0) found **0** credential values and 2 credential-*shaped* strings: the DSN in
  `.env.example:7`, which is `postgres:postgres` on `localhost` — the documented
  local-development example default, already committed by the user at HEAD and not
  part of this task's diff (see §5.2: this task's `.env.example` hunks all start at
  line 29) — and the f-string DSN *template* in
  `tests/integration/test_be037e2_ledger_identity_matrix.py:184`, which interpolates
  an armed environment variable and contains no value. **No report, log, evidence
  file, or file created by this task contains a credential, a signed URL or a JWT**,
  and no `pofa_dev`/`pofa_test` credential was ever written down.

*Scope limitations, stated rather than smoothed over*
- **No model weights were downloaded**, so the containerised inference path ran
  degraded: with `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` and no weights in the
  image (`weight_files_found: []`), the embedding column is written `null` with
  `embedding_status "unavailable"` and the loader error recorded verbatim. Semantic
  similarity is therefore **unverified in this environment**; §13's flow is real up to
  the point where it needs weights.
- Observation **WSF-OBS-1** (§12): machine intake needs a paired GLOBAL-scope
  `FIELD_OFFICER` credential, because an unprojected evidence has no resource scope to
  authorise against and `POST /api/v1/evidence` accepts no project of its own. This is
  a product-shape consequence, measured in both authorization shapes, not a security
  defect.
- **S8** (poison-message quarantine), **NEW-1** (idle recovery/counter behaviour),
  **NEW-2** (the analysis lifecycle appends no audit event — confirmed by the ledger
  histogram in §11: `API_CLIENT_CREATED 6, USER_CREATED 5, ROLE_ASSIGNED 5,
  EVIDENCE_UPLOADED 3, PROJECT_SCOPE_CHANGED 2, ORGANIZATION_CREATED 2`, and no
  `ANALYSIS_*` type at all) remain open owner decisions; none was fixed under cover of
  this run.
- G4, G6, G7 and I5–I9 were not in this task's scope and are reported as not run.

## 16. Disposable-resource manifest and cleanup results

Every resource below was created by this task under one of two run ids
(`be037wf7e3` for WS-F, `be037fin7c1f1` for WS-A…WS-E), was recorded as **free before
creation** in `wsf-00-manifest-before.json` (`all_names_free: true`, `all_ports_free:
true`), and was removed only after that name was matched against its own compose
project label or, for the one `docker run`-created container, against the harness that
started it.

| Kind | Names | Removed |
| --- | --- | --- |
| Containers (7) | `be037wf7e3_db`, `be037wf7e3_redis`, `be037wf7e3_minio`, `be037fin7c1f1_db`, `be037fin7c1f1_redis`, `be037fin7c1f1_minio`, `be037fin7c1f1_db2` | 7/7, each `rm -f` rc 0 and `docker inspect` rc≠0 afterwards |
| Volumes (7) | `<run>_db_data`, `<run>_redis_data`, `<run>_minio_data` for both runs, plus `be037fin7c1f1_db2_data` | 7/7 rc 0 (`db2_data` only after its container was identified and removed; the first attempt correctly reported "volume is in use") |
| Networks (2) | `be037wf7e3_net`, `be037fin7c1f1_net` | 2/2 rc 0 |
| Databases inside this run's clusters | `be037wf7e3_app` (acceptance), `be037wf7e3_suite` (suites), a disposable database deliberately named `pofa_test` inside `be037wf7e3_db`, and the sibling run's `be037fin7c1f1_app`, `be037fin7c1f1_app2` and its protected-named probe | Destroyed with their volumes; they never existed outside this run's containers |
| Roles | `be037wf7e3_runtime`, `be037wf7e3_migrator` (+ the roles the WS-E2 module creates per test) | Destroyed with the cluster |
| Buckets | `be037wf7e3-quarantine`, `be037wf7e3-evidence` (+ the sibling run's two) | Destroyed with their volumes |
| Queue keys | `be037wf7e3:analysis:jobs`, `be037wf7e3:analysis:jobs:processing` | Destroyed with the Redis volume |
| Host ports | 15442, 16389, 19010, 19011, 18080, 18081, 15432, 15433, 16379, 19000, 19001 | **All 11 free again** (`host_ports_free_after`, connect-probe `true` for each) |

Ad-hoc probe containers created inside this run's network (`be037wf7e3_f5_sink`,
`be037wf7e3_f5_probe`, `be037wf7e3_f5_seed`, `be037wf7e3_f5_api`,
`be037wf7e3_f5_chain`) were each named with this run's prefix and removed by the
harness that started them, in a `finally`, so none could survive as an unnameable
orphan.

**Verification after teardown** (`evidence/wsg-07-cleanup.json`):
`containers_remaining_matching_run_ids: []`, `volumes_remaining_matching_run_ids: []`,
`networks_remaining: ["bridge", "host", "none", "proof-of-action-final_default"]` —
i.e. only Docker defaults and the protected project's own network.

**Retained deliberately:** the image `poa-backend:be037final`
(`5f6224ec2790`, 3.06 GB, no container using it any more). It is a deterministic build
of committed code and contains no secrets; deleting a multi-gigabyte image the owner
may want for a rebuild is not a resource this task was asked to reclaim. It is reported
here so the owner can delete it with one command if they prefer.

**Credential-bearing files removed** (only after confirming each was written by this
task — the run id is embedded in the filename and the manifests recorded the resources
as absent before creation): `be037wf7e3.compose.yml`, `f2-worker.env`,
`be037fin7c1f1.compose.yml`, `worker-container.env`. The evidence records each file's
path, size, mtime and which credential *variable names* it carried — never a value.
Harness scripts, evidence JSON and run manifests were kept as the audit trail.

No broad cleanup command was used at any point: no `docker compose down`, no `-v`, no
`system prune`, no `volume prune`, no pattern deletion. `refuse()` in the cleanup
harness aborts before the docker call if any target name begins with `pofa`/`poa_` or
contains `proof-of-action`, and the run-id filter never presents a protected name to
the remover.

**Evidence artifacts.** WS-A…WS-E: `D:\CODING\Scratch\be037final\run_1013t1635_7c1f1\`
— `final-00-git-baseline.txt`, `final-00a-git-full-diff.txt`,
`final-00b-protected-db-baseline.txt`, `final-00c-docker-baseline.txt`,
`final-00d-image-provenance-probe.txt`, `final-01-g5-vacuity.txt`,
`final-02-pre-stack-snapshot.txt`, `final-03-ownership-manifest.md`,
`final-04-name-colliding-fixtures.txt`, `final-05-wsd-boot-evidence.txt`,
`final-05b-disposable-schema-objects.txt`, `final-06a-vendorsim-start.txt`,
`final-06b-vendorsim-measured.txt`, `final-07-wsc-baseline-frozen-redis.json`,
`final-08-redis-exception-hierarchy.txt`,
`final-09-wse1-minio-restart-forensics.txt`, `final-10-wsc-measured.md`,
`final-00-stage0-baseline.md`; in its `evidence\` subdirectory the `sc1`–`sc10`
scenario JSON+log set, `container_sigterm_*.json`, `wsd_second_boot.json`,
`wsd_protected_probe.json`, `wse2_owner_transcript.json` and the
`wse1_storage_{armed,unarmed}.pytest.log` transcripts.
WS-F/WS-G: `D:\CODING\Scratch\be037final\run_WSF_be037wf7e3\evidence\` —
`wsf-00-manifest-before.json`, `wsf-01-bootstrap.json(.out)`,
`wsf-01b-state-reset.json(.out)`, `wsf-02-f1-f3.json(.out)`, `wsf-03-f2.json(.out)`,
`wsf-03b-f2-c9.out`, `wsf-03b-f2-db-readback.json`, `wsf-04-suites.json(.out)` plus
the per-category `suites/*.txt` result lines, `wsf-05-safeguards.json(.out)`,
`wsf-05b-safeguards-rerun.out`, `wsf-06-environment-event.json`,
`wsg-07-cleanup.json(.out)`, `wsg-08-final-report.json` (this report's placement and
the git state at the moment of writing) and `wsg-09-final-secret-scan.txt`.
The harness scripts that produced them are retained as the audit trail; only the four
credential-bearing generated files were removed (§ above).

## 17. Protected-resource before-and-after evidence

The protected databases were measured **twice with the same read-only statement** —
once before any teardown (09:19, with the stack still up) and once after it completed —
using the same query shape, container and `default_transaction_read_only=on` session
option as the opening baseline of this task
(`run_1013t1635_7c1f1/final-00b-protected-db-baseline.txt`), so a difference would mean
a difference in the data and not in the probe. The three fields agree across all three
measurements.

| Field | `pofa_dev` before | `pofa_dev` after | `pofa_test` before | `pofa_test` after |
| --- | --- | --- | --- | --- |
| identity (db\|user) | `pofa_dev\|postgres` | identical | `pofa_test\|postgres` | identical |
| `audit_ledger_events` rows | 6023 | 6023 | 53316 | 53316 |
| sequence min / max | 1 / 6059 | 1 / 6059 | 1 / 53316 | 1 / 53316 |
| users | 1054 | 1054 | 3263 | 3263 |
| projects | 544 | 544 | 1636 | 1636 |
| evidence | 284 | 284 | 1216 | 1216 |
| analysis_jobs | 32 | 32 | 38 | 38 |
| webhook_events | 561 | 561 | 4455 | 4455 |
| public tables | 75 | 75 | 75 | 75 |
| `alembic_version` | `t0u1v2w3x030` | identical | `t0u1v2w3x030` | identical |
| extensions | `plpgsql,postgis,vector` | identical | `plpgsql,postgis,vector` | identical |
| vendor demo tables (`exemplo_dados`) | 0 | 0 | 0 | 0 |

`protected_databases_before_teardown == protected_databases_after_teardown` is recorded
literally as true for both databases, and both equal the task's opening baseline. The
75-vs-73 table-count relationship is the documented PostGIS-view artifact (73 `pg_class`
relations plus the `geometry_columns` / `geography_columns` views plus `spatial_ref_sys`),
not drift — see the schema-drift arithmetic in §9.

Protected containers, re-read before and after with name, full ID, creation time, start
time, restart count, state and restart policy:

| Container | Full ID (unchanged) | Created | After-teardown state |
| --- | --- | --- | --- |
| `pofa_db` | `7949c99808161e138c35489a9d34928b873cfcd4cead9eb0f00fb37261033baf` | 2026-09-18T18:09:18Z | running, `RESTARTS=0`, policy `unless-stopped`, started 2026-10-15T02:44:48.359Z |
| `pofa_redis` | `29b684e82d7c9b2818fc1a3d0f48415ab78f923ec7e063150208d275bd767af5` | 2026-09-13T16:58:41Z | running, `RESTARTS=0`, policy `unless-stopped`, started 2026-10-15T02:44:48.290Z |
| `pofa_minio` | `54fce2fccd46fa5b2f10daba312d1ed7bb78920918c9e620ebb111a63f45dcbd` | 2026-09-13T13:33:00Z | running, `RESTARTS=0`, policy `unless-stopped`, started 2026-10-15T02:44:48.292Z |

Same IDs as the opening manifest, same creation timestamps, `RESTARTS=0` throughout, and
a start time **identical across all three** — `02:44:48Z`, the moment the host Docker
Desktop engine stopped and recovered (§15). That shared timestamp is the signature of an
engine restart, not of anything this task did: this task never stopped, restarted,
recreated or reconfigured a protected container, and the only protected-resource
operations performed were `docker inspect` and read-only `psql` inside a
`default_transaction_read_only=on` session. The protected volumes
(`proof-of-action-final_db_data`, `proof-of-action-final_minio_data`) and the protected
network `proof-of-action-final_default` are listed as still present in the after state.

## 18. Remaining owner decisions and production blockers

Two different lists, because they need different actors.

### 18.1 Owner decisions (product / scope calls an engineer cannot make)

| Ref | Decision outstanding | Smallest next action |
| --- | --- | --- |
| D2 | `ensure_default_catalogue()` has no production caller, so a freshly deployed database has an empty roles/permissions catalogue (§9.2) | Owner chooses: call it from app startup, from a migration, or from a documented one-shot bootstrap job |
| WSF-OBS-1 | API-client ingestion needs a paired GLOBAL-scope `FIELD_OFFICER` credential because `POST /api/v1/evidence` accepts no project (§12) | Owner confirms the intake credential shape before any client ships |
| NEW-1 | Idle-worker recovery: no "reachable again" line and no failure-counter reset while the queue is empty, so backoff grows across independent outages (measured 151.9 s sleep through a restore, §8.3 C9) | Move the reset/recovery log so it also runs on a successful empty dequeue — a two-line change in `run_worker`, deliberately not made here because it changes observable ops behaviour the runbook documents |
| NEW-2 | The analysis path emits **no** audit-ledger event at all: `ANALYSIS_COMPLETED` / `ANALYSIS_FAILED` are enumerated in `AUDIT_EVENT_TYPES` but never appended — measured 0 ledger rows per job across all F2 jobs and the F3 flow (§15) | Owner decides whether analysis lifecycle belongs in the tamper-evident ledger; if yes, the append points and their writer policy need specifying (BE-032R D-CHAIN policy applies) |
| S8 | A single malformed payload in the processing list stops the consumer (exit 1) — propagation is mandated by the task, so it is a design call, not a bug fix | Owner chooses poison-message quarantine vs propagate-and-restart |
| G4/G6/G7, I5–I9 | Inherited Phase B findings recorded as open in the BE-037 backlog register | Owner triage |
| TRUNCATE | The in-database append-only trigger does not fire on TRUNCATE; the closing control is the out-of-band checkpoint digest plus the F-05 non-owner role (§11) | Owner: adopt the digest-preservation procedure as a control, or accept the residual |
| OQ-3 | `external_subject` contract still undecided (inherited from BE-030/BE-031) | Owner policy decision |
| Commit authorization | Everything from this task is unstaged (§4, §20) | Owner reviews the diff and commits if acceptable |

### 18.2 Production blockers (all still open, none changed by this task)

| Blocker | Current status | Evidence that would close it |
| --- | --- | --- |
| Approved production target environment | **Absent** — verified by enumeration: no production host/secret file/deployment target exists in the repo or the reachable environment | A named target plus an approved change window |
| Approved secret store / production secret management | **Absent** — JWTs exist only as `.env` values; there is no secret store | A provisioned store and a documented rotation procedure |
| Production runtime identity and cutover | Development cutover to `poa_runtime` is done and verified (BE-034/BE-035); **production** cutover has no target to happen on | Deployment on the approved target with `pg_stat_activity` proof of the runtime identity and no fallback |
| Live health and integrity verification against production | Not run — only disposable stacks were started here | `/health`, `/ready`, anchored `/api/v1/audit/verify/anchored` against the live cluster |
| Backup / PITR | `archive_mode=off` in the current Postgres setup; `pg_dump` exists only inside the container (BE-029 G3) | Enabled archiving plus a demonstrated restore to a point in time |
| Historical ledger gaps | `pofa_dev` chain remains `known_historical_only` with 7 gap-only failures and 0 hash mismatches (BE-032/BE-033); this run's fresh disposable ledger is `valid true` over 23 events | A reconciliation register accepted by the owner |
| App restart / D-RESTART | Procedure authored, execution held (no target) | Restart executed against the approved target with readiness proven |

## 19. Cloud deployment: none occurred

No cloud resource was provisioned, contacted or configured. No staging or production
deployment was performed. No container in the protected Compose project
(`proof-of-action-final`) was created, recreated, restarted or reconfigured by this
task. Every container this task started was on the private networks of its own
disposable Compose project (`be037fin7c1f1`, `be037wf7e3`), with host ports bound to
`127.0.0.1`. No webhook, e-mail or other external notification left the machine:
the webhook transport was exercised only against a disposable redirect sink
container on this run's own network, and the SSRF gate was enumerated against
loopback, RFC1918, link-local metadata (`169.254.169.254`) and
`*.invalid` names. No model weights or other large ML artifacts were downloaded.

## 20. Commit / push: none occurred

- Nothing was staged at any point (`git diff --cached` empty before and after).
- No commit was created and no commit was amended.
- No branch was switched; the branch is `Backend` at both ends of the session.
- Nothing was pushed; no remote was contacted.
- `git status --short` at the end shows exactly the entries in §4 — the three files
  this task modified, the two new test modules, and this report file
  itself — all of which are this task's documentation/test additions and the user's
  own pre-existing edits.
- No history rewrite, no `git clean`, no `git reset`, no destructive checkout. The
  user's committed deletions of the previous result reports (§4) are preserved; this
  report is therefore a new file rather than an edit of a deleted one.

