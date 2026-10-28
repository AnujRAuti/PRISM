# BE-037 Phase B — Stage F record: evidence ingestion + object storage (disposable run `be037b_20261013T062257Z_65cee2`)

Scope measured here: upload through the real supported API flow, metadata, presigned
download, rejected inputs, geospatial context, retention dry-run, and the
database ↔ object-storage reference agreement — all against this run's own
PostgreSQL/MinIO only.

All HTTP ran inside `be037b65cee2_client` on network `be037b65cee2_net`
(`internal: true`, no published ports). No secret value appears in any file here.

## F-result (final, re-run 2)

`stageF-result-rerun2.txt` — **26 checks, 26 PASS, 0 FAIL**.

| Section | Claim measured | Result |
|---|---|---|
| F0 | bootstrap an *authorized* disposable principal (create user → grant `FIELD_OFFICER`) | 2/2 PASS |
| F1 | `POST /api/v1/evidence` accepts a synthetic PNG through the supported flow → 201 with `evidence_id`, `storage_key=quarantine/<id>/original`, size 1534 | PASS |
| F2 | stored row status is the quarantine state `uploaded_quarantine`, and metadata agrees with the upload result (size/content type) | 3/3 PASS |
| F3 | presigned download URL issued **after** authorization, points only at `http://minio:9000/…`, and returns byte-identical content | 3/3 PASS |
| F4 | rejections per the implementation's limits: disallowed MIME 415, malformed payload with image MIME 415, real JPEG bytes declared `image/png` 415, empty 400, oversized (>10 MiB `max_upload_size`) 413 | 5/5 PASS |
| F5 | unknown evidence id → 404 (no phantom record) | PASS |
| F6 | `PATCH …/location` accepts valid coordinates, rejects out-of-range lat/lon 422, and the PostGIS `nearby` query returns the located evidence | 4/4 PASS |
| F7 | `FIELD_OFFICER` (catalogue has no `retention.read`) is refused the retention dry-run with 403; an `ADMINISTRATOR` principal gets 200 with `eligible=false, archive_eligible=false, deletion_eligible=false, blocking_reasons=["NO_APPLICABLE_POLICY"]`; the evidence row is still present afterwards | 7/7 PASS |

`evidence_id` of the accepted upload: `9e22a42a-0cc3-4853-8255-4a3eff44bba0`
storage key `quarantine/9e22a42a-0cc3-4853-8255-4a3eff44bba0/original`.

## Database ↔ object-storage reference agreement

`stageF-buckets-count.txt`, `stageF-db-rows.txt`.

Object inventory was re-measured with an **authenticated** `mc` alias created inside
the disposable MinIO container from that container's own
`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` environment (values never printed). The
earlier attempt (`stageF-counts.txt`) reported `quarantine=0 evidence=0` and is
**invalid** — it ran `mc ls` with no credentials and discarded stderr, so it measured
nothing. Corrected measurement:

- disposable buckets: `be037b65cee2-quarantine`, `be037b65cee2-evidence` (2, both
  created by `minio-init`, anonymous access `private`)
- `be037b65cee2-quarantine`: **4 objects**, 5.8 KiB — exactly the 4 accepted uploads
  of the three probe passes (7eb6c37c…, b0105ec8…, 15ffd949…, 9e22a42a…)
- `be037b65cee2-evidence`: **0 objects** — nothing was promoted out of quarantine by
  this stage, as expected
- `evidence` table in `be037b_app`: **4 rows**, all `uploaded_quarantine`, all
  `storage_key LIKE 'quarantine/%'` (0 rows without an object prefix)
- rows ↔ objects is 1:1 by `storage_key`, and the 14 rejected uploads across the
  three passes (4 + 5 + 5 rejections; the 4 accepted uploads are the 4 rows above —
  pass 1's `b0105ec8…` was the over-strict mismatch case, which was a valid PNG and
  correctly accepted) produced **neither a row nor an orphan object** — validation
  happens before any `put_object`
- the storage-failure/`SQLAlchemyError` cleanup branch (rollback + best-effort orphan
  delete) was **NOT RUN** in this stack: it needs fault injection into MinIO or the
  DB, which is exercised by the repository's unit/integration fault tests, not here

## Live environment untouched (read-only re-check)

`stageF-live-minio.txt`, `stageF-network-isolation.txt`.

- `pofa_minio` id `54fce2fccd46fa5b…`, `started=2026-10-13T06:15:07.080287176Z`,
  `restarts=0`, `status=running`, volume `proof-of-action-final_minio_data` —
  identical to the Stage C pre-creation baseline
- live bucket inventory is still exactly `pofa-evidence/`, `pofa-quarantine/`
  (both created 2026-09-13); **no `be037b*` bucket exists on the live MinIO**
- every disposable container is attached to exactly one network,
  `7d581f96427e…` = `be037b65cee2_net` (`internal=true`), with empty port-binding
  maps (exposed, never published); `pofa_db`/`pofa_redis`/`pofa_minio` are only on
  `77d8a8245370…` (`proof-of-action-final_default`) — there is no route from this run
  to the live datastores

## Probe defects found, classified, corrected (history kept)

Both Stage F failures in the first pass (`stageF-result.txt`: 19/21) were **probe
bugs, not product defects**; neither check was weakened or deleted.

1. `F4 signature/declared-type mismatch` returned 201 instead of the expected 415.
   FOUND: the probe generated a PNG and declared `image/png` — a *consistent* pair,
   so 201 was the correct product behaviour and the probe never tested mismatch.
   FIXED: added `synthetic_jpeg()` and re-declared real JPEG bytes as `image/png`.
   VERIFIED: 415 in both re-runs.
2. `F7 retention evaluate` returned 422 (`resource_type` enum; the body must send
   the uppercase `EVIDENCE`). FIXED. The re-run then returned **403**, which was
   re-measured as correct authorization behaviour rather than a defect:
   `backend/db/models.py` grants `retention.read` to the supervisory role set and
   `ADMINISTRATOR`, not to `FIELD_OFFICER`. Split into an explicit 403 boundary
   check plus a positive 200 dry-run with an `ADMINISTRATOR` principal.
   VERIFIED: `stageF-result-rerun2.txt` 26/26.

## Findings carried to Stage J (report, not fixed)

- **BE-037B-D2 (already recorded at Stage E)** — no supported bootstrap for the
  authorization catalogue: a freshly migrated database has `roles=0,
  permissions=0`, so role assignment 404s until something calls
  `ensure_default_catalogue`. Stage F had to seed it through the app service to
  obtain any authorized principal.
- **Minor contract inconsistency (new, low severity)** — `POST /api/v1/evidence`
  responds `status: "uploaded"` while the persisted and re-read row status is
  `uploaded_quarantine` (`backend/api/v1/endpoints/evidence.py:36` hard-codes the
  response field). Clients that trust the response field see a state that no
  stored row ever has. Reported; not changed.
- `PATCH /evidence/{id}/location` (BE-020 coordinate-context) was reachable and
  correct for a `FIELD_OFFICER` principal, so the `evidence.update_context`
  permission path is live in the container image.
