# BE-037 FINAL completion run `7c1f1` — Stage 0 written baseline

Captured **before any change** on 2026-10-13 (UTC). Everything below is a
measured value, not a recollection of an earlier report. Companion evidence
files in this directory: `final-00-git-baseline.txt`,
`final-00a-git-full-diff.txt`, `final-00b-protected-db-baseline.txt`,
`final-00d-image-provenance-probe.txt`.

## 1. Repository and Git state (measured)

| Item | Value |
| --- | --- |
| Root | `D:/CODING/Projects/Proof-Of-Action-Final` |
| Branch | `Backend` (as expected) |
| HEAD | `b5d4a5fba73b9a38289233f3fc75f6063fec39db` ("Docker Repair") |
| Staged | 0 lines (`git diff --cached --stat` empty) |
| Working tree | ` M backend/api/v1/endpoints/analysis.py`, ` M backend/core/config.py`, ` M backend/services/authorization.py`, ` M backend/workers/analysis_worker.py`, `?? tests/integration/test_be037g1_analysis_auth.py`, `?? tests/unit/test_be037i1_analysis_worker_redis_outage.py` |
| Diff size | 159 insertions / 18 deletions across the four modified files (`git diff --numstat`: 28/5, 9/0, 10/0, 112/13) |
| Tracked-file deletions in the working tree | none (`git ls-files -d` empty) |

The four modified files and two new test files are the **G1 + I1 remediation
from run `c95222`**, left unstaged and uncommitted exactly as that task
required. They are user work in progress: they must be preserved and are the
foundation this run continues from, not noise to be reverted.

### Documentation deletions that must stay deleted

Commit `52084de7` ("done with auditing") deleted, among others,
`docs/BE-037 Final Backend Production Deployment and Acceptance Report.md`,
`docs/BE-032R Operational Runbook - ... .md`,
`docs/Backend Technical Debt and Deferred Fixes Backlog.md` and every other
`docs/BE-0NN *Results/Report*.md`. Those deletions are **committed** — the
working tree shows no pending deletions. Consequence for this run: the
repository currently has **no** BE-037 report, no runbook and no backlog file.
This run must not resurrect a deleted path; the final report goes to a new,
clearly named file (see WS-G plan below).

`.env` (untracked) and `.env.example` (tracked) exist. The full working-tree
diff was scanned for secret-shaped strings (`secret|password|access_key|token`)
and contains **none**, so it was safe to archive.

## 2. Protected resources (measured, read-only)

Containers (all three are compose project `proof-of-action-final`, policy
`unless-stopped`, `RestartCount=0`):

| Name | ID (full) | Image (recorded on the container) | Created | StartedAt |
| --- | --- | --- | --- | --- |
| `pofa_db` | `7949c99808161e13...da0898e4` (see file) | `sha256:6ebf83d85b52...` | 2026-09-18T18:09:18Z | **2026-10-13T06:15:07Z** |
| `pofa_redis` | `29b684e82d7c9b28...` | `sha256:ff02b58f971e...` | 2026-09-13T16:58:41Z | **2026-10-13T06:15:07Z** |
| `pofa_minio` | `54fce2fccd46fa5b...` | `sha256:14cea493d9a3...` | 2026-09-13T13:33:00Z | **2026-10-13T13:51:24Z** |

Databases (every query ran with `default_transaction_read_only=on`):

| Database | audit ledger rows | seq range | users | projects | evidence | analysis_jobs | webhook_events | public tables | alembic | extensions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pofa_dev` | 6023 | 1–6059 | 1054 | 544 | 284 | 32 | 561 | 75 | `t0u1v2w3x030` | `plpgsql,postgis,vector` |
| `pofa_test` | 53316 | 1–53316 | 3263 | 1636 | 1216 | 38 | 4455 | 75 | `t0u1v2w3x030` | `plpgsql,postgis,vector` |
| `template1` | — | — | — | — | — | — | — | — | — | `plpgsql` only, no table-bearing schema |

`pofa_dev` / `pofa_test` counts and revisions are identical to the
`c95222` run's baseline (`remed-00b`), i.e. nothing changed them in between.
No `exemplo_dados` table exists in either protected database, nor in
`template1`.

## 3. Baseline findings that steer the workstreams

### F-A — the MinIO restarts are attributable to a repository test, not to a mystery

`pofa_minio` logs (read-only) show a clean, repeated pattern: `INFO: Exiting on
signal: TERMINATED` immediately followed by a fresh server banner — **140**
termination events since 2026-09-13, including
`2026-10-13T13:51:24.48Z` → restart `13:51:25.96Z`, which is the event the
`c95222` report recorded as "not attributable". `RestartCount=0` because the
restart is externally commanded, not docker-policy-driven.

The commanding code is in the repository:
`tests/integration/test_storage.py:68-98`
(`test_object_persists_across_minio_restart`) runs

```python
subprocess.run(["docker", "compose", "restart", "minio"],
               cwd=REPOSITORY_ROOT, check=True, ...)
