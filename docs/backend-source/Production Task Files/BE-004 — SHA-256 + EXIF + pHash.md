# BE-004 — Evidence Identity & Metadata Fingerprinting

## Objective

Implement the first evidence-analysis layer for uploaded evidence.

BE-004 must take an evidence object already accepted by BE-003, retrieve the original file from the quarantine storage, and generate three real, persisted evidence signals:

1. **SHA-256 cryptographic hash**
2. **EXIF metadata extraction**
3. **Perceptual hash (pHash)**

These signals establish evidence identity and metadata foundations for later duplicate detection, temporal analysis, geo analysis, provenance analysis, and the Evidence Graph.

This milestone must perform real computation on the actual uploaded evidence.

---

# Critical Engineering Principle

## Do NOT build a convincing demo.

"Make it work" means:

> Implement the actual underlying operation and persist its real result.

It does NOT mean:

- hardcoded hashes
- fake metadata
- placeholder pHash values
- fabricated confidence scores
- simulated analysis
- mocked success responses
- randomly generated fingerprints
- fake EXIF values
- pretending missing metadata exists
- returning successful analysis when processing failed

If the system cannot genuinely calculate a value, it must represent that value as unavailable/null and preserve the reason.

**Never fabricate evidence-derived information.**

Tests must verify actual computed outputs rather than merely checking that a function was called.

---

# Baseline Gate

Before making any changes:

1. Inspect the current `Backend` branch.
2. Verify BE-001 is still functioning.
3. Verify BE-002 storage functionality is still functioning.
4. Verify BE-003 upload functionality is still functioning.
5. Inspect the current `Evidence` model.
6. Inspect the current `EvidenceMetadata` model.
7. Inspect existing storage abstractions.
8. Inspect existing database/session/repository patterns.
9. Inspect existing engine structure under:
   - `backend/engines/hashing/`
   - `backend/engines/metadata/`
10. Inspect existing tests before adding new ones.

Do not redesign completed milestones.

If a previous milestone has a blocker that genuinely prevents BE-004:

- fix only the blocker required for BE-004;
- do not rewrite the previous milestone;
- do not perform unrelated cleanup.

---

# Milestone Boundary

The pipeline for this milestone is:

```text
Existing Evidence
      ↓
Retrieve original object
      ↓
SHA-256
      ↓
EXIF extraction
      ↓
pHash
      ↓
Persist analysis results
```

BE-004 ends after these three signals have been calculated and persisted.

---

# Explicitly OUT OF SCOPE

Do NOT implement:

- duplicate detection decisions
- similarity thresholds
- embedding generation
- CLIP
- SigLIP
- SIFT
- ORB
- feature matching
- fraud detection
- manipulation detection
- AI authenticity detection
- vision analysis
- object detection
- GPS verification
- geo scoring
- temporal scoring
- project matching
- claim matching
- Evidence Graph relationships
- cross-project intelligence
- corroboration
- fusion
- integrity scoring
- risk scoring
- explainability
- reviewer workflows
- human review
- Redis
- Celery
- Dramatiq
- background workers
- authentication
- authorization
- frontend
- ML
- blockchain
- C2PA

These belong to later milestones.

---

# 1. SHA-256

Implement real SHA-256 hashing of the original uploaded bytes.

The hash must be calculated from the **actual stored original evidence object** retrieved from quarantine storage.

Do not hash:

- filename
- storage key
- metadata JSON
- UUID
- compressed/transformed preview
- thumbnail
- reconstructed image
- arbitrary normalized representation

The SHA-256 input must be the original stored file bytes.

The resulting digest must be represented as the standard lowercase hexadecimal SHA-256 digest.

Example format:

```text
64 hexadecimal characters
```

Do not truncate the digest.

Do not use MD5 or SHA-1.

---

# 2. SHA-256 Determinism

For the exact same byte sequence:

```text
SHA256(file A) == SHA256(file B)
```

must always hold.

For different byte sequences:

```text
SHA256(file A) != SHA256(file B)
```

should be expected, subject to normal cryptographic collision assumptions.

Tests must verify deterministic behavior.

At minimum, use a known test byte sequence with a known SHA-256 digest.

