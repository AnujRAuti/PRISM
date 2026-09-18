BE-009 — Vision Intelligence

Project: Proof-of-Action (PoA)
Technical name: Evidence Integrity & Intelligence Layer (EIIL)
Milestone: BE-009
Status: Ready for implementation
Previous baseline: BE-008 + cleanup/hardening
Next milestone: BE-010 — Evidence Graph

1. Objective

Implement the first real Vision Intelligence capability in Proof-of-Action.

BE-009 introduces deterministic, reproducible image observations into the existing evidence-analysis pipeline.

The primary V1 capability is:

Real object detection on trusted image evidence using YOLO, with persisted, provenance-aware observations.

BE-009 must integrate into the existing architecture rather than creating a parallel analysis system.

The implementation must use the existing:

Evidence model
object storage abstraction
Redis analysis queue
AnalysisJob lifecycle
AnalysisResult / analysis infrastructure where appropriate
existing FastAPI API structure
existing configuration system
existing test infrastructure

Do not replace or bypass the existing BE-001→BE-008 architecture.

2. Architectural Position

The intended PoA data flow is:

Evidence

→ technical characterization

→ Vision Analysis Run

→ Vision Observations

→ future Evidence Graph

→ future Fusion

→ future Explainability

→ future Review

BE-009 stops at the observation layer.

Do not implement the later reasoning layers during this milestone.

3. Locked Architecture Constraints

The following decisions from the architecture baseline are mandatory.

3.1 Vision V1 is observation-only

V1 vision intelligence produces real visual observations.

It may identify objects such as:

person
vehicle
building
construction equipment
other classes provided by the configured detection model

The exact detected classes depend on the actual model.

The system must never fabricate detections.

4. Explicitly Out of Scope

BE-009 must NOT implement:

fraud detection
fraud probability
authenticity scoring
manipulation detection
deepfake detection
image tampering classification
semantic truth determination
compliance scoring
integrity scoring
risk scoring
review-priority scoring
Evidence Graph
Fusion Engine
Explainability Engine
Review Cases
human decisions
Audit Ledger expansion
authentication
RBAC
ML review prioritization
OCR as a truth mechanism
face recognition
facial identification
biometric identification
frontend implementation
mobile implementation
deployment infrastructure

If one of these appears necessary, stop and identify the dependency rather than silently implementing it.

5. Core Engineering Principle

Do not interpret "make it work" as "make a convincing demo."

Every capability must perform the real operation it claims to perform.

Never use:

fake detections
hardcoded detections
fake confidence values
fabricated bounding boxes
placeholder model outputs
simulated YOLO responses
mocked production inference
random observations
artificial success responses

If inference cannot genuinely execute:

Fail clearly or mark the analysis unavailable.

Never pretend it succeeded.

Tests may mock infrastructure where appropriate, but the production vision path must perform genuine inference.

6. Existing Backend Must Be Audited First

Before modifying code, inspect the existing repository.

Specifically audit:

backend/models/
backend/schemas/
backend/api/
backend/services/
backend/engines/
backend/workers/
backend/core/
Alembic migrations
Redis queue implementation
storage implementation
existing analysis models
existing analysis endpoints
existing integration tests
existing configuration
dependency versions

Determine:

How Evidence is represented.
How trusted evidence is retrieved.
How analysis jobs are created.
How workers dispatch analysis.
How AnalysisResult is persisted.
How analysis failures are represented.
How object storage is accessed.
Whether an existing analysis-engine abstraction should be extended.
Whether a VisionDetection table already exists.
Whether any previous vision placeholder code exists.

Do not duplicate an existing abstraction unnecessarily.

7. Vision Engine

Create or finalize:

backend/services/vision_intelligence.py

The service should provide a clean boundary around vision inference.

Conceptually:

trusted Evidence → image bytes → image decoding → YOLO inference → normalized observations

The service must not:

calculate fraud
calculate risk
make truth claims
modify Evidence
create Claims
create Review Cases
create graph relationships

Its responsibility is producing genuine visual observations.

