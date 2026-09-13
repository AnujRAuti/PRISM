# Object Storage Foundation

The backend uses one `StorageService` abstraction backed by an S3-compatible client:

```text
Application -> StorageService -> MinIO locally / Amazon S3 in production
```

## Local setup

From the repository root:

```bash
docker compose up -d
```

The Compose stack starts PostgreSQL and MinIO. An idempotent initialization container creates the private buckets:

- `pofa-quarantine`
- `pofa-evidence`

MinIO's API is available on `localhost:9000` and its console on `localhost:9001`. The persistent `minio_data` volume keeps objects across container restarts.

## Configuration

Set these variables in the untracked `.env` file. `.env.example` contains safe local placeholders:

```text
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_REGION=us-east-1
S3_USE_SSL=false
S3_QUARANTINE_BUCKET=pofa-quarantine
S3_EVIDENCE_BUCKET=pofa-evidence
MAX_UPLOAD_SIZE=10485760
```

For production, point `S3_ENDPOINT` and credentials at the selected S3-compatible provider and set `S3_USE_SSL=true`.

## Object keys

The service generates keys from trusted evidence identifiers:

```text
quarantine/{evidence_id}/original
evidence/{evidence_id}/original
evidence/{evidence_id}/derived/{artifact}
```

The storage layer provides presigned upload and download URLs, object existence and metadata checks, server-side copy/promotion, and deletion. It keeps buckets private and does not implement upload validation or evidence processing.

## Evidence upload

`POST /api/v1/evidence` accepts a multipart form field named `file`. The endpoint supports JPEG, PNG, and WebP images up to `MAX_UPLOAD_SIZE` bytes (10 MiB by default). It verifies that the content is a readable image, stores the original in `pofa-quarantine` under `quarantine/{evidence_id}/original`, and creates an `uploaded_quarantine` Evidence record.

The response contains the generated `evidence_id`, the `uploaded` response status, the quarantine `storage_key`, the validated `content_type`, and the byte `size`. Client filenames are retained only as metadata and never control object keys.

## Evidence fingerprints

BE-004 processes the original quarantine object bytes and persists three independent signals:

- `Evidence.sha256` stores the complete lowercase SHA-256 digest for exact byte identity.
- `Evidence.phash` stores the deterministic perceptual hash for visual comparison foundations.
- `EvidenceMetadata.metadata` stores extracted EXIF values and an explicit EXIF status. Images without EXIF use `no_metadata`; they are not treated as invalid.

Fingerprinting does not alter the original object, make duplicate or fraud decisions, validate GPS or timestamps, or start background jobs.

## Asynchronous analysis jobs

BE-005 adds Redis-backed asynchronous execution for the existing BE-004 fingerprinting operation. Start the local infrastructure with `docker compose up -d`, then run the worker with:

```text
python -m backend.workers.analysis_worker
```

Create a job with `POST /api/v1/analysis/jobs` and a JSON body containing `evidence_id`. Retrieve its PostgreSQL-backed state with `GET /api/v1/analysis/jobs/{job_id}`. Jobs move through `queued`, `running`, `completed`, or `failed`; processing retries up to `ANALYSIS_MAX_ATTEMPTS` (3 by default). Redis carries only the job ID, while PostgreSQL remains authoritative for state and results.

The worker invokes the existing BE-004 fingerprinting service and persists the real SHA-256, pHash, and EXIF status in `AnalysisResult`. It does not perform duplicate, fraud, risk, or other later-milestone analysis.

## Duplicate intelligence

BE-006 preserves duplicate signals independently. Exact candidates use equality of persisted SHA-256 values; perceptual candidates use the Hamming distance between persisted pHash values and `PHASH_MAX_HAMMING_DISTANCE` (8 by default). Candidate pairs are stored symmetrically and idempotently in `duplicate_matches` with signal provenance.

The embedding schema is PostgreSQL `VECTOR(512)` and the configured real model is `openai/clip-vit-base-patch32`, with normalized cosine-compatible vectors. Embedding generation is explicit: when a compatible `torch` and `transformers` runtime is installed, the worker computes and persists the real image embedding; otherwise the result records `embedding_status=unavailable` and no vector or semantic similarity is claimed. No fabricated vectors or scores are used.