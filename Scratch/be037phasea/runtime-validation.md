# BE-037 Phase A — Container Runtime Validation (2026-10-12)

Image `poa-backend:be037a`, `linux/amd64`, repo `Backend` branch @ HEAD `52084de7`.
Everything below was **executed**, not inferred. Raw logs: `build3.log` (first build),
`build4.log` (rebuild after D1), this file.

## Environment facts established first

- Engine: Docker Desktop 4.90.0 (238679) / Engine 29.7.2, `OS/Arch linux/amd64`,
  BuildKit v0.32.2 on builder `desktop-linux`.
- Live services (NOT treated as disposable, never restarted): `pofa_db` (5432),
  `pofa_redis` (6379), `pofa_minio` (9000/9001) on network
  `proof-of-action-final_default`; DNS aliases `db`/`redis`/`minio` resolve from
  containers joined to that network (verified).
- PostgreSQL 15.13; `pofa_dev` extensions plpgsql / postgis 3.4.2 / vector 0.7.4.
- Roles: `postgres` (superuser, owner) and `poa_runtime` (non-super, login,
  no createrole, no bypassrls). `poa_migrator` **does not exist** in this cluster.
- Baselines before any work: `pofa_dev` ledger **6023**, `pofa_test` ledger **52042**.
- Port 8000 free on host; tests used host port 18000.

## Defects found and disposition

| ID | Severity | Finding | Action taken |
|----|----------|---------|--------------|
| BE-037A-D1 | **Blocking (image defect)** | `import cv2` / `import ultralytics` raise `ImportError: libGL.so.1: cannot open shared object file`. `ldd cv2.abi3.so` → `libGL.so.1`, `libglib-2.0.so.0`, `libgthread-2.0.so.0` all `not found`. Cause: `opencv-python` (non-headless, pinned transitively by `ultralytics==8.4.155`) needs X11/GL runtime libs that the slim runtime layer did not install. Blast radius: every vision job fails at model load; worker/API *startup* is not blocked because `backend/engines/vision/detector.py` imports ultralytics lazily (lines 114/122/160, all inside functions). | **FIXED**: added `libgl1` + `libglib2.0-0` to the runtime apt layer in `Dockerfile` (system libs only — no Python pin touched, no dependency removed). Rebuilt once → both imports OK. |
| BE-037A-D2 | Minor | `.dockerignore` pattern `test-image.jpg` matched only the build-context root, so the 80 KB fixture `tests/test-image.jpg` was baked into the image. | **FIXED**: pattern changed to `**/test-image.jpg`; rebuild shows 0 JPEG/PNG under `/app`. |
| BE-037A-D3 | **CLOSED 2026-10-12 (see "BE-037A-D3 closure" section at the end of this file)** | The long-running `analysis_worker` cannot be gracefully stopped by `docker stop`: it exits **137** (SIGKILL after the grace period). Root cause measured: the worker runs as container **PID 1**, and the kernel does not apply *default-action* signals to the PID-namespace init; the only handler in the code is `except KeyboardInterrupt` (SIGINT) at `backend/workers/analysis_worker.py:193`. Evidence: `/proc/1/status` `SigCgt: 0000000000010002` (SIGINT+SIGPIPE only, no SIGTERM). Proof the code path itself is fine: `docker stop --signal SIGINT` → exit **0**. | **NOT FIXED — reported.** Requires an owner decision: (a) add a SIGTERM handler in the worker, or (b) run under an init reaper (e.g. `tini`) in the image, or (c) document `stop_grace_period` + `docker stop --signal SIGINT` / Compose `stop_signal: SIGINT`. Chose not to change worker code or the image entrypoint unilaterally. |

## §2 Image contents — after rebuild

- `docker image inspect`: ID `230828838302…`, **3.06 GB**, `Arch=amd64 OS=linux`,
  `Config.User=appuser`, `Cmd=uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`,
  `ExposedPorts=8000/tcp`. (Size grew 2.77 → 3.06 GB because of the GL/X11 libs.)
- In-container user: `appuser`, `uid=10001` → **non-root**; `/app` owned `root:root`,
  mode `drwxr-xr-x`, `test -w /app` → **NO** (read-only code tree as designed).
- Imports: `torch`, `torchvision`, `transformers`, `ultralytics`, `cv2`, `imagehash`,
  `geoalchemy2`, `pgvector`, `psycopg2` — **all OK**.
- `import backend.app.main` → OK (`FastAPI`); all four worker modules import OK.
- Versions: `torch 2.8.0+cpu`, `torch.version.cuda = None`,
  `torch.cuda.is_available() = False`, `torchvision 0.23.0+cpu`,
  `transformers 4.56.2`, `ultralytics 8.4.155`, `opencv 4.11.0`.
