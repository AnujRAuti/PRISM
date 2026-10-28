# BE-037 Phase B — Final Report: Full Isolated Stack Integration Validation

Run identifier: `be037b_20261013T062257Z_65cee2`
Resource prefix: `be037b65cee2` · Scratch: `D:/CODING/Scratch/be037phasea/phaseb_be037b65cee2/`
Repository: branch `Backend`, HEAD `b5d4a5fba73b9a38289233f3fc75f6063fec39db`, worktree clean.
Image under test: `poa-backend:be037a` (`839b0e63c0ff`), **reused, not rebuilt** — proven to contain
exactly the committed source by a CR-normalized tree hash over `backend/**.py` + `alembic/**.py`
identical inside the image and on the host (`158 files`, `92f4dae4a0c8…`, Stage B manifest §B4).
Execution window: 2026-10-13 06:22 → 09:15 UTC.
Report written: 2026-10-13 (this file is uniquely named; no Phase A report was touched).

---

## 1. VERDICT

> **PHASE B — CONDITIONAL PASS.** The application **does** function as an integrated system:
> one production-shaped container, running the real ASGI command and four real worker processes
> against real PostgreSQL + PostGIS + pgvector, real Redis, and real MinIO, completed every
> end-to-end flow this phase tested, and the audit ledger stayed `valid=true` across all of it.
> The condition is that **two High-severity defects were measured and are still live**, and a
> set of operational behaviours could not be observed at all in an isolated environment.

Explicitly **not** declared by this report, and not defensible from this evidence:

* **No production acceptance.** There is still no production target and no production secret
  store (BE-037 Phase 0 finding, unchanged). Nothing here was run against anything production.
* No high availability, no production recovery, no production backup readiness.
* No claim that the shipped `docker-compose.yml` restart policy works — it was deliberately
  **NOT RUN** (it would have required touching protected services). See §5.
* No claim that the disposable cluster's owner identity represents the real deployment's
  (it does not — see BE-037B-H2, §6).

Verdict per stage: **A PASS · B PASS · C PASS · D PASS · E 33/33 · F 26/26 · G 66/72 with the 6
non-passes being findings not flaky tests · H 47/47 + 3 tamper phases · I 13 scenarios, 1 High
defect · 12 cleanup PASS.**

---

## 2. What "integrated" was actually proven

Each line is a cross-process round trip measured on the disposable stack, not a unit test.

