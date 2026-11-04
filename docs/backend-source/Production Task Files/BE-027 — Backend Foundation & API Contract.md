# BE-027 — Backend Foundation & Core API Stabilization

**Project:** Proof-Of-Action (PoA)  
**Task ID:** BE-027  
**Category:** Backend / Architecture / API / Database  
**Priority:** Critical  
**Status:** Not Started  
**Depends On:** Previous completed backend tasks  
**Blocks:** Subsequent Evidence, Review, Audit, Geofence and Intelligence tasks

---

# 1. TASK OBJECTIVE

Establish and stabilize the core backend foundation of Proof-Of-Action so that all subsequent backend features can be implemented on top of a predictable, validated, testable API and database architecture.

This task is NOT intended to build every backend feature.

The objective is to ensure that the backend currently has a clean and reliable foundation consisting of:

- Backend application startup
- Configuration management
- Database connectivity
- PostgreSQL/PostGIS integration
- Core database models
- Database migrations
- API routing structure
- Request/response validation
- Error handling
- Project resource APIs
- Health checks
- Basic automated tests
- Developer documentation

The resulting backend should provide a stable foundation for later implementation of:

- Evidence ingestion
- Evidence integrity analysis
- pHash comparison
- EXIF analysis
- Image metadata analysis
- Risk scoring
- Geofence verification
- Reviewer workflows
- Audit ledger
- Background processing
- Analytics
- AI-assisted evidence intelligence

Do NOT attempt to implement those advanced systems as part of this task.

---

# 2. IMPORTANT PROJECT CONTEXT

Proof-Of-Action is an Evidence Intelligence Platform intended to help government reviewers and supervisors verify submitted evidence and monitor project/action progress.

The backend will eventually sit behind a system containing components such as:

- Reviewer Dashboard
- Project Dossiers
- Review Queue
- Evidence Management
- Before/After Evidence Viewer
- Geofence Map
- Audit Log / Audit Ledger
- Analytics
- Field Inspection / Mobile workflows
- Live Ingestion Sandbox
- Evidence Intelligence Engine

The backend must therefore be designed around real domain entities rather than temporary demonstration endpoints.

The current repository is the source of truth.

Before changing anything, inspect what already exists.

Do NOT assume that the repository is empty or that the architecture described in this task is identical to the current implementation.

---

# 3. PRIMARY GOAL

After BE-027 is completed, the following architecture should work reliably:

    Client
       |
       v
    API Router
       |
       v
    Request Validation
       |
       v
    Service / Business Layer
       |
       v
    Database / Repository Layer
       |
       v
    PostgreSQL + PostGIS

The exact implementation may differ depending on the existing repository architecture.

The important requirement is that responsibilities are separated clearly enough that future features do not turn the backend into one large collection of route handlers.

---

# 4. FIRST STEP — REPOSITORY AUDIT

Before modifying code, perform a complete backend audit.

Inspect:

- Backend directories
- Backend entry points
- API routes
- Database configuration
- ORM/query layer
- Existing models
- Existing schemas
- Existing migrations
- Authentication
- Authorization
- Environment configuration
- CORS
- Storage configuration
- Background workers
- Existing tests
- Docker configuration
- Package/dependency configuration
- Existing frontend API clients
- Existing API contracts

Determine:

1. What backend framework is currently being used?
2. What is the backend entry point?
3. How is the database currently accessed?
4. Which ORM/query library is currently being used?
5. Which database is configured?
6. Is PostGIS already configured?
7. Which models already exist?
8. Which API routes already exist?
9. Which functionality is already working?
10. Which functionality is incomplete or broken?
11. Which migrations already exist?
12. Which tests already exist?
13. Which parts of the existing architecture should be preserved?

DO NOT replace existing architecture simply because another architecture may look cleaner.

If the current implementation is already suitable, extend it.

---

# 5. ARCHITECTURAL RULE

Follow the existing project's technology choices wherever possible.

The expected PoA backend direction is:

- PostgreSQL
- PostGIS
- ORM / typed database access
- Schema validation
- API-first architecture
- Environment-based configuration

Potential technologies previously considered for PoA include:

- FastAPI
- PostgreSQL
- PostGIS
- SQLAlchemy
- Pydantic
- Drizzle
- Zod
- Supabase

However:

**DO NOT blindly introduce these technologies.**

The actual repository determines which stack is currently in use.

If the repository already uses an appropriate stack, preserve it.

If a technology replacement is genuinely required, explain why before making a broad architectural change.

---

# 6. BACKEND DIRECTORY STRUCTURE

Review the existing directory structure and normalize it only where necessary.

A reasonable architecture may resemble:

    backend/
    ├── app/
    │   ├── api/
    │   │   ├── routes/
    │   │   └── dependencies/
    │   │
    │   ├── core/
    │   │   ├── config/
    │   │   ├── security/
    │   │   └── logging/
    │   │
    │   ├── db/
    │   │   ├── models/
    │   │   ├── repositories/
    │   │   └── migrations/
    │   │
    │   ├── schemas/
    │   ├── services/
    │   ├── workers/
    │   └── main.*
    │
    ├── tests/
    ├── .env.example
    └── README.md

This is an architectural reference only.

Do NOT force this exact structure onto an existing repository if doing so would create unnecessary churn.

---

# 7. DATABASE FOUNDATION

The backend must use the project's configured PostgreSQL database.

PostGIS must remain available because future PoA functionality requires geographic operations.

The following core domain entities must exist or have an appropriate equivalent:

## 7.1 User

Represents a system user.

The final authentication system may expand this model later.

At minimum, establish a stable identity representation.

Potential fields include:

- id
- name
- email
- role
- created_at
- updated_at

Do not overbuild user management during this task.

---

## 7.2 Project

Represents a government/development project being monitored through PoA.

Potential fields:

- id
- project identifier
- name
- description
- status
- created_at
- updated_at

The exact naming must follow the existing schema.

The Project entity should be designed to support future relationships with:

- Evidence
- Reviews
- Audit events
- Locations
- Milestones
- Dossiers

---

## 7.3 Evidence

Represents evidence submitted against a project/action.

For BE-027, only establish the foundational entity.

Do NOT implement full evidence intelligence yet.

The model should be extensible for future fields such as:

- file reference
- MIME type
- original filename
- captured_at
- uploaded_at
- uploader
- project
- latitude
- longitude
- pHash
- EXIF information
- integrity score
- risk score
- analysis status

Do not implement all of those unless the repository already requires them.

---

## 7.4 Review

Represents reviewer interaction with submitted evidence/project information.

The foundation should support future states such as:

- pending
- approved
- rejected
- needs_review

Do not build the complete reviewer workflow yet.

---

## 7.5 AuditLog

Represents an immutable record of important system actions.

The eventual PoA audit system is a major feature, but this task only establishes the foundation.

Potential fields:

- id
- actor/user
- action
- entity type
- entity ID
- timestamp
- metadata

Do not implement cryptographic audit chaining in BE-027 unless it already exists.

That belongs to the dedicated audit task.

---

# 8. DATABASE RELATIONSHIPS

Establish sensible relationships between core entities.

At minimum:

    User
      |
      +---- creates/submits ----> Evidence
      |
      +---- performs -----------> Review
      |
      +---- generates ----------> AuditLog


    Project
      |
      +---- has ---------------> Evidence
      |
      +---- has ---------------> Review
      |
      +---- has ---------------> AuditLog

Use foreign keys where appropriate.

Avoid unnecessary duplication of data.

Ensure deletion/update behavior is intentional.

Do not use cascading deletion blindly for audit records.

---

# 9. DATABASE MIGRATIONS

Verify the project's migration system.

The schema must be reproducible from migrations.

Requirements:

- Existing migration history must be preserved.
- New schema changes must use migrations.
- Do not manually modify production-like databases.
- Do not delete migration history.
- Do not reset the database if existing development data may be lost.
- Do not use destructive migration shortcuts.

Verify that a clean database can be initialized using the repository's documented migration process.

If the existing migration system is broken, fix it as part of this task.

---

# 10. DATABASE CONNECTIVITY

Create or verify a clean database connection layer.

Requirements:

- Connection configuration comes from environment variables.
- Credentials must never be hardcoded.
- Connection failures must be reported clearly.
- Connections must be reused appropriately.
- Application shutdown must release resources correctly.
- Database errors must not expose credentials.

