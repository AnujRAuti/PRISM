# BE-037 Phase B — High-Defect Remediation (G1 + I1): ownership manifest

Written **before** any resource in this run is created. Only the names listed
here belong to this run; cleanup may remove nothing else.

- Run id / prefix: `c95222`
- Compose project name: `be037remc95222`
- Date opened: 2026-10-13 (UTC) — baseline files `remed-00`, `remed-00b`
- Scratch dir: `D:/CODING/Scratch/be037phasea/phaseB_remed_c95222`
- Repository: branch `Backend`, HEAD `b5d4a5fba73b9a38289233f3fc75f6063fec39db`
  ("Docker Repair"), no staging, no commit, no push at any point in this task.

## Scope

Remediate the two High defects from `phaseB-stageJ-final-report.md`:

- **G1** — `POST /api/v1/analysis/jobs` and `GET /api/v1/analysis/jobs/{job_id}`
  had no authentication or authorization dependency at all.
- **I1** — the analysis worker treated any transient Redis failure as a fatal
  error and exited.

No cloud provisioning, no deployment, no production acceptance claim.

## Owner decisions recorded for this run

- `POST /api/v1/analysis/jobs` is guarded by the **existing** permission
  `intelligence.reprocess`, scope-resolved against the request body's
  `evidence_id` (job created for that evidence).
- `GET /api/v1/analysis/jobs/{job_id}` is guarded by the **existing**
  permission `evidence.read`, scope-resolved through
  job → evidence → project → organization.
- No new permission is added to the catalogue; no migration is needed.
- Verification is against a disposable environment only. `pofa_dev` and
  `pofa_test` are not test targets for this run.

## Resources created by this run (unique names)

| Kind | Name | Notes |
| --- | --- | --- |
| container | `be037remc95222_db` | disposable PostgreSQL 15 + postgis/pgvector |
| container | `be037remc95222_redis` | disposable Redis 7, appendonly on |
| container | `be037remc95222_minio` | disposable MinIO |
| container | `be037remc95222_minio_init` | one-shot bucket creator (tools profile) |
| container | `be037remc95222_api` | disposable API, `AUTH_MODE=enforcing` |
| container | `be037remc95222_worker_iso` | one-shot worker on the internal net (tools profile) |
| volume | `be037remc95222_pgdata` | this run only |
| volume | `be037remc95222_redisdata` | this run only |
| volume | `be037remc95222_miniodata` | this run only |
| network | `be037remc95222_net` | bridge, ports published to 127.0.0.1 only |
| network | `be037remc95222_iso` | `internal: true`, no route outward |
| database | `be037rem_app` | inside the disposable container only |
| role | `be037rem_owner` | inside the disposable container only |
| buckets | `pofa-quarantine`, `pofa-evidence` | **inside the disposable MinIO only** |
| host process | uvicorn / analysis worker (this run's PIDs recorded below) | stopped by this run |
| queue keys | `pofa:analysis:jobs*` on the disposable Redis, `be037g1:*` | disposable Redis only |

Ports published by this run (loopback only): 55432, 56379, 59000, 59001, 58000.

## Protected resources — never touched

| Resource | Measured id (pre-creation) |
| --- | --- |
| container `pofa_db` | `7949c9980816` |
| container `pofa_redis` | `29b684e82d7c` |
| container `pofa_minio` | `54fce2fccd46` |
| database `pofa_dev` | ledger 6023 rows, seq 1..6059, rev `t0u1v2w3x030` |
| database `pofa_test` | ledger 53316 rows, seq 1..53316, rev `t0u1v2w3x030` |

## Standing safety rules carried into this run

- No broad `docker compose down` / `docker system prune` / `docker volume
  prune`; cleanup removes only the manifest-matched names above.
- Never restart, recreate or reconfigure `pofa_minio`, `pofa_db`, `pofa_redis`.
- Never run `scripts/provision_runtime_roles.sql` unchanged; never mount
  `docker/pg-init/init.sql`.
- No migrations or writes against `pofa_dev` / `pofa_test`.
- No real webhook, notification, or evidence egress; no model-weight downloads
  without explicit approval (the worker proof runs on an internal-only network).
- Never print a JWT secret, database password, or credential-bearing DSN into a
  log, report, source file, or Git object.
- Never substitute a weaker test for a failed one — mark it BLOCKED / NOT RUN.