| # | Integration claim | Measured as | Evidence |
|---|---|---|---|
| 1 | HTTP request → PostgreSQL write → audit ledger append, in one application path | `POST /api/v1/auth/users` advanced the ledger head 86 → 87 and the new row's `previous_hash` equalled the previous checkpoint `tail_event_hash` | `stageH-02`, `stageH-15` |
| 2 | `/ready` reflects all three dependencies and binds authorization | `{'application','postgresql','redis','storage'}` all healthy, three `required=True` | `stageE-result.txt` E1 |
| 3 | API → Redis queue → analysis worker → MinIO → PostgreSQL | Real YOLO vision inference on CPU with mounted weights (container `yolo11n.pt` sha256 == host file, **no download**), 1 persisted detection, result hash matched the uploaded bytes, queue drained to `LLEN=0 / processing=0` | `stageG-10`, `stageG-11`, `stageG-12` |
| 4 | Bounded retry then **honest** failure | Object deleted before processing → `queued → failed`, `attempt_count=3`, `error="Analysis processing failed"`, `result=None`, worker log carries the true `ObjectNotFoundError` | `stageG-13`, `stageG-14`, `stageG-15` |
| 5 | Evidence upload → quarantine bucket → metadata row → presigned download of byte-identical content | 201 with `storage_key=quarantine/<id>/original`, 1534 bytes, presigned fetch byte-identical, 3/3 | `stageF-result-rerun2.txt` F1/F2/F3 |
| 6 | Upload rejection follows the implementation's real limits | disallowed MIME 415, malformed payload 415, JPEG-as-PNG 415, empty 400, >10 MiB 413 (5/5) | `stageF-result-rerun2.txt` F4 |
| 7 | PostGIS is live in the product path | `PATCH …/location` accepts valid coords, rejects out-of-range 422, `nearby` returns the located evidence | `stageF-result-rerun2.txt` F6, `stageE-result.txt` E3b |
| 8 | Domain event → notification outbox → worker → notifications + deliveries → API read | `DISPUTE_CREATED/_ASSIGNED/_ESCALATED` written in the same transaction as the domain change; worker produced 2 `notifications` + 4 `notification_deliveries` (IN_APP + EMAIL); recipient read/marked over HTTP, cross-user read 404 | `stageG-17`, `stageG-22-notification_worker-pass.txt`, `stageG-24` |
| 9 | Webhook fan-out is idempotent and honours subscription state | two sweeps of a **running** worker → exactly one delivery per (event, ACTIVE subscription), zero for DISABLED | `stageG-17`, `stageG-23`, `stageG-24` |
| 10 | Retention archive crosses every boundary correctly | policy → version → activation → dry-run → archive: object moved (`quarantine/…` deleted, `archive/…` present, identical size), `retention_states=ARCHIVED` + `previous_storage_key`, `evidence.storage_key` updated, `RESOURCE_ARCHIVED` audit event at sequence 82 through the app path, `retention.archived` webhook event emitted | `stageG-26`, `stageG-27-runE2.txt`, `stageG-28`, `stageG-32` |
| 11 | SSRF containment at the API boundary | 11/11 sinks rejected with specific reasons: loopback (IP + hostname), bridge gateway, `api`/`db` service aliases resolved before comparison, link-local metadata, both RFC1918 ranges, `0.0.0.0`, non-HTTP schemes | `stageG-17` |
| 12 | Outbound attempts really leave the process and are recorded as **failure**, not success | both TEST-NET deliveries → `RETRYING`, `URLError: [Errno 101] Network is unreachable`, `attempt_count` 1 → 2 after the backoff window (proves the retry sweep fires) | `stageG-24-delivery-retry-fired.txt` |
| 13 | Append-only ledger enforced by the database, not just the app | runtime identity `be037b_rt`: INSERT allowed, UPDATE/DELETE/TRUNCATE denied by grants + `trg_audit_ledger_append_only`, owner-side wall proven inside rolled-back transactions | `stageH-03`, `stageH-05` (14/14), `stageH-06` |
| 14 | Tampering and gaps are **detected and classified** | forged row → `valid=false` with the right failure; gap → `known_historical`-class discrimination; both reversed afterwards | `stageH-08`, `stageH-09`, `stageH-11`, `stageH-13` |
| 15 | The API self-recovers from a PostgreSQL outage with no restart | `/ready` 503 naming postgresql during the outage; ~3 s after restore the same process served healthy responses; workers' next loop pass resumed | `stageI-03`, `stageI-13`, `stageI-11` |
| 16 | The API self-recovers from an object-storage outage with no orphan state | upload failed cleanly — no evidence row, no audit event, no orphan object; uploads and downloads worked again after restore | `stageI-06` |
| 17 | A stranded queue message is recoverable | after a manual consumer start: `llen 1 → 0`, `attempt_count 0 → 3`, row `failed` for the genuine `ObjectNotFoundError` reason — nothing lost, **but only because a person intervened** | `stageI-05` |
| 18 | Logs do not leak secrets | 9 containers × 5 secret values, exported before removal | `stageI-10-log-hygiene.txt`, `stage12-logs/*.log` |

Runtime identity discipline held throughout: the API and workers connected as the non-owner,
non-superuser role `be037b_rt` (`is_superuser=false`, D5 matrix), while migrations ran only
through `be037b_owner` in an explicit `tools`-profile container. No service ran migrations at
startup.

