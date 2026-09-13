# Proof-of-Action
## Evidence Integrity & Intelligence Layer (EIIL)
### Backend Engineering TODO

> **Purpose:** Build a production-grade backend that ingests field evidence, analyzes its integrity across multiple independent signals, correlates evidence across projects/time/location, produces explainable integrity and risk scores, and routes suspicious evidence to human reviewers.

---

# 0. CORE ENGINEERING RULES

These rules apply to the entire backend.

- [ ] **Never generate fake analysis results.**
- [ ] Never hardcode fake similarity percentages.
- [ ] Never claim an AI model analyzed an image unless it actually did.
- [ ] Never claim GPS verification unless GPS was actually extracted and checked.
- [ ] Never claim duplicate detection unless an actual comparison occurred.
- [ ] Never treat EXIF as proof of authenticity.
- [ ] Never treat one signal as proof of fraud.
- [ ] Keep **Integrity** and **Risk** as separate concepts.
- [ ] Every analysis must be reproducible.
- [ ] Every analysis must have a `model_version`.
- [ ] Every rule-based analysis must have a `rule_version`.
- [ ] Every reviewer override must be audited.
- [ ] Every important state change must be auditable.
- [ ] AI recommendations must never silently replace human decisions.
- [ ] The backend must remain usable without the frontend.
- [ ] API contracts must be defined before frontend integration.
- [ ] All services must be containerizable.
- [ ] All important functionality must have tests.
- [ ] Production secrets must never be committed.
- [ ] Do not introduce infrastructure before it solves a real backend requirement.

---

# 1. DEFINE THE BACKEND CONTRACT

Before writing analysis code, define exactly what the backend is responsible for.

## 1.1 Define the system boundary

- [DONE] Write `docs/backend-scope.md`.
- [DONE] Document what PoA does.
- [DONE] Document what PoA does NOT do.

### PoA DOES

- [ ] Ingest evidence.
- [ ] Validate evidence.
- [ ] Preserve evidence integrity.
- [ ] Extract metadata.
- [ ] Calculate cryptographic hashes.
- [ ] Calculate perceptual hashes.
- [ ] Generate embeddings.
- [ ] Analyze GPS consistency.
- [ ] Analyze temporal consistency.
- [ ] Detect duplicate/near-duplicate evidence.
- [ ] Analyze visual/claim consistency.
- [ ] Correlate evidence across projects.
- [ ] Generate explainable scores.
- [ ] Detect anomalies.
- [ ] Create reviewer queues.
- [ ] Maintain a complete audit trail.

### PoA DOES NOT

- [ ] Claim that AI can universally determine whether a photo is genuine.
- [ ] Replace government scheme systems.
- [ ] Automatically declare fraud from a single anomaly.
- [ ] Treat missing EXIF as fraud.
- [ ] Treat image manipulation as automatic proof of fraud.
- [ ] Make irreversible government decisions without authorized human workflow.

---

# 2. CREATE THE NEW REPOSITORY

## 2.1 Repository

- [DONE] Create new GitHub repository.
- [DONE] Name the repository appropriately.
- [DONE] Initialize with README.
- [DONE] Add `.gitignore`.
- [DONE] Add `.env.example`.
- [DONE] Add `LICENSE` if required.

## 2.2 Branches

Create:

```text
main
backend
frontend
```

- [DONE] `main` = stable integration branch.
- [DONE] `backend` = backend development.
- [DONE] `frontend` = future frontend development.
- [ ] Do all backend work on `backend`.
- [ ] Do not build frontend until backend API contracts are stable.

## 2.3 Initial structure

Create:

```text
proof-of-action/
│
├── backend/
│
├── frontend/
│
├── docs/
│
├── README.md
├── TODO.md
├── .gitignore
└── docker-compose.yml
```

---

# 3. BACKEND PROJECT STRUCTURE

Inside `backend/`:

```text
backend/
│
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── router.py
│   │       └── endpoints/
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── logging.py
│   │   └── errors.py
│   │
│   ├── db/
│   │   ├── session.py
│   │   ├── models/
│   │   └── migrations/
│   │
│   ├── schemas/
│   │
│   ├── services/
│   │
│   ├── engines/
│   │   ├── metadata/
│   │   ├── hashing/
│   │   ├── duplicate/
│   │   ├── embeddings/
│   │   ├── geo/
│   │   ├── temporal/
│   │   ├── vision/
│   │   ├── claims/
│   │   ├── fusion/
│   │   └── explainability/
│   │
│   ├── workers/
│   │
│   └── repositories/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── scripts/
│
├── Dockerfile
├── requirements.txt
└── .env.example
```

- [DONE] Create all directories.
- [DONE] Add `__init__.py` where required.
- [ ] Keep API logic separate from analysis engines.
- [ ] Keep database access separate from business logic.

---

# 4. SET UP PYTHON ENVIRONMENT

## 4.1 Python

- [ ] Install supported Python version.
- [DONE] Create virtual environment.
- [DONE] Activate environment.
- [DONE] Upgrade pip.

## 4.2 Initial dependencies

Install:

```text
fastapi
uvicorn
pydantic
pydantic-settings

sqlalchemy
alembic
psycopg

redis

boto3
minio

python-multipart

opencv-python
Pillow
imagehash
numpy

exifread
```

Later:

```text
pgvector
torch
transformers
scikit-learn
xgboost
```

Do not install every ML dependency immediately.

---

# 5. DOCKER DEVELOPMENT ENVIRONMENT

Create a development environment containing:

```text
FastAPI
PostgreSQL
Redis
MinIO
```

PostgreSQL must support:

- [ ] PostGIS.
- [ ] pgvector.

## 5.1 Docker Compose

Create:

```text
docker-compose.yml
```

Services:

```text
api
postgres
redis
minio
```

- [ ] PostgreSQL persists data through a volume.
- [ ] MinIO persists objects through a volume.
- [ ] Redis persists/configures appropriately for development.
- [ ] API connects to all services through Docker networking.

## 5.2 Verify

- [ ] PostgreSQL starts.
- [ ] PostGIS works.
- [ ] pgvector works.
- [ ] Redis responds.
- [ ] MinIO starts.
- [ ] FastAPI starts.

---

# 6. FASTAPI FOUNDATION

Create:

```text
app/main.py
```

Implement:

- [ ] FastAPI application.
- [ ] API versioning.
- [ ] `/health`.
- [ ] `/ready`.
- [ ] Global exception handling.
- [ ] Request ID generation.
- [ ] Structured logging.
- [ ] CORS configuration.
- [ ] Environment-based configuration.

Example:

```text
GET /health
GET /ready
```

Expected:

```json
{
  "status": "ok"
}
```

## Definition of done

- [ ] API starts locally.
- [ ] API starts through Docker.
- [ ] Swagger/OpenAPI works.
- [ ] Health endpoint works.
- [ ] Database readiness can be checked.

---

# 7. CONFIGURATION & SECRETS

Create:

```text
.env
.env.example
```

Variables should include:

```text
DATABASE_URL=
REDIS_URL=

S3_ENDPOINT=
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_BUCKET=

JWT_SECRET=
```

Later:

```text
MODEL_STORAGE=
C2PA_CONFIG=
EXTERNAL_DETECTOR_URL=
```

- [ ] `.env` is ignored by Git.
- [ ] `.env.example` contains placeholders only.
- [ ] No secrets in source code.
- [ ] Configuration loaded through Pydantic Settings.

---

# 8. DATABASE FOUNDATION

Use:

```text
PostgreSQL
SQLAlchemy
Alembic
PostGIS
pgvector
```

## 8.1 Create database models

Start with:

```text
User
Project
Activity
Claim
Evidence
EvidenceMetadata
Analysis
Anomaly
DuplicateMatch
Embedding
ReviewDecision
AuditEvent
```

Later:

```text
EvidenceRelation
FieldInspection
Webhook
APIKey
AnalysisJob
```

---

# 9. DESIGN THE EVIDENCE DATA MODEL

Evidence is the central object.

Minimum conceptual structure:

```text
Evidence
│
├── identity
├── storage
├── cryptographic fingerprints
├── metadata
├── capture information
├── location
├── temporal information
├── analysis state
├── integrity
├── risk
└── provenance
```

Implement fields for:

- [ ] `id`
- [ ] `project_id`
- [ ] `activity_id`
- [ ] `claim_id`
- [ ] `uploaded_by`
- [ ] `object_key`
- [ ] `mime_type`
- [ ] `size_bytes`
- [ ] `sha256`
- [ ] `phash`
- [ ] `captured_at`
- [ ] `latitude`
- [ ] `longitude`
- [ ] `gps_accuracy`
- [ ] `status`
- [ ] `stage`
- [ ] `integrity_score`
- [ ] `risk_score`
- [ ] `model_version`
- [ ] `rule_version`
- [ ] timestamps

Do NOT put every EXIF field directly into Evidence.

Use:

```text
EvidenceMetadata
```

---

# 10. DATABASE MIGRATIONS

- [ ] Initialize Alembic.
- [ ] Create initial migration.
- [ ] Apply migration.
- [ ] Verify tables.
- [ ] Verify indexes.
- [ ] Verify PostGIS geometry support.
- [ ] Verify vector column support.

Create indexes for:

- [ ] SHA-256.
- [ ] project ID.
- [ ] activity ID.
- [ ] capture time.
- [ ] status.
- [ ] risk level.
- [ ] GPS/location.
- [ ] vector embeddings.

---

# 11. OBJECT STORAGE

Use:

```text
MinIO → development
S3-compatible storage → production
```

Create storage abstraction:

```text
StorageService
```

Methods:

```text
create_upload_url()
upload()
download()
exists()
delete()
get_metadata()
```

## Storage layout

Use something like:

```text
quarantine/{evidence_id}/original
verified/{evidence_id}/original
derived/{evidence_id}/...
```

Never allow unvalidated uploads directly into trusted evidence storage.

---

# 12. EVIDENCE INGESTION PIPELINE

This is the **first major working feature**.

Pipeline:

```text
CLIENT
  ↓
CREATE EVIDENCE
  ↓
PRESIGNED UPLOAD
  ↓
QUARANTINE
  ↓
UPLOAD COMPLETE
  ↓
VALIDATE FILE
  ↓
SHA-256
  ↓
METADATA
  ↓
pHash
  ↓
DATABASE
  ↓
QUEUE ANALYSIS
```

---

# 13. EVIDENCE UPLOAD API

Create:

```http
POST /api/v1/evidence/uploads
```

Request:

```json
{
  "project_id": "...",
  "activity_id": "...",
  "claim_id": "...",
  "filename": "...",
  "mime_type": "...",
  "size_bytes": 12345
}
```

Response:

```json
{
  "evidence_id": "...",
  "upload_url": "...",
  "status": "UPLOAD_PENDING"
}
```

---

# 14. COMPLETE UPLOAD

Create:

```http
POST /api/v1/evidence/{id}/complete
```

This endpoint must:

- [ ] Verify object exists.
- [ ] Verify size.
- [ ] Verify actual file type.
- [ ] Decode image.
- [ ] Reject corrupt image.
- [ ] Calculate SHA-256.
- [ ] Move/mark object as verified.
- [ ] Create metadata record.
- [ ] Queue analysis.
- [ ] Update evidence status.

Return:

```json
{
  "evidence_id": "...",
  "status": "ANALYSIS_QUEUED"
}
```

---

# 15. FILE VALIDATION ENGINE

Build:

```text
engines/validation/
```

Validate:

- [ ] File extension.
- [ ] MIME type.
- [ ] Actual file signature.
- [ ] File size.
- [ ] Image dimensions.
- [ ] Image decodability.
- [ ] Corruption.
- [ ] Unsupported formats.

Never trust:

```text
filename
Content-Type
client metadata
```

as authoritative.

---

# 16. SHA-256 ENGINE

Implement:

```text
calculate_sha256(file)
```

Store:

```text
sha256
```

Use SHA-256 for:

- [ ] Exact duplicate detection.
- [ ] Evidence identity.
- [ ] Integrity verification.
- [ ] Audit references.

Important:

> SHA-256 proves that two byte sequences are identical. It does not prove that the photograph itself is genuine.

---

# 17. METADATA / EXIF ENGINE

Build:

```text
engines/metadata/
```

Extract:

- [ ] Camera make.
- [ ] Camera model.
- [ ] Lens.
- [ ] DateTimeOriginal.
- [ ] CreateDate.
- [ ] ModifyDate.
- [ ] GPS latitude.
- [ ] GPS longitude.
- [ ] GPS altitude.
- [ ] GPS timestamp.
- [ ] Orientation.
- [ ] Dimensions.
- [ ] Software.
- [ ] Color information.

Store normalized values.

Optionally preserve:

```text
raw_exif JSON
```

---

# 18. METADATA ANALYSIS

Do NOT implement:

```text
EXIF missing = fraud
```

Instead detect:

- [ ] Missing metadata.
- [ ] Conflicting timestamps.
- [ ] GPS inconsistencies.
- [ ] Modification software.
- [ ] Impossible metadata combinations.
- [ ] Timestamp anomalies.
- [ ] Metadata mismatch with project information.