```

with `REPOSITORY_ROOT = Path(__file__).resolve().parents[2]` (:11) — i.e. the
**protected** compose project `proof-of-action-final`, service `minio` =
container `pofa_minio`. The `c95222` run executed the full integration suite at
that time, so the restart was caused by this repository's own test being run by
that session. This corrects the earlier "unattributable" statement: it is
attributable, with log + code evidence. WS-E1 therefore has a concrete defect
to fix (the test must never be able to reach the protected service).

### F-B — the extra objects in a first-boot disposable database have a proven owner

The image `garapadev/postgres-postgis-pgvector:15-stable` is a **single image
ID `sha256:6ebf83d85b52...`**, and that is also the image ID recorded on
`pofa_db` itself, so the difference between the disposable and the protected
databases is not a different image. Extracting the image's init directory with
`docker create` + `docker cp` (no container was ever started —
`final-00d-image-provenance-probe.txt`) shows it ships
`/docker-entrypoint-initdb.d/init.sql` (2647 bytes, dated 2025-07-25) which, at
the **first boot of a fresh data directory**, runs against `POSTGRES_DB` and
executes:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS exemplo_dados (...);  -- + 3 INSERT rows + 2 indexes
```

That is the complete, measured provenance of the `c95222` "unexplained" drift:
the objects belong to the third-party image's own demo init script, applied to
the database the container created at first boot. Databases created afterwards
with `CREATE DATABASE` (from the clean `template1`, measured above) do **not**
get them — which is exactly why `pofa_dev`, `pofa_test` and the repository's
documented target (`backend/db/test_target.py:57-64`: `CREATE DATABASE` +
`CREATE EXTENSION postgis; vector` + `alembic upgrade head`) show only
`plpgsql,postgis,vector`.

Consequence for WS-D bootstrap: the disposable database for this run must
**not** be the container's `POSTGRES_DB`. It must be created by the
repository's intended path so the drift baseline is reproducible and no
unexplained object exists to be hidden.

### F-C — the frozen-connection gap is real and the current comment is wrong

Measured against the pinned client (`requirements.txt:8` → `redis==4.6.0`,
imported from `backend/.venv312_repro`):

```
issubclass(redis.exceptions.TimeoutError, redis.exceptions.ConnectionError) = False
redis.exceptions.TimeoutError.__mro__  = TimeoutError -> RedisError -> Exception
redis.exceptions.ConnectionError.__MRO__ = ConnectionError -> RedisError -> Exception
BusyLoadingError -> ConnectionError = True ; AuthenticationError -> ConnectionError = True
ResponseError -> ConnectionError = False
```

`backend/workers/analysis_worker.py:29-35` therefore states something false:
its comment claims `ConnectionError` "also covers `TimeoutError`". It does not
in redis-py 4.6.0 — they are siblings. `TRANSIENT_REDIS_ERRORS` catches only
`ConnectionError`, so a socket **timeout** escapes the retry loop and kills the
worker.

Also measured in `redis/connection.py` (4.6.0):
* `:997` / `:1192` — `sock.settimeout(self.socket_timeout)`; `socket_timeout`
  defaults to `None` (`:597`, `:634`), so a read blocks forever.
* `:817-820` — `check_health()` only fires **before sending the next command**
  (`if self.health_check_interval and time() > self.next_health_check`), so it
  cannot detect a connection that freezes mid-`brpoplpush`. The task's warning
  ("do not assume `health_check_interval` alone solves a frozen connection") is
  confirmed by the code.
* `:901-902` — `next_health_check` is only advanced after a *successful* reply.
* `redis/client.py` contains no blocking-command socket-timeout adjustment
  (the only `blocking=` hits are `Lock.acquire`).

And `backend/services/analysis_queue.py:20` builds the client with
`redis.Redis.from_url(settings.redis_url, decode_responses=True)` — no
`socket_timeout`, no `socket_connect_timeout`, no `health_check_interval`.
`dequeue()` (:29) issues `brpoplpush(..., timeout=5)`.

Conclusion: a Redis that stops answering **without** closing the TCP connection
can leave the worker blocked indefinitely, and the current exception tuple
would not even handle the timeout case if a timeout existed. WS-C has a real
defect to fix, with a measurable design constraint: any socket timeout must be
**greater** than the 5 s blocking dequeue timeout, or normal idle waits would
raise spuriously.

### F-D — documentation surface for the new worker settings (WS-B)

Measured: `Settings` is a plain `pydantic_settings.BaseSettings` subclass with
only `class Config: env_file = ".env"` (`config.py:159-160`); no `env_prefix`,
no `SettingsConfigDict`; names map upper-snake (`analysis_retry_backoff_base_seconds`
↔ `ANALYSIS_RETRY_BACKOFF_BASE_SECONDS`). Exactly one validator exists
(`_validate_production_settings`, `config.py:113-157`) and it is
production-mode gated; there are **no** `Field`/`ge`/`le` numeric constraints
anywhere, so no numeric-range precedent exists to copy — documentation must not
promise validation the code does not perform.

