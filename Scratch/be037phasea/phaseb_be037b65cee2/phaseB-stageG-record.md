# BE-037 Phase B — Stage G record (worker integration)

Run `be037b_20261013T062257Z_65cee2` · prefix `be037b65cee2` · measured 2026-10-13 07:07–08:20 UTC
Stack: disposable API `4f8c81a56b01`, analysis `a89b91747326`, notification `0c6ff14a5f56`,
retention `5cdcf41071ad`, webhook `9f572ceec444`, client `e98bb071c6c8`, db `996ee2c6da35`,
redis `102dacdc41ae`, minio `92628fb9f863`. Nothing in this stage touched `pofa_dev`,
`pofa_test`, `pofa_db`, `pofa_redis` or `pofa_minio`.

All worker containers were confirmed to use only disposable endpoints
(`DATABASE_URL=postgresql+psycopg2://be037b_rt@db:5432/be037b_app`,
`REDIS_URL=redis://redis:6379/0`, `S3_ENDPOINT=http://minio:9000`,
buckets `be037b65cee2-quarantine` / `be037b65cee2-evidence`) — `stageG-00-worker-config.txt`.

## 1. Result summary

| Run | Scope | Result | Evidence |
|---|---|---|---|
| A | Analysis worker success paths (vision + fingerprint), queue drain, hash equality | **18/18 PASS** | `stageG-10-runA.txt`, `stageG-11…`, `stageG-12…` |
| B | Failure path: job whose stored object was deleted first | **6/6 PASS** | `stageG-13-runB.txt`, `stageG-14…`, `stageG-15…` |
| C | Dispute → notification outbox, fusion → webhook event | 13/17, **webhook rows INVALID** (superseded) | `stageG-16-runC.txt` |
| D | SSRF matrix, subscription lifecycle, live delivery attempt, notification read | **20/22 PASS**, 2 FAIL = anonymous integration writes | `stageG-17-runD.txt` |
| D+ | Enforcing-mode instance (ephemeral process, port 8001, same disposable container) | anonymous guardless endpoints confirmed | `stageG-19…`, `stageG-20…` |
| E | Retention policy → archive → storage move → audit → webhook event | **9/9 PASS** | `stageG-27-runE2.txt`, `stageG-28…` |

One-shot worker passes: `notification_worker --limit 50`, `webhook_worker --limit 50`,
`retention_worker --limit 200` all exit 0 with honest no-op statistics
(`stageG-22-*-pass.txt`).

## 2. What was proven to work across process boundaries

1. **API → Redis → analysis worker → MinIO → PostgreSQL.** Vision inference ran for real with the
   mounted weights (container `/app/yolo11n.pt` sha256 equal to the host file; no download),
   `device=cpu`, ultralytics `8.4.155`, 1 persisted detection, and the result hash matched the
   uploaded bytes. Queue drained to `LLEN=0 / processing=0` after completion.
2. **Bounded retry then honest failure.** With the quarantine object deleted out from under the
   metadata row, the job went `queued → failed`, `attempt_count=3` (`analysis_max_attempts=3`),
   `error="Analysis processing failed"`, `result=None`, and the worker log carries the true cause
   (`ObjectNotFoundError … be037b65cee2-quarantine/quarantine/39b1fbb2-…/original`). No silent success.
3. **Webhook fanout is idempotent and respects subscription state.** Two sweeps of the running
   worker produced exactly **one** delivery per (event, ACTIVE subscription) and **zero** for the
   DISABLED subscription.
4. **Egress boundary holds and is recorded as failure, not success.** Both TEST-NET deliveries went
   `RETRYING` with `URLError: [Errno 101] Network is unreachable`; attempt_count advanced 1 → 2 after
   the backoff window (`stageG-24…`), proving the retry sweep fires.
5. **Dispute → notification chain is real.** `DISPUTE_CREATED / _ASSIGNED / _ESCALATED` were written
   to `notification_outbox` in the same transaction as the domain change; the notification worker
   turned them into 2 `notifications` (correct recipients) and 4 `notification_deliveries`
   (IN_APP + EMAIL). The recipient then read and marked the notification over the API; a
   cross-user read returned 404.
6. **Retention archive crosses every boundary correctly.** Policy → version → activation →
   dry-run evaluation → archive produced: object moved (`quarantine/988d9235…` deleted,
   `archive/988d9235…` present in the evidence bucket, identical size), `retention_states` row
   `ARCHIVED` with `previous_storage_key`, `evidence.storage_key` updated, audit event
   `RESOURCE_ARCHIVED` (ledger sequence 82, written through the application path), and a
   `retention.archived` webhook event that the worker published.
7. **SSRF validation is thorough at the API boundary**: 11/11 sinks rejected with specific reasons —
   loopback (IP and hostname), the Docker bridge gateway, the `api` and `db` service aliases
   (resolved to `172.19.0.x` before comparison), link-local metadata, both RFC1918 ranges,
   `0.0.0.0`, and non-HTTP schemes (`file`, `gopher`).