---

## 3. Defect register (measured in this phase — nothing was fixed here)

### High

| ID | Defect | Why it matters | Code | Evidence |
|---|---|---|---|---|
| **BE-037B-G1** | **The analysis endpoints carry no auth dependency at all.** `POST /api/v1/analysis/jobs` → 202 and `GET /api/v1/analysis/jobs/{id}` → 200 with **no** `Authorization` header — measured on an instance started with `AUTH_MODE=enforcing`, `AUTH_DEV_TOKENS_ENABLED=false`. | Not a development-mode artifact: anyone who can reach the API can enqueue worker jobs (compute spend, queue flooding) and read analysis results belonging to other tenants. | `backend/api/v1/endpoints/analysis.py:19-20,33-34` — both handlers declare only `db: Session = Depends(get_db)`; no auth/authorization dependency exists on either route (re-read to confirm the attribution). | `stageG-10-runA.txt`, `stageG-19-enforcing-matrix.txt` (G10g/G10h) |
| **BE-037B-I1** | **The analysis queue consumer cannot survive a Redis outage.** `run_worker()` loops `queue.dequeue(timeout=5)` with no exception handling; `__main__` catches only `KeyboardInterrupt`. A `redis ConnectionError` escapes and kills the process (measured `exit=1` within ~1 s of Redis disappearing). | Work already accepted with HTTP 202 stops being processed until a human restarts the consumer (one job stayed `queued` ≥ 36 s). `recover_abandoned()` inspects only the `:processing` list, so a message still on the main queue is not "recovered" — it waits. The system *reports* acceptance while silently not working. | `backend/workers/analysis_worker.py:197-224` (dequeue at `:213`), `:226-232`; `backend/services/analysis_queue.py` `recover_abandoned()` | `stageI-04-redis-outage.txt`, `stageI-05-stranded-queue-recovery.txt` |

### Medium

| ID | Defect | Note |
|---|---|---|
| **BE-037B-G2** | Guarded integration endpoints are wide open in development mode: anonymous `POST /integrations/systems` → 201, `POST /integrations/webhooks` → 201, and the anonymous subscription then received a real outbound attempt. Same requests return 401 under `AUTH_MODE=enforcing`, so this is the dev anonymous bypass contained by the BE-037 production fail-fast — it is a deployment-config dependency, not a missing guard. |
| **BE-037B-G3** | The retention sweep's candidate query is unsatisfiable through application paths: `states_expiring_before()` requires `expiry_timestamp IS NOT NULL` **and** `state ∈ (ACTIVE, ELIGIBLE_FOR_ARCHIVE, ELIGIBLE_FOR_DELETION)`, but the only `upsert_state` writers produce `ARCHIVED`+expiry, `ACTIVE`+**NULL** expiry, `DELETED`+expiry. Measured `evaluated=0` over two sweeps and `0` rows by SQL. Archiving therefore only ever happens by explicit API call — the automated lifecycle advertised by the worker does not fire. |
| **BE-037B-I2** | Shell-supervisor workers burn a core while idle: `while true; do python -m backend.workers.<x>; sleep 15; done` re-imports the app every pass — cold import **1.81–2.57 s**, samplers caught **39–99 % of a core** on an otherwise idle stack; observed cadence 17.5 s = 15 s sleep + ~2.5 s import. Cost/observability issue, not a reliability one (the same loop shape is what makes those workers survive a DB outage). |
| **BE-037B-I3** | A presigned download URL is issued with **HTTP 200** during a total storage outage (`backend/api/v1/endpoints/evidence.py:76` signs locally, no storage round trip), while `/ready` was simultaneously reporting storage unhealthy. A caller that trusts the 200 sees a phantom success; the failure surfaces only on the client fetch, 2 ms later, as a DNS error. |
| **BE-037B-I4** | Dependency outages map to different HTTP semantics for the same failure class: storage outage → evidence upload **500** (`StorageConnectionError` unmapped, falls to `backend/app/main.py:72`); Redis outage → analysis job **503** (`backend/api/v1/endpoints/analysis.py:28`). 500 tells a client not to retry. |
| **BE-037B-H1** | The database validates the ledger's *domain* and *uniqueness*, not its *chain continuity*: the append-only trigger is `BEFORE UPDATE OR DELETE` only, so a runtime-credential holder can commit a syntactically valid row with arbitrary hashes, or append at `max+5` to fabricate a gap — PostgreSQL accepted a direct runtime `INSERT` with `repeat('a',64)` hashes. Chain correctness on insert lives in `append_event` (D-2-A), i.e. inside the process a compromised credential controls. This is **detect, not prevent**; the published anchored checkpoint is what makes "nobody ran verification" itself detectable. |
| **BE-037B-H3** | Append-only protects the ledger only. The runtime identity retains full DML on business tables — raw `DELETE FROM organizations …` and `UPDATE organizations …` both succeeded (rolled back). Deleting such a row leaves its audit events intact but stranded. Design scope, reported not proposed. |

