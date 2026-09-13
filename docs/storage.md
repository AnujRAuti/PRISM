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