## 3. Stage G findings (report only — nothing was fixed here)

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| BE-037B-G1 | High | **Analysis endpoints carry no auth dependency at all.** `POST /api/v1/analysis/jobs` → 202 and `GET /api/v1/analysis/jobs/{id}` → 200 with **no** `Authorization` header, measured on an instance started with `AUTH_MODE=enforcing`, `AUTH_DEV_TOKENS_ENABLED=false`. Anyone can enqueue worker jobs and read results. | `stageG-10-runA.txt`, `stageG-19-enforcing-matrix.txt` (G10g/G10h) |
| BE-037B-G2 | Medium (config-scoped) | **Guarded integration endpoints are wide open in development mode.** With no token: `POST /integrations/systems` → 201 and `POST /integrations/webhooks` → 201, and the anonymous subscription then received a real outbound delivery attempt (`consecutive_failures=1`). The same requests return **401** under `AUTH_MODE=enforcing`, so this is the development anonymous bypass, not a missing guard; it is contained by the BE-037 production fail-fast, not by the endpoint. | `stageG-17-runD.txt` (G9a/G9c FAIL rows), `stageG-19…` |
| BE-037B-G3 | Low/Medium | **Retention sweep candidate query is unsatisfiable through application paths**, so `retention_worker` can never archive anything on its own. `states_expiring_before()` needs `expiry_timestamp IS NOT NULL` **and** `state ∈ (ACTIVE, ELIGIBLE_FOR_ARCHIVE, ELIGIBLE_FOR_DELETION)`, but the only `upsert_state` callers write `ARCHIVED`+expiry (archive), `ACTIVE`+**NULL** expiry (restore), `DELETED`+expiry (delete). Measured: two sweeps → `evaluated=0`, and the filter expressed in SQL over the live disposable table → `0` rows. Archiving therefore only happens by explicit API call. | `stageG-30…`, `stageG-31-retention-sweep-inert.txt` |
| BE-037B-G4 | Low | **CLIP embeddings reach for the network on every fingerprint job.** The worker issues outbound `HEAD https://huggingface.co/…` requests that only fail here because the network is internal; ~60 s of retry backoff per job and, in a connected deployment, a silent weights download. `embedding_status="unavailable"` is recorded honestly. | `stageG-12-analysis-worker-fulllog.txt` |
| BE-037B-G5 | Low | **`_complete_reprocessing_hook` logs ERROR + traceback after every completed job** (`LookupError: Reprocessing request not found`), an observability defect that buries real errors in expected noise. | `stageG-14-runB-workerlog.txt` |
| BE-037B-G6 | Info | Two metadata/semantics observations: `GET /evidence/{id}/download` presigns a URL for an object that no longer exists (the 404 `NoSuchKey` surfaces only when the client follows it); and `Evidence.status` stays `uploaded_quarantine` after archival even though `storage_key` now points into the evidence bucket. | `stageG-15…`, `stageG-28…` |
| BE-037B-G7 | Info | Webhook first retry delay is 300 s, not the documented 30 s: `compute_next_webhook_attempt()` indexes `RETRY_DELAYS` by `attempt_count` after the increment, so `RETRY_DELAYS[0]=30` is never used and the 7200 s tail is unreachable before the cap of 5. | `stageG-23…`, `stageG-24…` |
| inherited | — | Redis queue key `pofa:analysis:jobs` is not run/tenant-namespaced (Phase B observation carried from run A). | `stageG-01-prestate.txt` |

## 4. Marked NOT RUN / BLOCKED (no weaker substitute used)

- **Webhook `DELIVERED` (2xx) path at container level — BLOCKED by design.** The SSRF blocklist
  rejects every address reachable inside the isolated network, so a real 2xx sink cannot exist here.
  Substituted measurement: subscription accepted for a public TEST-NET address, attempted for real,
  and dying at the egress boundary as `RETRYING` (proves both the attempt and the containment).
  Positive-delivery behaviour is covered by repository unit tests (`tests/unit/test_be036_*`), not here.
- **Redirect refusal (BE-037B/D1 closure) at container level — NOT RUN**; same reachability reason.
  The `_NoRedirectHandler` path is unit-tested in the repo.
- **Terminal `FAILED` + auto-disable after 10 consecutive failures — NOT RUN**: would require ~5 h of
  backoff (300 s/1800 s/7200 s…) or clock manipulation beyond this stage's scope.
- **Storage-failure cleanup branch — NOT RUN** (needs storage fault injection; carried from Stage F).
- **Real email/webhook egress — deliberately not performed** (task rule: no external delivery).
  The EMAIL channel completed through `DevEmailProvider`, which is log-only and returns a fabricated
  `dev-msg-…` provider id while reporting `DELIVERED`: a silent-success risk that this stack cannot
  distinguish from real delivery. There is no configuration point to select a real provider.

## 5. Process notes (kept, not hidden)

- Run C's webhook rows were **invalid, not passes**: the external system was never created (bad
  `system_type`), so every subscription POST failed schema validation before the SSRF validator or
  the permission guard ran. Run D re-measured them with a real external system; the `422`-on-null-id
  "passes" in `stageG-16-runC.txt` must not be read as SSRF evidence.
- Run E's first pass failed 5 checks for a probe bug (`archive_after_days` must precede
  `retention_days`); the corrected run is `stageG-27-runE2.txt`. `stageG-26-runE.txt` is kept as history.
- The enforcing-mode instance was an ephemeral `uvicorn` process on port 8001 **inside the existing
  disposable API container** (no live service recreated or restarted); it was stopped by PID match on
  its own command line and the primary API was re-verified healthy (`stageG-21…`).
- Deliberate fault injection on the disposable dataset only: `evidence.created_at` of
  `988d9235-…` was moved back 10 days so an age-based policy could be exercised (PolicyRules
  requires `retention_days > 0`).
- One `docker inspect` of the API container printed the disposable runtime DSN to the terminal.
  It is recorded in no report or evidence file (verified by grep); the credential exists only in the
  run's local `secrets.env` and dies with the disposable stack at cleanup.