### Low / Info

* **BE-037B-I5** — `/ready` answers 503 in **10.08 s**, then **3.89 s**, during a storage outage (botocore endpoint retries against an unresolvable host; the check is uncached and fans out per request) vs ~50 ms healthy. An orchestrator with a probe timeout under ~10 s logs a timeout instead of the intended 503.
* **BE-037B-I6** *(by design, recorded so it is not mistaken for a defect)* — the api container healthcheck polls `/health`, the BE-020 **liveness** endpoint, deliberately dependency-agnostic; the container stayed `healthy` through a 34 s total DB outage while `/ready` correctly returned 503. Reasonable for restart storms, but Docker-level health carries no readiness information here.
* **BE-037B-I7** — during a DB outage an authenticated request returns **401 "Invalid credentials"** (dev-token validation needs a DB read): an infrastructure failure reported as an authentication failure.
* **BE-037B-I8** — only the api and analysis worker stop cleanly (exit 0). notification, webhook, retention and client all exit **137** (SIGKILL after the grace period). *The exact reason the `sh -c` loop outlives SIGTERM is not established by the measurement* (PID-1 masks show SIGTERM neither caught nor ignored), so it is recorded as an open question, not an explanation. Consequence: production shutdown of those three is unclean and an in-flight pass can be cut mid-way; no data was damaged in this run.
* **BE-037B-I9** — the shutdown log does not distinguish a clean stop from a crash: the `finally:` block printed "analysis worker stopping / stopped" on the fatal Redis path too.
* **BE-037B-G4** — CLIP embeddings reach for the network on every fingerprint job (`HEAD https://huggingface.co/…`), succeeding only because this network is internal; ~60 s of retry backoff per job, and in a connected deployment a silent weights download. `embedding_status="unavailable"` is recorded honestly.
* **BE-037B-G5** *(re-confirmed as I10)* — `_complete_reprocessing_hook` logs **ERROR + traceback after every completed job** (`LookupError: Reprocessing request not found`), burying real errors in expected noise.
* **BE-037B-G6** — `GET /evidence/{id}/download` presigns a URL for an object that no longer exists (the `NoSuchKey` 404 surfaces only when the client follows it); `Evidence.status` stays `uploaded_quarantine` after archival even though `storage_key` now points into the evidence bucket.
* **BE-037B-G7** — the first webhook retry delay is 300 s, not the documented 30 s: `compute_next_webhook_attempt()` indexes `RETRY_DELAYS` by `attempt_count` **after** the increment, so `RETRY_DELAYS[0]=30` is never used and the 7200 s tail is unreachable before the cap of 5.
* **BE-037B-H4** — `has_table_privilege` assertions and executed statements disagreed in *usefulness*, not outcome; only the executed statement reveals why a mutation is refused. Stage H therefore asserts the error class, which is the discipline that caught the four vacuous passes in run B1.
* **F-stage (low)** — `POST /api/v1/evidence` responds `status: "uploaded"` while the persisted and re-read row says `uploaded_quarantine` (`backend/api/v1/endpoints/evidence.py:36` hard-codes the field). Clients trusting the response see a state no stored row has.
* **BE-037B-D2** — see §4; blocks any fresh-deployment story.

