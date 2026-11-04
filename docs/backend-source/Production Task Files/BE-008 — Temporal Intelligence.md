# BE-008 — Temporal Intelligence

## Objective

Implement **BE-008: Temporal Intelligence** for Proof-of-Action (PoA).

The purpose of this milestone is to establish a real, deterministic temporal-analysis layer that can reason about the timing of evidence, claims, projects, and previously captured evidence.

BE-008 must build on the completed BE-001 through BE-007 implementation without breaking existing behavior.

---

# Engineering Integrity Gate

**Do not interpret "make it work" as "make a convincing demo."**

Every implemented capability must perform the real underlying operation it claims to perform.

Do NOT use:

- fake timestamps
- hardcoded temporal results
- simulated temporal analysis
- fabricated confidence scores
- placeholder anomaly results
- mocked success paths
- AI-generated claims about timestamps
- random temporal scores

If a temporal property cannot genuinely be determined from available data, return an explicit **unknown/unavailable** state rather than pretending it was verified.

Tests must verify actual temporal behavior and outputs.

Do not weaken validation or correctness merely to make tests pass.

Do not implement BE-009 or later functionality early.

---

# Current Architecture

Existing stack:

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy
- Alembic
- PostgreSQL
- PostGIS
- pgvector
- Redis
- MinIO
- Pillow
- OpenCV
- ExifTool
- imagehash
- PyTorch
- Hugging Face Transformers
- CLIP embeddings
- Pytest

Completed:

```text
BE-001 ✅ Database foundation
BE-002 ✅ Object storage
BE-003 ✅ Evidence upload
BE-004 ✅ SHA-256 / EXIF / pHash
BE-005 ✅ Async analysis jobs
BE-006 ✅ Embeddings / duplicate intelligence
BE-007 ✅ Project / activity / claim / geographic context
```

Implement only:

```text
BE-008 → Temporal Intelligence
```

---

# What BE-008 Must Do

BE-008 must establish deterministic temporal relationships and temporal consistency checks using timestamps already available in the system.

The implementation must distinguish between different timestamp sources instead of treating every timestamp as equally trustworthy.

Relevant timestamps may include:

- evidence `created_at`
- EXIF capture timestamp when available
- analysis job timestamps
- analysis result timestamps
- project creation time
- claim creation time
- activity creation time
- other explicitly persisted temporal metadata already present in the system

Do not invent a capture timestamp when EXIF data does not contain one.

---

# 1. Temporal Data Model

Inspect the existing models before making changes.

Determine what timestamp information is already persisted by BE-001 through BE-007.

Only add a migration if BE-008 genuinely requires additional persistent temporal data.

Do not duplicate timestamps that already exist.

If additional temporal metadata is required, use explicit fields with clear semantics.

For example, distinguish:

```text
captured_at
uploaded_at
created_at
analyzed_at
```

Do not overload one timestamp to represent another.

If EXIF capture time is already stored inside existing metadata JSON, reuse it rather than introducing unnecessary duplicate storage.

---

# 2. Temporal Analysis Service

Create a dedicated temporal-analysis service/module.

Example structure:

```text
backend/
├── services/
│   └── temporal_intelligence.py
```

Use the project's existing service conventions if another appropriate abstraction already exists.

The service must perform real deterministic analysis.

It should be capable of determining temporal relationships such as:

```text
CAPTURED_BEFORE
CAPTURED_AFTER
UPLOADED_BEFORE
UPLOADED_AFTER
CAPTURED_BEFORE_CLAIM
CAPTURED_AFTER_CLAIM
```

Only create a relationship when the required timestamps actually exist.

If a required timestamp is missing:

```text
status = unknown
```

rather than guessing.

---

# 3. Temporal Consistency

Implement deterministic temporal consistency checks.

Examples:

### Capture before upload

If:

```text
capture_time <= upload_time
```

the relationship is temporally consistent.

If:

```text
capture_time > upload_time
```

flag it as a temporal inconsistency.

Do not automatically classify this as fraud.

The system must distinguish:

```text
TEMPORALLY_CONSISTENT
TEMPORAL_INCONSISTENCY
UNKNOWN
```

A temporal inconsistency is a signal for later intelligence/review, not a fraud verdict.

---

# 4. Claim Temporal Context

Claims already belong to projects.

Use the existing claim/project relationships.

Determine whether evidence capture time is temporally compatible with the claim's available temporal context.

Do NOT invent a claim completion date or project deadline.

If the claim has no usable temporal boundary:

```text
UNKNOWN
```

must be returned.

Do not infer dates from claim title or description using an LLM.

