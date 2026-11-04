# PoA — Codebase Cleanup, Efficiency & Deferred Fixes

## Objective

Perform a controlled **post-BE-008 codebase cleanup and hardening pass** on the Proof-of-Action backend.

The goal is to:

1. Implement the currently queued/deferred fixes.
2. Remove genuinely unnecessary files and dead code.
3. Clean up duplication and obvious inefficiencies.
4. Improve maintainability, consistency, and reliability.
5. Preserve all completed BE-001 through BE-008 functionality.
6. Keep the implementation production-oriented without implementing BE-009+ functionality.

This is **not a new milestone**.

Do not add new product functionality during this pass.

---

# Engineering Integrity Gate

**Do not interpret "clean up" as "rewrite everything."**

Before changing anything:

- Inspect the existing repository.
- Understand existing architecture and contracts.
- Identify actual dead/unnecessary code before deleting it.
- Preserve working abstractions.
- Prefer small, justified changes.
- Do not perform speculative refactoring.
- Do not change API contracts unless required for a genuine bug fix.
- Do not weaken validation to make tests pass.
- Do not hide errors.
- Do not replace real functionality with mocks or placeholders.

Every existing capability must continue performing its real operation.

Do not introduce:

- fake results
- hardcoded values
- simulated analysis
- placeholder scores
- fake confidence
- mock success paths
- unnecessary abstractions
- unnecessary dependencies

---

# Completed Milestones

These are COMPLETE and must remain functional:

```text
BE-001 ✅ Database Foundation
BE-002 ✅ Object Storage
BE-003 ✅ Evidence Upload
BE-004 ✅ SHA-256 / EXIF / pHash
BE-005 ✅ Async Analysis Jobs
BE-006 ✅ Embeddings / Duplicate Intelligence
BE-007 ✅ Project / Activity / Claim / Geographic Context
BE-008 ✅ Temporal Intelligence
```

Do not reopen or redesign completed milestones unless a genuine issue is discovered during this cleanup.

---

# 1. Implement the Deferred Fix Queue

Apply only the currently queued fixes.

## FIX-001 — BE-006 deterministic latest embedding selection

Current known issue:

The latest embedding lookup relies on:

```text
MAX(created_at)
```

If multiple AnalysisResult rows for the same evidence have exactly the same `created_at`, the query can theoretically select multiple rows.

Fix this deterministically.

Requirements:

- Inspect the current BE-006 implementation first.
- Introduce a deterministic tie-breaker.
- Prefer an existing unique/monotonic identifier if appropriate.
- Ensure exactly one latest embedding is selected per evidence.
- Preserve current pgvector behavior.
- Do not change embedding dimensionality.
- Do not change the CLIP model.
- Do not change duplicate-match semantics.

Add a regression test that creates the timestamp-tie scenario and verifies deterministic selection.

---

# 2. Fix BE-005 Worker Crash Recovery

Current known issue:

BE-005 uses a Redis processing-list pattern where a worker crash can leave a message stranded in the processing list.

Implement a minimal reliable recovery mechanism.

Requirements:

- Inspect the existing Redis queue implementation.
- Do not replace Redis.
- Do not introduce another queue system.
- Do not redesign the entire worker architecture.
- Preserve existing job lifecycle states.
- Preserve duplicate-delivery protection.

The system should be able to identify and recover abandoned processing jobs/messages safely.

Recovery must be:

- deterministic
- idempotent
- safe against duplicate processing
- observable through existing job state

Do not mark jobs completed when processing did not actually succeed.

Add integration tests for:

- normal processing
- worker failure/interruption scenario where practical
- abandoned processing item
- successful recovery
- duplicate recovery attempt
- already-completed job

If a true crash simulation cannot be safely reproduced in the test environment, test the recovery mechanism at the Redis/job-state level rather than faking a successful worker result.

---

# 3. BE-003 Upload Hardening

Improve the existing evidence-upload implementation without changing its public contract.

Inspect current BE-003 behavior first.

Implement only justified hardening:

## MIME/header consistency

Verify that:

```text
declared Content-Type
+
actual file signature/content
+
Pillow-decoded image format
```

are consistent.

Do not trust multipart MIME alone.

Reject mismatches clearly.

## Streaming / memory handling

Inspect the current upload implementation.

If the current implementation loads the entire file into memory unnecessarily, improve it where practical without breaking:

- SHA-256 calculation
- image validation
- quarantine storage
- database persistence
- existing tests

Do not over-engineer this into a new upload subsystem.

## Exception handling

Replace unnecessarily broad exception handling with narrower exceptions where practical.