---

## 4. Blockers carried forward (must not be lost)

* **BE-037B-D2 — no supported bootstrap for the authorization catalogue.** A freshly migrated
  database has `roles=0, permissions=0`, so role assignment 404s until something calls
  `ensure_default_catalogue`. Stage F had to seed it through the application service just to
  obtain an authorized principal. This means **the disposable stack could not be brought up to
  an authorized state by any documented path** — that is a deployment blocker, not a test
  inconvenience. (`stageE-2a-catalogue.txt`, `phaseB-stageF-record.md` §"Findings carried to Stage J".)
* **BE-037B-D1 — `tests/integration/test_storage.py` restarts the LIVE MinIO container.** Line 77
  runs `docker compose restart minio` from the repository root, which resolves
  `docker-compose.yml` where the `minio` service is pinned to `container_name: pofa_minio`. Any
  `pytest tests/integration` run therefore restarts a real developer datastore. Observed in the
  Phase A timeline (`pofa_minio` `Exiting on signal: TERMINATED` at 16:34:30Z right after the
  869-test suite finished). Phase B was planned around this hazard and never ran that file.
  This is a standing hazard for anyone following "run the integration suite" advice.
  (`phaseB-stageA-preflight.md`.)
* **BE-037B-H2 — the append-only wall was not proven for an owner-identity DSN.** In the
  disposable cluster the migration identity `be037b_owner` *is* the container's `POSTGRES_USER`,
  i.e. a cluster superuser — an artifact of the throwaway bootstrap, never used by an application
  path. So this stack **cannot** demonstrate behaviour for a deployment whose runtime DSN is the
  table owner: there the trigger is the only defence against UPDATE/DELETE and **no defence at all**
  against TRUNCATE. The requirement *is* met on `pofa_dev` (BE-033/034/035: `poa_runtime` is not the
  owner, TRUNCATE denied) and is restated here so it is not mistaken for something Phase B proved.

---

## 5. NOT RUN / BLOCKED — no weaker substitute was passed off as a result

