# BE-037 Phase B — High-Defect Remediation (G1 + I1): Final Report

- Run id: `c95222` (scratch dir `D:/CODING/Scratch/be037phasea/phaseB_remed_c95222`)
- Date: 2026-10-13 (all timestamps UTC)
- Repository at start and at end: branch `Backend`, HEAD
  `b5d4a5fba73b9a38289233f3fc75f6063fec39db` ("Docker Repair")
- Working tree at end (identical to the pre-creation baseline `remed-00`):
  4 modified files + 2 new test files, **nothing staged**
- Scope as given: remediate **G1** (analysis endpoint authentication /
  authorization) and **I1** (analysis worker Redis-outage resilience). No cloud
  provisioning, no deployment, no staging, no commit, no push, no production
  acceptance declaration.
- Verdict: **BOTH DEFECTS REMEDIATED AND VERIFIED ON DISPOSABLE INFRASTRUCTURE —
  PRODUCTION ACCEPTANCE NOT CLAIMED** (the inherited BE-037 blocker still
  applies: there is no production target and no production secret store).

No earlier Phase A / Phase B report or log was overwritten. The defects being
closed here are `BE-037B-G1` and `BE-037B-I1` from
`../phaseb_be037b65cee2/phaseB-stageJ-final-report.md`.

---

## 0. Stage 0 — inspection and preservation

Measured before touching anything (`remed-00-precreation-baseline.txt`,
`remed-00b-protected-db-baseline.txt`, `remed-01-ownership-manifest.md`):

- git branch/HEAD/index/working tree as above; the ownership manifest and both
  baselines were written **before** any resource of this run was created.
- Read in full before editing: `backend/api/v1/endpoints/analysis.py`,
  `backend/security/authentication.py`, `backend/security/authorization.py`,
  `backend/services/authorization.py` (`resolve_resource_scope`, `Principal`,
  denial taxonomy), `backend/services/analysis_queue.py`,
  `backend/workers/analysis_worker.py`, and the existing analysis/authorization
  test suites.
- Every pre-existing user modification, including the documentation deletions
  already in the tree, was preserved. `git add`, `git commit`, `git push`,
  `git reset`, `git clean`, `git restore`, `git stash` were **not** run at any
  point in this task.

---

## 1. BE-037B-G1 — analysis endpoints had no authentication or authorization

### Root cause

`backend/api/v1/endpoints/analysis.py` declared exactly two routes, and both
handlers took only `db: Session = Depends(get_db)`. There was no
authentication dependency and no authorization check on either one, so on an
instance started with `AUTH_MODE=enforcing` an unauthenticated caller got
`202` from `POST /api/v1/analysis/jobs` and `200` from
`GET /api/v1/analysis/jobs/{job_id}`. This was not a development-mode artifact —
the routes simply were never wired into the BE-016 authorization surface that
every other guarded endpoint uses.

### Changes (all in the existing pattern; no new permission, no migration)

`backend/api/v1/endpoints/analysis.py` (+28/-5):

- `POST /jobs` → `Depends(require("intelligence.reprocess"))`, then
  `enforce(principal, "intelligence.reprocess",
  resolve_resource_scope(db, "evidence", payload.evidence_id), request)`.
  The target evidence is named in the **body**, so the scope can only be
  resolved after the body is parsed — the same shape the correction and
  reprocessing endpoints already use. The body parameter was renamed
  `request` → `payload` so `request: Request` can be the HTTP request that
  `enforce` needs for its audit context.
- `GET /jobs/{job_id}` → `Depends(require("evidence.read", "analysis_job",
  "job_id"))`, i.e. the generic path-scoped guard with the job resolved through
  its evidence.
- `if not is_development_bypass(principal)` wraps only the `enforce` call, so
  the documented `AUTH_MODE=development` anonymous behaviour is preserved
  exactly (root-level runtime scripts and the 12 pre-existing anonymous
  integration assertions keep working); authentication itself still runs.
- Router audit: the file has two `@router.*` routes
  (`analysis.py:22`, `analysis.py:52`) and no other endpoint, so there is no
  second unguarded analysis surface. Service-to-service access is not
  special-cased — an API-client principal passes the same `enforce`, scoped to
  the projects it holds the grant for.