Produce:

```json
{
  "metadata_score": 0-100,
  "anomalies": []
}
```

---

# 19. pHASH ENGINE

Implement perceptual hashing.

Pipeline:

```text
IMAGE
 ↓
NORMALIZE
 ↓
GRAYSCALE
 ↓
RESIZE
 ↓
DCT
 ↓
LOW FREQUENCY COMPONENTS
 ↓
BINARY HASH
```

Store:

```text
phash
```

Implement Hamming distance.

Do not call:

```text
distance < X = fraud
```

Instead return similarity evidence.

---

# 20. DUPLICATE ENGINE V1

Implement two levels.

### Level 1 — Exact

```text
SHA-256
```

### Level 2 — Perceptual

```text
pHash
```

Create:

```http
GET /api/v1/evidence/{id}/similar
```

Return:

```json
{
  "matches": [
    {
      "evidence_id": "...",
      "method": "PHASH",
      "distance": 4
    }
  ]
}
```

---

# 21. DUPLICATE ENGINE V2 — EMBEDDINGS

Introduce:

```text
pgvector
```

Generate an image embedding.

Candidate models:

```text
CLIP
SigLIP
```

Benchmark them using your own dataset.

Store:

```text
embedding
model_name
model_version
```

Search:

```text
new evidence
    ↓
vector search
    ↓
candidate evidence
    ↓
similarity
```

---

# 22. DUPLICATE ENGINE V3 — LOCAL FEATURES

Add:

```text
SIFT / ORB
```

Use it only on candidate matches.

Pipeline:

```text
Embedding
    ↓
Candidate retrieval
    ↓
SIFT/ORB
    ↓
Local feature verification
```

This prevents expensive feature matching against every image.

---

# 23. BUILD THE FIRST REAL END-TO-END PIPELINE

At this point, this must work:

```text
UPLOAD IMAGE
    ↓
STORE IMAGE
    ↓
VALIDATE
    ↓
SHA-256
    ↓
EXIF
    ↓
pHash
    ↓
DATABASE
    ↓
DUPLICATE SEARCH
    ↓
JSON RESPONSE
```

Test with:

- [ ] Original image.
- [ ] Same image uploaded twice.
- [ ] Resized image.
- [ ] Compressed image.
- [ ] Cropped image.
- [ ] Different image.
- [ ] Corrupt file.

Do not proceed until this works reliably.

---

# 24. REDIS + BACKGROUND JOBS

Do not run expensive analysis inside the HTTP request.

Architecture:

```text
API
 ↓
Redis Queue
 ↓
Worker
 ↓
Analysis
 ↓
Database
```

Create job types:

```text
VALIDATE_EVIDENCE
EXTRACT_METADATA
CALCULATE_PHASH
GENERATE_EMBEDDING
RUN_GEO_ANALYSIS
RUN_TEMPORAL_ANALYSIS
RUN_VISION_ANALYSIS
RUN_DUPLICATE_ANALYSIS
RUN_FUSION
```

---

# 25. ANALYSIS JOB MODEL

Create:

```text
AnalysisJob
```

Track:

```text
id
evidence_id
job_type
status
attempts
started_at
completed_at
error
worker_version
```

Statuses:

```text
QUEUED
RUNNING
COMPLETED
FAILED
RETRYING
```

---

# 26. ANALYSIS STATE MACHINE

Evidence should move through controlled states.

Example:

```text
UPLOAD_PENDING
      ↓
UPLOADED
      ↓
VALIDATING
      ↓
VALIDATED
      ↓
ANALYZING
      ↓
ANALYSIS_COMPLETE
      ↓
REVIEW_REQUIRED
      ↓
REVIEWED
```

Possible failure state:

```text
ANALYSIS_FAILED
```

- [ ] Prevent invalid state transitions.
- [ ] Record every transition in audit logs.

---

# 27. PROJECT ENGINE

Create APIs:

```http
POST /api/v1/projects
GET /api/v1/projects
GET /api/v1/projects/{id}
PATCH /api/v1/projects/{id}
```

Project should contain:

```text
name
scheme
description
location
geofence
start_date
end_date
status
```

Support PostGIS geometry.

---

# 28. ACTIVITY ENGINE

Create:

```http
POST /api/v1/projects/{id}/activities
GET /api/v1/projects/{id}/activities
```

Activity should contain:

```text
name
type
stage
planned_start
planned_end
status
```

Example:

```text
Road Construction
 ↓
Foundation
 ↓
Base Layer
 ↓
Surface
 ↓
Completion
```

---

# 29. CLAIM ENGINE

Claims represent what evidence is supposed to support.

Example:

```json
{
  "claim": "Solar street lights installed at site",
  "activity": "Installation",
  "stage": "Completion"
}
```

Convert natural language into structured expectations:

```json
{
  "asset": "solar_street_light",
  "activity": "installation",
  "stage": "completion",
  "expected_objects": [
    "pole",
    "solar_panel",
    "light"
  ]
}
```

---

# 30. GEOSPATIAL ENGINE

Use:

```text
PostGIS
```

Implement:

```text
distance_to_project()
inside_geofence()
gps_accuracy_check()
location_consistency()
```

Signals:

- [ ] GPS available.
- [ ] GPS accuracy.
- [ ] Distance from project.
- [ ] Inside geofence.
- [ ] Consistency with other evidence.

Anomalies:

```text
LOCATION_MISMATCH
GPS_MISSING
LOW_GPS_ACCURACY
IMPOSSIBLE_TRAVEL
```

---

# 31. TEMPORAL ENGINE

Compare:

```text
capture time
project timeline
activity timeline
other evidence
```

Detect:

- [ ] Evidence before project start.
- [ ] Evidence after project completion.
- [ ] Impossible activity ordering.
- [ ] Duplicate timestamps.
- [ ] Suspiciously repeated timestamps.
- [ ] Timeline contradictions.

Create:

```text
TemporalSignal
```

with:

```text
score
anomalies
explanation
```

---

# 32. IMPOSSIBLE TRAVEL ENGINE

Compare multiple evidence records.

Example:

```text
Evidence A
10:00
Location A

Evidence B
10:05
Location B
500 km away
```

Detect physically implausible movement.

Do not immediately classify as fraud.

Return:

```json
{
  "anomaly": "IMPOSSIBLE_TRAVEL",
  "severity": "HIGH",
  "explanation": "Evidence locations imply implausible travel time."
}
```

---

# 33. VISION ENGINE V1

Start simple.

Analyze:

- [ ] Image quality.
- [ ] Blur.
- [ ] Exposure.
- [ ] Resolution.
- [ ] Scene classification.

Do NOT immediately build a giant universal model.

---

# 34. VISION ENGINE V2 — OBJECT DETECTION

Introduce object detection only for useful scheme-specific objects.

Potential classes:

```text
road
road marking
bridge
water tank
pipeline
solar panel
street light
building
toilet
pump
```

Only implement classes relevant to your supported use cases.

Output:

```json
{
  "objects": [
    {
      "class": "solar_panel",
      "confidence": 0.91
    }
  ]
}
```

---

# 35. CLAIM ↔ VISION MATCHING

Compare:

```text
CLAIM
   +
VISION
   +
PROJECT CONTEXT
```

Example:

```text
Claim:
Solar street light installation complete.

Vision:
pole = detected
solar panel = detected
light = detected
```

Produce:

```text
claim_match_score
```

This is evidence consistency, not proof of completion.

---

# 36. IMAGE AUTHENTICITY / MANIPULATION SIGNAL

Create an abstraction:

```text
AuthenticityDetector
```

It may contain:

- [ ] Metadata signals.
- [ ] Compression analysis.
- [ ] Image forensic signals.
- [ ] External detector adapter.
- [ ] Future learned model.

Important:

> Manipulation detection is only one signal in PoA.

If using an external detector later:

```text
PoA
 ↓
Detector Adapter
 ↓
External Model/API
 ↓
Normalized Signal
 ↓
Fusion Engine
```

Never make the entire PoA decision depend on one provider.

---

# 37. BUILD THE EVIDENCE GRAPH

This is one of PoA's most important components.

Represent relationships between:

```text
Project
Activity
Claim
Evidence
Location
Time
Similar Evidence
Review
```

Relationships:

```text
BELONGS_TO
SUPPORTS
CONTRADICTS
SIMILAR_TO
DUPLICATE_OF
CAPTURED_AT
CAPTURED_BEFORE
CAPTURED_AFTER
CORROBORATES
DERIVED_FROM
```

Do NOT introduce Neo4j yet.

Use PostgreSQL relationships first.

---

# 38. CROSS-PROJECT CORRELATION

This is where PoA becomes more than a basic photo checker.

Search evidence across:

```text
same project
different project
same geographic region
different geographic region
same time period
historical evidence
```

Example:

```text
New Evidence
     ↓
Embedding similarity
     ↓
Old Evidence
     ↓
Different Project
     ↓
Location mismatch
     ↓
Temporal mismatch
     ↓
Cross-project anomaly
```

Generate:

```text
CROSS_PROJECT_REUSE
```

---

# 39. CORROBORATION ENGINE

Not all similar evidence is suspicious.

Example:

```text
Evidence A → road
Evidence B → same road
Evidence C → same location
```

This can be positive corroboration.

Build relationships that distinguish:

```text
CORROBORATES
```

from:

```text
DUPLICATE_OF
```

This is extremely important.

---

# 40. SIGNAL STANDARDIZATION

Every engine must return a common structure.

Example:

```json
{
  "signal": "GPS_CONSISTENCY",
  "score": 87,
  "confidence": 0.92,
  "status": "PASS",
  "anomalies": [],
  "explanation": "Evidence location is within the project geofence.",
  "engine_version": "geo-v1"
}
```

Standardize:

```text
score
confidence
status
anomalies
explanation
version
```

---

# 41. FUSION ENGINE

Now combine signals.

Initial signals:

```text
GPS
Temporal
Duplicate
Metadata
Authenticity
Visual
Claim
Completeness
```

Example initial weighting:

```text
GPS consistency          15%
Temporal consistency     10%
Duplicate evidence       20%
Metadata integrity       10%
Authenticity             15%
Visual/claim             20%
Completeness             10%
```

These are **starting values**, not scientifically validated weights.

---

# 42. SEPARATE INTEGRITY FROM RISK

Create two outputs.

## Integrity

Question:

> How internally consistent is this evidence?

## Risk

Question:

> How much attention should a reviewer give this evidence?

Example:

```text
Integrity: 82
Risk: 18
```

Another example:

```text
Integrity: 58
Risk: 74
```

The second case requires more investigation.

---

# 43. ANOMALY ENGINE

Create standardized anomaly types.

Examples:

```text
GPS_MISSING
LOCATION_MISMATCH
LOW_GPS_ACCURACY
IMPOSSIBLE_TRAVEL

TIMESTAMP_MISMATCH
TIMELINE_CONTRADICTION

EXACT_DUPLICATE
PERCEPTUAL_DUPLICATE
SEMANTIC_DUPLICATE
CROSS_PROJECT_REUSE

METADATA_INCONSISTENCY
SOFTWARE_METADATA
MISSING_METADATA

LOW_IMAGE_QUALITY
CLAIM_MISMATCH
OBJECT_MISSING

MANIPULATION_SIGNAL
```

Each anomaly should have:

```text
type
severity
source
confidence
explanation
```

---

# 44. SEVERITY SYSTEM

Define:

```text
INFO
LOW
MEDIUM
HIGH
CRITICAL
```

Do not let severity automatically equal fraud.

Example:

```text
Photoshop metadata
=
LOW

Photoshop metadata
+
GPS mismatch
+
cross-project duplicate
=
HIGH
```

Context matters.

---

# 45. EXPLAINABILITY ENGINE

The system must answer:

> Why did PoA flag this evidence?

Generate structured explanations.

Example:

```text
HIGH RISK

Reasons:

1. Evidence is 184 km outside the project geofence.
2. A visually similar image exists in another project.
3. Capture time conflicts with the project timeline.
4. Image metadata indicates editing software.
```

Store explanations as structured data.

---

# 46. ANALYSIS RESULT API

Create:

```http
GET /api/v1/evidence/{id}/analysis
```

Response:

```json
{
  "evidence_id": "...",
  "integrity": {
    "score": 82,
    "confidence": 0.91
  },
  "risk": {
    "score": 71,
    "level": "HIGH"
  },
  "signals": {},
  "anomalies": [],
  "similar_evidence": [],
  "explanations": []
}
```

---

# 47. REVIEW ENGINE

Create reviewer queue:

```http
GET /api/v1/reviews/queue
```

Sort by:

```text
risk
severity
project priority
age
```

Reviewer actions:

```text
APPROVE
REJECT
FLAG
REQUEST_RESUBMISSION
REQUEST_FIELD_INSPECTION
OVERRIDE
```

---

# 48. REVIEW DECISION MODEL

Store:

```text
reviewer_id
evidence_id
decision
reason
previous_status
new_status
timestamp
```

Never overwrite previous decisions.

Create an immutable history.

---

# 49. REVIEWER OVERRIDE

Allow authorized reviewers to override AI/rule recommendations.

Example:

```text
System:
HIGH RISK

Reviewer:
APPROVE

Reason:
"Known camera synchronization issue; field verification confirms location."
```

This becomes valuable future training data.

---

# 50. AUDIT ENGINE

Everything important must generate an audit event.

Track:

```text
UPLOAD
VALIDATION
ANALYSIS_STARTED
ANALYSIS_COMPLETED
ANALYSIS_FAILED
SCORE_GENERATED
REVIEW_OPENED
REVIEW_DECISION
OVERRIDE
DOWNLOAD
STATE_CHANGE
PROJECT_CHANGE
CLAIM_CHANGE
```

Audit record:

```text
actor
action
resource
timestamp
request_id
previous_state
new_state
reason
metadata
```

---

# 51. AUTHENTICATION

Implement:

```text
OAuth2/OIDC
```

or a properly designed JWT authentication layer.

Support:

```text
Access token
Refresh token
Token expiry
Token rotation
Revocation
```

Never store plain passwords.

---

# 52. RBAC

Roles:

```text
CITIZEN
REVIEWER
SUPERVISOR
PROGRAM_ADMIN
AUDITOR
```

Define permissions separately from roles.

Example:

```text
evidence.upload
evidence.read
evidence.analyze

review.read
review.decide
review.override

audit.read

project.create
project.update
```

---

# 53. AUTHORIZATION

Do not only check:

```text
"is logged in?"
```

Check:

```text
"does this user have permission to access this resource?"
```

Prevent:

- [ ] IDOR.
- [ ] Cross-project access.
- [ ] Unauthorized downloads.
- [ ] Unauthorized reviewer actions.
- [ ] Privilege escalation.

---

# 54. API SECURITY

Implement:

- [ ] Rate limiting.
- [ ] Request validation.
- [ ] Size limits.
- [ ] MIME validation.
- [ ] Authentication.
- [ ] Authorization.
- [ ] Secure headers.
- [ ] Error sanitization.
- [ ] Request IDs.
- [ ] Audit logging.

Follow:

```text
OWASP API Security Top 10
OWASP ASVS
```

---

# 55. API VERSIONING

All production APIs should start with:

```text
/api/v1/
```

Example:

```text
/api/v1/evidence
/api/v1/projects
/api/v1/reviews
/api/v1/audit
```

Never casually break existing API contracts.

---

# 56. ERROR SYSTEM

Create standardized errors.

Example:

```json
{
  "error": {
    "code": "EVIDENCE_NOT_FOUND",
    "message": "Evidence does not exist.",
    "request_id": "..."
  }
}
```

Create error codes for:

```text
INVALID_FILE
FILE_TOO_LARGE
UNSUPPORTED_FORMAT
EVIDENCE_NOT_FOUND
PROJECT_NOT_FOUND
UNAUTHORIZED
FORBIDDEN
ANALYSIS_FAILED
STORAGE_ERROR
```

---

# 57. OBSERVABILITY

Implement:

- [ ] Structured logs.
- [ ] Request IDs.
- [ ] Job IDs.
- [ ] Analysis IDs.
- [ ] Error tracking.
- [ ] Worker monitoring.
- [ ] Database monitoring.

Eventually:

```text
OpenTelemetry
Prometheus
Grafana
```

Do not overbuild observability before the core system works.

---

# 58. TESTING — UNIT

Test every engine independently.

## Hashing

- [ ] Same file → same SHA-256.
- [ ] Different file → different SHA-256.

## pHash

- [ ] Same image → very close.
- [ ] Resized image → close.
- [ ] Different image → distant.

## Metadata

- [ ] Valid EXIF.
- [ ] Missing EXIF.
- [ ] Corrupted metadata.

## Geo

- [ ] Inside geofence.
- [ ] Outside geofence.
- [ ] Missing GPS.
- [ ] Low accuracy.

## Temporal

- [ ] Valid timeline.
- [ ] Before project.
- [ ] After completion.
- [ ] Impossible ordering.

---

# 59. TESTING — INTEGRATION

Test:

```text
API
 ↓
Database
 ↓
Storage
 ↓
Redis
 ↓
Worker
 ↓
Analysis
```

Test:

- [ ] Upload.
- [ ] Complete upload.
- [ ] Queue job.
- [ ] Worker execution.
- [ ] Database result.
- [ ] Analysis API.

---

# 60. TESTING — END TO END

Build a complete test:

```text
Upload evidence
 ↓
Validate
 ↓
Hash
 ↓
Metadata
 ↓
pHash
 ↓
Embedding
 ↓
Duplicate search
 ↓
Geo
 ↓
Temporal
 ↓
Vision
 ↓
Fusion
 ↓
Anomaly
 ↓
Review
 ↓
Audit
```

The entire chain must work without frontend intervention.

---

# 61. BUILD A REAL BENCHMARK DATASET

Create:

```text
ml/datasets/
```

Dataset categories:

```text
VALID
EXACT_DUPLICATE
RESIZED_DUPLICATE
COMPRESSED_DUPLICATE
CROPPED_DUPLICATE
EDITED_IMAGE
WRONG_LOCATION
WRONG_TIME
IRRELEVANT_IMAGE
BEFORE_AFTER_INCONSISTENCY
VALID_SIMILAR_SCENE
CROSS_PROJECT_REUSE
```

Do not use synthetic fake scores as evaluation.

---

# 62. EVALUATE DUPLICATE DETECTION

Measure:

```text
Precision
Recall
F1
False Positive Rate
False Negative Rate
```

Compare:

```text
SHA-256
pHash
Embedding
SIFT/ORB
Combined approach
```

Find appropriate thresholds using real data.

---

# 63. CALIBRATE THE FUSION ENGINE

Do not assume the initial weights are correct.

Collect:

```text
signal outputs
+
reviewer decisions
```

Analyze:

```text
Which signals are useful?
Which produce false positives?
Which anomalies matter?
```

Then adjust:

```text
weights
thresholds
severity
confidence
```

Version everything.

---

# 64. MODEL VERSIONING

Every AI result must contain:

```text
model_name
model_version
input_version
timestamp
```

Example:

```text
vision-model-v1.2
embedding-model-v1
fusion-rules-v3
```

Never silently replace a model.

---

# 65. ML — ONLY AFTER LABELS EXIST

Do NOT start by training:

```text
"fraud detector"
```

Instead first collect:

```text
reviewer decisions
```