---

# 5. Evidence-to-Evidence Temporal Relationships

For evidence belonging to the same project or claim, determine actual temporal ordering when capture timestamps are available.

Example:

```text
Evidence A
captured_at = 2026-01-10

Evidence B
captured_at = 2026-02-15
```

The system can establish:

```text
A CAPTURED_BEFORE B
B CAPTURED_AFTER A
```

If timestamps are equal, represent that explicitly rather than arbitrarily choosing an order.

If timestamps are missing:

```text
UNKNOWN
```

---

# 6. Temporal Gap Calculation

Implement real elapsed-time calculations.

Examples:

```text
Evidence A → Evidence B
time difference = 36 days
```

Support appropriate units such as:

```text
seconds
minutes
hours
days
```

The underlying calculation must use actual timestamps.

Do not round away meaningful differences.

---

# 7. Timezone Handling

Handle timezone information correctly.

Requirements:

- timezone-aware timestamps must remain timezone-aware
- do not silently convert timestamps incorrectly
- do not compare naive and timezone-aware timestamps without normalization
- normalize timestamps to a consistent comparison basis when required
- preserve original timezone information where it is stored

If EXIF provides a timestamp without timezone information, do not fabricate a timezone.

Treat it as timezone-unknown unless the existing system has an explicit, trustworthy timezone context.

---

# 8. Temporal Analysis Result

Integrate temporal analysis into the existing analysis architecture without breaking BE-005/BE-006.

Inspect the existing:

```text
AnalysisJob
AnalysisResult
```

implementation first.

If appropriate, extend the existing analysis result structure with structured temporal output.

Do not create a parallel job system.

Do not replace the existing Redis worker architecture.

A temporal result should contain structured information such as:

```json
{
  "status": "temporally_consistent",
  "relationships": [],
  "time_differences": [],
  "inconsistencies": []
}
```

Use the project's actual schema conventions.

Do not return fabricated numeric confidence values.

---

# 9. API

Add only the API endpoints required to expose BE-008 functionality.

Follow the existing:

```text
/api/v1/
```

routing conventions.

Use Pydantic request/response models.

Do not create unnecessary endpoint aliases.

Do not change existing BE-007 contracts.

Potential endpoint:

```text
POST /api/v1/analysis/temporal/{evidence_id}
```

or another route consistent with the existing analysis API.

Before implementing a new route, inspect the existing analysis router and worker contracts.

The endpoint must trigger or execute the real temporal analysis.

It must not simply return a preconstructed response.

---

# 10. Existing Analysis Worker Integration

BE-005 already provides asynchronous analysis jobs.

BE-008 must integrate temporal processing into that architecture where appropriate.

Do not create:

- another Redis queue
- another worker system
- another job table
- another analysis lifecycle

Reuse the existing infrastructure.

If the existing analysis pipeline needs a minimal extension to support temporal analysis, make only that extension.

---

# 11. Database Integrity

All temporal relationships must respect existing foreign keys and project/claim ownership.

Never allow temporal relationships to connect unrelated entities accidentally.

For evidence-to-evidence temporal analysis:

- validate evidence existence
- preserve evidence IDs
- preserve project context
- never silently cross project boundaries where project scoping is required

Use database constraints where appropriate.

---

# 12. No Fraud Detection

BE-008 must NOT implement:

- fraud detection
- fraud probability
- risk score
- integrity score
- final verification
- claim verification
- anomaly scoring
- ML classification
- LLM judgement

Those belong to later milestones.

BE-008 only establishes **temporal facts and temporal consistency signals**.

---

# 13. No Vision Intelligence

Do NOT implement:

- YOLO
- object detection
- scene understanding
- image classification
- visual change detection
- OCR
- image-to-image temporal reasoning

Those belong to BE-009.

---

# 14. No Evidence Graph Implementation

Do not implement the full BE-010 graph engine.

However, structure temporal outputs so they can later support relationships such as:

```text
CAPTURED_BEFORE
CAPTURED_AFTER
```

Do not create the full graph architecture prematurely.

---

# 15. Testing

Create focused integration tests:

```text
tests/integration/test_be008_temporal.py
```

Tests must use real PostgreSQL infrastructure.

At minimum test:

### Timestamp availability

- capture timestamp present
- capture timestamp absent
- upload timestamp present
- upload timestamp absent

### Ordering

- A captured before B
- A captured after B
- equal timestamps

### Capture/upload consistency

- capture before upload
- capture equal to upload
- capture after upload
- missing capture timestamp

### Time difference

- seconds
- minutes
- hours
- days

