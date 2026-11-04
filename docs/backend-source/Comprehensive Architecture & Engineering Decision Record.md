# Proof-Of-Action (PoA)
# Comprehensive Architecture & Engineering Decision Record

**Document type:** Architecture Decision Record (ADR) and Engineering Reference  
**Project:** Proof-Of-Action — Evidence Intelligence Platform  
**Purpose:** Preserve the architecture, product decisions, security requirements, deployment strategy, operational constraints, and release criteria established during the 72-question Grill Me interview.

**Status:** Architecture decisions locked; implementation and production verification remain outstanding in several critical areas.

**Release target:** Working, verified Reviewer journey first. Optional functionality is conditional on release-gate completion.

---

## 1. Document Purpose and Authority

This document is the consolidated record of the decisions made during the PoA architecture interview.

It is intended to serve as the reference for:

- Frontend and backend implementation.
- API contracts and integration.
- Authentication and authorization.
- Evidence ingestion, storage, provenance, and retrieval.
- Intelligence and explainability.
- Human review and decision governance.
- Deployment and database operations.
- Backup, recovery, and failure handling.
- Testing and acceptance.
- Scope control during the two-day release window.

### 1.1 Status terminology

The following distinctions must be maintained throughout implementation.

- **DECIDED:** The architecture or product behavior has been selected.
- **CODE-VERIFIED:** The behavior was identified in the repository or existing implementation.
- **PLANNED:** The behavior is intended but has not yet been verified as implemented.
- **BLOCKED:** A missing dependency or unresolved issue prevents safe release.
- **CONDITIONAL:** The feature may be included only if its dependencies and acceptance tests pass.
- **DEFERRED:** The feature is intentionally excluded from the first release.

A decision being recorded here does not prove that the corresponding implementation is complete.

### 1.2 Source-of-truth hierarchy

Use the following sources when determining actual implementation status:

1. Current source code and migrations on the active repository branch.
2. Tests and their actual execution results.
3. The existing architecture and backend-scope documents.
4. The backend completion and acceptance report.
5. This consolidated architecture record for decisions made during the interview.

If the code contradicts an architecture decision, do not silently assume the architecture has been implemented. Record the discrepancy, correct it, and add an appropriate test.

### 1.3 Existing project references

Repository: `AnujRAuti/Proof-Of-Action-Final`

Branch: `Backend`

Existing architecture document:

https://github.com/AnujRAuti/Proof-Of-Action-Final/blob/Backend/docs/Final%20Architecture.md

Backend completion report:

https://github.com/AnujRAuti/Proof-Of-Action-Final/blob/Backend/docs/BE-037%20Final%20Backend%20Completion%20and%20Acceptance%20Report.md

Backend scope:

`docs/backend-scope.md`

The existing architecture document is a major reference and should be reconciled with this record before implementation work is divided into milestones.

---

# 2. Product Definition

## 2.1 Product purpose

Proof-Of-Action is an evidence intelligence platform intended to help authorized government reviewers and supervisors evaluate whether reported public works or other actions are supported by submitted evidence.

The platform organizes evidence, provenance, integrity checks, relationships, analytical findings, review decisions, and audit history.

It is not an automated fraud verdict system.

Its purpose is to help authorized humans understand:

- What evidence was submitted.
- Which case and project the evidence belongs to.
- Which integrity checks have actually been performed.
- What analytical signals exist.
- Where evidence is missing, inconsistent, or inconclusive.
- How the available evidence relates to the claim being reviewed.
- What previous reviewers decided.
- Why the current reviewer reached a decision.
- What remains uncertain.

## 2.2 Core product principle

**Evidence intelligence supports human judgment; it does not replace human judgment.**

PoA must not treat an algorithmic score, a matching image, a geographic discrepancy, or a graph relationship as an independent verdict.

In particular:

- A matching hash does not prove authenticity.
- A GPS coordinate is a signal, not proof that an action occurred at that location.
- An image-similarity match does not independently establish fraud.
- A missing analysis result is not a negative result.
- A failed integrity check is not automatically proof of misconduct.
- An inconclusive result must remain distinguishable from insufficient evidence.
- A reviewer decision must be attributable to the authenticated human who made it.

## 2.3 Initial demonstration scenario

The first seeded demonstration scenario is public works and infrastructure.

The dataset should use fictional identities, fictional locations, and clearly labelled synthetic evidence.

The seeded case mix should include realistic variation:

- Completed work with supporting evidence.
- Work awaiting review.
- Inconclusive cases.
- Cases with insufficient evidence.
- Cases with pending or unavailable analysis.

These dimensions must remain separate:

1. Case workflow status.
2. Evidence completeness.
3. Analysis execution status.
4. Integrity-check status.
5. Human decision outcome.

The demo must not fabricate findings or imply that synthetic evidence represents a real government investigation.

---

# 3. User Roles and Access Model

PoA recognizes six roles.

| Role | Intended purpose | First-release status |
|---|---|---|
| Citizen | Submit or interact with permitted public-facing workflows | Deferred |
| Field Officer | Capture and submit field evidence | Full workflow deferred |
| Reviewer | Inspect cases, evaluate evidence, and record decisions | Primary release role |
| Supervisor | Read-only oversight and review visibility | Conditional |
| Administrator | Govern platform configuration and access | Restricted provisioning operations only |
| API Client | Authorized machine-to-machine operations | Existing backend capability; public-facing use conditional |