Then build a model for:

> Review priority prediction.

Features can include:

```text
GPS score
Temporal score
Metadata score
pHash distance
Embedding similarity
Duplicate count
Claim score
Vision score
Distance from project
Software metadata
Anomaly count
```

Start with:

```text
XGBoost
LightGBM
Scikit-learn
```

before deep learning.

---

# 66. REVIEW PRIORITY MODEL

Goal:

```text
Which evidence should a human inspect first?
```

Output:

```text
review_priority
```

This is safer and easier to validate than claiming:

```text
fraud_probability
```

---

# 67. EVIDENCE GRAPH API

Create APIs such as:

```http
GET /api/v1/evidence/{id}/graph
GET /api/v1/projects/{id}/evidence
GET /api/v1/evidence/{id}/relationships
```

Return:

```text
Evidence
 ├── Project
 ├── Activity
 ├── Claim
 ├── Similar Evidence
 ├── Duplicate Evidence
 ├── Location
 ├── Timeline
 ├── Anomalies
 └── Reviews
```

---

# 68. SEARCH API

Create:

```http
GET /api/v1/evidence/search
```

Support filters:

```text
project
activity
date
risk
integrity
anomaly
location
status
review status
```

Later:

```text
semantic similarity
```

---

# 69. PAGINATION

Every large collection endpoint must support pagination.

Example:

```text
?page=1&page_size=50
```

or cursor pagination where appropriate.

Do not return thousands of records by default.

---

# 70. WEBHOOKS

Later implement:

```text
analysis.completed
analysis.failed
review.required
evidence.flagged
```

This allows government systems to integrate PoA without tightly coupling to the frontend.

---

# 71. API DOCUMENTATION

Maintain:

```text
docs/api/
```

Document:

- [ ] Authentication.
- [ ] Evidence upload.
- [ ] Evidence analysis.
- [ ] Projects.
- [ ] Activities.
- [ ] Claims.
- [ ] Reviews.
- [ ] Audit.
- [ ] Search.
- [ ] Webhooks.

OpenAPI must remain accurate.

---

# 72. SDK / INTEGRATION LAYER

After API stabilization, consider:

```text
Python SDK
TypeScript SDK
```

The objective is:

```text
Government System
        ↓
      PoA API
        ↓
Evidence Intelligence
```

PoA should remain API-first.

---

# 73. SECURITY HARDENING

Perform:

- [ ] Dependency audit.
- [ ] Secret scan.
- [ ] Container scan.
- [ ] API penetration testing.
- [ ] Authentication testing.
- [ ] Authorization testing.
- [ ] File upload abuse testing.
- [ ] Malformed image testing.
- [ ] Rate-limit testing.
- [ ] SQL injection testing.
- [ ] Path traversal testing.
- [ ] Object storage access testing.

---

# 74. FILE SECURITY

Specifically test:

```text
malformed JPEG
malicious filename
oversized image
decompression bomb
invalid MIME
fake extension
corrupted EXIF
polyglot file
```

Use safe image processing practices.

Never execute uploaded files.

---

# 75. DATA RETENTION

Define:

```text
evidence retention
audit retention
analysis retention
derived image retention
```

Document:

```text
Who can delete?
When can evidence be deleted?
Is audit history immutable?
What happens to derived artifacts?
```

---

# 76. BACKUP & RECOVERY

Implement:

- [ ] PostgreSQL backup.
- [ ] Object storage backup strategy.
- [ ] Database restore test.
- [ ] Disaster recovery documentation.
- [ ] Migration rollback strategy.

A backup that has never been restored is not proven reliable.

---

# 77. PERFORMANCE TESTING

Benchmark:

```text
upload throughput
analysis latency
database query latency
embedding search latency
duplicate search latency
queue throughput
```

Identify:

```text
P50
P95
P99
```

Do not optimize prematurely.

---

# 78. SCALE TESTING

Test:

```text
10 evidence
100 evidence
1,000 evidence
10,000 evidence
100,000 evidence
```

Find bottlenecks in:

```text
storage
database
embedding search
workers
duplicate detection
```

---

# 79. WORKER SCALING

Workers should be independently scalable.

Example:

```text
API workers
     × N

Analysis workers
     × N

Embedding workers
     × N

Vision workers
     × N
```

Do not force everything into one process.

---

# 80. CACHING

Only after measuring performance:

- [ ] Cache project information.
- [ ] Cache frequently requested analysis.
- [ ] Cache expensive similarity searches where appropriate.

Never cache mutable security decisions incorrectly.

---

# 81. PROVENANCE — FUTURE

Research and eventually implement:

```text
C2PA
```

Long-term pipeline:

```text
Secure Capture
      ↓
C2PA Provenance
      ↓
Evidence
      ↓
SHA-256
      ↓
EXIF
      ↓
PoA Analysis
```

C2PA should provide provenance information.

PoA should interpret provenance alongside other signals.

---

# 82. SECURE CAPTURE — FUTURE

Potential mobile capture system:

```text
Camera
 ↓
GPS
 ↓
Timestamp
 ↓
Device integrity
 ↓
Secure signing
 ↓
C2PA
 ↓
Upload
```

Features:

- [ ] Offline capture.
- [ ] GPS.
- [ ] Timestamp.
- [ ] Device identity.
- [ ] Secure signing.
- [ ] Upload queue.

This should come after the post-capture intelligence platform works.

---

# 83. EXTERNAL DETECTOR ADAPTERS

Create a generic interface:

```text
AuthenticityDetector
```

Possible implementations:

```text
InternalDetector
ExternalDetector
FutureModel
```

The fusion engine receives normalized signals.

This prevents vendor lock-in.

---

# 84. PRODUCTION DEPLOYMENT

Prepare:

```text
Docker images
Environment configuration
Secrets management
Database migrations
Object storage
Redis
Worker deployment
API deployment
Monitoring
```

Deployment architecture:

```text
                ┌───────────────┐
                │   API Gateway │
                └───────┬───────┘
                        ↓
                ┌───────────────┐
                │   FastAPI     │
                └───────┬───────┘
                        ↓
              ┌─────────┴─────────┐
              ↓                   ↓
        PostgreSQL             Redis
        PostGIS                Queue
        pgvector                 ↓
              ↑              Workers
              │                  ↓
              └──────────── Analysis
                        ↑
                      MinIO/S3
```

---

# 85. CI/CD

Create GitHub Actions.

Pipeline:

```text
Push
 ↓
Lint
 ↓
Type/static checks
 ↓
Unit tests
 ↓
Integration tests
 ↓
Security scan
 ↓
Build Docker
 ↓
Deploy
```