The backend should be able to distinguish between:

    API running
    Database available
    Database unavailable

---

# 11. HEALTH ENDPOINT

Implement or stabilize:

    GET /api/health

The endpoint must verify that the backend is alive.

Where appropriate, it should also verify database connectivity.

Example conceptual response:

    {
      "status": "ok",
      "service": "poa-backend",
      "version": "...",
      "database": "connected"
    }

The exact response format should follow existing project conventions.

Do not expose:

- Database URLs
- Passwords
- Secrets
- Internal filesystem paths
- Stack traces
- Infrastructure credentials

If the database is unavailable, return an appropriate failure status rather than falsely reporting the backend as completely healthy.

---

# 12. API VERSIONING / ROUTING

Establish a predictable API namespace.

Preferred direction:

    /api/...

If the repository already uses:

    /api/v1/...

preserve that convention.

Do not introduce multiple incompatible API prefixes.

All new routes should follow the established routing convention.

---

# 13. PROJECT API

Implement a complete minimal Project API.

At minimum, support:

    POST /api/projects

    GET /api/projects

    GET /api/projects/{id}

If appropriate to the existing architecture, also support:

    PATCH /api/projects/{id}

Do not implement unnecessary CRUD operations simply for completeness.

---

# 14. CREATE PROJECT

The create endpoint must:

1. Validate the request.
2. Validate required fields.
3. Create the database record.
4. Return the persisted resource.
5. Return a proper HTTP status.
6. Handle database failures safely.

The returned ID must be the actual persisted database ID.

Do not return fake/generated-in-memory objects.

---

# 15. LIST PROJECTS

The project list endpoint must:

- Retrieve real records from PostgreSQL.
- Return validated response objects.
- Handle an empty database correctly.
- Avoid exposing internal database structures.
- Follow existing pagination conventions if they already exist.

Do not introduce complicated pagination infrastructure unless required.

However, structure the endpoint so pagination can be added later without redesigning the entire API.

---

# 16. GET PROJECT

The project detail endpoint must:

- Validate the project ID.
- Query PostgreSQL.
- Return the actual project.
- Return a proper not-found response when the project does not exist.
- Avoid raw database exceptions.

Expected behavior:

    Existing ID
        -> 200

    Valid but nonexistent ID
        -> 404

    Invalid ID
        -> 400/422 depending on framework conventions

---

# 17. REQUEST VALIDATION

Every new API endpoint must have explicit request validation.

Validate:

- Required fields
- Data types
- String lengths
- Enumerations where applicable
- IDs
- Dates/timestamps
- Optional fields

Do not accept arbitrary unvalidated JSON when a structured schema can be defined.

---

# 18. RESPONSE SCHEMAS

Do not return raw ORM/database objects directly if the project's architecture supports explicit response schemas.

Responses should have stable API contracts.

This is important because the frontend will eventually depend on these contracts.

Avoid leaking:

- Internal ORM fields
- Password hashes
- Internal database metadata
- Debug fields
- Internal exception information

---

# 19. ERROR HANDLING

Establish consistent API errors.

At minimum, handle:

- Validation errors
- Authentication errors where applicable
- Authorization errors where applicable
- Resource not found
- Database failures
- Unexpected server errors

The client should receive controlled responses.

Never expose development stack traces in production responses.

Errors should be useful enough for frontend developers to understand what went wrong.

---

# 20. CONFIGURATION MANAGEMENT

Review the current configuration system.

Environment-specific values must not be hardcoded.

Check:

- DATABASE_URL
- API environment
- API host/port
- CORS origins
- Authentication configuration
- Storage configuration
- External service configuration

Update:

    .env.example

where necessary.

Do not add real secrets to `.env.example`.

Do not commit:

- API keys
- passwords
- tokens
- private keys
- service credentials

---

# 21. CORS

Review the current CORS configuration.

It must allow the legitimate PoA frontend development environment without opening the backend unnecessarily to every origin.

Avoid blindly using:

    *

if credentials/authentication are involved.

Do not break the existing frontend integration.

---

# 22. AUTHENTICATION / AUTHORIZATION