8. Model

Use Ultralytics YOLO.

The model must be configurable.

Configuration should include at minimum:

model name/path
confidence threshold
IoU threshold where applicable
device selection
inference image size where appropriate

Example configuration conceptually:

VISION_MODEL_NAME

VISION_CONFIDENCE_THRESHOLD

VISION_IOU_THRESHOLD

VISION_DEVICE

VISION_IMAGE_SIZE

Do not hardcode these values inside the service.

Actual configuration names may follow the existing project naming conventions.

9. Dependency

Add the actual Ultralytics dependency required for YOLO inference.

Do not add unrelated computer-vision dependencies.

Do not add:

OCR frameworks
face-recognition libraries
deepfake detectors
manipulation-detection frameworks

unless a genuine BE-009 dependency is demonstrated.

The existing CLIP/transformers dependency from BE-006 must remain intact.

10. Model Weights

Model weights must never be committed to Git.

The system should obtain the configured model through the supported runtime mechanism.

The implementation must clearly distinguish:

model configuration
model availability
model loading
inference failure

If the model cannot be obtained or loaded, the analysis must fail or be marked unavailable according to the existing analysis lifecycle.

Do not silently substitute a fake model.

11. CPU Compatibility

CPU execution is mandatory.

The system must be capable of running YOLO inference on CPU.

GPU acceleration may be supported when available.

Do not make CUDA/GPU availability a mandatory prerequisite for BE-009.

The implementation should select the configured device explicitly rather than assuming CUDA exists.

12. Input Handling

Vision analysis must operate on trusted evidence, not arbitrary filesystem paths.

Use the existing storage abstraction.

Do not introduce direct hardcoded MinIO filesystem access.

The general path is:

Evidence ID

→ trusted object storage key

→ storage service

→ image bytes

→ Pillow/image decoder

→ YOLO

The original evidence object must remain immutable.

13. Image Validation

Before inference:

Retrieve the trusted evidence object.
Decode the image.
Confirm it is a supported image.
Obtain actual image dimensions.
Pass the image to the detector.

Do not trust dimensions supplied by the client.

Use dimensions obtained from the actual image.

Existing BE-003/BE-004 validation remains authoritative.

Do not duplicate upload validation unnecessarily.

14. Detection Output

Each actual detection must contain:

class ID
class name
confidence
bounding box
image dimensions
normalized bounding box coordinates

Bounding boxes should be represented in a deterministic normalized format.

Recommended representation:

x_min

y_min

x_max

y_max

with every coordinate normalized to:

0.0 <= coordinate <= 1.0

Normalization must be calculated from the actual image dimensions.

Do not store pixel coordinates as the canonical representation if the BE-009 schema specifies normalized coordinates.

15. Detection Example

For an image with:

width = 1920

height = 1080

and a detector returning:

x1 = 384

y1 = 216

x2 = 960

y2 = 756

the normalized coordinates would be calculated from the actual dimensions.

The implementation must perform this calculation programmatically.

Never hardcode example values into production behavior.

16. Confidence

Confidence must come directly from the actual YOLO inference result.

Do not:

manufacture confidence
round away meaningful precision unnecessarily
convert confidence into a risk score
interpret confidence as truth probability

A YOLO confidence value means model detection confidence.

It does not mean:

probability that the object actually exists.

The API/documentation must preserve that distinction.

17. Detection Persistence

Introduce a dedicated persistence representation for vision observations.

Preferred design:

VisionDetection

or an equivalent dedicated table/entity.

It should preserve enough information to reproduce and audit what the model observed.

At minimum, the relationship should identify:

Evidence
Analysis Run / Analysis Result
class ID
class name
confidence
normalized bounding box
image width
image height
model identifier/version
relevant inference configuration

Use the existing project naming conventions if an equivalent structure already exists.

Do not overload unrelated BE-004 or BE-006 fields with detection-specific data.

18. Analysis Run Governance

Vision inference is an analytical execution.

It must therefore integrate with the existing analysis-job architecture.

