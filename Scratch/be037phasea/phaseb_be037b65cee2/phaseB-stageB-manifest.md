# BE-037 Phase B — Stage B: resource manifest + isolation proof (recorded BEFORE creation)

Run identifier: `be037b_20261013T062257Z_65cee2`
Resource prefix: `be037b65cee2`
Scratch directory: `D:/CODING/Scratch/be037phasea/phaseb_be037b65cee2/`
Recorded: 2026-10-13 (local) — **before** any Phase B Docker resource existed.
Repository state at recording: branch `Backend`, HEAD `b5d4a5fba73b9a38289233f3fc75f6063fec39db`, `git status --porcelain` empty.

Nothing in this manifest shares a name, alias, volume, or network with `pofa_db`,
`pofa_redis`, `pofa_minio`, `pofa_minio_init`, `pofa_api`, the `pofa` network, or the
`db_data` / `minio_data` volumes.

## B1. Planned resources (all owned by this run, all disposable)

| # | Kind | Exact name | Purpose | Ownership proof to record at creation |
|---|------|-----------|---------|--------------------------------------|
| 1 | Compose project | `be037b65cee2` | Namespace for the whole disposable stack | `docker compose ls` shows the project with this config file only |
| 2 | Network | `be037b65cee2_net` | `internal: true` bridge — no egress, no published ports | network ID captured at creation |
| 3 | Volume | `be037b65cee2_pgdata` | PostgreSQL data dir for the disposable cluster | volume ID captured at creation |
| 4 | Volume | `be037b65cee2_miniodata` | MinIO `/data` for the disposable object store | volume ID captured at creation |
| 5 | Container | `be037b65cee2_db` | PostgreSQL 15 + PostGIS + pgvector, DB `be037b_app`, owner role `be037b_owner` | container ID |
| 6 | Container | `be037b65cee2_redis` | Redis 7, no persistence (`--save '' --appendonly no`) | container ID |
| 7 | Container | `be037b65cee2_minio` | MinIO, empty data volume, disposable credentials | container ID |
| 8 | Container | `be037b65cee2_minio_init` | One-shot: creates `be037b65cee2-quarantine`, `be037b65cee2-evidence`, anonymous off | container ID |
| 9 | Container | `be037b65cee2_api` | PoA API, production ASGI command (`uvicorn backend.app.main:app`) | container ID |
| 10 | Container | `be037b65cee2_analysis` | Analysis worker (PID 1 = python; D3 SIGTERM path under test) | container ID |
| 11 | Container | `be037b65cee2_notification` | Notification worker loop | container ID |
| 12 | Container | `be037b65cee2_retention` | Retention worker loop, **no `--auto-delete`** | container ID |
| 13 | Container | `be037b65cee2_webhook` | Webhook worker loop (`--once`) | container ID |
| 14 | Container | `be037b65cee2_migrate` | `tools` profile only: `alembic upgrade head` as `be037b_owner` | container ID (created on demand, removed after) |
| 15 | Container | `be037b65cee2_provision` | `tools` profile only: creates the disposable `be037b_rt` role | container ID (created on demand, removed after) |
| 16 | Container | `be037b65cee2_client` | `tools` profile only: HTTP/DNS/boto test client on the internal network | container ID (created on demand, removed after) |
| 17 | Local role | `be037b_rt` | Least-privilege runtime identity **inside the disposable cluster only** | `pg_roles` row; dropped with the cluster |
| 18 | Local role | `be037b_owner` | Migration/owner identity **inside the disposable cluster only** | `pg_roles` row; dropped with the cluster |

Scratch files (created by this run, deleted at cleanup): `compose.disposable.yml`,
`secrets.env` (mode 600), `pg-init/init.sql`, `provision-runtime.sql`, `treehash.py`,
plus logs/reports written under this directory.

No port of any disposable service is published to the host or to any network other than
`be037b65cee2_net` (grep of the definition for `ports:` returned none).