`backend/services/authorization.py` (+10): new `analysis_job` branch in
`resolve_resource_scope`, following the established fallback used by
`correction_request`, `reprocessing_request`, `publication` and
`intelligence_invalidation`: an analysis job has no scope columns of its own, so
it is scoped job → evidence → project → organization by delegating to
`resolve_resource_scope(db, "evidence", row.evidence_id)`. An unknown job id
falls through to the existing `RESOURCE_UNSCOPEABLE` path (404), consistent with
the other types.

Permission choice is the owner's, recorded in `remed-01`: `intelligence.reprocess`
for enqueueing, `evidence.read` for reading a job.

### Security impact

- Closes anonymous compute-spend / queue-flooding: an unauthenticated caller can
  no longer enqueue worker jobs.
- Closes cross-tenant read: job results are only visible inside the caller's
  scope; a cross-organization job is **404, not 403**, so its existence is not
  disclosed. Measured: a cross-org `POST` was denied with 404 and the
  `analysis_jobs` row count was unchanged (2 before, 2 after) — denial happens
  before any row is created, so an unauthorized caller cannot even leave queue
  work behind.

### Tests and actual results

| What | File / command | Actual result | Exit |
| --- | --- | --- | --- |
| New G1 integration suite (13 tests: missing/invalid credentials → 401/403, authorized → 202/200, cross-org → 404 with no row created, malformed id → 422 before lookup, scope resolution contract, development-mode bypass unchanged) | `tests/integration/test_be037g1_analysis_auth.py` | first run 1 failed / 12 passed (my own assertion contradicted the measured delegation contract — `remed-07-int-g1.txt`); after the assertion was corrected to the real contract, **13 passed in 26.13s** (`remed-07-int-g1-rerun.txt`) | 1† then 0† |
| Relevant regressions (analysis jobs, vision intelligence, temporal, governance, integration + unit authorization) | 6 selections, `remed-08-regression.txt` | **78 passed**, 7 warnings, 193.89s; no FAILED line | 0† |
| **Real endpoint authentication matrix over a socket** against the disposable enforcing API (`AUTH_MODE=enforcing`, `AUTH_DEV_TOKENS_ENABLED=false`) | `be037rem_g1_live_probe.py` → `remed-10-live-g1.txt` | **13/13 checks passed**: anonymous 401, invalid bearer 401, malformed id 422, CITIZEN-role POST 403, cross-org POST 404 (row count unchanged), cross-org GET 404, authorized FIELD_OFFICER POST 202 / GET 200, CITIZEN GET 200 on its own project, service-to-service API-client POST 202, API-client GET on another org's job 404 | 0† |