The existence of a role does not mean the corresponding UI or complete workflow is available.

### 3.1 First-release account policy

- No public signup.
- Pre-provisioned, restricted accounts.
- Reviewer account first.
- Optional read-only Supervisor account only if the Reviewer journey passes.
- No frontend role switching.
- No user-controlled role assignment.
- No assumption that a successful login grants access to every project.

### 3.2 Identity and permissions are separate

Supabase Auth establishes the authenticated identity.

PoA independently establishes:

- Whether the corresponding PoA user exists.
- Whether the PoA user is active.
- Which roles the user has.
- Which permissions apply.
- Which project scopes apply.
- Whether the requested operation is permitted.

A valid identity provider session does not automatically imply authorization.

---

# 4. Frontend Architecture

## 4.1 Application structure

The application will use one Next.js application with shared foundations and role-specific shells.

The Reviewer workflow is the first complete experience.

The application should not be split into separate frontend applications for every role during the initial release.

### Selected technologies

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query
- React Hook Form
- Zod
- MapLibre for a future authorized geospatial experience

Only the technologies actually present and configured in the current repository should be treated as implemented dependencies.

## 4.2 Rendering and deployment model

The selected direction is a statically exported Next.js application with client-side API calls.

Potential frontend host: Cloudflare Pages.

This is conditional on verifying that the existing application builds successfully using the static export configuration and that the required routes work on the actual host.

The initial frontend must not depend on:

- Next.js server actions.
- Next.js server-only API routes.
- Next.js middleware.
- Server-rendered request-time data fetching.
- Server-side secret access.

All protected business data must be loaded through FastAPI.

Supabase browser functionality is limited to authentication and session management.

## 4.3 Public environment configuration

The API base URL will be supplied through a build-time public environment variable:

`NEXT_PUBLIC_API_BASE_URL`

Public Supabase project configuration may be exposed through the browser client where required.

No privileged credentials may be placed in:

- Frontend source code.
- Static bundles.
- Public environment variables.
- Browser logs.
- Client-side configuration files.

## 4.4 Case URL contract

Case URLs use:

`/review/case?id=UUID`

This URL format is preserved.

The deployed application must support:

- Opening a case directly in a new tab.
- Refreshing a case page.
- Opening a bookmarked case.
- Invalid case IDs.
- Nonexistent cases.
- Unauthorized cases.
- Expired sessions.

Static-host rewrites must not incorrectly redirect API requests or missing static assets to the main HTML document.

A case UUID is an identifier, not an authorization credential.

## 4.5 Reviewer workspace

The primary journey is:

**Reviewer queue → Case workspace → Evidence and intelligence → Decision → Workflow history**

The case workspace should provide a persistent case header and the following primary sections:

1. Overview
2. Evidence
3. Intelligence
4. Timeline
5. Decision

Relationships may be exposed only if a real, authorized backend relationship API is available and its results can be presented accurately.

If a subsystem is not ready, display an honest unavailable state rather than fake data.

## 4.6 User interface principles

The visual direction is a modern civic-intelligence workspace.

The design should be:

- Light-theme first.
- Evidence-first.
- Calm and restrained.
- Neutral, with navy and teal accents.
- Dense enough for professional review without becoming visually overwhelming.
- Independent of any implied government endorsement.
- Responsive for desktop, tablet, and mobile.
- Accessible in line with WCAG 2.2 AA goals.

Do not use visual treatment that implies an AI result is an official verdict.

## 4.7 Frontend data handling

Use a centralized typed API client.

The API client should own:

- Base URL handling.
- Bearer-token attachment.
- Request and response parsing.
- Standardized error handling.
- 401 behavior.
- 403 behavior.
- Safe handling of unavailable or unknown responses.

Use Zod runtime validation for critical responses, especially:

- Login identity mapping.
- Case details.
- Evidence upload responses.
- Decision responses.
- Workflow history.
- Critical analysis status and integrity status.

TypeScript interfaces alone cannot guarantee that live JSON matches the expected response.

Unknown enum values must not crash the UI or be silently mapped to a known state. Display a safe, neutral unknown-status state and disable actions that depend on the unknown value.

## 4.8 Client-side cache policy

TanStack Query will use short-lived in-memory caching.

Requirements:

- Cache data only within the authenticated user's context.
- Clear or invalidate relevant queries on sign-out.
- Clear or invalidate queries on account changes.
- Invalidate affected records after mutations.
- Never persist private evidence or signed download URLs in durable browser storage.
- Never persist authentication tokens through a second custom storage mechanism.
- Avoid caching authorization-sensitive data across users.
- Reconcile uncertain writes with the server before retrying.

---

# 5. Backend Architecture

## 5.1 API framework

FastAPI is the authoritative business-data gateway.

The API uses versioned REST endpoints under:

`/api/v1`

The frontend must use the actual configured API prefix and deployed base URL. Do not assume local development URL behavior matches production.

## 5.2 Business operations handled by FastAPI

The backend owns:

- Case queues and case details.
- Evidence metadata and uploads.
- Evidence-to-case association.
- Evidence retrieval authorization.
- Integrity checks.
- Analysis job creation and status.
- Fusion and explainability responses.
- Review decisions.
- Case workflow transitions.
- Audit history.
- Authorization and project-scope enforcement.

The browser must not bypass these controls through direct database access.

## 5.3 Authorization architecture

