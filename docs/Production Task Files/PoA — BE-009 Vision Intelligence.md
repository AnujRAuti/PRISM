# BE-009 — Vision Intelligence

## Objective

Implement the first real computer-vision intelligence layer for Proof-of-Action.

The system must analyze uploaded evidence images and extract **real, reproducible visual observations** that can later be consumed by:

- BE-010 — Evidence Graph
- BE-011 — Fusion Engine
- BE-012 — Explainability
- BE-013 — Human Review

BE-009 must **not** make final fraud, authenticity, compliance, or risk decisions.

The vision layer should answer:

> "What can we objectively observe in this image?"

It should NOT answer:

> "Is this evidence fraudulent?"

---

# NON-NEGOTIABLE ENGINEERING INTEGRITY GATE

Do not interpret "make it work" as "make a convincing demo."

Every implemented capability must perform the real underlying operation it claims to perform.

DO NOT use:

- fake AI results
- hardcoded detections
- fabricated confidence scores
- placeholder bounding boxes
- simulated objects
- random results
- mocked model outputs in production code
- fake image classifications
- fabricated evidence observations
- hardcoded risk/fraud decisions

If the model cannot analyze an image:

- fail clearly, or
- return an explicit unavailable/error state.

Never pretend analysis succeeded.

Tests must verify actual behavior and outputs, not merely that a function was called.

Do not weaken validation or correctness to make tests pass.

---

# SCOPE

BE-009 should implement:

1. Vision analysis job execution
2. Real image loading
3. Real object detection
4. Real visual observations
5. Detection persistence
6. Bounding boxes
7. Model metadata/provenance
8. Deterministic result structure
9. Idempotent analysis
10. API access to vision results
11. Failure handling
12. Tests using real image fixtures

Do NOT implement:

- Evidence Graph
- Fusion Engine
- fraud scoring
- risk scoring
- authenticity scoring
- human review workflow
- LLM-based interpretation
- automatic government-scheme compliance decisions
- BE-010 functionality
- BE-011 functionality
- BE-012 functionality
- BE-013 functionality

---

# FIRST: INSPECT THE EXISTING CODEBASE

Before modifying anything:

Inspect:

- BE-001 through BE-008 implementations
- SQLAlchemy models
- existing Evidence model
- AnalysisJob
- AnalysisResult
- worker implementation
- Redis queue abstraction
- storage abstraction
- image/fingerprint services
- API router structure
- Pydantic schemas
- Alembic migrations
- configuration/settings
- existing tests
- fixtures
- `.env.example`

Understand and reuse existing abstractions.

Do NOT create a second storage system, queue system, image-loading system, or job architecture if one already exists.

Do NOT refactor unrelated completed milestones.

---

# 1. VISION MODEL

Use a real object-detection model.

Preferred initial implementation:

## Ultralytics YOLO

Use a small pretrained YOLO model suitable for local development and CPU/GPU execution.

Prefer the smallest practical model initially so the system remains usable on development hardware.

The model must actually perform inference on the supplied image.

Do not manually download model weights into the repository.

Model weights must NOT be committed to Git.

---

# 2. MODEL CONFIGURATION

Add configuration for the vision model.

Example:

```env
VISION_ENABLED=true
VISION_MODEL_NAME=...
VISION_CONFIDENCE_THRESHOLD=0.25
VISION_IOU_THRESHOLD=0.45
VISION_MAX_DETECTIONS=100
```

Use the existing project configuration pattern.

Do not duplicate configuration loading.

Do not expose secrets.

The model name must be configurable.

Do not hardcode model-specific paths throughout the codebase.

---

# 3. VISION SERVICE

Create a dedicated service.

Suggested:

```text
backend/services/vision_intelligence.py
```

The service should be responsible for:

```text
image
 ↓
validation/loading
 ↓
model inference
 ↓
detections
 ↓
normalized observations
 ↓
persisted result
```

Keep model-specific implementation isolated from API endpoints and workers.

The API should not directly call YOLO.