Do not suppress unexpected errors.

Failures must remain visible and must not be converted into successful responses.

Add tests for:

- MIME mismatch
- invalid file signature
- valid image
- malformed image
- oversized file
- empty file
- unsupported type
- persistence/storage failure cleanup

Preserve the existing BE-003 API contract.

---

# 4. Repository Cleanup

Perform a full repository inspection.

Look for:

- obsolete files
- abandoned prototypes
- temporary files
- local databases
- generated artifacts
- duplicate configuration files
- unused scripts
- stale documentation
- dead modules
- unused imports
- unused functions
- unreachable code
- obsolete comments
- duplicate utilities
- obsolete migrations
- accidental IDE files
- cache directories
- test artifacts

Examples of things to investigate:

```text
*.db
*.sqlite
__pycache__/
.pytest_cache/
.coverage
*.log
temporary exports
debug files
old prototype modules
unused scripts
```

### Important

Do NOT blindly delete files.

For every candidate:

1. Determine whether it is tracked.
2. Determine whether it is referenced.
3. Determine whether it is required by tests/runtime/deployment.
4. Determine whether it is part of Alembic history.
5. Only delete it if it is genuinely unnecessary.

### Alembic

Never delete an existing migration merely because it looks old.

Alembic migration history must remain intact.

If a migration is obsolete but already part of the migration chain, leave it alone unless there is a very strong reason to change migration history.

---

# 5. Python Code Cleanup

Review the backend for obvious code-quality issues.

Clean up:

- unused imports
- unused variables
- dead functions
- duplicate helper logic
- inconsistent naming
- unnecessary type conversions
- unnecessary database queries
- unnecessarily repeated validation
- overly broad exceptions
- redundant comments
- stale docstrings

Prefer existing project conventions.

Do not introduce a large framework or abstraction merely to make code "cleaner."

---

# 6. Database Query Efficiency

Review database-heavy code from BE-001 through BE-008.

Look for obvious inefficiencies such as:

```text
N+1 queries
repeated existence queries
unnecessary full-table loads
missing filters
unnecessary COUNT queries
queries that fetch columns never used
```

Only optimize issues that are clearly real.

Do not prematurely optimize every query.

Pay particular attention to:

- duplicate intelligence queries
- latest embedding selection
- nearby evidence queries
- project-scoped evidence queries
- activity/claim listing
- temporal analysis queries

Do not alter query semantics while optimizing.

---

# 7. Redis / Worker Efficiency

Review the existing analysis worker and Redis implementation.

Look for:

- unnecessary Redis round trips
- repeated job lookups
- unsafe acknowledgement behavior
- duplicate processing
- abandoned processing messages
- unbounded retry behavior
- incorrect job state transitions

Preserve:

```text
queued
running
completed
failed
```

and existing retry semantics.

Do not redesign the worker system.

---

# 8. Storage Efficiency

Review MinIO/S3 storage operations.

Check for:

- unnecessary duplicate downloads
- unnecessary uploads
- redundant object copies
- missing cleanup on failure
- unsafe object-key handling
- unnecessary temporary files

Do not change the storage provider abstraction.

Do not break quarantine/trusted lifecycle behavior.

---

# 9. API Consistency

Review existing API endpoints for consistency.

Ensure:

- consistent UUID handling
- consistent HTTP error handling
- consistent response models
- consistent pagination
- consistent validation
- no accidental route collisions
- no unnecessary aliases

Do not change the frozen BE-007 contracts.

Do not remove working endpoints.

Do not add unrelated endpoints.

---

# 10. Pydantic / SQLAlchemy Cleanup

Review current models and schemas.

Look for:

- duplicated schemas
- mutable default values
- stale fields
- inconsistent optional typing
- unnecessary `Any`
- obsolete compatibility code
- stale comments describing old implementations

Be especially careful around:

```text
AnalysisResult.embedding
```

It is a real pgvector field with the configured embedding dimension.

Do NOT revert it to an array/placeholder implementation.

Do not modify database semantics unless required by one of the explicit fixes above.

---

# 11. BE-008 Cleanup

Review the completed temporal implementation for obvious cleanup issues.

Do not redesign temporal intelligence.

Verify:

- missing timestamps remain UNKNOWN
- timezone provenance remains visible
- claim temporal boundaries remain explicit
- no fabricated timestamps exist
- no fraud/risk/confidence scores exist
- no BE-009+ functionality has leaked into BE-008

Remove only genuinely unused helpers/imports/code.

Do not change the established temporal behavior merely for stylistic reasons.

---

# 12. Dependencies

Review:

```text
requirements.txt
```