Do not merely assert that the output has length 64.

---

# 3. SHA-256 Persistence

Inspect the existing database schema before deciding where the hash belongs.

Prefer the smallest schema change necessary.

The hash must be persisted so future milestones can query it efficiently.

If adding a dedicated column to `Evidence` is consistent with the existing architecture, prefer that over hiding the hash inside an unrelated JSON structure.

The database representation should support future exact-duplicate queries.

Add an appropriate database index if the hash is stored as a dedicated field and future lookup efficiency requires it.

Do not create a second competing hash storage mechanism.

---

# 4. EXIF Metadata Extraction

Extract metadata from the actual original image.

Use an appropriate existing dependency where possible.

The extraction must be real.

Potential EXIF fields include:

- camera make
- camera model
- software
- capture date/time
- orientation
- image dimensions where appropriate
- GPS information
- focal length
- exposure information
- ISO
- other available EXIF fields

Do not assume any of these fields exist.

---

# 5. Missing EXIF

Missing EXIF is a legitimate evidence state.

For example:

```text
EXIF present
```

and:

```text
EXIF absent
```

must be distinguishable.

Do NOT create fake values such as:

```text
camera_make = "Unknown Camera"
```

unless that is explicitly part of a defined presentation layer.

Prefer representing unavailable metadata as null/absent.

The system must never interpret:

```text
EXIF missing
```

as:

```text
evidence is fraudulent
```

That kind of interpretation belongs to later intelligence/fusion logic.

---

# 6. EXIF GPS

If GPS EXIF exists, extract it accurately.

Do not yet:

- verify GPS against project location
- calculate distance
- assign geo confidence
- determine whether GPS is trustworthy
- declare the evidence geographically valid

BE-004 only extracts the available metadata.

GPS validation belongs to the Geo milestone.

---

# 7. EXIF Timestamp

If EXIF contains a capture timestamp, extract it.

Do not yet:

- compare it with upload time
- compare it with project dates
- detect future timestamps
- detect impossible timestamps
- calculate temporal anomalies

Those belong to later temporal analysis.

Do not overwrite the timestamp merely because it looks suspicious.

Persist what was actually present in the source metadata.

---

# 8. EXIF Serialization

Metadata must be persisted in a JSON-compatible structure.

Inspect the existing `EvidenceMetadata` model.

If it is suitable, reuse it.

Do not create a duplicate metadata table.

Metadata values must be serialized safely.

Handle values that are not naturally JSON serializable.

Do not silently discard metadata because of serialization errors without recording an appropriate processing outcome.

Avoid exposing raw binary EXIF blobs unnecessarily.

---

# 9. EXIF Privacy

Be deliberate about what metadata is persisted.

EXIF can contain sensitive information.

Do not log the complete EXIF payload.

Do not print EXIF data during normal processing.

Do not expose metadata through the upload endpoint unless the existing API explicitly requires it.

BE-004 is an internal processing layer.

Later API endpoints can decide what metadata is appropriate to expose.

---

# 10. Perceptual Hash (pHash)

Generate a real perceptual hash from the image.

Use a proper pHash implementation rather than inventing a custom arbitrary fingerprint.

The pHash must represent visual characteristics of the image so that visually similar images can later be compared.

The pHash is NOT a cryptographic identity.

It must not replace SHA-256.

---

# 11. pHash Semantics

Clearly preserve the distinction:

```text
SHA-256
= exact byte identity
```

versus:

```text
pHash
= perceptual/visual fingerprint
```

Do not call a pHash match an exact duplicate.

Do not implement duplicate classification in BE-004.

Do not introduce arbitrary similarity thresholds in this milestone.

Future BE-006 will determine how multiple signals are combined for duplicate intelligence.

---

# 12. pHash Determinism

For the same image processed using the same implementation:

```text
pHash(image A) == pHash(image A)
```

must hold.

Tests should verify deterministic output.

Where practical, tests should also verify that a visually modified/resized/compressed version can produce a comparable perceptual fingerprint.

Do not make the test depend on an arbitrary claim such as:

```text
distance < X means duplicate
```

because duplicate decision logic is out of scope.

