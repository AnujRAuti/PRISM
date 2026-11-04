# Proof-of-Action — Grill Me Session Results

## Product, Architecture, Domain Model, Governance & Engineering Contract

**Status:** Locked decision record / architecture baseline  
**Project:** Proof-of-Action (PoA)  
**Technical name:** Evidence Integrity & Intelligence Layer (EIIL)

> **“We don't collect more evidence; we make existing evidence trustworthy.”**

---

# 1. Executive Product Definition

Proof-of-Action is an end-to-end application and API platform for making existing evidence more trustworthy, traceable, explainable, and operationally useful in public-infrastructure and government-scheme monitoring.

PoA sits beside existing government systems rather than replacing them. It is an evidence intelligence and verification layer, not the authoritative source of truth.

Its core differentiator is the combination of:

- Evidence Graph
- multi-signal analysis
- cross-evidence intelligence
- cross-project intelligence
- provenance
- deterministic measurements
- explainable fusion
- human review and decision governance

The central transformation is:

**Raw Facts → Relationships → Signals → Integrity Assessment → Review Priority → Human Decision**

These layers remain distinct.

---

# 2. Permanent Product Principles

## 2.1 PoA is not the source of truth

PoA provides evidence intelligence and structured assessments. Final substantive determinations belong to an authorized human workflow.

## 2.2 Integrity is not authenticity

Integrity, authenticity, fraud probability, manipulation detection, compliance, and human decision are separate concepts.

## 2.3 Low evidence quality is not automatically fraud

Missing metadata, uncertain GPS, temporal gaps, or incomplete corroboration must not automatically become negative evidence.

Missing information should remain **UNKNOWN**, **INCONCLUSIVE**, or another explicitly defined uncertain state where appropriate.

## 2.4 Automated intelligence does not replace human authority

Models and rules generate observations and signals. They do not make final substantive decisions in V1.

## 2.5 Deterministic before probabilistic

Use actual measurable operations whenever possible:

- SHA-256
- perceptual hashes
- EXIF
- PostGIS calculations
- timestamp comparisons
- object detections
- explicit domain relationships

ML is introduced only where it provides a genuine capability.

## 2.6 Explainability is mandatory

Derived relationships, signals, assessments, and analytical observations must preserve their source, method, version, execution time, relevant inputs, and explanation.

---

# 3. Actors

PoA has six primary actor types:

1. Citizen
2. Field Officer
3. Reviewer
4. Supervisor
5. Administrator
6. API Client

The application uses one Next.js application with role-oriented experiences.

---

# 4. Citizen Experience

The citizen portal focuses on:

- **Discover**
- **Report**
- **Track**

It is not an internal investigation interface.

Citizen reports are private by default and can become publicly releasable only through explicit publication/releasability rules.

Citizen evidence enters the same evidence pipeline but retains its provenance and unverified status. It can contribute intelligence and conflicts but does not automatically create an official determination.

Authentication supports authenticated citizens and limited anonymous participation.

---

# 5. Field Officer Experience

The field experience is a mobile-first offline-capable PWA.

Field officers work on assigned Activities rather than receiving unrestricted project access.

Offline capabilities include:

- assignment synchronization
- capture
- GPS/time collection
- notes
- local validation
- secure local queue
- deferred synchronization
- stable client IDs
- idempotent sync
- preservation of capture, queue, upload, and server timestamps
- explicit conflict handling

Server-side intelligence remains online.

Native mobile is deferred.

---

# 6. Reviewer Experience

The reviewer interface is a **Reviewer Investigation Workspace**, not a gallery.

Primary flow:

**Queue → Case → Claim / Evidence / Timeline / Graph / Assessment → Actions → Human Decision**

Reviewers can:

- inspect evidence
- inspect measurements
- inspect relationships
- dispute relationships
- request evidence
- escalate
- annotate
- investigate
- make authorized decisions

Measurements remain immutable.

---

# 7. Supervisor Experience

The supervisor workspace focuses on:

- projects
- team assignments
- workload
- case oversight
- evidence requests
- escalations
- scoped analytics

Supervisors do not receive unrestricted override authority.

---

# 8. Administrator Experience

Administrators manage:

- identity
- configuration
- integrations
- operations
- security
- retention
- governance

Administrative authority is separate from substantive decision authority.

---

# 9. Organization and Domain Hierarchy

The organization hierarchy is:

**Organization → Organizational Unit → Project**

## Project

The Project is the top-level operational domain object.