Require CI to pass before merging.

---

# 86. CODE QUALITY

Use:

```text
Ruff
Black
Pytest
MyPy
```

where appropriate.

Rules:

- [ ] No giant files.
- [ ] No giant functions.
- [ ] No business logic in route handlers.
- [ ] No direct database logic inside API endpoints.
- [ ] No hardcoded secrets.
- [ ] No duplicated analysis code.

---

# 87. API ARCHITECTURE REVIEW

Before frontend development, verify:

```text
POST /api/v1/evidence/uploads
POST /api/v1/evidence/{id}/complete
GET  /api/v1/evidence/{id}
POST /api/v1/evidence/{id}/analyze
GET  /api/v1/evidence/{id}/analysis
GET  /api/v1/evidence/{id}/similar
GET  /api/v1/evidence/{id}/anomalies

POST /api/v1/projects
GET  /api/v1/projects
GET  /api/v1/projects/{id}

GET  /api/v1/reviews/queue
POST /api/v1/reviews/{id}/decision

GET  /api/v1/evidence/{id}/graph
GET  /api/v1/audit/events
```

- [ ] All endpoints documented.
- [ ] All endpoints authenticated where required.
- [ ] Authorization verified.
- [ ] Responses standardized.
- [ ] Errors standardized.
- [ ] Pagination implemented.
- [ ] OpenAPI validated.

---

# 88. FRONTEND HANDOFF CONTRACT

Before touching the frontend:

- [ ] Backend can create project.
- [ ] Backend can create activity.
- [ ] Backend can upload evidence.
- [ ] Backend can analyze evidence.
- [ ] Backend returns real signals.
- [ ] Backend returns real anomalies.
- [ ] Backend returns real similarity matches.
- [ ] Backend returns integrity.
- [ ] Backend returns risk.
- [ ] Backend returns explanations.
- [ ] Backend supports reviewer decisions.
- [ ] Backend records audit events.

The frontend should simply consume this.

---

# 89. FINAL BACKEND DEMO FLOW

The complete SIH demonstration should work like this:

```text
1. Create Project
       ↓
2. Create Activity
       ↓
3. Create Claim
       ↓
4. Upload Evidence
       ↓
5. Evidence enters quarantine
       ↓
6. File validation
       ↓
7. SHA-256
       ↓
8. EXIF extraction
       ↓
9. pHash
       ↓
10. Embedding
       ↓
11. GPS analysis
       ↓
12. Temporal analysis
       ↓
13. Vision analysis
       ↓
14. Duplicate search
       ↓
15. Cross-project search
       ↓
16. Claim matching
       ↓
17. Evidence graph
       ↓
18. Fusion engine
       ↓
19. Integrity score
       +
20. Risk score
       ↓
21. Anomalies
       ↓
22. Explainability
       ↓
23. Reviewer queue
       ↓
24. Human decision
       ↓
25. Audit event
```

---

# 90. DEFINITION OF PRODUCTION-READY

The backend is NOT production-ready until:

## Infrastructure

- [ ] PostgreSQL production deployment.
- [ ] PostGIS working.
- [ ] pgvector working.
- [ ] Redis production deployment.
- [ ] S3-compatible object storage.
- [ ] Workers independently deployable.
- [ ] Database backups.
- [ ] Monitoring.
- [ ] CI/CD.

## Security

- [ ] Authentication.
- [ ] Authorization.
- [ ] RBAC.
- [ ] Rate limiting.
- [ ] Secure uploads.
- [ ] Secrets management.
- [ ] Audit logs.
- [ ] Security testing.

## Evidence

- [ ] File validation.
- [ ] SHA-256.
- [ ] EXIF.
- [ ] pHash.
- [ ] Embeddings.
- [ ] Duplicate detection.
- [ ] GPS.
- [ ] Temporal.
- [ ] Vision.
- [ ] Claim matching.

## Intelligence

- [ ] Evidence Graph.
- [ ] Cross-project correlation.
- [ ] Multi-signal fusion.
- [ ] Integrity score.
- [ ] Risk score.
- [ ] Anomaly detection.
- [ ] Explainability.

## Human workflow

- [ ] Reviewer queue.
- [ ] Review decisions.
- [ ] Overrides.
- [ ] Field inspection workflow.
- [ ] Audit history.

## Quality

- [ ] Unit tests.
- [ ] Integration tests.
- [ ] End-to-end tests.
- [ ] Benchmark dataset.
- [ ] Performance testing.
- [ ] False-positive analysis.
- [ ] Model/rule versioning.

---

# 91. THE ACTUAL BUILD ORDER

Do NOT randomly pick tasks from above.

Follow this order:

```text
PHASE 1
Repository
 ↓
Python
 ↓
FastAPI
 ↓
Docker
 ↓
PostgreSQL
 ↓
Redis
 ↓
MinIO

PHASE 2
Database
 ↓
SQLAlchemy
 ↓
Alembic
 ↓
PostGIS
 ↓
pgvector

PHASE 3
Evidence
 ↓
Upload
 ↓
Quarantine
 ↓
Validation
 ↓
SHA-256
 ↓
EXIF
 ↓
pHash

PHASE 4
Workers
 ↓
Redis Queue
 ↓
Analysis Jobs
 ↓
Async Pipeline

PHASE 5
Duplicate Intelligence
 ↓
pHash search
 ↓
Embeddings
 ↓
pgvector
 ↓
SIFT/ORB candidate verification

PHASE 6
Project
 ↓
Activity
 ↓
Claim
 ↓
Geo
 ↓
Temporal

PHASE 7
Vision
 ↓
Image Quality
 ↓
Object Detection
 ↓
Claim Matching

PHASE 8
Evidence Graph
 ↓
Cross-project correlation
 ↓
Corroboration
 ↓
Duplicate relationships

PHASE 9
Fusion
 ↓
Integrity
 ↓
Risk
 ↓
Anomalies
 ↓
Explainability

PHASE 10
Human Review
 ↓
Reviewer Queue
 ↓
Decision
 ↓
Override
 ↓
Audit

PHASE 11
Security
 ↓
Auth
 ↓
RBAC
 ↓
Rate limiting
 ↓
Upload security
 ↓
Audit

PHASE 12
Testing
 ↓
Unit
 ↓
Integration
 ↓
E2E
 ↓
Benchmark
 ↓
Performance

PHASE 13
ML
 ↓
Collect reviewer labels
 ↓
Review-priority model
 ↓
Calibration
 ↓
Evaluation

PHASE 14
Production
 ↓
CI/CD
 ↓
Deployment
 ↓
Monitoring
 ↓
Backups
 ↓
Security testing

PHASE 15
Future
 ↓
C2PA
 ↓
Secure Capture
 ↓
Mobile
 ↓
Advanced ML
```