### Timezones

- two equivalent timestamps with different offsets
- timezone-aware comparisons
- timezone-unknown EXIF timestamp

### Claim context

- usable temporal context
- missing temporal context

### Project isolation

- evidence from different projects
- invalid evidence IDs
- invalid project relationships

### API

- valid temporal request
- invalid UUID
- missing evidence
- malformed request
- correct response structure

### Persistence

Verify that temporal analysis results are actually persisted if the implementation requires persistence.

Do not merely assert that a function was called.

---

# 16. Regression Testing

After implementation:

```text
pytest tests/integration/test_be008_temporal.py
```

Then run the complete suite:

```text
pytest
```

Also run:

```text
python -m alembic upgrade head
```

and:

```text
git diff --check
```

If PostgreSQL/PostGIS/Redis/MinIO are required for the tests, verify that they are actually running.

---
## Claim Temporal Boundary Model

Extend Claim with:

- temporal_start_at: nullable timezone-aware timestamp
- temporal_end_at: nullable timezone-aware timestamp

These represent explicitly supplied temporal boundaries for the claim.

Rules:

- Both fields are optional.
- If both are present, temporal_start_at must be <= temporal_end_at.
- Do not infer either field from claim title or description.
- Do not use an LLM to extract temporal boundaries.
- Missing boundaries must produce UNKNOWN rather than an inferred value.
- Support explicit null on PATCH to remove a previously stored boundary.
- Preserve timezone information correctly.
- Use TIMESTAMPTZ in PostgreSQL.

Evidence temporal evaluation:

- captured_at within [start, end] → WITHIN_CLAIM_WINDOW
- captured_at before start → BEFORE_CLAIM_WINDOW
- captured_at after end → AFTER_CLAIM_WINDOW
- unavailable required timestamp/boundary → UNKNOWN

This temporal boundary is contextual metadata, not a claim-truth determination.
Do not produce fraud, risk, integrity, or confidence scores from it.

# 17. Backward Compatibility

BE-001 through BE-007 are complete.

Do not break:

- existing evidence upload
- fingerprinting
- analysis jobs
- embeddings
- duplicate intelligence
- project APIs
- activity APIs
- claim APIs
- evidence context
- evidence location
- nearby evidence queries

Existing tests must continue passing.

Do not modify completed milestone behavior unless a genuine BE-008 compatibility requirement exists.

---

# 18. Dependency Discipline

Do not add dependencies unless genuinely required.

Prefer the Python standard library and existing project dependencies.

Do not introduce a new temporal database.

Do not introduce a new queue.

Do not introduce a new workflow engine.

Do not introduce an LLM.

Do not introduce an ML model.

---

# 19. Scope Exclusions

Do NOT implement:

- BE-009 vision intelligence
- BE-010 evidence graph
- BE-011 fusion engine
- BE-012 explainability
- BE-013 human review
- BE-014 audit expansion
- BE-015 authentication/RBAC
- BE-017 ML
- BE-018 production deployment

Do not perform unrelated refactoring.

---

# Definition of Done

BE-008 is complete only when:

- [ ] Existing temporal fields/storage have been inspected.
- [ ] Additional schema changes are made only if genuinely required.
- [ ] Real temporal analysis service exists.
- [ ] Capture/upload temporal consistency is implemented.
- [ ] Evidence-to-evidence temporal ordering works.
- [ ] Real elapsed-time calculations work.
- [ ] Timezone handling is correct.
- [ ] Missing timestamps produce explicit UNKNOWN results.
- [ ] Claim temporal context is handled without fabricated dates.
- [ ] Temporal analysis integrates with existing analysis architecture.
- [ ] API contract is implemented if required.
- [ ] No fake scores or fabricated temporal conclusions exist.
- [ ] No BE-009+ functionality was implemented.
- [ ] Focused BE-008 tests pass.
- [ ] Full regression suite passes.
- [ ] Alembic upgrade passes.
- [ ] `git diff --check` passes.
- [ ] PostgreSQL/PostGIS/Redis/MinIO integration is verified where required.
- [ ] Existing BE-001 through BE-007 functionality remains intact.

---

# Final Copilot Response

After implementation, report:

1. Files changed
2. Database/migration changes
3. Temporal capabilities implemented
4. API endpoints added/changed
5. Worker integration changes
6. Tests added
7. Focused test result
8. Full test result
9. Infrastructure verification
10. Any warnings
11. Any deferred issues
12. Confirmation that no BE-009+ functionality was implemented

Do not claim BE-008 is complete unless the implementation and tests genuinely satisfy the requirements above.