---

# 4. IMAGE INPUT

The vision service must obtain the actual evidence image through the existing storage abstraction.

Do NOT:

- assume local filesystem paths
- duplicate object storage logic
- download arbitrary URLs
- trust user-supplied filesystem paths

Use the existing evidence/storage relationship.

The image analyzed must correspond to the requested `Evidence` record.

---

# 5. OBJECT DETECTION

Run actual object detection.

For each detection capture:

```text
class_id
class_name
confidence
x_min
y_min
x_max
y_max
```

Coordinates must represent the actual bounding box produced by the model.

Do not fabricate coordinates.

Confidence must be the actual model confidence.

---

# 6. NORMALIZED COORDINATES

Persist bounding boxes in a resolution-independent format.

Prefer normalized coordinates:

```text
x_min
y_min
x_max
y_max
```

where values are between:

```text
0.0 and 1.0
```

Example:

```json
{
  "x_min": 0.12,
  "y_min": 0.25,
  "x_max": 0.63,
  "y_max": 0.81
}
```

Ensure:

```text
0 <= x_min < x_max <= 1
0 <= y_min < y_max <= 1
```

Preserve the original image dimensions as metadata.

---

# 7. PERSISTENCE

Inspect the existing database model structure before deciding whether to extend `AnalysisResult` or create a dedicated vision table.

Preferred design:

Create a dedicated table for individual detections rather than putting an unlimited detection array directly into a relational column.

Potential structure:

```text
VisionDetection

id
analysis_result_id
class_id
class_name
confidence
x_min
y_min
x_max
y_max
created_at
```

Use the existing UUID/timestamp conventions.

Foreign keys must be real.

Add appropriate indexes.

At minimum consider:

```text
analysis_result_id
class_name
```

Do not create indexes without understanding the query patterns.

If the existing architecture already has a better representation, reuse it.

---

# 8. VISION ANALYSIS RESULT

The existing `AnalysisResult` should identify that vision analysis was performed.

Do not overload fields intended for fingerprinting.

A vision result should preserve:

```text
analysis type
model name
model version if available
image dimensions
detection count
processing metadata
status
```

Model provenance is important.

Example conceptual structure:

```json
{
  "analysis_type": "vision_detection",
  "model": {
    "name": "...",
    "version": "..."
  },
  "image": {
    "width": 1920,
    "height": 1080
  },
  "detection_count": 4
}
```

Use the project's existing schema conventions.

---

# 9. NO FRAUD SCORE

BE-009 MUST NOT produce:

```text
fraud_score
risk_score
authenticity_score
trust_score
compliance_score
```

Vision observations are signals.

For example:

```text
person detected
vehicle detected
building detected
road detected
```

does NOT mean:

```text
project verified
```

and does NOT mean:

```text
fraud detected
```

Those decisions belong to later milestones.

---

# 10. VISUAL OBSERVATIONS

The system should produce useful raw observations.

For example:

```json
{
  "class_name": "person",
  "confidence": 0.91,
  "bounding_box": {
    "x_min": 0.12,
    "y_min": 0.18,
    "x_max": 0.43,
    "y_max": 0.94
  }
}
```

The exact available classes depend on the actual pretrained model.

Do not invent domain-specific classes that the model was not trained to detect.

---

# 11. DOMAIN CLAIM MATCHING — DO NOT IMPLEMENT YET

Do NOT attempt to determine whether:

> "The image proves a road was constructed."

from generic YOLO detections.

That requires domain-specific semantics and belongs in later intelligence layers.

BE-009 only extracts visual observations.

---

# 12. IMAGE DIMENSIONS

Record:

```text
width
height
```

from the actual analyzed image.

Do not trust client-provided dimensions.

Use the actual image.

---

# 13. MODEL PROVENANCE

Record enough information to reproduce or understand the analysis.

At minimum:

```text
model name
model version/package version where available
confidence threshold
IoU threshold
```

If practical, record the model identifier/checksum used.

Do not store the model weights in PostgreSQL.