Projects are owned by an organization/unit and have a supervisor.

## Activity

An Activity is the work or inspection unit within a Project.

## Claim

A Claim is a canonical, testable assertion.

Claims belong to a Project and may relate to multiple Activities.

External authorized sources may import canonical claims.

Automated models cannot create canonical claims in V1.

## Citizen Report

A Citizen Report contains:

- statement
- context
- evidence references

The statement is an assertion, not evidence.

---

# 10. Evidence Architecture

Evidence is independent of Projects and Claims.

An Evidence item may relate to:

- multiple Claims
- multiple Activities
- Projects
- other Evidence
- external sources
- analytical observations

Evidence-to-Claim relationships are first-class.

V1 is image-first, while the general architecture supports:

- images
- video
- documents
- PDFs
- audio
- structured records

Unsupported media must be rejected or explicitly marked unavailable.

Future derivatives preserve lineage through `DERIVED_FROM`.

---

# 11. Evidence Immutability

Original evidence properties are immutable:

- original file
- cryptographic identity
- original provenance

Corrections create new versions/evidence.

Derived intelligence is recomputable and versioned.

Context changes require authorization and auditability.

Human decisions are append-only.

Evidence may be withdrawn or superseded under controlled lifecycle rules.

Deletion is retention-policy controlled and auditable.

---

# 12. Provenance

Provenance is first-class but is **not equivalent to truth**.

The system traces:

- source
- submitter/source system
- capture
- ingestion
- cryptographic identity
- storage
- transformations
- derivatives
- analytical processing
- human actions

External decisions remain external assertions rather than being silently converted into PoA determinations.

---

# 13. Evidence Pipeline

**Submission → Quarantine → Validation → Trusted Immutable Storage → Async Analysis → Authorized Availability → Intelligence / Assessment → Optional Review Case → Retention / Archive / Deletion**

Each analysis capability runs independently.

Evidence acceptance does not mean evidence truth.

---

# 14. Evidence Graph

The Evidence Graph is a core PoA differentiator.

V1 uses PostgreSQL rather than a separate graph database.

Graph nodes include domain, analytical, and review entities.

Initial relationship vocabulary:

- `BELONGS_TO`
- `SUPPORTS`
- `CONTRADICTS`
- `SIMILAR_TO`
- `DUPLICATE_OF`
- `CAPTURED_AT`
- `CAPTURED_BEFORE`
- `CAPTURED_AFTER`
- `DERIVED_FROM`
- `REQUIRES`
- `CORROBORATES`

Relationships preserve:

- source
- target
- provenance
- status
- timestamps
- method
- methodology/version
- explanation

The graph is not truth. It is a structured representation of known and derived relationships.

Historical relationships remain preserved.

---

# 15. Cross-Project Intelligence

Cross-project intelligence is supported.

Rules:

- project-local intelligence is the default
- cross-project access is authorization-aware
- graph traversal is filtered by authorization and visibility
- sensitive related evidence may require escalation
- cross-project relationships are signals/intelligence, not automatic wrongdoing determinations

---

# 16. Geospatial Intelligence

Spatial context exists at:

- Project
- Activity
- Claim
- Evidence

The architecture supports:

- points
- polygons
- containment
- distance
- boundaries
- geofences

PostGIS performs spatial calculations.

Source metadata captures uncertainty where applicable.

Missing or uncertain GPS remains unknown/uncertain.

Geofence violations produce warnings/signals rather than automatic blocks or fraud conclusions.

Historical geometry is versioned.

---

# 17. Temporal Intelligence

Temporal intelligence uses:

- capture time
- event time
- ingestion time
- synchronization time
- processing time
- domain/project time

Source timestamps are preserved.

Known time zones are normalized.

Missing timestamps are not invented.

Temporal conflicts indicate uncertainty or inconsistency rather than automatically indicating fraud.

BE-008 temporal semantics remain part of the architecture.

---

# 18. Vision Intelligence — V1

V1 vision intelligence is deliberately limited to real, reproducible image observations.

Primary mechanism: YOLO/object detection plus image properties.

Observations can contain:

- class ID
- class name
- confidence
- normalized bounding box
- image dimensions
- model provenance
- thresholds/configuration
- analysis execution information

V1 does **not** include:

- authenticity scoring
- manipulation detection
- deepfake detection
- fraud probability
- semantic truth determination
- face recognition
- OCR as a truth mechanism

CPU compatibility is required.