The repository contains a centralized fail-closed authorization evaluator.

Roles and permissions are separate concepts. Administrative access does not automatically grant human decision authority.

Every protected operation must establish:

1. A valid authenticated identity.
2. An active PoA user.
3. The required permission.
4. The correct project or case scope.
5. Any operation-specific policy, including quarantine or state-transition rules.

Do not rely on the presence of a route or a frontend-hidden button as proof of authorization.

## 5.4 Existing backend capabilities

The existing code includes modules for:

- Authentication and principal resolution.
- Centralized authorization.
- Evidence ingestion.
- Storage abstraction.
- Analysis jobs and workers.
- Fusion.
- Explainability.
- Review-case operations.
- Workflow history.
- Field operations.
- Evidence graph operations.
- Context and nearby-evidence queries.

The existence of these modules does not prove that every route is correctly secured or production-ready.

Known gaps and required checks are documented later in this file.

---

# 6. Authentication and Identity

## 6.1 Authentication provider

Supabase Auth is the selected identity provider.

The browser uses the official Supabase client for sign-in and session management.

FastAPI independently verifies the access token.

## 6.2 Production JWT verification requirements

The backend must verify Supabase JWTs using trusted JWKS signature verification.

It must validate:

- Signature.
- Trusted issuer.
- Audience.
- Expiry.
- Accepted signing algorithm.
- Key rotation behavior.

The backend must fail closed if the token is invalid or the identity cannot be established.

Do not accept an unverified JWT payload as proof of identity.

## 6.3 PoA identity mapping

The existing `User` model supports:

- `external_subject`
- `identity_provider`
- Account status
- A uniqueness constraint on the identity-provider/subject pair

After JWT verification, the backend must map the trusted subject to the correct PoA user.

If the mapping is missing, ambiguous, inconsistent, disabled, or suspended, access must be denied.

## 6.4 Current permissions

The backend will resolve the active PoA user and current database-backed permissions and project scopes on every protected request.

This avoids relying on stale role claims in a JWT.

If the database is unavailable and authorization cannot be established, protected actions must fail closed.

For the expected low demo traffic, current authorization checks are preferable to introducing an authorization cache before release.

## 6.5 Session behavior

On a 401 response:

1. Allow the official Supabase client to refresh the session once if appropriate.
2. Retry the original request once.
3. If it still fails, return the user to the sign-in flow.

Do not refresh or retry indefinitely.

Do not treat a 403 as a refreshable authentication failure.

## 6.6 Known implementation gap

The current authentication code supports development bearer tokens and machine API-client credentials. Production Supabase JWT verification is not yet verified as implemented.

The development path must not remain enabled on the shared deployment.

Required work includes the JWT bridge, trusted identity mapping, disabled-user enforcement, and negative authorization tests.

---

# 7. Role Provisioning

## 7.1 First-release policy

Use fixed, pre-provisioned Reviewer and optional read-only Supervisor accounts.

Do not build a full in-app role-management interface for the first release.

Role and project-scope changes must use a controlled, auditable backend or provisioning operation.

## 7.2 Provisioning workflow

The selected approach is a controlled, idempotent server-side provisioning script.

It must:

1. Create or verify the Supabase Auth account.
2. Establish or verify the matching PoA identity mapping.
3. Assign the approved role.
4. Assign the required project scope.
5. Verify effective permissions through the actual backend authorization path.

The script must not overwrite decisions, evidence, or audit history.

## 7.3 Separation from database seeding

Supabase Auth provisioning and database demo seeding are separate processes.

The database seeder must be idempotent and non-destructive.

Running the seeder twice must not duplicate accounts or demo records, reset decisions, or rewrite existing audit history.

Privileged Supabase credentials must remain server-side.

---

# 8. Database Architecture

## 8.1 Primary database

Supabase PostgreSQL is the authoritative persistent database.

The backend uses SQLAlchemy and Alembic.

The schema includes concepts such as:

- Users.
- Projects.
- Claims.
- Evidence.
- Analysis jobs.
- Fusion assessments.
- Review cases.
- Workflow history.
- Audit events.
- Authorization roles and permissions.

PostGIS and pgvector are part of the existing backend architecture. Their availability and compatibility must be verified against the selected Supabase project before deployment.

## 8.2 Runtime connection

Use the Supabase session pooler for the API, provided the actual connection settings and driver support it.

Configure conservative SQLAlchemy pool sizes and bounded connection timeouts.

Calculate total connection capacity across all API processes rather than considering only one process.

## 8.3 Migration connection

Use a separately verified migration credential and connection mode.

Do not run migrations automatically on every Render API startup.

## 8.4 Database roles

Use separate runtime and migration privileges.

The API runtime role should have only the privileges required for normal operations, including the necessary table, sequence, and function access.

The migration credential should be used only for explicit schema changes.

Verify the actual Supabase roles and grants. Separate credentials alone do not guarantee least privilege.

## 8.5 Migration policy

The release sequence is:

1. Back up the database where feasible.
2. Verify the backup procedure.
3. Apply Alembic migrations explicitly.
4. Verify the resulting schema and migration revision.
5. Verify required extensions and permissions.
6. Run the non-destructive seeder separately.
7. Deploy compatible application code.
8. Run the authenticated critical-path smoke test.

Prefer additive, backward-compatible migrations.

Avoid destructive changes during the demonstration window.

Application rollback must not automatically reverse schema changes or erase evidence and decisions.