---

# 13. Image Processing

Use the actual stored image.

Do not:

- use a fake test image in production code
- generate a placeholder pHash
- skip processing and return null on valid images
- permanently convert the original stored object
- overwrite the original evidence

Any image normalization required internally by the pHash library must happen in memory.

The original quarantine object must remain unchanged.

---

# 14. Processing Architecture

Keep responsibilities separated.

Preferred conceptual structure:

```text
API / service layer
        ↓
Evidence processing service
        ↓
Hashing engine
Metadata engine
pHash engine
        ↓
Persistence
```

Reuse the existing engine directories where appropriate:

```text
backend/engines/hashing/
backend/engines/metadata/
```

Do not put all three algorithms directly into the API endpoint.

The API should not contain the implementation of SHA-256, EXIF parsing, and pHash logic.

---

# 15. Processing Trigger

BE-004 does not need to implement the final asynchronous processing architecture.

BE-005 will introduce async analysis jobs.

For BE-004, use the simplest clean synchronous/service-level processing mechanism that fits the current architecture.

Do not introduce Redis or workers just to process BE-004.

Do not prematurely implement BE-005.

The design should, however, keep the processing logic callable later by a background worker.

---

# 16. Processing Failure

If processing fails:

- do not fabricate a result;
- do not mark the analysis as successful;
- preserve the underlying evidence object;
- return/record an appropriate processing failure according to the current architecture.

A failure in EXIF extraction should not necessarily prevent SHA-256 from being calculated if those operations are independently possible.

Likewise, failure of pHash should not invalidate a successfully calculated SHA-256.

Prefer independent signal computation where practical.

Example:

```text
SHA-256       → SUCCESS
EXIF          → SUCCESS
pHash         → SUCCESS
```

or:

```text
SHA-256       → SUCCESS
EXIF          → NO_METADATA
pHash         → SUCCESS
```

or:

```text
SHA-256       → SUCCESS
EXIF          → SUCCESS
pHash         → FAILED
```

Do not turn these into one fake all-or-nothing result.

---

# 17. Processing Status

Inspect the existing schema before introducing status fields.

If processing status is required, use the smallest coherent representation.

Do not create an elaborate job/state machine.

BE-005 will own the asynchronous job lifecycle.

BE-004 only needs enough state to represent whether these fingerprint operations were successfully calculated and persisted.

---

# 18. Database Consistency

Ensure the persisted values correspond to the actual object that was processed.

For a given evidence ID:

```text
stored object
      ↓
actual bytes
      ↓
SHA-256
```

must correspond to the same object referenced by the Evidence record.

Do not process one object and persist results for another.

---

# 19. Reprocessing / Idempotency

Inspect the existing schema before implementing reprocessing behavior.

The processing code should be safe to invoke more than once for the same evidence.

Running fingerprint generation twice on unchanged bytes should not produce contradictory values.

Avoid creating uncontrolled duplicate metadata rows.

If the existing schema requires uniqueness or an upsert pattern, implement the smallest appropriate solution.

Do not create a complex job-idempotency framework.

---

# 20. Tests

Tests must validate real behavior.

Do NOT write tests that merely assert:

```python
mock.called
```

for the core fingerprint operations.

At least the following must be tested.

## Test 1 — SHA-256 known value

Use known bytes and verify the exact expected SHA-256 digest.

---

## Test 2 — SHA-256 actual uploaded object

Upload a real image through BE-003.

Retrieve the object from MinIO.

Calculate SHA-256 independently in the test.

Verify that the persisted SHA-256 equals the independently calculated digest.

This must test the complete path.

---

## Test 3 — SHA-256 determinism

Process the same evidence twice.

Verify the same SHA-256 result is produced.

---

## Test 4 — EXIF extraction

Use an image containing known EXIF metadata.

Verify that the expected metadata is extracted.

Do not use arbitrary assertions such as:

```text metadata != null
```

Verify actual values.

---

## Test 5 — Image with no EXIF

Use a valid image without EXIF.

Verify:

- processing succeeds where appropriate;
- EXIF is represented as absent/empty;
- no fake metadata is generated.

---

## Test 6 — EXIF GPS