Every vision execution must be traceable to an analysis execution.

The system must preserve:

capability
input evidence
model/version
configuration
start time
completion time
status
failure information where applicable

The architecture distinguishes:

COMPLETED

Inference successfully ran.

It is valid for this to produce:

zero detections.

Zero detections is a legitimate successful result.

FAILED

The analysis was attempted but execution failed.

Examples:

corrupted trusted object
model loading failure
inference exception
persistence failure
UNAVAILABLE

The capability cannot currently execute.

Examples may include:

configured model unavailable
required runtime capability unavailable

Do not convert failures into successful zero-detection results.

19. Zero Detections

This distinction is critical.

If YOLO executes successfully and finds no objects above the configured threshold:

Analysis status = COMPLETED

Detection count = 0

This is not:

FAILED
UNAVAILABLE
suspicious
fraudulent
low integrity

Do not fabricate an empty detection merely to create a record.

The successful analysis execution itself should establish that inference completed.

20. Failure Semantics

If image retrieval fails:

→ analysis must fail.

If image decoding fails:

→ analysis must fail.

If model loading fails:

→ analysis must fail or be unavailable according to the established analysis semantics.

If inference throws an exception:

→ analysis must fail.

If detection persistence fails:

→ analysis must not be reported as successfully completed.

Never catch an exception and return a successful fake result.

21. Redis Worker Integration

Use the existing Redis analysis worker.

Do not create:

a second worker
a second queue
a second job framework
a separate Celery system
a second Redis processing pipeline

The existing worker must dispatch the vision capability through the established architecture.

The exact implementation should follow the current BE-005/BE-006 job lifecycle.

22. Analysis Dispatch

Determine how the current system identifies analysis capabilities.

If the existing worker already has a capability/analysis dispatch mechanism:

extend it.

Do not create an unrelated mechanism.

The new vision capability should fit naturally into:

queued → running → completed/failed

and the existing recovery/idempotency behavior must remain intact.

23. Reprocessing

Running vision analysis again must create a new analytical execution.

Do not overwrite the previous analytical result.

This preserves historical provenance.

For example:

Evidence A

→ Vision Run 1

→ model v1

→ 3 detections

Later:

Evidence A

→ Vision Run 2

→ model v2

→ 4 detections

Both executions remain historically available.

Do not mutate Run 1 into Run 2.

24. Model Provenance

The persisted observation must make it possible to determine:

Which model generated this observation?

At minimum preserve:

model identifier
model version or configured model reference
inference configuration

Where practical, preserve a deterministic model/configuration identity.

Do not claim a model version that the runtime did not actually use.

25. Configuration Provenance

The analysis should preserve the relevant configuration used during inference.

At minimum:

confidence threshold
IoU threshold if used
image size if configurable
device
model reference

This is necessary because changing thresholds can change detection output.

26. API

Expose vision results through the canonical API structure where appropriate.

Follow:

/api/v1

Use existing API conventions.

Do not create an unrelated /vision API namespace outside the established architecture.

Possible conceptual endpoint:

GET /api/v1/evidence/{evidence_id}/vision

or an equivalent route consistent with the existing analysis API.

The exact endpoint should be determined after auditing the current API design.

The API must expose actual persisted observations.

Do not generate detections at request time merely to make the API return something.

27. API Response

A vision response should make clear:

evidence ID
analysis execution
analysis status
model information
image dimensions
threshold/configuration information where appropriate
detection count
individual detections

A detection should expose:

class ID
class name
confidence
normalized bounding box

Do not expose fabricated:

risk
fraud
authenticity
integrity
truth
review priority

fields.

28. Schema Validation

Pydantic schemas must enforce sensible bounds.

For example:

Confidence:

0 <= confidence <= 1

Normalized coordinates:

0 <= x <= 1

0 <= y <= 1

Image dimensions:

positive integers.

Class ID:

non-negative integer unless the model/runtime genuinely defines another convention.

Do not weaken schema validation merely to accommodate bad inference output.

29. Bounding Box Validation