## 8.6 Database persistence

The database must remain persistent across:

- API restarts.
- Frontend deployments.
- Worker restarts.
- Application rollback.

Do not use ephemeral application filesystem storage for authoritative records.

Do not reset the database during normal startup or recovery.

---

# 9. Evidence Data Model and Association

## 9.1 Existing evidence model

The existing `Evidence` model includes fields such as:

- ID.
- Project association.
- Claim association.
- SHA-256 field.
- Perceptual hash field.
- Location.
- Status.
- Storage key.
- Content and metadata.

The project and claim associations are nullable in the current model.

The current upload endpoint does not yet establish the required case association through the chosen case-context workflow.

## 9.2 Association contract

The browser sends the case ID when uploading evidence from within a case.

FastAPI must:

1. Authenticate the caller.
2. Load the case.
3. Derive the project and claim association from trusted database records.
4. Verify the caller's permission and project scope.
5. Validate the upload.
6. Persist the evidence and its association.
7. Record the correct actor and project attribution.
8. Return an accurate status.

The backend must not trust arbitrary project IDs or claim IDs supplied by the browser.

## 9.3 Unassigned evidence

If unassigned evidence is accepted in a future workflow, it must remain visibly unassigned or quarantined in an authorized inbox.

The first release should prioritize case-context upload and secure retrieval. A general inbox is conditional on safe implementation.

## 9.4 Upload validation

The current ingestion service supports JPEG, PNG, and WebP.

The existing default upload limit is 10 MiB.

Validation includes checks such as:

- File size.
- Empty uploads.
- Declared content type.
- File signature and image decoding.

The frontend must not imply that the file is trusted simply because the upload endpoint accepted it.

## 9.5 Status consistency

The existing ingestion flow creates a database record with `uploaded_quarantine`, while the upload response currently reports `uploaded`.

This mismatch must be resolved or explicitly handled by a contract that accurately distinguishes receipt from quarantine and processing.

A successful upload is not proof of completed analysis.

---

# 10. Evidence Storage and Access

## 10.1 Storage provider

Use private S3-compatible object storage, with Cloudflare R2 as the proposed provider.

Verify the actual account, bucket configuration, limits, pricing, retention behavior, and access policies before release.

## 10.2 Browser access

The browser never receives storage credentials.

The browser requests evidence access through FastAPI.

Before issuing a signed download URL, FastAPI must verify:

- JWT validity.
- Active PoA identity.
- Evidence-read permission.
- Case/project scope.
- Quarantine policy.
- Any additional evidence-specific restrictions.

## 10.3 Signed URLs

The existing backend uses short-lived presigned download URLs with a default lifetime of 900 seconds.

A signed URL is a bearer capability: anyone possessing it may be able to use it until expiry.

Issuing a URL does not guarantee that an already-issued URL can be revoked immediately.

Never persist signed URLs in durable browser storage or expose them in unnecessary logs.

## 10.4 Retention

The first-release retention policy is to preserve evidence and audit history.

Do not configure automatic expiration or deletion of evidence objects.

If storage quota is approached, stop or restrict new uploads safely rather than silently deleting evidence.

Future deletion must be an authorized, auditable workflow.

## 10.5 Evidence integrity

The UI must distinguish:

- Computed.
- Match.
- Mismatch.
- Not checked.
- Failed.
- Unavailable.

Only display a result as computed if the backend actually computed and persisted it.

The existence of SHA-256 and perceptual-hash fields in the database model does not prove the ingestion path populates them correctly.

A hash match establishes byte-level or algorithm-specific similarity, not the authenticity or origin of the evidence.

---

# 11. Cross-Service Ingestion Failure Recovery

R2 and PostgreSQL do not share a normal atomic transaction.

An object may be written successfully while the database transaction fails. The opposite inconsistency can also occur if the system commits a record before the corresponding storage operation completes.

## 11.1 Selected recovery strategy

Use bounded compensation and reconciliation.

A full distributed transaction or new ingestion state machine is not required for the initial release.

## 11.2 Storage succeeds, database fails

- Do not report successful evidence ingestion.
- Record a safe operational error.
- Identify the affected object for reconciliation where feasible.
- Preserve the object if reference ownership is ambiguous.
- Delete only when it is proven that no committed evidence record references it.

## 11.3 Database succeeds, response fails

The browser may not know whether the operation succeeded.

It must:

1. Preserve the file and relevant request context.
2. Display an uncertain outcome.
3. Query authoritative server state.
4. Retry only when it is safe to do so.

A filename or checksum alone is not sufficient to establish that an earlier upload was committed.

## 11.4 Cleanup race protection

A single database query showing no object reference is not enough if another operation could still be committing a reference.

Automated cleanup requires a safe operation identifier and race-resistant checks.

When that cannot be established, use manual reconciliation rather than speculative deletion.

---

# 12. Evidence Backup and Recovery

## 12.1 Database backup

Verify the actual backup capabilities of the selected Supabase plan.

Where feasible, create a restricted, encrypted logical backup before risky migrations and the demonstration.

Test the export and restore procedure against a disposable database.

Do not overwrite the live database during a recovery test.

Verify restored:

- Schema.
- Required extensions.
- Projects and claims.
- Evidence metadata.
- Decisions.
- Workflow history.
- Audit records.
- Object references.

## 12.2 Object-storage recovery