| Item | Status | Why |
|---|---|---|
| Shipped `restart: unless-stopped` behaviour for the Redis-loss crash-loop (I1) | **NOT RUN** | My Stage B choice was `restart: "no"` on all 9 services precisely so nothing could be recreated. Testing the shipped policy means the protected stack. The defect is the same either way: an unhandled dependency exception is used as the shutdown mechanism. |
| Webhook `DELIVERED` (2xx) path at container level | **BLOCKED by design** | The SSRF blocklist rejects every address reachable inside the isolated network, so a real 2xx sink cannot exist here. Substituted measurement (attempt is real, dies at the egress boundary as `RETRYING`) proves attempt + containment, and is labelled as such. Positive delivery is covered by repo unit tests, not by Phase B. |
| Redirect refusal (the BE-036-D1 closure) at container level | **NOT RUN** | Same reachability reason; unit-tested in the repository. |
| Terminal `FAILED` + auto-disable after 10 consecutive failures | **NOT RUN** | Would need ~5 h of backoff or clock manipulation beyond this stage's scope. |
| Storage-failure cleanup branch inside the upload path | **NOT RUN** | Needs storage fault injection at a finer grain than stop/restore; carried from Stage F. |
| Real email / webhook egress | **Deliberately not performed** | Task rule. Note the product risk it exposes: the EMAIL channel completes through `DevEmailProvider`, which is log-only and returns a fabricated `dev-msg-…` id while reporting `DELIVERED` — a silent-success risk this stack cannot distinguish from real delivery, and there is no configuration point to select a real provider. |
| `TRUNCATE audit_ledger_events` as owner/superuser | **NOT RUN, on purpose** | The trigger does not fire for TRUNCATE, so the statement would have destroyed the disposable ledger unrecoverably and invalidated the rest of Phase B. TRUNCATE protection is F-05 non-ownership, which **was** measured from the runtime side (`permission denied for table audit_ledger_events`). Recorded as NOT RUN, not as a pass. |
| Full "attacker forges a row, then the app chains onto it" scenario | **NOT RUN** | Requires leaving the damage committed; Stage H reversed everything instead. |
| A `BEFORE INSERT` chain validator test | **NOT RUN** | No such validator exists (finding H1); its absence was demonstrated by the accepted direct insert. |
| Any write against `pofa_dev` / `pofa_test` | **Not performed** | Both measured read-only, before and after; see §7. |
| Model-weight download | **Not performed** | Weights were confirmed present locally first (`/app/yolo11n.pt` hash-matched the host file), so real vision inference ran with zero egress. G4 is reported as a gap, not exercised. |
| pytest suites inside the container | **NOT RUN** | Out of Phase B scope (this phase validates the integrated *system*, not the unit suite; the repo suite result carries forward from BE-037 Phase 8: 862 passed / 1 skipped / 0 failed). |

---

## 6. Accuracy corrections made during Phase B (kept, not hidden)

1. **`/health` attribution was wrong in earlier session notes.** The trivial router in
   `backend/api/v1/endpoints/health.py` is reachable only at `/api/v1/health` and
   `/api/v1/ready`. Root `/health` is BE-020 **liveness** (`backend/app/main.py:87`) and root
   `/ready` is BE-020 readiness with application + postgresql + redis + storage
   (`observability/health.py:75,115,144,188,201`). The correct statement is that `/health` is
   dependency-agnostic **on purpose** (finding I6), not that it is a static stub.
2. **Phase A's exit-code prediction beat my reasoning.** I predicted 143 for the loop workers
   from the PID-1 signal masks; the measured result is **137** (`stageI-09`, confirmed at removal
   time in `stage12-02-removal.txt`). The masks therefore did not explain the outcome, and that
   is recorded as an open question rather than smoothed over.
3. **Stage G run C's webhook rows were invalid, not passes.** The external system was never
   created (bad `system_type`), so every subscription POST failed schema validation before the
   SSRF validator or the permission guard ran. Run D re-measured them. The `422`-on-null-id
   "passes" in `stageG-16-runC.txt` must not be read as SSRF evidence; the file is kept as history.
4. **Stage H run B1 produced four vacuous passes.** `'a'*64` is parsed by PostgreSQL as integer
   multiplication, so the ledger INSERT probes died on `invalid input syntax for type integer`.
   Run B2 (`stageH-05`) re-measured with `repeat('a',64)` and asserted the error class.
5. **`secrets.env` was never actually mode 600.** The Stage B manifest asserted it; the file was
   measured at **644**, and `chmod 600` is a no-op on this NTFS volume — so the manifest claim was
   unverifiable and wrong. Content verified by **key name only** (5 disposable-only keys, 203
   bytes, no live credential); the values are now dead because the whole stack was removed.
   Recorded in `stage12-03-post-cleanup-verification.txt` with the failed chmod attempt intact.
6. **Some evidence landed in the repository root by mistake.** Six Stage G/H files
   (`stageG-20/21/23`, `stageH-01/04/07`) were written there by a relative-path redirect bug.
   They were untracked and are this run's own output; they were **moved** (not deleted) into the
   scratch directory, and `git status --porcelain` is now empty.

---

## 7. Safety record — protected resources

