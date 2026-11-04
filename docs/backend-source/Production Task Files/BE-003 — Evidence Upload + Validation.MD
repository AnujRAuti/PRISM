# BE-003 — Evidence Upload + Validation

## Objective

Implement the actual Evidence Upload API on top of the completed BE-001 database foundation and BE-002 object-storage layer.

The API must accept a real multipart file upload, validate it, create an evidence database record, and store the original file in the MinIO quarantine bucket.

The upload must represent a real stored file and a real database record. Do not return fake/demo success responses.

---

# Baseline Gate

Before making changes:

1. Inspect the current repository and branch.
2. Verify BE-001 database functionality still works.
3. Verify BE-002 `StorageService` is the existing storage abstraction.
4. Inspect the existing Evidence ORM model/table and existing API/schema structure before creating anything new.
5. Reuse existing abstractions where possible.

If a previous milestone has a blocker that prevents BE-003 from working:

- Fix only the blocker necessary for BE-003.
- Do NOT rewrite or redesign BE-001/BE-002.
- Do NOT perform unrelated cleanup.

Do not implement future milestones.

---

# Scope

BE-003 includes ONLY:

1. Evidence upload endpoint
2. Multipart/form-data handling
3. Upload validation
4. Evidence database record creation
5. Storage into the quarantine bucket
6. Basic upload response
7. Integration tests

Pipeline for this milestone:

Client
↓
Evidence Upload API
↓
Validation
↓
Evidence DB record
↓
StorageService
↓
`pofa-quarantine`

---

# Explicitly OUT OF SCOPE

Do NOT implement any of the following:

- SHA-256 hashing
- EXIF extraction
- pHash
- image embeddings
- CLIP/SigLIP
- duplicate detection
- SIFT/ORB
- Redis
- Celery
- Dramatiq
- background workers
- vision analysis
- object detection
- geo analysis
- GPS validation
- temporal analysis
- claims
- evidence graph
- cross-project intelligence
- corroboration
- fusion engine
- integrity score
- risk score
- explainability
- human review
- authentication
- authorization/RBAC
- frontend
- notifications
- ML
- blockchain
- C2PA
- external AI APIs

Those belong to later milestones.

---

# 1. Inspect Existing Architecture

Before implementation inspect:

- `backend/api/`
- `backend/app/`
- `backend/core/`
- `backend/db/`
- `backend/repositories/`
- `backend/schemas/`
- `backend/services/`
- existing Evidence model
- existing API router registration
- existing database session/dependency pattern
- existing error-handling conventions
- existing `StorageService`
- existing tests

Do not create duplicate database/session/storage abstractions.

---

# 2. Upload Endpoint

Create an endpoint under:

`/api/v1/evidence`

Use multipart/form-data.

Preferred endpoint:

`POST /api/v1/evidence`

Request:

- multipart file field: `file`

The server must generate the Evidence ID.

Do not allow the client to choose the storage object key.

---

# 3. File Validation

Validate the uploaded file before accepting it.

At minimum:

### Empty file

Reject files with:

`size == 0`

Return an appropriate HTTP 4xx response.

### File size

Implement a configurable maximum upload size.

Do not hard-code the limit inside the route if the project configuration system can reasonably support it.

The default should be conservative for development and clearly documented.

### Content type

Initially support image evidence only.

Allowed MIME types:

- `image/jpeg`
- `image/png`
- `image/webp`

Reject unsupported MIME types.

Do not trust only the filename extension.

Where practical, verify that the uploaded content is actually a readable image using the existing image-processing dependency.

The validation must prevent a text file renamed to `.jpg` from being accepted as valid image evidence.

### Filename

Treat the original filename as untrusted input.

Never use the client filename directly as the storage object key.

Do not allow path traversal such as:

`../../file.jpg`

---

# 4. Evidence ID

Generate a new UUID server-side for every accepted upload.

Example:

`evidence_id = UUID(...)`

The generated ID must be used consistently for:

- database record
- quarantine object key
- API response

Do not use filenames as identifiers.

---

# 5. Quarantine Storage

Use the existing `StorageService` from BE-002.

Do NOT implement raw boto3/S3 logic inside the API route.

The uploaded original must be stored in:

`pofa-quarantine`

Use the existing storage key convention:

`quarantine/{evidence_id}/original`

Example:

`quarantine/550e8400-e29b-41d4-a716-446655440000/original`

The object must actually exist in MinIO after a successful request.

Do not store uploads directly in the trusted evidence bucket.

---

# 6. Database Record

Use the existing Evidence ORM model/table.

Do not redesign the Evidence schema unless a genuine blocker exists.

Create a database record representing the uploaded evidence.

Populate only fields that are appropriate for BE-003, such as:

- evidence ID
- lifecycle/status
- storage reference/object key
- original filename if supported
- content type
- file size
- timestamps
- project/activity references only if the existing schema requires them

Do NOT populate future analysis fields with fake values.

Especially do not create fake:

- hash
- EXIF
- pHash
- embedding
- GPS
- confidence
- risk
- integrity
- vision results

Those must remain unavailable/unprocessed until their respective milestones.

Use the existing database/session/repository pattern if one already exists.

---

# 7. Evidence Lifecycle Status

Inspect the existing Evidence model before deciding the exact status value.

Use the existing lifecycle/status convention if available.

The uploaded evidence should clearly represent:

"uploaded and stored in quarantine, not yet analyzed"

Do not invent a second status system.

If the existing schema does not have a suitable status, add the smallest possible change required for BE-003.

Do not redesign the lifecycle model.

---

# 8. Transaction / Failure Handling

The upload operation involves:

1. receiving file
2. validating file
3. storing object
4. creating database record

Avoid leaving inconsistent state.

At minimum:

- If validation fails → no object and no evidence record.
- If storage fails → do not report successful upload.
- If database creation fails after storage succeeds → attempt to remove the newly-created quarantine object.
- Never return success unless both storage and database persistence succeeded.

Use the existing application's error-handling conventions.

Do not silently swallow storage or database errors.

---

# 9. API Response

Return a concise JSON response containing enough information for the client to identify the uploaded evidence.

Example structure:

```json
{
  "evidence_id": "uuid",
  "status": "uploaded",
  "storage_key": "quarantine/<uuid>/original",
  "content_type": "image/jpeg",
  "size": 123456
}