**Exit-code provenance (applies to both tables in this report).** Captured
verbatim in the log: `remed-06` ("FIRST RUN: exit code 1", "SECOND RUN: exit code
0"), `remed-16` (unit exit=1, integration exit=1), `remed-17` (unit exit=0),
`remed-20` / `remed-21` (teardown and post-check exit=0), and the per-step
`exit=` markers inside `remed-14`. Marked **0†** where the shell code was not
separately written to the file and the value is derived from the recorded
summary line (a pytest run whose tail reports only `passed`, and a probe that
prints its own `13/13 checks passed`, cannot have exited non-zero under those
tools' contracts). Nothing in this report presents a derived number as a
measurement.

### G1 limitations
- The live matrix proves the API process, not a browser; no TLS/reverse-proxy
  layer was involved.
- `POST` reuses `intelligence.reprocess` because the catalogue has no
  `analysis.*` action; if the owner later wants a dedicated action, that is a
  catalogue + migration change and was explicitly out of scope here.
- No audit-ledger event is written by the analysis endpoints themselves (the
  job row and the worker's later events are the trail). That matches the other
  enqueue endpoints and was not changed.

---

## 2. BE-037B-I1 — the analysis consumer could not survive a Redis outage

### Root cause

`run_worker()` looped `queue.dequeue(timeout=5)` with no exception handling and
`__main__` caught only `KeyboardInterrupt`, so one `redis.exceptions.ConnectionError`
escaped and killed the process (measured previously as `exit=1` within ~1 s of
Redis disappearing). Nothing in the loop backed off, and messages still on the
main queue were simply stranded, because `recover_abandoned()` inspects only the
`:processing` list. The shipped `restart: unless-stopped` policy turned that into
a crash-loop rather than fixing it.

### Changes

`backend/workers/analysis_worker.py` (+112/-13) and `backend/core/config.py`
(+9):

- `TRANSIENT_REDIS_ERRORS = (redis.exceptions.ConnectionError,)` — **only** the
  dependency-outage class is handled in-loop. A `ResponseError` (e.g. WRONGTYPE,
  i.e. a programming/configuration fault) still propagates and fails loudly;
  pinned by a test.
- `_backoff_delay(consecutive_failures)`: `min(max_seconds,
  base * 2**(n-1))`, split into a fixed half plus `random.uniform(0, half)` —
  bounded exponential with jitter, so several workers restarted together do not
  synchronise their retries.
- `_interruptible_sleep(seconds)`: sleeps in `analysis_shutdown_poll_seconds`
  (0.5 s) slices and returns `True` as soon as `_shutdown_requested` is set, so
  a long backoff never delays SIGTERM.
- `_await_redis_retry(failures)`: logs
  `redis unavailable; backing off %.1fs (consecutive failures %d)` and returns
  whether the loop should stop (shutdown requested).
- `requeue_needs_recovery` flag: when Redis comes back, the loop re-runs
  `recover_abandoned()` before the next `dequeue`, so whatever was left
  un-acknowledged during the outage is reclassified. Recovery skips fresh
  `running` jobs, so this cannot steal live work.
- Acknowledgement discipline unchanged and re-pinned: `process_message`
  acknowledges only after the DB outcome is committed. If the ack (or the retry
  requeue) itself hits the outage, the payload stays in the `:processing` list —
  exactly the state a crash leaves — and the next recovery pass either discards
  it (terminal) or requeues it (abandoned). No job is ever acknowledged early.
- Graceful shutdown preserved: `finally` still closes the queue client and calls
  `get_engine().dispose()`; per-message sessions are closed by
  `process_message`.
- Additional defect found by reading, not by a red test: the startup recovery
  pass was an unprotected call *before* the loop, so an outage beginning during
  process start escaped the guard and crashed the worker. It is now the loop's
  first guarded action (`requeue_needs_recovery = True` at entry), pinned by
  `test_startup_outage_is_backed_off_instead_of_crashing_the_worker`.
- New settings (defaults, no migration, no `.env` change):
  `analysis_retry_backoff_base_seconds = 1.0`,
  `analysis_retry_backoff_max_seconds = 60.0`,
  `analysis_shutdown_poll_seconds = 0.5`.

### Reliability impact

Queue work that was previously stranded (or silently dropped by a crash-loop)
now survives a full Redis stop/start, the consumer stays alive and observable,
and shutdown stays immediate. The system no longer reports 202-acceptance while
not consuming.

### Tests and actual results

| What | File / command | Actual result | Exit |
| --- | --- | --- | --- |
| Focused unit tests: outage, repeated outage, outage during ack, outage during requeue, recovery-only-at-startup, non-transient error still propagates, backoff bounds/jitter, interruptible sleep, startup outage | `tests/unit/test_be037i1_analysis_worker_redis_outage.py` (14 tests) + the 7 pre-existing BE-037A worker-shutdown tests | first run 1 failed / 19 passed — my scripted dequeue also injected a second outage, so the loop correctly took a *larger* second backoff; assertions were kept and the fake corrected (`remed-06-unit-i1.txt`); then **20 passed in 3.14s**. The 14th test was added afterwards and is covered by the full unit runs below | 1 then 0 |
| **Real Redis-outage / recovery scenario on disposable infrastructure** (`docker stop`/`docker start` on this run's own Redis; worker on an `internal: true` network) | `i1-outage-driver3.sh` → `remed-14-live-i1-run3.txt`, `remed-15-i1-pg-outcomes.txt` | worker started **into** the outage and never exited: measured backoffs **4.1 / 14.4 / 27.4 / 58.3 s** with `ANALYSIS_RETRY_BACKOFF_BASE_SECONDS=8`, cap 60; `status=running restarts=0` throughout; SIGTERM delivered while inside the 58.3 s wait was honoured — `stopping`/`stopped` logged at 13:38:25.6, container `exit=0` at 13:38:25.9 (**< 1 s**, not after the remaining ~30 s); restart into the still-live outage backed off again (4.7 / 14.3 / 25.6 s); **immediately after `docker start` of Redis the queue held `LLEN=3`, `processing=0`** — payloads survived the outage untouched; within 60 s the worker logged `redis reachable again after 3 backoff(s)`, drained the queue to `queue=0 processing=0`, and every job reached a terminal state (`9 failed`, 27 attempts total, **0 non-terminal**) | 0† |
| Isolation / no external egress during the proof | same driver, phase 11 | `BLOCKED ('1.1.1.1', 443) OSError [Errno 101] Network is unreachable`, `BLOCKED ('download.pytorch.org', 443) gaierror` — no model weights downloaded, no webhook or evidence left the machine | 0 |

The 9 jobs ended `failed` because the synthetic evidence rows have no stored
object behind them; what was proven is **queue preservation, bounded backoff,
recovery and graceful shutdown**, not successful ML inference.

---

## 3. Stage 3 — environment, verification target, and cleanup

Disposable stack (compose project `be037remc95222`, `remed-02-stack-up.txt`):
`_db` (PostgreSQL 15 + postgis/pgvector, loopback 127.0.0.1:55432), `_redis`
(appendonly, 127.0.0.1:56379), `_minio` (127.0.0.1:59000/59001), `_api`
(`poa-backend:be037a`, `AUTH_MODE=enforcing`, 127.0.0.1:58000, current source
mounted read-only), `_worker_iso` (internal-only network). All names and both
networks were declared in `remed-01-ownership-manifest.md` **before** creation.

- Schema built by `alembic upgrade head` on the disposable DB only
  (`remed-04-alembic-upgrade.txt`); final measured version
  `t0u1v2w3x030` (`remed-05-db-identity.txt`, re-measured in `remed-18`).
- Isolation proved, not assumed: the disposable cluster exposes no `pofa_dev` /
  `pofa_test`; `pofa_dev` and `pofa_test` were **not** written at any point in
  this run (post-check below).
- No real webhook, notification, or evidence egress; no model-weight download
  (network evidence above).

### Full suites against the approved disposable target

| Suite | Result | Exit |
| --- | --- | --- |
| full unit (`remed-16-full-suites.txt`) | 1 failed, 520 passed, 1 skipped (31.88s) | 1 |
| full unit, re-run **without** my own `JWT_SECRET` override (`remed-17-unit-no-jwt-override.txt`) | **521 passed, 1 skipped** (25.56s) | **0** |
| full integration (`remed-16-full-suites.txt`) | 3 failed, 372 passed (442.12s) | 1 |

Last source edit was 13:28:31Z; the suites ran at 13:44–13:51Z and 13:55Z, so
both full runs measured the final code.

### The four failures, classified with measurement (not assumption)

1. `tests/unit/test_configuration_and_logging.py::test_development_and_staging_keep_the_permissive_jwt_default`
   — **harness artifact of my own environment**, not a code defect. The test
   constructs `Settings(environment="development")` and asserts the documented
   `"changeme"` default; my runner exported `JWT_SECRET` for the disposable API,
   so the default was legitimately overridden. Re-running the identical suite
   with only the DB/Redis/S3 variables set gives 521 passed, exit 0
   (`remed-17`). No assertion was touched.
2. `tests/integration/test_be029_database_safety_guard.py::test_verification_context_refuses_the_shared_test_database_over_a_real_connection`
   — **target-identity coupling.** `backend/db/safety.py` raises in the
   verification context only when the connected database is in
   `PROTECTED_DATABASE_NAMES = {pofa_dev, pofa_test}`. This run's whole point was
   a *uniquely named* disposable database, so the guard correctly had nothing to
   refuse and the test's `pytest.raises` saw no exception. Measured both ways,
   read-only, in `remed-18-drift-classification.txt`: on `be037rem_app`
   `confirm_server_database(...)` returned `'be037rem_app'`; on `pofa_test` it
   raised `ProtectedDatabaseError: Verification context resolved to protected
   database 'pofa_test'`. The guard works; the other tests in that file passed.
3. + 4. `test_schema_drift_gate.py::test_drift_is_exactly_the_documented_baseline`
   and `::test_extension_owned_objects_are_excluded_not_suppressed` —
   **disposable-database extension set, not a different image.** Measured: the
   image `garapadev/postgres-postgis-pgvector:15-stable` resolves to a single ID
   `6ebf83d85b52`, used by **both** `pofa_db` and `be037remc95222_db`, so the
   difference is not the image. It is how each database came to exist: this run's
   database was created by the container's first-boot initialization of
   `POSTGRES_DB` (`compose.remed.yml`: `POSTGRES_DB: be037rem_app`) while
   `pofa_test` is created by the repository's own `CREATE DATABASE` path
   (`backend/db/test_target.py`). Measured difference
   (`remed-18-drift-classification.txt`): the disposable DB has
   `pg_extension = fuzzystrmatch, plpgsql, postgis, postgis_tiger_geocoder,
   postgis_topology, vector`; `pofa_test` has only `plpgsql, postgis, vector`.
   Those extension-owned tables, plus the `exemplo_dados` sample table (owner
   `be037rem_owner`, and with **no** `pg_depend` extension row — so the exact
   mechanism that created it is not attributed here), are objects no migration in
   this repository creates. Alembic's comparison therefore proposes to drop ~34
   tiger tables and their indexes, which the gate is right to call unexplained.
   Both sides were then compared read-only at the **same** migration head
   `t0u1v2w3x030` (same `remed-18` log):
   - `be037rem_app`: 69 diff operations, **67 unexplained** (all tiger /
     topology / `exemplo_dados` objects), 0 stale baseline entries.
   - `pofa_test`: 2 diff operations, **0 unexplained** — i.e. exactly the
     documented baseline (`ACCEPTED_SIGNATURES`, the
     `uq_user_role_scoped` Alembic tooling pair), 0 stale entries, and the
     `remove_table` assertion holds there.

   The repo's extension exclusion list is intentionally narrow
   (`EXTENSION_OWNED_TABLES == {"spatial_ref_sys"}`), so it does not — and must
   not — absorb another database's extension objects to make a gate pass. A
   repository-wide search over the whole tree (excluding `.git` and the
   virtualenv directories) found **no** reference to `postgis_tiger_geocoder` or
   `exemplo_dados`, and a read-only catalog query shows `pofa_test` has no
   non-public table-bearing schema at all. **No baseline entry was added or
   removed**, because the drift is not the repository's.

None of the four failures touches a G1 or I1 code path, and every G1/I1 focused
test, every relevant regression and both full suites were re-run against the
disposable target with the actual exit codes recorded above.

### Teardown and protected-resource post-check

`docker compose -p be037remc95222 -f compose.remed.yml down -v
--remove-orphans` (exit 0, `remed-20-teardown.txt`) plus one explicit
`docker rm be037remc95222_worker_iso` (exit 0) — that container sits under a
compose profile, so `down` alone left it. Post-check
(`remed-21-post-teardown-protected-check.txt`):

- no `be037rem*` containers, volumes or networks remain;
- `pofa_db` `7949c9980816…` and `pofa_redis` `29b684e82d7c…`: same ids, same
  `StartedAt=2026-10-13T06:15:07…`, `RESTARTS=0`, still `Up`, still published;
- `pofa_dev` and `pofa_test` row-for-row identical to the pre-creation baseline:
  ledger `6023|1|6059` and `53316|1|53316`; users `1054`/`3263`; projects
  `544`/`1636`; evidence `284`/`1216`; analysis_jobs `32`/`38`; webhook_events
  `561`/`4455`; public tables `75`/`75`; both at `t0u1v2w3x030`; same 18
  non-template databases;
- git: HEAD and the six working-tree entries unchanged.

**One deviation, reported because it is a protected resource:** `pofa_minio`
(`54fce2fccd46…`, id unchanged, `RESTARTS=0`) shows
`StartedAt=2026-10-13T13:51:24Z` where the baseline recorded `06:15:07Z`; its own
log reads `INFO: Exiting on signal: TERMINATED` immediately before the new start.
No command in this run names `pofa_minio` — every `docker stop`/`docker start` in
the drivers targets `be037remc95222_redis` / `be037remc95222_worker_iso`, and the
only file in this scratch directory that mentions `pofa_minio` is the read-only
post-check script itself. The container was **not** recreated (same id, same
`Created`, same `proof-of-action-final_minio_data` volume) and `health/live`
answers `200`. **I cannot attribute the restart**; it happened during the
integration-suite window and is consistent with something outside this run
issuing a restart. Nothing was done to it in response.

---

## 4. Remaining limitations and hazards carried forward

1. **A frozen Redis is still not survivable.** redis-py's blocking
   `brpoplpush` has no socket timeout in this configuration, so a Redis that is
   hanging (rather than stopped) can keep the worker parked inside the call
   instead of raising `ConnectionError`. A stopped/restarted Redis — the case
   that was measured — is handled. Fixing the frozen case needs a
   `socket_timeout`/`health_check_interval` decision on the queue client, which
   changes queue-connection semantics and is an owner call.
2. **Outage re-detection latency equals the current backoff wait.** Observed
   ~26 s in run 3: a message queued while the worker is asleep in a 58 s window
   waits until that window ends. Correct for a consumer that must not busy-loop,
   but it is latency, not a fix.
3. **The three new settings are undocumented in ops material.**
   `ANALYSIS_RETRY_BACKOFF_BASE_SECONDS`, `ANALYSIS_RETRY_BACKOFF_MAX_SECONDS`
   and `ANALYSIS_SHUTDOWN_POLL_SECONDS` are code defaults only; no `.env.example`
   or runbook entry was added, because documentation edits outside the task
   scope were not requested.
4. **Inference success was not proven live.** Synthetic evidence rows have no
   stored object, so the live jobs terminate `failed` after the standard retry
   path; that is the correct outcome and is what made the drain observable, but a
   real vision job completion still needs an object in the bucket.
5. **Measurement lessons for the next outage test** (both of my first two
   attempts produced a *false negative* — no real outage): `docker network
   disconnect` on a multi-network container does not cut connectivity (cross-
   bridge routing), and `docker compose up -d <svc>` starts that service's
   `depends_on` containers, which silently resurrected a Redis I had just
   stopped. Only plain `docker stop`/`docker start` on this run's own containers
   produced a real outage.
6. **Inherited, still open:** `BE-037B-G5` (`_complete_reprocessing_hook` logs
   ERROR + traceback after every completed reprocessing-less job); the shipped
   `restart: unless-stopped` policy now masks rather than needs I1; audit-chain
   remains `known_historical_only`; production identity/secret store and the
   live cutover from BE-033/BE-034/BE-035 remain owner-gated.
7. **The newest I1 test has no standalone re-run.** After the manifest-scoped
   teardown there is no test target left, and `pytest tests/unit/...` was
   measured to refuse to start at all without one (`TEST_DATABASE_URL` unset →
   collection error, exit code 4, BE-023 design). So
   `test_startup_outage_is_backed_off_instead_of_crashing_the_worker` is
   evidenced only through the two full unit-suite runs (`remed-16`, `remed-17`),
   both of which post-date the last source edit (13:28:31Z). Re-creating a
   disposable stack would be needed for a focused re-run.
8. **No HA, backup or production claims** are made from any of these local,
   disposable checks.

---

## 5. Evidence index (`D:/CODING/Scratch/be037phasea/phaseB_remed_c95222`)

`remed-00`, `remed-00b` baselines · `remed-01` ownership manifest ·
`remed-02` stack up · `remed-03` buckets · `remed-04` alembic upgrade ·
`remed-05` DB identity · `remed-06` I1 focused unit (FAILED run + classification
+ passing re-run) · `remed-07` / `remed-07-…-rerun` G1 integration (FAILED run +
passing re-run) · `remed-08` relevant regressions · `remed-09` API up ·
`remed-10` live G1 matrix 13/13 · `remed-11` I1 setup ·
`remed-12`/`remed-13` the two false-negative outage attempts (kept) ·
`remed-14` live I1 run 3 full evidence · `remed-15` disposable-DB job outcomes ·
`remed-16` full suites · `remed-17` unit suite without the JWT override ·
`remed-18` read-only drift + guard classification on both targets ·
`remed-19` pre-teardown inventory · `remed-20` teardown ·
`remed-21` post-teardown protected check · scripts
`be037rem_g1_live_probe.py`, `be037rem_i1_setup.py`, `i1-outage-driver*.sh`,
`run-full-suites.sh`, `run-unit-nojwt.sh`, `be037rem_drift_classification.py`,
`be037rem_guard_classification.py`, `run-post-teardown-check.sh`.
`secrets.env` holds this run's disposable credentials; it is Scratch-local and
no secret, password or DSN appears in any log or in this report.

## 6. Git state handed to the owner

Unstaged and uncommitted, exactly as found plus this remediation:

```
 M backend/api/v1/endpoints/analysis.py     (G1 guards)
 M backend/core/config.py                   (I1 backoff/poll settings)
 M backend/services/authorization.py        (G1 analysis_job scope fallback)
 M backend/workers/analysis_worker.py       (I1 outage-tolerant loop)
?? tests/integration/test_be037g1_analysis_auth.py          (13 tests)
?? tests/unit/test_be037i1_analysis_worker_redis_outage.py  (14 tests)
```

Nothing was staged, committed, pushed, reset, cleaned or restored. Deployment,
cloud provisioning and production acceptance were deliberately **not** performed.