Cleanup was executed only against resources whose exact **name and full ID** were in the Stage B
manifest and which carried the `com.docker.compose.project=be037b65cee2` label. Forbidden
commands (`docker compose down`, `docker system prune`, `docker volume prune`, `docker network
prune`, wildcard `rm`) were never used. 10 containers, 2 volumes and 1 network were removed;
`be037b` residual grep → containers none, volumes none, networks none, compose projects none.

Post-cleanup verification re-ran the identical read-only checks captured immediately before
cleanup: **27 of 27 baseline lines matched, 0 drift** (`stage12_step4_diff.py` output appended to
`stage12-03-post-cleanup-verification.txt`).

* `pofa_db` `7949c9980816…`, `pofa_redis` `29b684e82d7c…`, `pofa_minio` `54fce2fccd46…` — same IDs,
  `state=running`, **`restarts=0`**, same `StartedAt=2026-10-13T06:15:07…` ⇒ never stopped,
  restarted or recreated. `pofa_minio_init` still `Exited (0) 2 weeks ago`.
* Volumes `proof-of-action-final_db_data`, `proof-of-action-final_minio_data` and network
  `proof-of-action-final_default` present and untouched.
* `pofa_dev`: alembic `t0u1v2w3x030`, ledger 6023 rows (`lo=1 hi=6059`), users 1054, projects 544,
  evidence 284, analysis_jobs 32, webhook_events 561, 73 tables, PostgreSQL 15.13 — all identical.
* `pofa_test`: alembic `t0u1v2w3x030`, ledger 53316 dense `1..53316`, users 3263, projects 1636,
  evidence 1216, analysis_jobs 38, webhook_events 4455, 73 tables — all identical.
* `poa_runtime` still present with `canlogin=true`; no `poa_migrator` (never existed); **no
  `be037b_*` role leaked into the live cluster** (they existed only inside the disposable one).
* Live buckets `pofa-evidence` / `pofa-quarantine` present; **zero entries dated 2026-10-13**
  across a 2 142-line recursive listing (newest 2026-10-12, pre-existing) ⇒ no Phase B write.
* Isolation during the run: every Phase B container published **no host port**; all nine attached
  only to the `internal=true` network `be037b65cee2_net`; `docker/pg-init/init.sql` (it does
  `\connect pofa_dev`) and `scripts/provision_runtime_roles.sql` (line 69 alters the cluster-wide
  `poa_runtime`) were both deliberately **not** used.
* Repository: HEAD unchanged at `b5d4a5fb`, nothing staged, nothing committed, nothing pushed, no
  `git add`, no `reset/clean/restore`, no source file modified, no Phase A report overwritten.

---

## 8. Decisions this phase now needs from the owner (priority order)

1. **G1 — unauthenticated analysis endpoints.** In scope to fix now, or accepted as a known gap?
   This is the only finding that exposes tenant data and worker compute with no credential at all.
2. **I1 — Redis-loss kills the analysis consumer.** Fix the loop (catch dependency errors, back
   off, keep serving) *and/or* adopt a supervisor that does not re-import the app per pass (I2)?
   Note that the shipped `restart: unless-stopped` masks I1 as a crash-loop rather than fixing it.
3. **D2 — catalogue bootstrap.** Ship a supported seed path (migration-time or CLI) or document
   `ensure_default_catalogue` as a required first-run operation? Until then a fresh deployment
   cannot reach an authorized state by any documented route.
4. **H1 — chain validation at insert time in the database.** Accept "detect, not prevent", or add
   a `BEFORE INSERT` validator?
5. **G3 — the retention sweep can never fire.** Automated lifecycle is effectively dead code;
   either make the state machine produce eligible states or stop describing retention as automatic.
6. **I3/I4 — outage HTTP semantics.** Should presigning fail when storage is unhealthy, and should
   dependency-failure paths be unified on 503?
7. **G4 / model weights.** Confirm the deployment policy for embedding weights (pre-baked vs
   forbidden egress) — this phase proved inference works with mounted weights and no download.