GPU acceleration is optional.

Model weights must not be committed to Git.

---

# 19. Analysis Runs and Model Governance

Every analytical execution is a versioned **Analysis Run**.

It records:

- capability
- input
- model/capability version
- configuration
- timestamps
- status
- provenance

Statuses distinguish:

- `COMPLETED` with zero observations
- `FAILED`
- `UNAVAILABLE`

Reprocessing creates a new run.

Dependencies and lineage are preserved.

A lightweight model/capability registry is sufficient initially.

---

# 20. Duplicate Intelligence

The architecture uses actual multiple signals:

- SHA-256 exact identity
- perceptual hash
- embedding semantic similarity
- future local-feature verification

Similarity relationships are analytical relationships, not fraud verdicts.

---

# 21. Fusion Engine

The Fusion Engine produces two distinct outputs.

## Integrity Assessment

A structured assessment based on configured evidence-integrity signals.

## Review Priority

An indication of how much reviewer attention should be allocated.

These must remain separate.

Fusion is:

- deterministic/configurable initially
- versioned
- auditable
- explainable
- aware of missing data

Missing data is not negative evidence.

Human overrides remain separate from automated fusion.

---

# 22. Review Cases

A Review Case is the primary human-review unit.

Proposed lifecycle:

**OPEN → ASSIGNED → INVESTIGATING → DECISION_PENDING → RESOLVED / ESCALATED**

The lifecycle is configurable.

Not every anomaly automatically creates a case.

Origins include:

- system signals
- authorized users
- citizen reports
- external systems

Cases support:

- assignment
- investigation
- evidence requests
- escalation
- resolution
- reopening

Status and outcome are separate.

---

# 23. Human Decision Governance

Final substantive outcomes require human authorization.

Example vocabulary:

- `SUPPORTED`
- `CONTRADICTED`
- `INCONCLUSIVE`
- `INSUFFICIENT_EVIDENCE`

A rationale is required.

Human decisions are append-only.

Escalation does not overwrite prior decisions.

---

# 24. Evidence Requests

Evidence Request is a first-class auditable object containing:

- requester
- recipient
- scope
- instructions
- due date
- priority
- lifecycle
- linked evidence

V1 notification:

- in-app
- optional email

Push/SMS and chat are deferred.

---

# 25. Dispute and Correction

Outputs may be:

- disputed
- invalidated
- superseded
- versioned

Upstream changes can mark dependent outputs stale.

Reprocessing creates new analysis runs.

Humans cannot rewrite raw measurements.

---

# 26. Audit Ledger

PoA uses a dedicated append-only, tamper-evident, hash-chained audit ledger.

It is separate from ordinary domain history.

It records important:

- evidence actions
- analytical executions
- relationship changes
- review actions
- human decisions
- administrative/security actions
- sensitive access

Future external anchoring is possible.

---

# 27. Visibility and Authorization

Visibility depends on:

- role
- organization scope
- project scope
- data visibility
- action permission

Visibility classes:

- public
- citizen-owned/private
- operational
- intelligence/internal
- administrative/security

Authorization is centralized conceptually around:

`can(user, action, resource, context)`

The backend is authoritative.

V1 authorization uses:

- RBAC
- organization/resource scope
- contextual authorization

A heavyweight policy engine is deferred.

---

# 28. Authentication

Authentication remains configurable.

Architecture supports:

- OIDC
- OAuth2
- government SSO
- citizen-approved identity providers
- limited anonymous access
- API machine authentication with explicit scopes

Authentication, authorization, and substantive authority remain separate.

---

# 29. External Systems and API

Canonical API:

**REST `/api/v1`**

Next.js and external clients use the same API.

Requirements:

- structured errors
- OpenAPI
- request IDs
- asynchronous jobs
- presigned uploads
- idempotency

Webhooks are deferred.

External systems are first-class sources.

External decisions remain external assertions.

---

# 30. Offline Field Architecture

The field PWA synchronizes assigned work and preserves separate:

- capture timestamp
- local queue timestamp
- synchronization timestamp
- server ingestion timestamp
- processing timestamp

Stable client IDs support idempotency.

Conflicts are explicit.

Server intelligence runs after connectivity is available.

---

# 31. Threat Model

Threats include:

- malicious uploads
- evidence tampering
- compromised accounts
- privilege escalation
- cross-organization access
- API abuse
- insider manipulation
- adversarial evidence
- model supply-chain attacks
- infrastructure compromise

Security controls include:

- TLS
- encrypted storage
- encrypted backups
- protected object storage
- signed URLs
- server-side authorization
- organization isolation
- rate/resource limits
- secure logging
- privacy-aware metadata handling
- audited sensitive actions

Protected information includes raw evidence, EXIF, GPS, citizen identity, and internal intelligence.

---

# 32. Retention and Deletion

Retention is policy-driven and configurable.

Object types can have separate lifecycles.

Legal/administrative holds prevent deletion.

Deletion is controlled, authorized, and auditable.

Archival/cold storage can be introduced.

---

# 33. Analytics

Analytics are role- and scope-aware.

They provide descriptive/diagnostic information with drill-down.

Scopes:

- project
- organization
- system
- intelligence

Metrics define:

- metric definition
- time period
- scope
- methodology/version

Review-priority analytics may support workload allocation but must not become unsupported fraud rankings.

---

# 34. ML Strategy

The platform is ML-ready but not ML-dependent.

The first production ML target is:

**Review Prioritization**

It is explicitly not:

- fraud detection
- authenticity detection
- truth determination
- automatic decision-making

Models carry:

- model version
- training/data provenance
- execution provenance
- configuration

Human decisions may contribute labels but are not unquestionable ground truth.

---

# 35. Accessibility and Localization

The interface follows WCAG 2.2 AA principles.

Requirements include:

- keyboard access
- screen-reader compatibility
- touch accessibility
- non-color-only communication
- accessible non-map alternatives

The platform is localization-ready and timezone-aware.

Original source data is preserved.

Translations are derived data with provenance.

---

# 36. Independent State Machines

The system must not use one global status.

Independent state models exist for:

- Evidence
- Analysis Runs
- Assessments
- Review Cases
- Retention
- Publication

Each is independently governed.

---

# 37. Technology Direction

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- PostGIS
- pgvector
- Redis
- MinIO/S3
- Pillow
- OpenCV
- ExifTool where needed
- imagehash
- Ultralytics/YOLO
- CLIP/SigLIP where semantic embeddings are required
- scikit-learn/XGBoost/LightGBM later

## Frontend

- Next.js
- React
- TypeScript
- Tailwind
- shadcn/ui
- TanStack Query
- React Hook Form
- Zod
- MapLibre

## Production

Potential platform components:

- OpenTelemetry
- metrics
- logging
- tracing
- reverse proxy/load balancer
- containers
- CI/CD

Deployment remains deployment-neutral and government-friendly.

---

# 38. Backend Milestone Baseline

The preserved backend reaches:

**BE-001 → BE-008 → cleanup/hardening**

Current Git baseline:

**`6388325 cleanup1`**

Current branch:

**`Backend`**

Remote:

**`origin/Backend`**

Working tree was verified clean.

**BE-009 has not yet been implemented.**

---

# 39. Backend Roadmap

1. **BE-001** — Database foundation
2. **BE-002** — Object storage
3. **BE-003** — Evidence upload
4. **BE-004** — Fingerprinting
5. **BE-005** — Async analysis jobs
6. **BE-006** — Duplicate intelligence
7. **BE-007** — Project/activity/claim/context/geo
8. **BE-008** — Temporal intelligence
9. **BE-009** — Vision intelligence
10. **BE-010** — Evidence graph
11. **BE-011** — Fusion
12. **BE-012** — Explainability
13. **BE-013** — Review
14. **BE-014** — Audit
15. **BE-015** — Authentication/RBAC
16. **BE-016** — Security/testing hardening
17. **BE-017** — ML
18. **BE-018** — Production deployment

---

# 40. Permanent Engineering Integrity / Anti-Shortcut Gate

> **Do not interpret “make it work” as “make a convincing demo.”**

Every capability must perform the real operation it claims to perform.

Never use:

- fake values
- hardcoded results
- placeholder confidence scores
- simulated analysis
- mocked production success paths
- fabricated evidence
- fake similarity
- fake risk
- fake AI output

If a capability cannot genuinely be implemented:

> **Fail clearly or mark it unavailable. Never pretend it succeeded.**

Do not implement future milestone functionality early.

Prefer deterministic measurable operations over AI-generated assertions.

Tests must verify actual behavior and outputs, not merely that a function was called.

Never weaken validation/correctness to make tests pass.

Do not hide errors or convert failures into success.

Preserve completed milestones unless a genuine blocker requires a minimal compatibility fix.

---

# 41. Architecture Freeze Rule