- Artifact scan: `.env` **absent**, `.env.example` present (intended), `.git` 0,
  `.venv*` 0, `*.db`/`*.sqlite*` 0, `*.pt` outside site-packages 0, `*.pem`/`*.key` 0,
  JPEG/PNG under `/app` 0. Secret-like env names baked in: none (`GPG_KEY` is the
  base image's own build arg). No secret values printed anywhere in this work.
- One benign runtime warning: ultralytics cannot write `/home/appuser/.config/Ultralytics`
  (no home dir, by design) and falls back to `/tmp/Ultralytics` — works.

## §3 Runtime — API

Started with the intended production ASGI command (no Compose `up`, to avoid
recreating the live datastores): `docker run … -p 18000:8000 poa-backend:be037a uvicorn
backend.app.main:app --host 0.0.0.0 --port 8000`.

- Startup log: `application.starting` → `Application startup complete.` →
  `Uvicorn running on http://0.0.0.0:8000`.
- Real HTTP from the host: `/health` **200**, `/ready` **200** (`postgresql` healthy
  required=true, `redis` healthy required=true, `storage` healthy), `/healthz` **200**,
  `/api/v1/health` **200** `{"status":"ok"}`.
- DB-backed route: `GET /api/v1/projects` → **200** `{"items":[],"limit":50,"offset":0,"total":0}`;
  `GET /api/v1/evidence/nearby` (no args) → **422** with a structured validation detail.
- Shutdown: `docker stop -t 15` → exit **0**, logs
  `application.shutting_down` → `Application shutdown complete.` (uvicorn handles SIGTERM).
- Production fail-fast measured **inside the image**: with `ENVIRONMENT=production` +
  `JWT_SECRET=changeme` + `AUTH_MODE=development` + dev tokens on, `import
  backend.app.main` exits **1** with `ValidationError: jwt_secret is unsafe for
  production …` (value not echoed). A complete, safe production config
  (`enforcing`, dev tokens off, explicit CORS allowlist, 48-char secret) imports fine —
  so the validator is fail-closed on unsafe values, not broken.

## §3 Runtime — four workers (real entry points, exact Compose commands)

| Worker | Command run | Result |
|---|---|---|
| notification | `python -m backend.workers.notification_worker --limit 50` | exit **0**; `{'outbox': {'processed': 0, 'failed': 0}, 'retries': {'retried': 0, 'succeeded': 0, 'failed': 0}}` |
| retention | `python -m backend.workers.retention_worker --limit 200` (deliberately **no** `--auto-delete`) | exit **0**; `retention sweep evaluated=0 archived=0 deleted=0 blocked=0 failed=0` |
| webhook | `python -m backend.workers.webhook_worker --once --limit 50` | exit **0**; `events=0 pending_deliveries=0 retries=0` — **zero outbound HTTP**, the disposable DB held no subscriptions/endpoints |
| analysis | `python -m backend.workers.analysis_worker` (daemon) | starts + runs (`analysis worker started`); SIGINT stop → exit **0**; **SIGTERM stop → exit 137** = BE-037A-D3 |

No worker was run against real subscriptions or external webhook destinations; only
one copy of each was started; no concurrency test was attempted.

## §4 Database compatibility and isolation

- Isolation actually built: a uniquely named disposable database `poa_be037a_disp`
  created inside the existing `pofa_db` container (volumes never touched), plus a
  least-privilege role `poa_be037a_rt` (`NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOINHERIT NOBYPASSRLS`) with a freshly generated throwaway password that was never
  printed (kept only in a `chmod 600` scratch file, now deleted).
- **Why not reuse `poa_runtime`:** `scripts/provision_runtime_roles.sql:69` runs
  `ALTER ROLE poa_runtime WITH PASSWORD …` and roles are **cluster-wide** — executing
  it with a different password would have broken the live dev app's credential. The
  disposable role reproduces the same grant shape per-database instead.
- Migration identity vs runtime identity, both from the container: `alembic upgrade
  head` as the **owner** (with `POA_DATABASE_CONTEXT=verification` and
  `POA_AUTHORIZED_DATABASE_NAME=poa_be037a_disp` armed so the guard would refuse a
  protected DB) migrated the empty database through the full chain to head
  **`t0u1v2w3x030`**; the API and workers then ran as the **non-owner runtime role**.
- Compatibility proven from the image: PostgreSQL **15.13**, `postgis_version()`
  `3.4 USE_GEOS=1 USE_PROJ=1 USE_STATS=1`, pgvector `0.7.4`; **73** public tables,
  1 registered geometry column, 1 `vector` column — i.e. the migrations that need
  PostGIS and pgvector succeeded from inside the container.
- Enforcement measured on the live container connection: `current_user =
  poa_be037a_rt`, `is_superuser = false`; ledger `SELECT` **allowed**,
  `UPDATE` / `DELETE` / `TRUNCATE` **denied** (`InsufficientPrivilege`),
  `CREATE TABLE` **denied** (permission denied for schema public),
  `alembic_version` write **denied**.
- Protected databases **untouched**: `pofa_dev` 6023 and `pofa_test` 52042 measured
  before, during and after; `poa_runtime` role still present and unmodified; the
  pre-existing `pofa_be028_*` / `pofa_be029_*` / `pofa_be030_*` databases were left
  exactly as found (not mine to delete).
- Cleanup done: disposable DB dropped `WITH (FORCE)`, disposable role dropped,
  test containers removed, throwaway password file deleted. `pofa_db`/`pofa_redis`/
  `pofa_minio` still `Up` with continuous uptime (never restarted).

## Checks NOT performed (and why)

- No `docker compose up` of the app/worker services: the committed Compose adds a
  `pofa` network + healthchecks to `db`/`redis`/`minio`, so `up` would **recreate the
  live datastores holding pofa_dev**. Compose was therefore validated statically
  (`docker compose config --quiet` → OK; default services = redis db webhook_worker
  minio analysis_worker api minio-init retention_worker notification_worker; `migrate`
  appears **only** with `--profile tools`) and each service's command was executed
  equivalently via `docker run` on the existing network.
- No app-driven business write (e.g. evidence upload + analysis end-to-end) and no
  YOLO/CLIP model inference: model weights are fetched over TLS at first use, which is
  an outbound-network action; CPU execution path was verified instead at the library
  level. Not claimed as tested.
- No concurrency/multi-replica worker test (explicitly out of scope here).
- Image was not re-scanned for CVEs, and no registry push / deployment / cloud action.
- Git: nothing staged, committed, or pushed. Working tree = ` M Dockerfile`,
  ` M .dockerignore` only.

## Necessary code/config changes (for owner decision)

1. **Required:** none outstanding for the image to run — D1/D2 are already fixed here.
2. **Recommended for D3 (one of):** add a SIGTERM handler in
   `backend/workers/analysis_worker.py` (graceful drain of the current message), or
   install an init reaper (`tini`) as the image entrypoint, or set
   `stop_signal: SIGINT` + `stop_grace_period` on the `analysis_worker` Compose service.
   Each of these (except the Compose-only option) needs another image rebuild.
3. Note for the deployment target: if a GPU target is ever chosen, dropping the
   `--index-url` line in the Dockerfile restores the CUDA build (owner decision).

---

# BE-037A-D3 closure — analysis worker graceful shutdown (2026-10-12)

Chosen remedy: option (a), a SIGTERM handler inside the worker (no `tini`, no Compose
`stop_signal` workaround, no shell wrapper, no `kill -9`).

## Change

`backend/workers/analysis_worker.py`:
- module flag `_shutdown_requested` + `_request_shutdown(signum, frame)` that **only**
  flips the flag (no I/O, no logging, no cleanup — a signal can arrive while a DB
  transaction is open, so the handler must do no work);
- `install_shutdown_handlers()` registers **SIGTERM only** and is called exactly once
  inside `if __name__ == "__main__":` — importing the module changes no process-wide
  signal state, and SIGINT is deliberately left unregistered so it keeps raising
  `KeyboardInterrupt`;
- `run_worker()`'s `while True:` became `try: while not _shutdown_requested:` with a
  `finally:` that logs `analysis worker stopping; releasing queue and database
  resources`, closes the Redis client (`queue.client.close()`), disposes the SQLAlchemy
  pool (`get_engine().dispose()`) and logs `analysis worker stopped`. The flag is only
  tested **between** messages, so an in-flight `process_message()` (and its session,
  which it closes in its own `finally`) is never interrupted;
- `except KeyboardInterrupt: sys.exit(0)` preserved; the `finally` runs on that path too.

Scope check: `analysis_worker` is the only daemon-loop worker. `notification_worker`,
`retention_worker` and `webhook_worker` are one-shot sweeps (`--limit` / `--once`) that
exit on their own, so they cannot exhibit D3 and were not touched.

## Verification (executed)

| Check | Result |
|---|---|
| Focused tests `tests/unit/test_be037a_analysis_worker_shutdown.py` | **7 passed** (handler registration, handler does no work + idempotent, loop exit + resource release, in-flight message completes first, flag-already-set fast exit, KeyboardInterrupt propagates with cleanup). No DB / Redis / network. |
| Worker-adjacent regression | `test_analysis_jobs`, `test_be008_temporal`, `test_evidence_graph`, `test_fusion`, `test_vision_intelligence` → **50 passed / 0 failed** |
| Full suite on `pofa_test` | **869 passed / 1 skipped / 0 failed**, exit 0 (= BE-037's 862 + the 7 new tests; the 1 skip is the ML-stack preflight) |
| Image rebuild | `BUILD_EXIT:0`, new ID `839b0e63c0ff`, 3.06 GB, `linux/amd64`, `User=appuser`; the fix is present in `/app/backend/workers/analysis_worker.py` (SIGTERM registered, SIGINT not) |
| PID-1 signal mask after fix | `/proc/1/status` `SigCgt: 0000000100004002` — SIGTERM bit `0x4000` now caught (was `0000000000010002`) |
| `docker stop -t 10` (default SIGTERM) | container **exit_code = 0** (was **137**), logs show both orderly shutdown lines 2.3 ms apart (`stopping; releasing…` → `stopped`). Latency, measured by timing the host `docker stop` call: on a `--rm` container it returned in **2.491 s** (that flag deletes the container on exit, so its code was not retrievable); on `poa_be037a_res` it returned in **5.151 s** with exit_code **0**. Both are inside the 10 s grace period and consistent with the 5 s dequeue timeout |
| `docker stop --signal SIGINT -t 10` | exit_code **0**, latency **1.06 s**, same orderly log lines → **no SIGINT regression** |
| Resources released | The release path ran: `docker stop` logs `… stopping; releasing queue and database resources` (before `queue.client.close()` / `get_engine().dispose()`) followed by `analysis worker stopped`. Postgres: `pg_stat_activity` rows for the disposable role were **0 both during and after** the run — by design the idle worker holds no session (per-message sessions), so this shows no leak rather than differentially proving `dispose()`. Redis: disposable keyspace (DB **15**, chosen because the live app uses DB 0) `DBSIZE = 0` → nothing stranded in the processing list, and `connected_clients` returned to baseline |
| Isolation | ran on a freshly created `poa_be037a_disp` (migrated by the owner identity from inside the image to `t0u1v2w3x030`) under the non-owner role `poa_be037a_rt` (grant shape `insert=t / update=f / delete=f / truncate=f`); no worker ever connected to `pofa_dev`/`pofa_test`; zero outbound HTTP (no subscriptions, no webhook calls, no model download) |
| Protected databases | `pofa_dev` ledger **6023** before and after, rev `t0u1v2w3x030`, `poa_runtime` role intact. `pofa_test` grew (52131 → 53316) purely from the suite's own appends — that database is the mutable test target by design |
| Cleanup | containers removed, `DROP DATABASE … WITH (FORCE)`, `DROP ROLE poa_be037a_rt`, throwaway password + env files deleted. `pofa_db`/`pofa_redis`/`pofa_minio` never restarted; no volumes touched; nothing committed or pushed |

## Remaining shutdown limitations (honest scope)

- A job longer than the stop grace period still gets SIGKILL: the handler can only stop
  *between* messages. Compose's `stop_grace_period` is the knob for long vision jobs.
- "In-flight message completes before exit" is proven by the unit test, **not** by a
  container run — producing a real multi-second job would have required model weights
  (outbound download) or synthetic DB rows, so it was not exercised end to end here.
- `install_shutdown_handlers()` is called by `__main__` only; a future WSGI/ASGI-embedded
  or supervisor-spawned entry point must call it explicitly.
- SIGQUIT, SIGHUP and `docker kill` (SIGKILL) remain unhandled by design — SIGKILL is
  not catchable, and adding the others was outside the reported defect.

## Environment anomaly observed (not caused by this work)

`pofa_minio` restarted at **2026-10-12T16:34:30Z**, after the suite finished. Its own log shows
`INFO: Exiting on signal: TERMINATED` and Docker restarted it under its `unless-stopped` policy.
Same container ID (created 2026-09-13), so it was stopped/started, **not recreated**; the named
volume `proof-of-action-final_minio_data` is intact with both buckets present
(`/data/pofa-evidence`, `/data/pofa-quarantine`, 3.3 MB) and `/minio/health/live` returns **200**.
No command issued in this session targeted `pofa_minio` (the only `docker stop`/`docker rm` calls
named `poa_be037a_*` containers), and `pofa_db`/`pofa_redis` kept their 14:42:36Z start times
throughout. Recorded as an environment flakiness event consistent with the known Docker-Desktop
outage pattern, not as a defect in this change.