Audit the current authentication system.

If authentication is already implemented:

- Preserve it.
- Verify that protected routes use it correctly.
- Do not replace it unnecessarily.

If authentication is not yet implemented:

- Establish only the architectural hooks required for future authentication.
- Do not build a complete authentication platform inside BE-027 unless the repository already requires it.

Future PoA roles may include:

- Admin
- Government reviewer
- Supervisor
- Field inspector
- Project authority

Do not invent complicated RBAC rules prematurely.

---

# 23. LOGGING

Verify that backend logging is usable.

Logs should help developers diagnose:

- Startup failures
- Database connection failures
- API failures
- Background task failures

Do not log:

- Passwords
- Tokens
- API keys
- Authentication headers
- Sensitive evidence content

---

# 24. TESTING STRATEGY

Implement or improve automated backend tests.

At minimum, cover:

## Health

    GET /api/health

Verify:

- Backend responds.
- Database status is correct.

---

## Project creation

Test:

    POST /api/projects

Verify:

- Valid input succeeds.
- Invalid input fails.
- Database record is actually created.

---

## Project retrieval

Test:

    GET /api/projects/{id}

Verify:

- Existing project returns correctly.
- Missing project returns 404.
- Invalid ID is handled correctly.

---

## Project listing

Test:

    GET /api/projects

Verify:

- Empty database works.
- Existing projects are returned.
- Response conforms to schema.

---

## Error handling

Test:

- Invalid request body
- Missing required field
- Invalid project ID
- Non-existent project
- Database failure where practical

---

# 25. TEST DATABASE SAFETY

Tests must not accidentally destroy the user's real development database.

Use:

- Dedicated test database
- Test schema
- Transaction rollback
- Appropriate test fixtures

depending on the existing project architecture.

Do not run destructive commands against the normal development database.

---

# 26. BACKGROUND PROCESSING

Inspect the current background worker infrastructure.

Possible PoA future architecture includes:

    API
      |
      v
    Queue
      |
      v
    Worker
      |
      v
    Evidence Analysis

For BE-027:

- Preserve existing worker infrastructure.
- Fix obvious integration problems if required.
- Do not implement the complete evidence-processing pipeline.
- Do not introduce Redis/Celery/RQ/BullMQ solely because they may be useful later.

If no worker currently exists, document the integration point for future tasks.

---

# 27. STORAGE

Inspect how file/object storage is currently configured.

Potential future evidence storage may use:

- Supabase Storage
- S3-compatible storage
- Local development storage

For BE-027:

- Do not build the complete evidence storage system.
- Do not upload real evidence as part of tests unless the repository already supports it.
- Ensure the architecture leaves a clean integration point for evidence storage.

---

# 28. POSTGIS

Verify whether PostGIS is correctly enabled.

Do not implement the complete geofence engine.

Only establish that the database foundation is capable of supporting geographic fields and queries.

If the repository already contains geographic models:

- Preserve them.
- Verify their migrations.
- Verify PostGIS compatibility.

If PostGIS is currently broken, fix the configuration/migration problem if it is directly required for the backend foundation.

---

# 29. API DOCUMENTATION

If the backend framework automatically provides API documentation, ensure it works.

For example:

    OpenAPI
    Swagger
    ReDoc

Verify that the new Project endpoints appear correctly.

Documentation should show:

- Endpoint
- HTTP method
- Request schema
- Response schema
- Error responses

Do not manually duplicate generated documentation unless the project already follows that practice.

---

# 30. FRONTEND COMPATIBILITY

Inspect existing frontend API calls before changing endpoint contracts.

Do not break existing working frontend functionality.

If an endpoint already exists:

- Preserve its contract where possible.
- Improve its implementation without unnecessarily changing its response format.

If a breaking API change is unavoidable:

- Document it clearly.
- Update the frontend client accordingly.
- Update tests.

---

# 31. DEPENDENCY DISCIPLINE

Do not add dependencies unless they are actually required.

Before adding a package:

1. Check whether an existing dependency already provides the required functionality.
2. Check whether the functionality can be implemented using the existing stack.
3. Add the dependency only if justified.

Do not perform broad package upgrades as part of this task.

Do not upgrade major framework versions unless absolutely necessary.