---

# 92. FIRST MILESTONE — DO THIS FIRST

Ignore everything below this milestone until it is complete.

## Milestone 1: Real Evidence Pipeline

### Goal

Make this work:

```text
POST /evidence/uploads
        ↓
Presigned URL
        ↓
MinIO
        ↓
Complete Upload
        ↓
File Validation
        ↓
SHA-256
        ↓
EXIF
        ↓
pHash
        ↓
PostgreSQL
        ↓
JSON
```

### Checklist

- [ ] New repository created.
- [ ] `main`, `backend`, `frontend` branches created.
- [ ] Backend directory created.
- [ ] Python environment created.
- [ ] FastAPI installed.
- [ ] Docker Compose created.
- [ ] PostgreSQL running.
- [ ] PostGIS enabled.
- [ ] pgvector enabled.
- [ ] Redis running.
- [ ] MinIO running.
- [ ] SQLAlchemy connected.
- [ ] Alembic working.
- [ ] Evidence table created.
- [ ] EvidenceMetadata table created.
- [ ] Storage service created.
- [ ] Upload endpoint created.
- [ ] Presigned upload implemented.
- [ ] Upload completion endpoint created.
- [ ] File validation implemented.
- [ ] SHA-256 implemented.
- [ ] EXIF extraction implemented.
- [ ] pHash implemented.
- [ ] Results stored in PostgreSQL.
- [ ] Evidence retrieval endpoint created.
- [ ] Unit tests written.
- [ ] Integration test written.
- [ ] Full pipeline tested using a real image.

### Milestone 1 Definition of Done

You can upload an actual photograph and receive something like:

```json
{
  "evidence_id": "EVD-000001",
  "status": "ANALYSIS_COMPLETE",
  "sha256": "...",
  "phash": "...",
  "metadata": {
    "captured_at": "...",
    "latitude": 18.52,
    "longitude": 73.85,
    "camera_make": "...",
    "camera_model": "..."
  }
}
```

**Every value must come from actual processing.**

---

# 93. SECOND MILESTONE — DUPLICATE INTELLIGENCE

After Milestone 1:

```text
SHA-256
 ↓
pHash
 ↓
Embedding
 ↓
pgvector
 ↓
SIFT/ORB
```

Definition of done:

- [ ] Exact duplicate detected.
- [ ] Resized duplicate detected.
- [ ] Compressed duplicate detected.
- [ ] Similar but legitimate image does not automatically become duplicate.
- [ ] Cross-project matches can be identified.
- [ ] Similarity results are explainable.

---

# 94. THIRD MILESTONE — CONTEXT INTELLIGENCE

Implement:

```text
Project
 ↓
Activity
 ↓
Claim
 ↓
GPS
 ↓
Temporal
 ↓
Vision
```

Definition of done:

- [ ] Evidence can belong to a project.
- [ ] Evidence can support a claim.
- [ ] GPS can be checked.
- [ ] Time can be checked.
- [ ] Visual evidence can be compared with claim expectations.

---

# 95. FOURTH MILESTONE — EVIDENCE INTELLIGENCE

Implement:

```text
Evidence Graph
+
Cross-project correlation
+
Corroboration
+
Anomaly engine
```

Definition of done:

PoA can answer:

> "What other evidence is related to this evidence, and why?"

---

# 96. FIFTH MILESTONE — DECISION INTELLIGENCE

Implement:

```text
Fusion
 ↓
Integrity
+
Risk
 ↓
Explainability
 ↓
Review
```

Definition of done:

PoA can answer:

> "How internally consistent is this evidence?"

and:

> "Why should a human reviewer investigate it?"

---

# 97. SIXTH MILESTONE — PRODUCTION HARDENING

Implement:

```text
Authentication
RBAC
Audit
Testing
Security
Observability
CI/CD
Deployment
Backups
```

Definition of done:

The backend can be deployed independently of the frontend.

---

# 98. SEVENTH MILESTONE — LEARNING SYSTEM

Only after real reviewer data exists:

```text
Reviewer Decisions
       ↓
Dataset
       ↓
Feature Engineering
       ↓
ML Model
       ↓
Review Priority
       ↓
Evaluation
       ↓
Calibration
```

Do not skip directly to automated fraud classification.

---

# 99. FINAL ARCHITECTURE

The final backend should conceptually look like:

```text
                         ┌─────────────────────┐
                         │ Government Systems  │
                         │ / Mobile / Web      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     PoA API         │
                         │      FastAPI        │
                         └──────────┬──────────┘
                                    │
                     ┌──────────────┼──────────────┐
                     ▼              ▼              ▼
                 PostgreSQL       Redis         MinIO/S3
                 PostGIS          Queue         Evidence
                 pgvector                       Storage
                     │              │
                     │              ▼
                     │          Workers
                     │              │
                     ▼              ▼
              ┌─────────────────────────────┐
              │     Evidence Intelligence   │
              │                             │
              │ Metadata                    │
              │ SHA-256                     │
              │ pHash                       │
              │ Embeddings                  │
              │ Duplicate Detection         │
              │ Geospatial                  │
              │ Temporal                    │
              │ Vision                      │
              │ Claim Matching              │
              └──────────────┬──────────────┘
                             ▼
                    ┌──────────────────┐
                    │  Evidence Graph  │
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │  Fusion Engine   │
                    └────────┬─────────┘
                             ▼
                  ┌────────────────────────┐
                  │ Integrity + Risk Score │
                  └────────────┬───────────┘
                               ▼
                       ┌──────────────┐
                       │ Explainability│
                       └───────┬──────┘
                               ▼
                       ┌──────────────┐
                       │ Human Review │
                       └───────┬──────┘
                               ▼
                         ┌────────────┐
                         │ Audit Log  │
                         └────────────┘
```

---

# 100. THE MOST IMPORTANT PRINCIPLE

PoA should ultimately answer:

```text
"What evidence do we have?"
        ↓
"What does each signal say?"
        ↓
"How do those signals relate?"
        ↓
"Do they corroborate or contradict each other?"
        ↓
"What anomalies exist?"
        ↓
"How confident are we?"
        ↓
"How much attention should this receive?"
        ↓
"What should the human reviewer investigate?"
```

Not:

```text
"AI looked at photo → REAL / FAKE"
```

The **Evidence Graph + Multi-Signal Fusion + Cross-Project Correlation + Explainability** is the actual product.

Everything else exists to make that system reliable.