## B2. Name-availability checks actually run (before creation)

```
docker ps -a --format '{{.Names}}' | grep -c 'be037b'   -> 0
per-name loop over _db _redis _minio _minio_init _api _analysis _notification
             _retention _webhook _migrate _provision _client -> all "free"
docker volume ls  | grep 'be037b'  -> none
docker network ls | grep 'be037b'  -> none
```

## B3. No reference to a protected resource

`grep -nE 'pofa_dev|pofa_test|pofa_db|pofa_redis|pofa_minio|poa_runtime|poa_migrator'`
over `compose.disposable.yml`, `pg-init/init.sql`, `provision-runtime.sql`:
**only comment lines matched** (the header text and the post-provision audit query that
asserts `poa_runtime`/`poa_migrator` were *not* created). Zero configuration, URL,
bucket, volume, or mount reference.

Additional design choices taken in this stage:

* Bucket names are run-prefixed (`be037b65cee2-quarantine` / `-evidence`) instead of
  reusing the live `pofa-*` bucket names. They are environment-driven, so the real
  application storage path is still exercised, and a misresolved endpoint could not
  write into the live evidence or quarantine buckets.
* `docker/pg-init/init.sql` is **not** mounted: it does `\connect pofa_dev`. The
  disposable cluster uses this directory's own `pg-init/init.sql`.
* `scripts/provision_runtime_roles.sql` is **not** run: line 69 `ALTER ROLE
  poa_runtime WITH PASSWORD …` is cluster-wide. The disposable equivalent provisions
  the uniquely named `be037b_rt` with the identical F-05 grant shape and then asserts
  that no `poa_runtime` / `poa_migrator` role exists in the disposable cluster.

## B4. Image reuse decision (Stage C: "reuse unless the code under test changed")

```
poa-backend:be037a
  image ID : sha256:839b0e63c0ffecf9a40112272b60a13b012d7f6f6471cf6924973175149c94f1
  short    : 839b0e63c0ff
  created  : 2026-10-12T16:18:24.94428095Z  (linux/amd64, 3.06 GB)
  HEAD commit time of the code it was built from: 2026-10-12T16:09:56Z (b5d4a5fb)
```

Source-tree proof — CR-normalized SHA-256 over `backend/**.py` + `alembic/**.py`
(excluding dot-dirs and `__pycache__`), computed **inside the image** and **on the host
working tree**:

```
image : 158 92f4dae4a0c80f71fd90e1fd5b9ee4c2a46dc19861d1fd69fbf3c9095bc9c8e6
host  : 158 92f4dae4a0c80f71fd90e1fd5b9ee4c2a46dc19861d1fd69fbf3c9095bc9c8e6
```

Identical file count and identical digest ⇒ the image under test contains exactly the
committed source, including the BE-037A-D3 SIGTERM handler (`grep -c
install_shutdown_handlers backend/workers/analysis_worker.py` = 2 in the image).
**Decision: reuse `poa-backend:be037a`; do not rebuild.**

## B5. Static configuration validation

```
docker compose --project-name be037b65cee2 --env-file secrets.env \
  -f compose.disposable.yml config --quiet          -> CONFIG_EXIT:0
services (default)  : api, analysis_worker, db, minio, minio-init, notification_worker,
                      redis, retention_worker, webhook_worker
services (+ tools)  : + client, migrate, provision
```

The `migrate`, `provision`, and `client` services sit behind the `tools` profile, so a
plain `up` cannot run migrations or role provisioning implicitly. No service runs
migrations at startup (Stage C requirement).

## B6. Isolation gate

All B2/B3/B5 checks passed ⇒ **isolation demonstrated; creation authorized for this
run's named resources only.** Redis uses a dedicated disposable instance (the live
`pofa_redis` is never referenced; DB index 0 of *that* instance is irrelevant because
the endpoint itself is different). Disposable PostgreSQL is initialized from scratch
with synthetic data only.