8. **D1 — `tests/integration/test_storage.py` restarting the live MinIO.** Needs a decision on
   containment (skip marker, dedicated service name, or a disposable-profile compose) before the
   integration suite is run against live developer infrastructure again.
9. **I8 — unclean shutdown of three workers (exit 137).** Accept, or restructure the supervisor
   loops so SIGTERM reaches the Python process?

Phase B reports; it changes no code and fixes nothing.

---

## 9. Evidence index

Under `D:/CODING/Scratch/be037phasea/phaseb_be037b65cee2/` (nothing was deleted; the Docker
resources are gone but their logs and data captures are retained).

* **Stage A (read-only preflight)** — `../phaseB-stageA-preflight.md`, `../runtime-validation.md`
  (Phase A, not overwritten).
* **Stage B (boundary + manifest)** — `phaseB-stageB-manifest.md` (18 owned resources recorded
  before creation), `compose.disposable.yml`, `pg-init/`, `provision-runtime.sql`, `treehash.py`,
  `secrets.env` (disposable-only).
* **Stage C (creation)** — `stageC-00-precreation-baseline.txt`,
  `stageC-01-protected-db-baseline.txt`, `stageC-02-migrate.log`, `stageC-03-provision.log`.
* **Stage D (infrastructure readiness)** — `stageD-readiness.txt` (resource IDs, PG/PostGIS/
  pgvector, Redis, MinIO readiness), `stageD-identity.txt` (D4 alembic + D5 runtime privilege
  matrix), `stageD-egress.txt` (no published ports, internal network only).
* **Stage E (API integration)** — `stageE-api-startup.txt`, `stageE-result.txt` (**33/33**),
  `stageE-1b-endpoints.txt`, `stageE-1c-openapi-paths.txt`, `stageE-2a-catalogue.txt` (D2),
  `stageE-2b-schemas.txt`, `stageE-2d-prodfailfast.txt`.
* **Stage F (evidence + object storage)** — `phaseB-stageF-record.md`,
  `stageF-result.txt` / `-rerun.txt` / `-rerun2.txt` (**26/26** final), `stageF-db-rows.txt`,
  `stageF-counts.txt`, `stageF-buckets-count.txt`, `stageF-buckets-rerun.txt`,
  `stageF-network-isolation.txt`, `stageF-live-minio.txt`.
* **Stage G (workers)** — `phaseB-stageG-record.md`, runs A–E:
  `stageG-10…12` (A), `stageG-13…15` (B), `stageG-16` (C, invalid history),
  `stageG-17…21` (D + enforcing), `stageG-26…28`, `stageG-22-*-pass.txt`,
  `stageG-23…24`, `stageG-25`, `stageG-29…32`.
* **Stage H (ledger + DB security)** — `phaseB-stageH-record.md`, `stageH-00…15`
  (A 28/28, B1 25/29 with the 4 vacuous rows explained in §5, B2 14/14, C, E, F 5/5, close).
* **Stage I (operational / failure)** — `phaseB-stageI-record.md`, `stageI-00…13`.
* **Stage 12 (cleanup)** — `stage12-00-pre-cleanup-evidence.txt`,
  `stage12-01-protected-baseline-before.txt`, `stage12-02-removal.txt`,
  `stage12-03-post-cleanup-verification.txt`, `stage12-04-live-minio-tree.txt`,
  `stage12-04b.txt`, `stage12_step4_diff.py`, `stage12-logs/*.log` (all 10 containers,
  api 1 594 lines / 162 826 B).
* **This report** — `phaseB-stageJ-final-report.md`.

---

## 10. Phase B stops here

No deployment, no commit, no push, no staging, no new milestone, no production acceptance.
Phase B is the last integration phase of BE-037; the findings above are handed to the owner for
disposition, and **further action requires explicit approval**.