Remove a dependency only if:

- it is genuinely unused, AND
- it is not required indirectly by the runtime/test/deployment setup.

Do not upgrade packages just because newer versions exist.

Do not introduce dependencies unless required for one of the explicit fixes.

Preserve the current production stack.

---

# 13. Configuration Cleanup

Review:

```text
.env
.env.example
configuration modules
```

Ensure:

- configuration names are consistent
- obsolete settings are removed only if genuinely unused
- secrets are not committed
- `.env.example` contains required non-secret configuration
- development-only values are not accidentally treated as production defaults

Do not expose secrets.

Do not change working environment variable names without necessity.

---

# 14. Tests

After cleanup and fixes, run focused tests for each affected area.

At minimum:

```text
pytest tests/integration/test_be005_*.py
pytest tests/integration/test_duplicate_intelligence.py
pytest tests/integration/test_be007_*.py
pytest tests/integration/test_be008_temporal.py
```

If filenames differ, discover the correct existing test files rather than inventing paths.

Then run:

```text
pytest
```

Also run:

```text
python -m alembic upgrade head
git diff --check
```

If infrastructure is required, verify:

```text
PostgreSQL
PostGIS
Redis
MinIO
```

are actually available.

---

# 15. No Scope Expansion

Absolutely DO NOT implement:

```text
BE-009 Vision Intelligence
BE-010 Evidence Graph
BE-011 Fusion Engine
BE-012 Explainability
BE-013 Human Review
BE-014 Audit Expansion
BE-015 Authentication / RBAC
BE-016 Security Hardening beyond directly relevant cleanup
BE-017 ML
BE-018 Production Deployment
```

Do not add:

- YOLO
- OCR
- object detection
- fraud scoring
- risk scoring
- evidence graph
- fusion engine
- LLM reasoning
- authentication
- frontend
- production infrastructure

unless already existing functionality is required to preserve compatibility.

---

# 16. Git Hygiene

Before committing:

```text
git status
git diff
git diff --check
```

Ensure:

- no secrets
- no local databases
- no temporary files
- no generated caches
- no accidental large binaries
- no unrelated modifications

Do not rewrite Git history.

Do not force-push.

Create a single clean commit for this maintenance pass unless a genuine repository constraint requires otherwise.

Suggested commit:

```text
cleanup: harden and optimize backend
```

---

# Definition of Done

This cleanup pass is complete only when:

- [ ] BE-006 latest-embedding tie-breaker is deterministic.
- [ ] BE-005 abandoned processing recovery is implemented safely.
- [ ] BE-003 upload MIME/content validation is hardened.
- [ ] BE-003 exception handling is appropriately narrowed.
- [ ] Genuine dead/unnecessary files are removed.
- [ ] No required migrations were deleted.
- [ ] Unused imports/functions/code are removed where justified.
- [ ] Obvious database inefficiencies are addressed.
- [ ] Redis/worker inefficiencies are addressed where justified.
- [ ] Storage inefficiencies are addressed where justified.
- [ ] API consistency issues are cleaned up without changing frozen contracts.
- [ ] Pydantic/SQLAlchemy code is cleaned up.
- [ ] BE-008 behavior remains correct.
- [ ] No fake functionality was introduced.
- [ ] No BE-009+ functionality was implemented.
- [ ] Focused tests pass.
- [ ] Full test suite passes.
- [ ] Alembic upgrade passes.
- [ ] `git diff --check` passes.
- [ ] Required infrastructure is verified.
- [ ] No secrets or temporary artifacts are committed.

---

# Final Report

After completing the work, report:

## 1. Deferred fixes implemented

For each fix:

```text
Problem
Change
Files
Tests
```

## 2. Files deleted

List every deleted file and explain why it was confirmed unnecessary.

## 3. Files changed

List every modified file and its purpose.

## 4. Efficiency improvements

List only measurable or clearly justified improvements.

## 5. API compatibility

Confirm whether any existing endpoint contracts changed.

Expected:

```text
No BE-001 through BE-008 API contracts changed.
```

unless a genuine bug fix required it.

## 6. Dependency changes

List additions/removals.

## 7. Tests

Report:

```text
Focused tests: X passed
Full suite: X passed
Alembic: passed/failed
git diff --check: passed/failed
```

## 8. Infrastructure

Report PostgreSQL/PostGIS/Redis/MinIO status.

## 9. Remaining technical debt

List only genuine remaining issues.

## 10. Scope confirmation

Explicitly confirm:

```text
BE-009+ functionality was NOT implemented.
```

Do not claim the cleanup is complete unless the actual repository state and tests support that claim.