Keep evidence objects private and maintain a recoverable inventory linking:

`Evidence ID → Storage key → Expected checksum`

Verify the checksum against actual object contents where the necessary persisted checksum exists and its provenance is trustworthy.

Test retrieval of a known object.

Identify missing and unreferenced objects without modifying live evidence.

## 12.3 Recovery limitation

A PostgreSQL backup does not contain R2 object contents.

An inventory and checksum can detect or diagnose missing evidence but cannot recreate a missing object.

Stronger recovery requires a verified additional copy, supported versioning, or another tested recovery mechanism.

Do not claim full disaster recovery until the actual restore process has been tested.

---

# 13. Analysis and Intelligence

## 13.1 Analysis workflow

The current backend separates evidence upload from analysis job creation.

The upload endpoint does not automatically enqueue analysis.

Analysis job creation requires the relevant permission, including `intelligence.reprocess`.

The worker architecture includes fingerprinting, duplicate intelligence, temporal intelligence, and vision components.

The existence of these components does not prove that all models and dependencies work on the selected free host.

## 13.2 First-release analysis policy

Automatically enqueue supported analysis after upload only if the worker and required dependencies have been verified on the actual deployment.

Otherwise, show an honest pending or unavailable state.

If a real persisted analysis result exists, display its timestamp and whether it is stale.

Do not fabricate findings or imply that an analysis ran when it did not.

## 13.3 Vision models

The current configuration references models such as `yolo11n.pt` and `openai/clip-vit-base-patch32`.

Model weights were not present according to the earlier backend completion report.

Runtime downloads, CPU requirements, memory usage, model licenses, network access and free-tier constraints must be verified.

Automatic vision analysis is conditional and may be deferred.

## 13.4 Analysis job failure

If a worker fails:

- Preserve previous completed results.
- Record the new run's failure.
- Display the run timestamp and state.
- Do not overwrite a previous successful result with invented or empty findings.
- Disable unsupported reprocessing.
- Avoid unbounded job retries.

The current analysis-job creation function does not provide a verified deduplication guarantee. Do not assume duplicate requests create only one job.

## 13.5 Explainability

The intelligence experience should show:

- Plain-language summary.
- Supporting signals.
- Provenance.
- Methodology and version.
- Relevant rules and configuration.
- Unknowns and limitations.
- Review priority.
- Analysis timestamp and state.

Scores and graph edges are signals, not verdicts.

## 13.6 Fusion assessments

Fusion APIs may expose assessment status/value, integrity score, signal summaries, method/version, and configuration version.

The frontend must preserve the distinction between an assessment and a human decision.

An integrity score must not be presented as a fraud probability unless the model and calibration actually support that interpretation.

---

# 14. Case Review and Human Decisions

## 14.1 Queue

The current case-list response includes items, limit, offset and total.

The frontend should use actual backend enums and data.

A review priority may be derived only from real, explainable fields such as case status, evidence completeness and last activity.

Do not invent an unexplained risk score merely to sort the queue.

## 14.2 Decision outcomes

The backend decision enum includes:

- `SUPPORTED`
- `CONTRADICTED`
- `INCONCLUSIVE`
- `INSUFFICIENT_EVIDENCE`

These outcomes must not be collapsed into a simple approved/rejected distinction.

## 14.3 Rationale

The selected UI policy requires a minimum of 20 characters, a character counter, and a prompt encouraging the reviewer to refer to evidence and uncertainty.

The current backend rationale validation is weaker, with a minimum length of one character.

Mirror stronger validation in the backend if it can be safely implemented and tested.

A length limit alone does not guarantee that a rationale is meaningful.

## 14.4 Decision confirmation

The decision flow requires an explicit review-and-confirm step.

The UI must:

1. Validate the selected outcome.
2. Require a meaningful rationale.
3. Confirm the intended action.
4. Submit through FastAPI.
5. Wait for the authoritative response.
6. Show success only after persistence is confirmed.
7. Refresh the case and history from the server.

Do not claim that a decision was saved before receiving confirmation.

## 14.5 Actor attribution

The current decision endpoint accepts an optional `decided_by` UUID.

Production behavior must derive the actor from the authenticated principal.

The browser must not be trusted to declare which user made a decision.

## 14.6 Concurrent decisions

The frontend should check current case state before submitting a decision.

Where supported, the backend should use expected-state or version checks to reject stale submissions atomically.

A frontend-only freshness check cannot prevent concurrent requests from racing.

If atomic state/version checks cannot be implemented and tested before the deadline, document the limitation and avoid claiming full concurrency protection.

## 14.7 Uncertain decision writes

If the server may have persisted a decision but the response is lost:

- Preserve the rationale in the UI.
- Show an uncertain outcome.
- Fetch authoritative case state and workflow history.
- Retry only after reconciliation.
- Never blindly resubmit a decision.

## 14.8 Reopening resolved cases

The existing workflow supports `RESOLVED` → `OPEN`.

The selected product decision is to support authorized reopening with a meaningful reason, validated state transition and append-only history.

The prior decision and rationale must remain preserved.

The correction endpoints are intended for governed evidence-context changes, not generic rewriting of a decision.

Expose the reopening UI only after authorization, state-transition, rationale, and history-preservation behavior passes focused tests.

---

# 15. Audit and Governance

## 15.1 Audit principles

PoA must preserve a trustworthy record of important actions.

This includes, where applicable:

- Case creation.
- Assignment.
- Decision recording.
- Escalation.
- Resolution.
- Reopening.
- Evidence ingestion.
- Evidence-context changes.
- Administrative provisioning.

The workflow history should be append-only.

Do not overwrite an old decision merely because a new decision has been made.

## 15.2 Actor and project attribution

Audit records should identify the authenticated actor and the relevant project/case where applicable.

The existing evidence-ingestion audit event currently records `actor_id=None` and `project_id=None`.

This must be corrected as part of the evidence-association and attribution work.

## 15.3 Audit immutability limitations

Application-level append-only behavior and least-privilege database roles reduce the risk of accidental or unauthorized modification.

They do not make records absolutely immutable against every sufficiently privileged database administrator.

Do not claim tamper-proof audit storage unless the underlying technical controls justify that claim.

---

# 16. Maps and Evidence Relationships

## 16.1 Map

The map is a case-context feature, not the primary release path.

If implemented, it may show authorized nearby evidence or geofence context.

Requirements include:

- Correct project-scope authorization.
- Accurate location source and accuracy.
- Clear distinction between precise, approximate and missing coordinates.
- No implication that GPS proves the action occurred.
- No unnecessary disclosure of sensitive metadata to third-party tile or analytics providers.

## 16.2 Known authorization concern

Existing nearby-context endpoints were identified without clearly established complete authorization enforcement.

The project-specific route also needs verification of its permission checks.

Do not expose nearby-evidence map functionality until these authorization issues are fixed and tested.

## 16.3 Relationship graph

The graph must use real, authorized backend relationships.

The API's one-hop graph capability does not justify unrestricted graph traversal or mutation.

Graph mutations must not be exposed until the associated permission requirements are audited.

Defer interactive graph functionality if it jeopardizes the release gate.

---

# 17. Field Application and Offline Operation

## 17.1 Long-term target

The Field Officer experience is intended to be a full offline-first PWA workflow.

It should eventually support:

- Secure evidence capture.
- Stable client-generated IDs.
- Idempotent synchronization.
- Retry and recovery behavior.
- Explicit conflict reporting.
- Reconciliation of uncertain uploads.
- Encrypted local evidence storage with an explicit key-management design.

## 17.2 Security boundary

Browser storage encryption alone does not protect data from malicious JavaScript executing within the application or from every compromised-device scenario.

Do not store sensitive offline evidence unencrypted or claim a secure offline workflow until the key lifecycle and threat model have been reviewed.

## 17.3 First release

The full field workflow is deferred.

The initial release focuses on the Reviewer journey.

Existing field endpoints and offline-sync capabilities may be reused later, but they must be tested independently before being presented as a complete field application.

---

# 18. Deployment Architecture

## 18.1 Proposed hosting topology

| Component | Proposed service | Important constraint |
|---|---|---|
| Frontend | Cloudflare Pages | Static export and routing must be verified |
| API | Render free Docker web service | Cold starts, CPU, memory and service limits |
| Database | Supabase PostgreSQL | Connection limits, extensions, persistence and backup limitations |
| Authentication | Supabase Auth | JWT validation and identity mapping must be implemented |
| Evidence storage | Private Cloudflare R2 bucket | Verify storage, egress, quotas and retention |
| Redis | Conditional managed service | Must be verified before relying on it |
| Analysis worker | Conditional worker deployment | Model/runtime dependencies must be tested |

This is the selected deployment direction, not a claim that every service is configured or operational.

## 18.2 Cost policy

The first release should use free managed tiers where compatible.

However, free-tier availability, quotas, persistence, cold starts, CPU, memory, bandwidth, egress and retention must be checked against the actual account and provider terms.

A free service must not be described as always-on or production-reliable without evidence.

## 18.3 Backend runtime

The existing backend Docker image was documented as tested on `linux/amd64`.

ARM deployment was not validated.

The selected API host must be tested against the supported image architecture.

## 18.4 Persistent storage

Do not store authoritative evidence files on the Render application filesystem.

The API container may restart or be replaced.

PostgreSQL stores authoritative application records; R2 stores evidence objects.

Local Docker Compose volumes are useful for development and fallback demonstrations, but they are not backups.

## 18.5 Secrets

Use provider-managed environment variables.

Secrets must never be committed to Git, included in frontend bundles, written to logs, or returned to clients.

Disable development authentication defaults and wildcard CORS in the shared deployment.

Use exact allowed frontend origins.

---

# 19. API Rate Limiting and Abuse Controls

## 19.1 Selected approach

Use a verified shared or provider-supported limiter where available.

Do not claim that a per-process in-memory counter is a global limiter.

## 19.2 Separate protections

Authentication-sensitive endpoints, evidence uploads and expensive analysis should have separate controls.

Evidence uploads retain the 10 MiB default limit and content validation.

Analysis operations should be disabled or limited if reliable worker infrastructure is unavailable.

## 19.3 Fallback

If no suitable shared limiter is verified before release:

- Keep access restricted to pre-provisioned users.
- Enforce authentication and authorization.
- Retain file-size and content validation.
- Apply provider-level safeguards where available.
- Disable unsupported expensive operations.
- Document the remaining rate-limiting limitation.

Do not spend the deadline building a fragile substitute and then claim global protection.

---

# 20. Failure Handling

## 20.1 Frontend failure states

The frontend must distinguish:

- Loading.
- Empty.
- Forbidden.
- Unavailable.
- Failed.
- Pending.
- Incomplete.
- Unknown.
- Successfully completed.

Do not present an API failure as an empty result.

Do not present a missing analysis result as evidence that no issue exists.

## 20.2 Retry policy

- Reads may use bounded retries where safe.
- A 401 may trigger one session refresh and one retry.
- A 403 must not trigger token-refresh loops.
- Writes must not be blindly retried.
- Uncertain writes must be reconciled with authoritative server state.
- Upload retries must not assume exactly-once behavior unless a reliable idempotency mechanism exists.

## 20.3 User input preservation

On failures, preserve relevant unsaved rationale and form input where appropriate.

Do not silently discard a reviewer's work.

Reconcile server state before allowing a duplicate decision or upload.

## 20.4 Logging

Logs may include:

- Request IDs.
- HTTP status.
- Latency.
- Sanitized error categories.
- Analysis job state.
- Provider health information.

Do not log:

- Authentication tokens.
- Secrets.
- Raw evidence.
- Full EXIF payloads.
- Unnecessary precise location data.
- Unnecessary personal information.
- Signed URLs where exposure could grant evidence access.

---

# 21. Database and Object-Storage Recovery

## 21.1 Database recovery

The chosen approach is to verify the actual Supabase backup features, create restricted encrypted logical backups where feasible, and test restoration against a disposable database.

Do not overwrite the live database during a recovery test.

## 21.2 Object recovery

Maintain an inventory linking evidence IDs to object keys and checksums.

Test retrieval and reconciliation.

Do not automatically delete an object whose ownership or references are ambiguous.

## 21.3 Application rollback

Rollback application code if required, but preserve database records, evidence objects and audit history.

Prefer a forward-compatible schema and a tested forward fix for a migration that already contains important data.

## 21.4 Recovery acceptance

A recovery test should verify:

- The expected database revision.
- Critical records.
- Evidence metadata.
- Decision and audit history.
- Referenced object availability.
- Authorized retrieval.

Database recovery and object-storage recovery are separate requirements.

---

# 22. Testing Strategy

## 22.1 Existing backend test results

The backend completion report records 930 passed tests, one skipped test and zero failures against an isolated disposable stack.

This is useful evidence of backend test coverage.

It is not proof of production acceptance, deployed authentication, live provider compatibility, persistent object storage or working model inference.

## 22.2 Critical automated tests

### Authentication

- Valid Supabase JWT.
- Invalid signature.
- Wrong issuer or audience.
- Expired token.
- Key rotation.
- Unmapped identity.
- Disabled user.
- Suspended user.
- Development authentication disabled on shared deployment.

### Authorization

- Unauthenticated request.
- Wrong role.
- Wrong project scope.
- Cross-project access.
- Unauthorized evidence download.
- Quarantine restrictions.
- Unauthorized decision.
- Unauthorized reopening.
- Disabled account attempting a protected operation.

### Evidence

- Valid upload.
- Oversized upload.
- Malformed image.
- Unsupported content type.
- Empty upload.
- Case association.
- Actor/project audit attribution.
- Storage failure.
- Database failure after object write.
- Database success followed by lost response.
- Unauthorized retrieval.
- Quarantine retrieval policy.
- Checksum verification.
- Restart persistence.

### Review decisions

- Valid decision and rationale.
- Too-short rationale.
- Whitespace-only rationale.
- Unauthorized decision.
- Stale case state.
- Duplicate submission.
- Uncertain response.
- Decision history persistence.
- Reopening with reason.
- Preservation of prior decisions.

### Deployment

- Direct case URL.
- Browser refresh.
- API cold start.
- Database connectivity.
- Migration verification.
- Database persistence after restart.
- Evidence object retrieval.
- Safe behavior when a provider is unavailable.

## 22.3 Deployed smoke test

The deployed smoke test must exercise:

1. Sign in.
2. Open the authorized case queue.
3. Open a permitted case.
4. View its associated evidence.
5. Retrieve authorized evidence.
6. Record a decision with rationale.
7. Reload the case.
8. Verify the decision and workflow history persisted.
9. Verify an unauthorized request is rejected.
10. Confirm records remain after an API restart.

The test must use the real deployed services, not mocks.

---

# 23. Demo Data and Judge Access

## 23.1 Data policy

Use a small set of realistic synthetic public-works cases.

The initial target is approximately three to five synthetic evidence images ingested through the real backend path.

Do not bypass the evidence-ingestion and association workflow simply to preload files.

Clearly label synthetic evidence.

## 23.2 Account policy

Provision individual restricted demo accounts.

Do not use a shared privileged account.

Provide credentials privately.

Do not enable public signup.

## 23.3 Supervisor access

A read-only Supervisor account may be added only if the Reviewer journey and security checks pass first.

The Supervisor must not gain decision authority simply because of the role name.

## 23.4 Presentation fallback

The local Docker Compose fallback must use synthetic data and be tested separately.

Do not import production data or production credentials into the fallback environment.

---

# 24. Release Scope and Cutover Policy

## 24.1 Release blockers

The following are blockers until implemented and verified:

1. Production Supabase JWT verification.
2. Trusted PoA identity mapping.
3. Current active-user and scoped authorization checks.
4. Correct evidence-to-case association.
5. Secure private evidence upload and retrieval.
6. Correct actor and project audit attribution.
7. Persistent human decisions and workflow history.
8. Safe deployed migrations and database connectivity.
9. Negative authorization tests.
10. Deployed critical-path smoke test.