---

# 32. SECURITY REQUIREMENTS

The backend must follow basic security hygiene.

Never:

- Hardcode secrets.
- Commit credentials.
- Return passwords.
- Return tokens unnecessarily.
- Log credentials.
- Expose raw database errors.
- Expose filesystem internals.
- Disable validation for convenience.
- Disable authentication simply to make tests pass.

Development shortcuts must not silently become production behavior.

---

# 33. PERFORMANCE REQUIREMENTS

Do not prematurely optimize.

However:

- Avoid unnecessary database queries.
- Avoid N+1 queries where obvious.
- Use appropriate indexes for frequently queried identifiers.
- Use database constraints for important invariants.
- Do not load entire large tables unnecessarily.

The evidence system will eventually deal with potentially large datasets, so the foundation must not introduce obviously inefficient patterns.

---

# 34. DATA INTEGRITY

Use database constraints where appropriate.

Examples:

- NOT NULL
- UNIQUE
- Foreign keys
- Appropriate indexes
- Valid enum/status values

Application validation alone should not be relied upon for critical database invariants.

---

# 35. TRANSACTION SAFETY

Database writes that represent one logical operation should be atomic where appropriate.

For example:

    Create Project
        |
        +-- Project record
        |
        +-- related initialization

If multiple writes are required, use the project's transaction mechanism.

Do not leave partially created resources when an operation fails halfway through.

---

# 36. AUDITABILITY

Do not implement the final PoA audit ledger yet.

However, design the foundation so important mutations can later generate:

    AuditLog

events.

Do not silently couple every endpoint to an incomplete audit system.

Document the integration point if necessary.

---

# 37. FILES THAT MAY NEED TO CHANGE

Depending on the existing repository, likely areas include:

- Backend entry point
- API router
- Project routes
- Database configuration
- Database models
- Schemas
- Services
- Migrations
- Tests
- `.env.example`
- Backend README
- API documentation

Do not modify unrelated frontend/UI files unless required to preserve API compatibility.

---

# 38. FILES THAT MUST NOT BE MODIFIED UNNECESSARILY

Avoid unrelated changes to:

- Frontend design
- UI components
- Authentication UI
- Mobile application
- ML models
- Evidence analysis code
- Deployment configuration
- Infrastructure
- Docker setup
- WSL configuration
- Personal developer environment
- Generated files

Only modify them if BE-027 genuinely requires it.

---

# 39. DEVELOPMENT WORKFLOW

Follow this sequence.

## Phase 1 — Inspect

Understand the current implementation.

Do not code immediately.

---

## Phase 2 — Plan

Identify:

- Existing components to reuse
- Missing components
- Broken components
- Required migrations
- Required API changes
- Required tests

---

## Phase 3 — Implement Foundation

Implement only the required backend foundation.

---

## Phase 4 — Database Verification

Verify:

- Connection
- Migration
- Models
- Constraints
- PostgreSQL
- PostGIS

---

## Phase 5 — API Verification

Verify:

- Health
- Project creation
- Project listing
- Project retrieval
- Validation
- Error handling

---

## Phase 6 — Testing

Run:

- Unit tests
- Integration tests
- API tests
- Type checking
- Linting

Use the repository's existing commands.

---

## Phase 7 — Regression Check

Verify that existing PoA functionality still works.

Do not declare success merely because the new tests pass.

---

# 40. DEFINITION OF DONE

BE-027 is complete only when ALL applicable requirements below are satisfied.

### Backend

- [ ] Backend starts successfully.
- [ ] Existing backend architecture has been audited.
- [ ] Core backend structure is stable.
- [ ] Configuration is environment-based.
- [ ] No secrets are hardcoded.

### Database

- [ ] PostgreSQL connection works.
- [ ] PostGIS availability is verified.
- [ ] Core models are present or appropriately represented.
- [ ] Migrations work.
- [ ] Existing migration history is preserved.
- [ ] Database constraints are appropriate.

### API

- [ ] Health endpoint works.
- [ ] Project creation works.
- [ ] Project listing works.
- [ ] Project retrieval works.
- [ ] Validation works.
- [ ] Not-found handling works.
- [ ] Errors are controlled and consistent.