Before persistence, validate:

coordinates are finite
coordinates are within [0,1]
x_min <= x_max
y_min <= y_max

Reject malformed detector output rather than persisting impossible geometry.

If the underlying detector violates expectations, the analysis should fail clearly rather than silently correcting invalid output.

30. Database Migration

If a new VisionDetection table or other schema change is required:

Create a proper Alembic migration.

The migration must:

have the correct parent revision
be reversible where practical
use the existing naming conventions
preserve existing data
avoid destructive changes
work from a clean database
work from the current BE-008 head

Do not manually edit the database.

Do not modify previous migrations to make the new migration work.

31. Indexing

Add indexes only where justified by actual access patterns.

Likely useful relationships include:

evidence ID
analysis run/result ID

Do not add speculative indexes everywhere.

The goal is correctness first and measured efficiency second.

32. Evidence Immutability

BE-009 must never modify the original evidence file.

It must not modify:

SHA-256
pHash
original object
original EXIF
original provenance

Vision results are derived analytical data.

33. Provenance

Every persisted detection must be traceable to:

Evidence

→ Vision Analysis Run

→ Model/configuration

→ Detection

This creates the foundation for future Evidence Graph lineage.

Do not implement the graph itself yet.

34. No Evidence Graph Yet

BE-010 is responsible for the Evidence Graph.

Therefore BE-009 must not create:

graph nodes
graph relationship APIs
graph traversal
SUPPORTS
CONTRADICTS
SIMILAR_TO
CORROBORATES

unless an existing BE-008 relationship mechanism genuinely requires a minimal compatibility integration.

Even then, do not pull BE-010 functionality forward.

35. No Fusion

Do not turn detections into:

integrity scores
risk scores
review scores
fraud scores
confidence aggregates

Those belong to later architecture layers.

A detection is an observation.

36. No Semantic Interpretation

Do not implement logic such as:

"A detected person proves that construction occurred."

or:

"A detected excavator proves project progress."

YOLO identifies visual patterns/classes.

It does not establish the truth of a project claim.

Any future interpretation belongs to the relationship/signal/fusion layers.

37. Security

Do not expose raw storage credentials.

Use the existing storage abstraction.

Do not create arbitrary filesystem access based on user-supplied paths.

Do not allow a user to request arbitrary object keys.

Respect existing evidence access boundaries.

Do not log:

object storage credentials
signed URLs
sensitive evidence contents

Avoid logging full raw image data.

38. Resource Limits

Vision inference is computationally expensive.

Use existing infrastructure/configuration patterns to prevent uncontrolled resource consumption.

At minimum consider:

image size limits already established by BE-003
model image size
inference timeout where supported
worker concurrency
memory consumption

Do not introduce a large speculative resource-management subsystem.

If a concrete limit is required, implement it through existing configuration patterns.

39. Determinism

Given:

the same image
same model
same model version
same configuration

the analysis should produce reproducible observations to the extent supported by the underlying runtime.

Persist the configuration necessary to understand the execution.

Do not add randomness to inference.

40. Logging

Use the existing logging/request-ID conventions.

Useful events include:

vision analysis started
model loaded
inference completed
detection count
analysis completed
analysis failed

Do not log sensitive image contents.

Do not log giant tensor outputs.

Do not log credentials.

41. Testing Requirements

Tests must verify actual behavior.

Do not write tests that only assert:

model.predict() was called.

Tests must verify outputs.

42. Unit Tests

Add unit coverage for:

Bounding box normalization

Given known pixel coordinates and dimensions:

→ expected normalized coordinates.

Bounding box validation

Reject:

negative coordinates
coordinates > 1
inverted boxes
non-finite values
Confidence validation

Reject:

negative confidence
confidence > 1
Configuration

Verify configuration is correctly loaded.

Zero detections

Successful inference with zero observations must produce:

COMPLETED

not failure.

43. Real Inference Integration Test

At least one integration test must execute real YOLO inference.

The test must use an actual image.

It must verify:

Evidence exists.
Evidence is accessible through the real storage path.
Vision analysis executes.
YOLO actually runs.
Analysis completes.
Output is persisted.
Detection structure is valid.
Bounding boxes are normalized.
Confidence values are within [0,1].
Model provenance exists.

Do not mock the YOLO model for this test.

44. Real Zero-Detection Test

Where practical, include a real image expected to produce zero detections under the configured threshold.

Verify:

real inference succeeds → zero observations → COMPLETED

Do not construct a fake zero-detection response.

If a stable zero-detection fixture cannot be guaranteed, document that limitation rather than weakening the test.

45. Worker Integration Test

Verify that a queued vision analysis is processed through the existing worker.

Test:

API/job creation

→ Redis queue

→ worker

→ actual vision service

→ database result

The test must verify persisted results.

Do not create a separate test-only worker architecture.

46. Failure Test

Test a genuine failure path.

For example:

invalid/corrupt image
unavailable model
inference exception

Verify the AnalysisJob does not become falsely successful.

The resulting state must accurately represent the failure.

47. Idempotency

Preserve the existing BE-005/BE-006 protections.

If a completed analysis message is delivered again, it must not:

duplicate the analytical result incorrectly
rerun unnecessarily
corrupt state

Do not weaken existing job semantics to accommodate vision.

48. Recovery Compatibility

The new vision workload must remain compatible with the repaired BE-005 recovery behavior.

In particular:

fresh running jobs must not be stolen
stale jobs may be recovered
completed jobs must not be requeued
queued-in-processing jobs must be recoverable
duplicate delivery must remain safe

Do not modify recovery semantics unless BE-009 exposes a genuine requirement.

49. Performance Reporting

Measure real inference performance.

Report at least:

model
device
image dimensions
inference time
total analysis time
detection count

Do not promise a performance target without measurement.

CPU performance should be reported separately if tested.

50. Model Download / Runtime Setup

Document how the model is obtained.

The repository must not contain large model weight files.

The setup documentation should explain:

required dependency
model configuration
first-run model acquisition if applicable
CPU execution
optional GPU execution
where model weights are stored
how to change the model

Do not silently download arbitrary models from unknown sources.

51. Existing Tests Must Continue Passing

BE-009 must preserve BE-001→BE-008 behavior.

Run:

focused BE-009 tests
existing analysis tests
existing evidence tests
duplicate intelligence tests
temporal tests
full test suite

Do not delete or weaken previous tests.

Do not modify previous tests merely to make BE-009 pass.

If an existing test exposes a genuine compatibility issue:

identify it
determine whether BE-009 caused it
make the smallest legitimate compatibility fix
preserve the original contract
52. Infrastructure Verification

Run BE-009 against the real development infrastructure:

PostgreSQL/PostGIS
Redis
MinIO
actual Python environment

The integration path must not depend entirely on mocks.

Verify:

database migration
storage retrieval
Redis job processing
YOLO model loading
real inference
persistence
API retrieval
53. Alembic Verification

If a migration is created:

Run:

upgrade from the existing BE-008 head

Then verify the resulting schema.

Also verify a clean migration path where practical.

The final Alembic head must be documented.

54. API Contract Verification

Verify that:

existing BE-001→BE-008 routes remain functional
existing response shapes remain compatible
new vision endpoints follow /api/v1
errors use existing structured error conventions
request IDs remain available
OpenAPI reflects the new endpoints

Do not silently change existing contracts.

55. Scope Gate

Before declaring BE-009 complete, search the diff for accidental future functionality.

The final implementation must not contain unrelated additions involving:

Evidence Graph
Fusion
Explainability
Review
Audit
Auth/RBAC
ML
frontend
deployment

The only new analytical capability should be:

real image observation through YOLO/object detection.

56. Anti-Fake Verification

Before completion, explicitly verify that the implementation does not contain:

hardcoded detection arrays
hardcoded bounding boxes
hardcoded confidence values
fake model names
fake model versions
random detection generation
placeholder success responses
mocked production inference
fabricated zero-detection results
fake performance numbers