Do not commit model weights to Git.

---

# 14. ANALYSIS JOB INTEGRATION

Integrate vision analysis with the existing BE-005 analysis worker.

Do not create another worker system.

Existing architecture:

```text
API
 ↓
Redis
 ↓
Analysis Worker
 ↓
Analysis Services
```

Extend it to support vision analysis.

Do not break fingerprint analysis.

---

# 15. JOB TYPES

Inspect the existing AnalysisJob design.

If analysis type support already exists:

Reuse it.

If not, introduce the minimum required structure for:

```text
fingerprint
vision
```

Do not redesign the entire job system.

A vision job should be identifiable as:

```text
vision
```

or the existing project's equivalent.

---

# 16. IDEMPOTENCY

Repeated vision analysis of the same evidence must not create uncontrolled duplicate results.

Use the existing job/result/idempotency architecture where possible.

The system should behave predictably if:

```text
same evidence
same analysis type
same model/configuration
```

is processed multiple times.

Do not simply delete old results blindly.

Preserve provenance where the architecture requires historical analysis.

---

# 17. FAILURE HANDLING

Vision failures must be real failures.

Examples:

- missing object
- storage read failure
- corrupt image
- unsupported image
- model initialization failure
- inference failure
- invalid image dimensions
- insufficient resources

The job should transition to the appropriate failed state using the existing worker/job semantics.

Do NOT:

```text
except Exception:
    return []
```

Do not convert inference failures into successful empty detections.

---

# 18. PERFORMANCE

Design the first implementation for practical local execution.

Requirements:

- load the model once per worker process where possible
- do not initialize YOLO for every image
- avoid loading the same image multiple times unnecessarily
- avoid unnecessary database queries
- avoid unnecessary storage downloads
- release image resources properly
- avoid storing full image binaries in PostgreSQL
- use inference settings appropriate for the configured hardware

Do not introduce premature distributed inference infrastructure.

---

# 19. CPU/GPU COMPATIBILITY

The implementation must work on CPU.

If CUDA is available, allow the model to use it where appropriate.

Do not make CUDA mandatory.

The service should determine the available execution device using a clean configuration strategy.

Do not hardcode:

```text
cuda
```

as the only device.

---

# 20. API

Add API endpoints only where they fit the existing API architecture.

At minimum provide a way to:

### Start vision analysis

```text
POST /api/v1/analysis/jobs
```

using the existing analysis-job endpoint if it already supports analysis types.

Do NOT create a duplicate endpoint simply for vision.

### Retrieve vision result

Provide an appropriate GET endpoint for retrieving the persisted vision observations.

Follow existing `/api/v1` conventions.

Example concept:

```text
GET /api/v1/evidence/{evidence_id}/vision
```

Only use this exact endpoint if it fits the existing architecture.

Return:

```text
evidence_id
analysis_result
model metadata
image dimensions
detections
```

Do not return fake fields.

---

# 21. PAGINATION

If detections are exposed through an endpoint and the existing API supports pagination:

Use the existing pagination pattern.

Do not load thousands of detections unnecessarily.

Do not introduce a new pagination convention.

---

# 22. SECURITY

Do not allow the vision API to access arbitrary files.

The requested evidence must be resolved through the database and existing storage abstraction.

Validate:

- UUIDs
- evidence existence
- storage object existence
- image type
- authorization boundaries where existing auth permits

Do not introduce BE-015 authentication/RBAC early.

Respect existing project authorization boundaries.

---

# 23. TEST FIXTURES

Create a small set of real image fixtures.

Tests must use actual image files.

Include at least:

1. image containing detectable objects
2. image containing no detectable objects if practical
3. invalid/corrupt image
4. unsupported image where relevant

Do not generate fake YOLO result objects and call that an integration test.

---

# 24. UNIT TESTS

Test:

- normalized bounding box conversion
- coordinate validation
- detection serialization
- configuration validation
- image dimension extraction
- model metadata generation
- empty detection handling
- malformed model output handling where appropriate