The Grill Me decisions are an architectural contract.

Future implementation must conform to them.

If a future requirement contradicts this document:

1. identify the contradiction
2. explain the impact
3. resolve the architectural decision explicitly
4. update this decision record
5. implement only after resolution

Do not silently change the architecture through code.

---

# 42. North-Star Data Flow

**Evidence exists**
→ **Evidence is technically characterized**
→ **Evidence is related to domain claims**
→ **Evidence is related to other evidence**
→ **Signals are generated**
→ **Signals are fused**
→ **Reasoning is explained**
→ **A human investigates**
→ **An authorized human decides**
→ **The decision is permanently auditable**

---

# 43. What PoA Must Not Become

PoA must not become:

- a generic photo-upload application
- an AI demo
- a single-model fraud detector
- an opaque risk-score generator
- an automatic government decision-maker
- a replacement for authoritative government systems
- a gallery with superficial metadata
- a system where missing evidence automatically means wrongdoing
- a system where model confidence is treated as truth

PoA is an **evidence intelligence and human decision-support platform**.

---

# 44. The 51 Locked Grill-Me Decisions

The session locked 51 decisions covering:

1. End-to-end PoA application and API platform
2. One Next.js app with role-oriented experiences
3. Citizen, Field Officer, Reviewer, Supervisor, Administrator, API Client actors
4. Citizen portal as public transparency/participation
5. Project → Activity → Claim domain structure
6. Evidence as a general architecture with image-first V1
7. Raw facts → relationships → signals → Integrity Assessment → Review Priority → Human Decision
8. PoA is not source of truth
9. Citizen evidence uses the same pipeline with provenance/unverified status
10. Review Case as the primary human-review unit
11. Citizen Report as statement/context/evidence
12. Visibility controlled by role/scope/data/action
13. Organization → Organizational Unit → Project hierarchy
14. Explicit ownership and assignment
15. Immutable original evidence and append-only decisions
16. Full provenance traceability
17. External systems as first-class sources
18. Canonical testable claims
19. First-class Evidence-Claim relationships
20. Separate Integrity Assessment and Review Priority fusion
21. Configurable Review Case generation/lifecycle
22. Human-authorized final decisions
23. Dedicated append-only tamper-evident audit ledger
24. Versioned dispute/correction propagation
25. Policy-driven retention/deletion
26. Deployment neutrality and data sovereignty
27. Offline-first field PWA
28. Explicit threat model
29. Configurable OIDC/OAuth2 authentication
30. RBAC + resource/context authorization
31. PostgreSQL Evidence Graph V1
32. Authorization-aware cross-project intelligence
33. Real YOLO/image observations for vision V1
34. PostGIS geospatial intelligence
35. Multi-source temporal intelligence
36. Defined evidence processing pipeline
37. General media architecture with image-first V1
38. Canonical REST API
39. First-class Evidence Requests and workflow notifications
40. Reviewer Investigation Workspace
41. Supervisor operational workspace
42. Administrator governance/operations workspace
43. Citizen Discover/Report/Track portal
44. Role/scope-aware analytics
45. ML-ready architecture with Review Prioritization first
46. Versioned Analysis Runs and model governance
47. Security/privacy architecture
48. Accessibility/localization
49. Independent state machines
50. Domain model boundaries
51. Architecture Freeze meta-rule

---

# 45. Immediate Next Stage

The implementation baseline is:

**BE-008 → cleanup1 → BE-009**

The next capability is:

**BE-009 — Vision Intelligence**

BE-009 should first audit the existing backend against the BE-009 contract, then implement only the required V1 vision-observation capability.

Do not pull BE-010+ functionality forward unless it is a genuine minimal dependency.

Preserve all BE-001 through BE-008 behavior.

---

# 46. Final Architecture Summary

The intended system is:

**Citizens / Field Officers / External Systems**
→ **Evidence Ingestion**
→ **Validation + Crypto + Provenance + Storage**
→ **Independent Analysis Runs**
→ **Evidence Graph**
→ **Fusion**
→ **Explainability**
→ **Review Case**
→ **Authorized Human Decision**
→ **Audit Ledger**

The architecture is designed around one central principle:

> **Turn raw evidence into a defensible, traceable chain of reasoning without pretending that automated intelligence is the same thing as truth or human judgment.**

---

## Status

**Grill-Me architecture decisions: LOCKED**

**Backend baseline: `6388325 cleanup1`**

**Current development stage: BE-009**
