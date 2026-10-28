# BE-037 Phase B — Stage A read-only preflight

Run identifier: `be037b_20261013T062257Z_65cee2` (short resource prefix `be037b65cee2`)
Started: 2026-10-13T06:22:57Z. No state-changing command was issued in this stage.

## A1. Git and repository state

| Item | Measured |
|---|---|
| Branch | `Backend` |
| HEAD | `b5d4a5fba73b9a38289233f3fc75f6063fec39db` — **"Docker Repair"** (author AnujRAuti, 2026-10-12 22:09:56 +0530) |
| Prior HEAD noted in the task file | `52084de7` — **superseded**: the Phase A + D3 work was committed while the last session closed |
| Working tree | **clean** — `git status --porcelain` empty, `git diff --cached --stat` empty, no untracked files |
| Required-to-preserve files | `Dockerfile`, `.dockerignore`, `backend/workers/analysis_worker.py`, `tests/unit/test_be037a_analysis_worker_shutdown.py` are now **committed in HEAD** (`git show --stat HEAD`: 4 files, +281/−23), so there is nothing in the tree to preserve — and nothing may be committed on top. |
| D3 fix present at HEAD | yes: `_shutdown_requested` / `install_shutdown_handlers` in `backend/workers/analysis_worker.py`, and the 190-line test file is in HEAD (`git cat-file -e` OK) |

Because the tree is clean and HEAD contains the code under test, the Phase A image is still the
correct artifact for Phase B (see A1-image below) — **no rebuild needed**.

Image `poa-backend:be037a`:
`id=sha256:839b0e63c0ffecf9a40112272b60a13b012d7f6f6471cf6924973175149c94f1`,
RepoDigest present (local build, content-addressed), `created=2026-10-12T16:18:24.944Z`,
`linux/amd64`, `Size=694097738` bytes unpacked (3.06 GB virtual), `User=appuser`,
`Cmd=uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`.
Built at 16:18Z on 2026-10-12; the D3 worker change was added to the source and rebuilt into this
same tag at 16:18Z — verified in the previous session by inspecting `/app/backend/workers/analysis_worker.py`
inside the image. HEAD `b5d4a5fb` (16:09:56+0530 = 10:39Z? no: 22:09 +0530 = 16:09Z) predates the
image build by 9 minutes, and no source file changed after the image was built, so
**image content == HEAD content** for the worker. Verified again in Stage D.

## A2. MinIO restart anomaly — evidence-based conclusion: **KNOWN CAUSE (repo test code)**

The `2026-10-12T16:34:30Z` single-container MinIO restart was **not** environment flakiness. It is
caused by committed test code:

```
tests/integration/test_storage.py:1  import subprocess
tests/integration/test_storage.py:68 def test_object_persists_across_minio_restart(storage)
tests/integration/test_storage.py:76     subprocess.run(
tests/integration/test_storage.py:77         ["docker", "compose", "restart", "minio"],
tests/integration/test_storage.py:78         cwd=REPOSITORY_ROOT, check=True, capture_output=True)
```

`docker compose` run from the repository root resolves the base `docker-compose.yml`, whose `minio`
service is pinned to `container_name: pofa_minio` — i.e. **the live developer datastore**. So any
`pytest tests/integration` run restarts the real MinIO container. Timeline corroborates it: the
869-test suite finished ~16:33:30Z and `pofa_minio` received `Exiting on signal: TERMINATED` at
16:34:30Z, while `pofa_db`/`pofa_redis` (started 14:42:36Z) kept running — a per-container event, not
an engine event.

`pofa_minio` container facts (read-only): ID `54fce2fccd46…`, created `2026-09-13T13:33:00Z`,
`restart=unless-stopped`, `RestartCount=0`, last `ExitCode=0`, started `2026-10-13T06:15:07Z`.
Volume `proof-of-action-final_minio_data` intact; `/data` holds both bucket prefixes
(`pofa-evidence`, `pofa-quarantine`, 3.3 MB); `/minio/health/live` → **200**. Cumulative
`Exiting on signal` log lines = 106 since creation, all correlated with engine or test-driven stops
— no crash loop, no OOM kill, no restart storm.

Separately, **all three** live containers restarted together at `2026-10-13T06:15:07Z`
(`RestartCount=0`, same container IDs). Host uptime is 47.3 h and `LastBootUpTime` is unchanged, so
the host did not reboot — this was a Docker Desktop / WSL2 VM (re)start. Cause: **suspected
user/Docker-Desktop lifecycle**, benign, and it did not damage data (`pofa_dev` ledger and revision
verified below).

Safety consequence for the rest of Phase B (recorded as **BE-037B-D1**): the integration suite cannot
be run from the repository root against any stack, because it will restart `pofa_minio` regardless of
which MinIO the tests are pointed at. Phase B therefore does not run `tests/integration` wholesale;
where a pytest-style check is used against the disposable stack, this test is explicitly deselected
and the check is reported as `NOT RUN (guarded)` with the reason.

## A3. Compose inspected statically — never started

`docker compose config --quiet` → **exit 0** (valid; no output, no secrets rendered).
Services: `db minio retention_worker minio-init webhook_worker redis analysis_worker api
notification_worker` (+ `migrate` behind `profiles: ["tools"]`).