---

# 25. INTEGRATION TESTS

At minimum verify:

### Real inference

Given a real fixture image:

```text
Evidence
 ↓
Vision Service
 ↓
Actual YOLO inference
 ↓
Detections
```

Verify that the returned observations correspond to actual model output.

### Persistence

Verify:

```text
VisionDetection
 ↓
PostgreSQL
```

and retrieve the persisted records.

### Bounding boxes

Verify all persisted coordinates satisfy:

```text
0 <= coordinate <= 1
```

and:

```text
x_min < x_max
y_min < y_max
```

### Provenance

Verify model information and thresholds are persisted/returned correctly.

### Failure

Corrupt image or failed storage access must result in a failed analysis—not a successful empty result.

### Idempotency

Repeated processing must follow the defined idempotency behavior.

---

# 26. TEST REALISM

Do NOT make tests pass by:

- mocking the YOLO model everywhere
- hardcoding expected detection objects into production
- returning fixed confidence values
- bypassing storage
- bypassing the worker
- disabling validation
- catching errors

Mocks may be used for narrow unit tests where appropriate, but at least one integration test must exercise the actual model inference path.

---

# 27. MODEL DEPENDENCY

Add only the dependency actually required for the chosen implementation.

Before adding it:

Inspect:

```text
requirements.txt
pyproject.toml
requirements-dev.txt
```

Use the existing dependency management approach.

Do not add multiple competing computer-vision frameworks.

Do not add TensorFlow if the implementation uses PyTorch/Ultralytics.

Do not add unnecessary AI libraries.

---

# 28. ALEMBIC

If schema changes are required:

Create a proper Alembic migration.

Requirements:

- correct revision chain
- reversible downgrade
- no manual database edits
- no deletion of existing migrations
- migration works on a clean database
- `alembic upgrade head` succeeds

Do not modify historical migrations unless absolutely necessary.

---

# 29. DATABASE EFFICIENCY

Review all new queries for:

- unnecessary joins
- N+1 queries
- missing indexes
- loading full ORM objects unnecessarily
- duplicate queries
- inefficient detection retrieval

Do not blindly add indexes.

Use indexes that support actual access patterns.

---

# 30. API SCHEMAS

Use Pydantic v2 conventions already established by the project.

Schemas must reject invalid:

```text
confidence
coordinates
UUIDs
thresholds
pagination values
```

Do not duplicate schemas unnecessarily.

---

# 31. LOGGING

Use the existing logging system.

Useful events:

```text
vision analysis started
vision analysis completed
vision analysis failed
model initialized
detection count
processing duration
```

Do not log:

- image binary data
- secrets
- credentials
- presigned URLs
- unnecessary personal information

Use request/job/evidence IDs for correlation.

---

# 32. OBSERVABILITY

Record enough information to diagnose slow or failed inference.

At minimum where consistent with existing logging:

```text
job_id
evidence_id
model
device
duration
detection_count
```

Do not introduce a new observability stack in BE-009.

---

# 33. CODE QUALITY

During implementation:

Remove:

- unused imports
- dead variables
- unreachable code
- duplicated conversion logic
- unnecessary helper functions
- misleading comments
- obsolete TODOs related to this milestone

Keep functions focused.

Prefer:

```text
API
 ↓
service
 ↓
repository/database
```

where that matches the existing architecture.

Do not create unnecessary abstraction layers.

---

# 34. DO NOT BREAK COMPLETED MILESTONES

BE-009 must preserve:

- BE-001 DB foundation
- BE-002 storage
- BE-003 upload
- BE-004 fingerprinting
- BE-005 analysis jobs/worker
- BE-006 embedding/duplicate intelligence
- BE-007 project/activity/claim/geo functionality
- BE-008 temporal intelligence

Run the complete existing test suite.

If an existing test breaks:

1. determine why
2. fix the compatibility issue
3. do not simply rewrite the test to match broken behavior

---

# 35. REQUIRED TEST SEQUENCE