Use a test image containing known GPS metadata.

Verify the actual extracted coordinates.

Do not perform geo validation.

---

## Test 7 — EXIF timestamp

Use a test image containing a known capture timestamp.

Verify that the extracted value corresponds to the source metadata.

Do not perform temporal analysis.

---

## Test 8 — pHash determinism

Process the same image twice.

Verify that the pHash is identical.

---

## Test 9 — pHash persistence

Verify that the calculated pHash is persisted and can be retrieved from PostgreSQL.

---

## Test 10 — Original object unchanged

After processing:

- verify the quarantine object still exists;
- verify its bytes are unchanged.

Fingerprinting must never modify the original evidence.

---

## Test 11 — Processing failure

Where practical, simulate a genuine processing failure at the engine/service boundary.

Verify the system:

- does not fabricate a fingerprint;
- records/returns an appropriate failure;
- does not corrupt the evidence object.

Do not weaken the production implementation solely to make this test easy.

---

# 21. Integration Testing

Use the actual infrastructure where practical:

```text
PostgreSQL
+
MinIO
```

Do not replace the complete BE-004 flow with mocks.

Mocks may be used for isolated unit tests, but the core integration test must prove:

```text
Evidence
→ MinIO object
→ actual bytes
→ actual algorithms
→ PostgreSQL
```

---

# 22. Security / Integrity Requirements

The implementation must:

- process the actual stored object;
- never trust client-provided hash values;
- never accept a client-provided SHA-256 as authoritative;
- never accept a client-provided pHash as authoritative;
- never accept client-provided EXIF as authoritative;
- never overwrite the original evidence during processing;
- never log sensitive EXIF indiscriminately;
- never expose storage credentials;
- never fabricate metadata;
- never fabricate fingerprint results.

The source file itself is authoritative for the computed fingerprints.

---

# 23. Performance

Do not prematurely optimize.

However:

- avoid unnecessary multiple downloads of the same object;
- where practical, retrieve the object once and reuse the bytes for SHA-256, EXIF, and pHash;
- avoid writing temporary files unless the chosen library genuinely requires them;
- do not introduce a distributed processing system in this milestone.

The architecture must remain compatible with BE-005 async processing.

---

# 24. Dependencies

Reuse existing dependencies wherever possible.

Likely relevant existing dependencies include:

- hashlib / Python standard library for SHA-256
- Pillow
- existing EXIF library
- existing imagehash dependency

Do not add a new dependency if an existing dependency already provides the required capability.

Do not add:

- Celery
- Dramatiq
- Redis processing infrastructure
- ML frameworks
- embedding models

for BE-004.

---

# 25. Documentation

Update documentation only for BE-004.

Document:

- SHA-256 purpose
- EXIF extraction purpose
- pHash purpose
- distinction between cryptographic and perceptual fingerprints
- missing EXIF behavior
- where results are persisted
- that BE-004 does not make fraud/duplicate decisions

Do not document future functionality as if it already exists.

---

# 26. Files

Inspect before changing.

Likely areas:

```text
backend/engines/hashing/
backend/engines/metadata/
backend/services/
backend/db/models.py
backend/schemas/
backend/repositories/
alembic/
tests/
docs/
```

Only modify/create files necessary for BE-004.

Do not create speculative abstractions for BE-005+.

---

# 27. Schema Migration

If database changes are necessary:

1. Create a proper Alembic migration.
2. Ensure upgrade works on a clean database.
3. Ensure downgrade works where appropriate.
4. Do not manually modify the database outside migrations.
5. Do not destroy existing evidence data.
6. Do not redesign unrelated tables.

Do not silently rely on:

```python
Base.metadata.create_all()
```

to create production schema changes.

---

# 28. Anti-Shortcut Gate

Before declaring BE-004 complete, explicitly verify:

- SHA-256 is calculated from real stored bytes.
- EXIF comes from the actual image.
- pHash comes from the actual image.
- Values are persisted in PostgreSQL.
- Tests independently verify the calculations.
- No fingerprint is client-controlled.
- No fake metadata exists.
- No fake analysis result exists.
- No future milestone logic was added.
- No existing milestone was rewritten unnecessarily.