Search the implementation and tests for suspicious shortcuts.

57. Definition of Done

BE-009 is complete only when all of the following are true:

Architecture
 BE-001→BE-008 behavior preserved.
 Grill-Me architecture contract followed.
 Vision remains observation-only.
 BE-010+ functionality not pulled forward.
Model
 Real Ultralytics YOLO integrated.
 Model configurable.
 CPU execution works.
 GPU is optional.
 Weights are not committed.
Analysis
 Vision uses the existing analysis-job architecture.
 Existing Redis worker is reused.
 Analysis executions are traceable.
 Successful zero detections are represented correctly.
 Failures are not converted into success.
 Reprocessing creates separate analytical executions.
Detection
 Real detections persisted.
 Class ID persisted.
 Class name persisted.
 Actual confidence persisted.
 Bounding boxes persisted.
 Bounding boxes normalized.
 Image dimensions persisted.
 Model/configuration provenance persisted.
Storage
 Existing storage abstraction reused.
 Trusted evidence used as input.
 Original evidence remains immutable.
API
 Vision results accessible through /api/v1.
 Schemas validated.
 Existing API contracts preserved.
 OpenAPI updated.
Database
 Migration created if required.
 Migration chain valid.
 No destructive changes.
Testing
 Unit tests pass.
 Real YOLO inference test passes.
 Worker integration test passes.
 Failure test passes.
 Existing BE-001→BE-008 tests pass.
 Full suite passes where infrastructure is available.
Infrastructure
 PostgreSQL/PostGIS verified.
 Redis verified.
 MinIO verified.
 Real model loading verified.
 Real inference verified.
Integrity
 No fake outputs.
 No hardcoded detections.
 No fake confidence.
 No fake performance measurements.
 No mocked production inference path.
 No hidden failures.
58. Required Final Report

When implementation is complete, report:

1. Implementation Summary

What was implemented.

2. Files Changed

List every added/modified file and why.

3. Model

Report:

model used
version/reference
dependency version
model acquisition method
CPU/GPU behavior
4. Database

Report:

tables added
columns
indexes
migration revision
migration parent
5. API

Report:

new endpoints
request schemas
response schemas
example successful response structure
6. Worker

Explain exactly how vision integrates into the existing Redis worker.

7. Analysis Lifecycle

Explain:

queued
running
completed
failed
unavailable
zero-detection behavior
8. Real Inference

Report:

actual test image
image dimensions
model
device
inference time
total processing time
number of detections
example detection structure

Do not fabricate numbers.

9. Tests

Report:

focused tests
integration tests
full suite
failures
skipped tests
reasons for skips
10. Infrastructure

Report whether:

PostgreSQL/PostGIS
Redis
MinIO
model runtime

were actually available.

11. Scope Verification

Explicitly confirm:

BE-010+ functionality was not implemented.

12. Remaining Technical Debt

List only real remaining issues.

Do not hide known limitations.

59. Git Requirements

Work only on:

Backend

Do not:

reset branches
delete branches
force push
rewrite history
modify main
modify Frontend
modify unrelated branches

Do not commit model weights.

Before committing:

inspect git status
inspect git diff
run git diff --check
verify only BE-009 files are included

Use a focused commit message:

BE-009: implement vision intelligence

Do not push automatically unless explicitly instructed.

60. Final Instruction

Treat this document and docs/Final Architecture.md as the architectural contract.

The implementation sequence must be:

AUDIT → DESIGN AGAINST EXISTING CODE → IMPLEMENT → MIGRATE IF REQUIRED → TEST → REAL INFERENCE → VERIFY → REVIEW DIFF → COMMIT

Do not skip the audit.

Do not implement future milestones.

Do not create a demo.

Do not fabricate model output.

Do not weaken existing correctness.

The finished BE-009 system must perform actual YOLO inference against actual PoA evidence and persist actual, reproducible visual observations with provenance.

BE-009 ends at the observation layer.

BE-010 begins the Evidence Graph.