`.env.example` (71 lines) carries an unlabeled analysis/embedding group at
**:21-28** (`REDIS_URL`, `ANALYSIS_QUEUE_NAME`, `ANALYSIS_MAX_ATTEMPTS`,
`ANALYSIS_ABANDONED_TIMEOUT_SECONDS`, `PHASH_…`, `EMBEDDING_…`) — that is where
the three new settings belong. The only prose config guide is
`docs/storage.md` (`## Configuration` :24, and worker-tuning prose already
citing `ANALYSIS_MAX_ATTEMPTS` at :77 and `PHASH_MAX_HAMMING_DISTANCE` at :83).
`docker-compose.yml:23-42` (`x-app-environment`) documents deployment env and
contains **no** `ANALYSIS_*` variable at all — precedent: analysis tuning lives
in `.env`/defaults, not compose. All 30 currently documented `.env.example`
values match `config.py` defaults; the three new settings are the only analysis
defaults missing from it.

### F-E — drift gate and guard machinery (WS-D, for the test refactor)

* `backend/db/schema_drift_policy.py:32` `EXTENSION_OWNED_TABLES = {"spatial_ref_sys"}`;
  `include_object` (:35-39) excludes only that table name.
* `signature()` and the baseline live in `tests/schema_drift_baseline.py`
  (`:31-49` signature, `:54-85` `ACCEPTED`/`ACCEPTED_SIGNATURES` = the two
  `uq_user_role_scoped` entries, `:88-106` `DriftVerdict`/`compare`).
  "Unexplained" = `set(collected) - ACCEPTED_SIGNATURES`.
* `tests/integration/test_schema_drift_gate.py`: `collect_drift` (:46-55) uses
  `MigrationContext.configure(..., include_object=include_object)` +
  `compare_metadata`; module fixture (:73-88) first asserts
  `script_head() == database_version`. Failing assertions on a polluted target:
  `:91-102` (`verdict.clean`) and `:170`
  (`assert not [d for d in drift if d.startswith("remove_table|")]`).
* `backend/db/safety.py`: `:49` `PROTECTED_DATABASE_NAMES = {pofa_dev, pofa_test}`
  (name-based only), `CONTEXT_VERIFICATION = "verification"` (`:45`),
  `confirm_server_database` (`:116-134`) raises only when the **server-reported**
  name is protected. Call sites: `backend/db/session.py:36,41,45`;
  `backend/observability/health.py:86,94`; `alembic/env.py:61,64,69,71`;
  `backend/db/test_target.py:184,197`.
* `tests/integration/test_be029_database_safety_guard.py:145-148` is the test
  that fails against a disposable name; the repo already contains the
  stub-identity precedent `tests/unit/test_database_safety.py:44-75,200-223`
  (`_StubBind`, refusal loop over `PROTECTED_DATABASE_NAMES`), plus
  `tests/preflight.py:243,251-257` fake-engine injection and
  `tests/integration/test_be027_foundation_contract.py:290-301` real engine to
  an unreachable DSN.
* `docker/pg-init/init.sql` (repo) is only `\connect pofa_dev` +
  `CREATE EXTENSION postgis; vector` — it does **not** create tiger/topology/
  `exemplo_dados`, so mounting it is not the cause (and it is unusable as-is for
  a differently named database because of the `\connect`).

## 4. Environment

* Verification interpreter: `backend/.venv312_repro` (has click/torch-CPU
  stack); other venvs are unusable for servers/probes (see project memory).
* `redis==4.6.0`, `pydantic==2.11.9`, `pydantic-settings==2.3.0` per
  `requirements.txt`.
* Disposable image available locally: `poa-backend:be037a` (3.06 GB, from Phase
  A) plus `alpine:latest`, `redis:7-alpine`, `quay.io/minio/minio:latest`,
  `quay.io/minio/mc:latest`, the postgres image above.
* No `be037fin*` container, volume or network exists yet — measured in
  `final-00c-docker-baseline.txt` ("no be037fin containers / volumes / networks").
* Leftover files at repo root that are **not** this run's and must not be
  touched: `pofa_dev.db`, `stage_d_runtime_checks.py`, `stage_d_server.log`,
  `stage_e_runtime_checks.py`, `stage_e_server.log`, `test-image.jpg`,
  `yolo11n.pt`, `temp_test_env/`, `tmp_test_env/`, `openapi.json`.

## 5. Run identity and naming

| Item | Value |
| --- | --- |
| Run id | `7c1f1` (2026-10-13T16:35Z) |
| Scratch dir (outside the repo) | `D:/CODING/Scratch/be037final/run_1013t1635_7c1f1` |
| Planned disposable prefix | `be037fin7c1f1_*` (containers, volumes, networks) |
| Planned compose project | `be037fin7c1f1` |
| Planned disposable databases | `be037fin7c1f1_app` (app DB, created by `CREATE DATABASE`, **not** `POSTGRES_DB`), plus deliberately name-colliding guard fixtures `pofa_dev`/`pofa_test` inside the disposable container only (empty, read-only use) |
| Planned disposable Redis keys | `pofa:analysis:jobs*` on the disposable Redis only |

The ownership manifest is written **before** any disposable resource is created
(see `final-01-ownership-manifest.md`). Nothing outside that manifest may be
removed at cleanup.