If any of these are false, BE-004 is not complete.

---

# 29. AI Implementation Discipline

Because this project is being developed with an AI coding agent:

### Inspect before changing

Do not blindly create files or rewrite existing implementations.

Understand:

- current model structure;
- current StorageService;
- current database session;
- current API conventions;
- current test fixtures;
- existing engine boundaries.

### Reuse before creating

If an abstraction already exists, use it.

Do not create:

```text
StorageService2
EvidenceRepository2
HashService2
MetadataService2
```

or equivalent duplicate abstractions.

### No unrelated refactoring

Do not:

- reformat unrelated files;
- rename unrelated modules;
- replace working infrastructure;
- upgrade dependencies without necessity;
- redesign BE-001/BE-002/BE-003.

### No scope creep

Do not implement BE-005 or later functionality simply because it appears useful.

### No fake tests

Do not change tests simply to make an incorrect implementation pass.

### No hiding failures

Do not:

- catch errors and silently return success;
- replace failures with null without preserving meaning;
- suppress important exceptions;
- skip difficult cases simply to achieve green tests.

### No premature optimization

Correctness comes first.

---

# 30. Definition of Done

BE-004 is complete only when:

- [ ] SHA-256 is calculated from the actual stored original object.
- [ ] SHA-256 is a complete lowercase 64-character hexadecimal digest.
- [ ] SHA-256 has deterministic behavior.
- [ ] SHA-256 is persisted.
- [ ] SHA-256 can be queried from the database.
- [ ] EXIF is actually extracted from the original image.
- [ ] Missing EXIF is represented honestly.
- [ ] Known EXIF values are correctly extracted.
- [ ] GPS EXIF is extracted when present.
- [ ] EXIF timestamps are extracted when present.
- [ ] EXIF does not automatically imply authenticity or fraud.
- [ ] pHash is generated using a real perceptual hashing implementation.
- [ ] pHash is deterministic.
- [ ] pHash is persisted.
- [ ] Original evidence bytes remain unchanged.
- [ ] Processing can be invoked repeatedly without contradictory results.
- [ ] Real PostgreSQL integration is tested.
- [ ] Real MinIO integration is tested.
- [ ] Independent tests verify SHA-256 correctness.
- [ ] Independent tests verify EXIF correctness.
- [ ] Tests verify pHash persistence/determinism.
- [ ] Existing BE-001 functionality still passes.
- [ ] Existing BE-002 functionality still passes.
- [ ] Existing BE-003 functionality still passes.
- [ ] No fake/demo values are used.
- [ ] No BE-005+ functionality is implemented.

---

# Verification Commands

Run:

```bash
python -m alembic upgrade head
```

Then run the focused BE-004 tests.

Then run:

```bash
python -m pytest -q
```

Verify the API/application still starts.

If Docker infrastructure is required:

```bash
docker compose up -d
```

Verify PostgreSQL and MinIO are healthy.

Do not claim completion based only on static analysis.

---

# Final Agent Response

After implementation, report ONLY:

1. Files changed
2. BE-004 functionality implemented
3. Database/schema changes
4. Tests executed
5. Test results
6. Any warnings
7. Any blockers
8. Confirmation that:
   - real SHA-256 was calculated;
   - real EXIF was extracted;
   - real pHash was calculated;
   - results were persisted;
   - original evidence was not modified;
   - no fake/demo results were used;
   - no BE-005+ functionality was implemented.

If tests fail:

- report the exact failure;
- fix only the BE-004 issue responsible;
- rerun the relevant tests;
- do not claim completion while required tests are failing.

---

# Milestone Boundary

BE-004 establishes evidence fingerprints.

It does NOT determine whether evidence is:

- genuine;
- fraudulent;
- duplicated;
- geographically valid;
- temporally valid;
- high risk;
- low risk.

Those conclusions require later independent signals and the Fusion Engine.

The output of BE-004 is:

```text
Evidence
   │
   ├── SHA-256
   │
   ├── EXIF metadata
   │
   └── pHash
```

These become foundational inputs for later evidence intelligence.

Next milestone:

**BE-005 — Async Analysis Jobs**