Collision surface, all of which make a second stack from the **base file** impossible:

| Hazard | Value |
|---|---|
| Fixed container names | `pofa_db`, `pofa_minio`, `pofa_minio_init`, `pofa_redis`, `pofa_api`, `pofa_analysis_worker`, `pofa_notification_worker`, `pofa_retention_worker`, `pofa_webhook_worker`, `pofa_migrate` — absolute names, project-independent → collide with the live containers |
| Published ports | `5432`, `6379`, `9000`, `9001`, `8000` — all already taken by the live stack |
| Global volumes | `db_data`, `minio_data` → `<project>_db_data` / `_minio_data` (project-scoped, so a new project would get *new empty* volumes; but combined with the fixed names above, `up` fails/conflicts first) |
| Network | top-level `pofa` bridge |
| Bind mount | `./docker/pg-init:/docker-entrypoint-initdb.d:ro` (creates `postgis` + `vector` **only in `pofa_dev`** via `\connect pofa_dev` — a disposable DB with a different name would NOT get its extensions from this script) |
| Runtime env anchor | `x-app-environment` defaults: `DATABASE_URL=…postgres:postgres@db:5432/pofa_dev`, `REDIS_URL=redis://redis:6379/0`, `S3_ENDPOINT=http://minio:9000`, `JWT_SECRET=changeme`, `CORS_ALLOW_ORIGINS=*`, `AUTH_MODE=development`, dev tokens **true** |

Confirmed: `docker compose up` is never used in this task. The disposable stack is built from a
**separate scratch compose file** generated from these inspected facts, with its own names, network,
volumes and ports, and it does not modify the base file.

## A4. Resource capacity

| Measure | Value | Verdict |
|---|---|---|
| Engine | Docker 29.7.2, 4 containers (3 running), 5 images | — |
| `docker system df` | images 4.346 GB (3.06 GB reclaimable = untagged old build), containers 5.37 MB, volumes 799.6 MB, build cache 6.257 GB (3.179 GB reclaimable) | **no pruning performed** (forbidden); headroom is sufficient without it |
| Engine VM disk (`/` in the VM) | 1007 GB total, 12 GB used, **945 GB avail** | ample |
| Host disk | C: 23.2 GB free, D: 113.7 GB free | adequate; nothing large is written to C: |
| Docker VM memory | MemTotal 7.98 GB, MemFree 5.60 GB, **MemAvailable 6.97 GB**, SwapFree 2.0 GB | ample for a second stack (~1.5–2 GB expected) |
| Host free physical memory | **0.9 GB of 15.7 GB** | **CONSTRAINT** — the WSL2 VM already holds its allocation; the host itself is at pressure, which is the known trigger for engine restarts (§A2). Mitigated by keeping the disposable stack small and by not running model inference that loads CLIP. |
| CPU | 12 logical, VM load average 0.13 | fine |
| Existing container use | `pofa_db` 104 MiB, `pofa_redis` 6.5 MiB, `pofa_minio` 81 MiB, all ~0% CPU | fine |

Capacity decision: **proceed**, with the host-memory pressure recorded as a risk and these limits
self-imposed: no build, no image pulls (all needed images already local), no load tests, disposable
stack torn down immediately after Stage I.

## A5. Local assets relevant to later stages

- Disposable-dependency images already present (no pull needed): `garapadev/postgres-postgis-pgvector:15-stable` (902 MB, the same image the live stack uses — PG 15.13 + PostGIS 3.4.2 + pgvector), `redis:7-alpine`, `quay.io/minio/minio:latest`, `quay.io/minio/mc:latest`.
- **YOLO weights ARE local**: `D:/CODING/Projects/Proof-Of-Action-Final/yolo11n.pt`, 5,613,764 bytes, valid torch zip checkpoint, dated 2026-09-18. `backend/core/config.py:43 vision_model_name = "yolo11n.pt"` and `detector.py:128 YOLO(settings.vision_model_name)` resolve relative to CWD (`/app`), so a **read-only bind mount** of this one file to `/app/yolo11n.pt` enables real CPU inference with **no download**. It is git-ignored (`*.pt`) and excluded from the image by `.dockerignore`.
- **CLIP weights are NOT local**: no `~/.cache/huggingface` at all, and `embedding_model_name = "openai/clip-vit-base-patch32"`. Any check needing embeddings is **BLOCKED — would require an external download**, which this task forbids without asking. Recorded as gap **BE-037B-G1** (semantic/embedding paths validated only at the documented-degradation level).
- Live stack baseline to re-verify at the end: `pofa_dev` ledger **6023**, rev `t0u1v2w3x030`; `pofa_test` ledger **53316**, rev `t0u1v2w3x030`; PG 15.13; containers `pofa_db`/`pofa_redis`/`pofa_minio` started `2026-10-13T06:15:07Z`; Redis `PONG`; MinIO live 200.

## Stage A gate result

**PASS — proceed to Stage B**, with three standing constraints carried forward:
1. never `docker compose up/down` against the base file; separate scratch compose only;
2. never run the integration suite from the repo root while `pofa_minio` exists (BE-037B-D1);
3. no CLIP/semantic inference, no downloads (BE-037B-G1).