### Testing

- [ ] Health endpoint tested.
- [ ] Project creation tested.
- [ ] Project retrieval tested.
- [ ] Project listing tested.
- [ ] Validation tested.
- [ ] Error handling tested.
- [ ] Tests do not destroy the real development database.

### Integration

- [ ] Existing frontend integration has been checked.
- [ ] Existing backend functionality has not been unnecessarily broken.
- [ ] API documentation reflects the new endpoints.

### Documentation

- [ ] Backend setup instructions are accurate.
- [ ] Environment variables are documented.
- [ ] Migration instructions are documented.
- [ ] Test commands are documented.
- [ ] API foundation is documented.

---

# 41. ACCEPTANCE TEST

The following scenario must work from a clean running development environment:

    1. Start PostgreSQL/PostGIS.

    2. Start the PoA backend.

    3. Call:
       GET /api/health

    4. Receive a successful health response.

    5. Create a Project through the API.

    6. Verify that the returned Project has a real database ID.

    7. Query PostgreSQL and confirm that the record exists.

    8. Retrieve the Project through:
       GET /api/projects/{id}

    9. Retrieve the Project through:
       GET /api/projects

    10. Send malformed Project data.

    11. Verify that validation rejects it.

    12. Request a nonexistent Project.

    13. Verify that the API returns an appropriate 404.

    14. Run the complete backend test suite.

    15. Confirm that existing PoA functionality still works.

---

# 42. DO NOT FAKE SUCCESS

This is critical.

Do NOT mark BE-027 complete if:

- The API returns mocked projects.
- Data is stored only in memory.
- The health endpoint always says the database is healthy.
- Tests use fake implementations instead of the actual database layer.
- The project API bypasses the existing architecture.
- Migrations were skipped.
- Existing functionality was silently removed.
- Tests were deleted to make the build pass.
- Errors were hidden instead of fixed.

The purpose of this task is to establish a **real backend foundation**.

---

# 43. STOP CONDITIONS

Immediately stop and report instead of making a risky architectural change if:

- The existing backend architecture is substantially different from the expected architecture.
- The database cannot be safely migrated without destroying existing data.
- Existing migrations are inconsistent.
- A required dependency has incompatible versions.
- Authentication is deeply coupled to the current architecture.
- A frontend contract would require a breaking change.
- PostGIS cannot be enabled without infrastructure changes.
- A major rewrite appears necessary.

Do not improvise a replacement architecture.

Report the blocker and wait for direction.

---

# 44. FINAL REPORT

When implementation is complete, provide a final report in exactly this general structure:

## BE-027 Implementation Report

### 1. Repository Audit

- Backend framework:
- Entry point:
- Database:
- ORM/query layer:
- Existing API structure:
- Existing migration system:
- Existing test system:

### 2. Changes Made

List every meaningful file/component changed.

### 3. Database

- Models added/modified:
- Migrations:
- Constraints:
- PostGIS status:

### 4. API

- Endpoints added:
- Endpoints modified:
- Request schemas:
- Response schemas:
- Error handling:

### 5. Tests

Report the exact tests/commands executed and their results.

Example:

    Backend startup: PASS
    Health endpoint: PASS
    Project creation: PASS
    Project retrieval: PASS
    Validation: PASS
    Migration check: PASS
    Test suite: PASS

Do not claim PASS for anything that was not actually tested.

### 6. Existing Functionality

State whether existing PoA functionality was verified and whether any regressions were found.

### 7. Issues / Blockers

List unresolved problems honestly.

### 8. Technical Debt

List anything intentionally deferred.

### 9. Next Recommended Task

Recommend the next BE task based on the actual repository state after BE-027.

**Do not implement the next task automatically.**

---

# 45. FINAL INSTRUCTION

Treat BE-027 as a **foundation/stabilization task**, not as permission to build the entire PoA backend.

Prioritize:

    correctness
    > stability
    > compatibility
    > testability
    > maintainability
    > feature breadth

Inspect first.

Reuse existing working code.

Make the smallest architectural changes necessary.

Test every meaningful change.

Do not destroy existing data.

Do not fake functionality.

Do not move on to the next BE task until BE-027 is genuinely complete.