After implementation run:

### Focused BE-009 tests

```powershell
pytest -q <BE-009-test-files>
```

### Full suite

```powershell
pytest -q
```

### Migration

```powershell
python -m alembic upgrade head
```

### Git validation

```powershell
git diff --check
```

Also verify:

```powershell
git status
```

and inspect the final diff.

---

# 36. REAL INFRASTRUCTURE TEST

If the project uses:

```text
PostgreSQL/PostGIS
Redis
MinIO
```

verify the relevant services are actually running.

Do not claim infrastructure integration succeeded from mocked tests.

---

# 37. GIT HYGIENE

Before committing:

Inspect:

```powershell
git status
git diff --stat
git diff
```

Do not commit:

- `.env`
- secrets
- model weights
- cache directories
- Python bytecode
- IDE files
- generated temporary files
- huge test artifacts

Verify `.gitignore`.

Do not rewrite history.

Do not force-push.

---

# 38. SCOPE GUARD

Do NOT implement:

```text
BE-010 Evidence Graph
BE-011 Fusion Engine
BE-012 Explainability
BE-013 Human Review
BE-014 Audit
BE-015 Auth/RBAC
BE-016 Security hardening
BE-017 ML
BE-018 Production deployment
```

BE-009 only creates the **raw visual intelligence layer** required by those later milestones.

---

# 39. DEFINITION OF DONE

BE-009 is complete only when all of the following are true:

- [ ] Real YOLO inference implemented
- [ ] Model loaded through a dedicated vision service
- [ ] CPU execution supported
- [ ] GPU execution supported when available
- [ ] Actual evidence image retrieved through existing storage
- [ ] Object detections generated from real inference
- [ ] Actual model confidence persisted
- [ ] Actual bounding boxes persisted
- [ ] Bounding boxes normalized correctly
- [ ] Image dimensions captured from the real image
- [ ] Model provenance recorded
- [ ] Vision results persisted
- [ ] Vision job integrated with existing Redis worker
- [ ] Existing fingerprint jobs still work
- [ ] Failure states are real failures
- [ ] No fake results
- [ ] No fraud/risk/authenticity scores
- [ ] Idempotency handled
- [ ] API retrieval implemented
- [ ] Database queries reviewed
- [ ] Tests use real image fixtures
- [ ] At least one test exercises real model inference
- [ ] Focused tests pass
- [ ] Full test suite passes
- [ ] Alembic upgrade succeeds if migration added
- [ ] `git diff --check` passes
- [ ] No secrets/model weights/cache files committed
- [ ] No BE-010+ functionality implemented

---

# FINAL RESPONSE REQUIRED FROM COPILOT

When finished, report:

## 1. Implementation

List exactly what was implemented.

## 2. Files changed

List:

```text
created
modified
deleted
```

and explain why each deletion was safe.

## 3. Vision model

Report:

```text
model:
version:
device:
input behavior:
```

## 4. Database

Report:

- tables added/modified
- indexes
- migration revision

## 5. API

List all new/modified endpoints.

## 6. Worker

Explain exactly how vision jobs flow through Redis and the existing worker.

## 7. Tests

Report:

```text
focused tests: X passed
full suite: X passed
migration: passed/failed
git diff --check: passed/failed
```

## 8. Real inference verification

State explicitly whether an actual image was passed through the actual model.

Do not claim this unless it actually happened.

## 9. Performance

Report any meaningful optimizations made.

## 10. Remaining issues

List genuine remaining limitations.

Do not hide known problems.

## 11. Scope verification

Explicitly confirm:

> BE-009 implemented only the vision intelligence layer. BE-010+ functionality was not implemented.

---

# FINAL RULE

The purpose of BE-009 is not to make PoA say:

> "AI thinks this evidence is valid."

The purpose is to make PoA capable of saying:

> "This image was actually analyzed by model X. These objects were detected at these locations with these model-generated confidence values, using this configuration."

Everything beyond those observations belongs to the subsequent intelligence layers.