## 24.2 Conditional functionality

These features are deferred if they jeopardize the release gate:

- Automatic vision analysis.
- Unverified background workers.
- Interactive map.
- Interactive graph.
- Advanced analytics.
- Supervisor extras.
- Full Field Officer offline workflow.
- In-app role administration.
- Advanced recovery automation.
- Optional visual polish.

## 24.3 Final cutover decision

The final policy is strict:

**Freeze scope, fix and retest critical blockers, and use the separately tested local Docker Compose fallback if the hosted release still fails its critical acceptance gate.**

Do not weaken security to make the public deployment appear functional.

Do not claim that the hosted release passed because the local fallback works.

Do not present unverified functionality as complete.

A limited hosted release is acceptable only when the critical Reviewer journey passes and any unavailable noncritical subsystem is clearly represented as unavailable.

---

# 25. Known Code Gaps Requiring Verification

The following observations were identified from the repository during the interview. Recheck them against the current branch before changing code.

| Area | Existing observation | Required action |
|---|---|---|
| Authentication | Development bearer tokens exist; production Supabase JWT bridge is not verified | Implement and test trusted JWT validation |
| Configuration | Development defaults include development auth, enabled dev tokens, wildcard CORS and a placeholder secret | Override and validate shared-deployment configuration |
| Identity | User model supports external identity mapping | Verify active-user mapping and fail-closed behavior |
| Evidence association | Upload endpoint does not yet implement the selected case-context association contract | Add trusted association derived from case ID |
| Evidence audit | Ingestion audit event has null actor and project attribution | Derive both from trusted backend context |
| Evidence status | Upload response says `uploaded`, while database record uses `uploaded_quarantine` | Align API contract and frontend state |
| Integrity | Model fields for hashes exist | Verify actual computation and persistence |
| Download | Evidence download returns a short-lived signed URL | Verify project scope and quarantine policy before signing |
| Analysis | Upload does not automatically enqueue analysis | Add only if reliable worker is verified |
| Vision | Model weights were not present in the completion report | Verify dependencies, weights and free-host feasibility |
| Decisions | Client may supply `decided_by` | Derive actor from authenticated principal |
| Rationale | Backend currently accepts very short rationale | Implement stronger validation if safely testable |
| Reopening | `RESOLVED` → `OPEN` exists | Verify authorization, reason and history preservation |
| Nearby context | Authorization coverage needs verification | Do not expose map endpoints until fixed |
| Database roles | Runtime/migration privileges need actual verification | Test grants against real SQLAlchemy operations |
| Backup | Actual provider backup and restore capabilities must be checked | Export and restore in a disposable environment |
| Rate limiting | Shared limiter depends on available provider infrastructure | Verify or explicitly document the fallback |
| Frontend | Exact current frontend location/build configuration needs confirmation | Inspect actual repository files before implementing |

---

# 26. Implementation Rules

All future implementation work should follow these rules.

1. Inspect the current repository before editing.
2. Reuse existing architecture and code where appropriate.
3. Do not invent endpoints or response fields.
4. Keep frontend API types aligned with actual Pydantic schemas.
5. Use Zod validation at critical runtime boundaries.
6. Keep business-data access in FastAPI.
7. Keep secrets out of browser code.
8. Derive actors from verified server-side identities.
9. Enforce authorization on the backend, not just in navigation.
10. Keep evidence and audit history intact.
11. Avoid destructive migrations during release.
12. Do not fabricate analysis results or relationships.
13. Do not claim untested features work.
14. Run relevant tests after each critical change.
15. Run the deployed smoke test after the final deployment.
16. Preserve the local synthetic-data fallback as a separate environment.
17. Freeze scope when the acceptance gate is at risk.
18. Record deviations from this architecture explicitly.

---

# 27. Architecture Decision Summary

The most important decisions from the interview are:

- Reviewer-first product experience.
- One shared Next.js application.
- Static export with client-side API calls.
- Supabase Auth for sign-in.
- FastAPI as the sole business-data gateway.
- Verified Supabase JWTs and current database-backed authorization.
- Fixed, pre-provisioned roles for the first release.
- Restricted, idempotent account provisioning.
- Supabase PostgreSQL as authoritative application storage.
- Conservative API connection pooling and separate migration credentials.
- Explicit Alembic migrations.
- Private R2 evidence storage.
- Case association derived and authorized by the backend.
- Cautious cross-service ingestion reconciliation.
- Append-only decision and workflow history.
- Human decisions remain separate from analytical assessments.
- Explainability-first intelligence.
- Maps, graphs and workers conditional on verified readiness.
- No automatic evidence deletion.
- Database and object-storage recovery tested separately.
- Strict deployed acceptance gate.
- Local synthetic-data fallback if hosted critical checks fail.

---

# 28. Final Project Status Statement

This document records the architecture and engineering decisions agreed during the Grill Me interview.

It does not certify that PoA is production-ready.

The highest-priority remaining work is to implement and verify the production identity boundary, project-scoped authorization, case-associated evidence workflow, correct actor attribution, persistent human decisions, and deployed end-to-end acceptance.

Only after those checks pass should optional intelligence, map, graph, Supervisor and field functionality be considered for the first release.

**The governing principle is simple: PoA must show what it can prove, preserve what people have decided, and be honest about what remains unknown.**
