# Proof-of-Action
## Backend Scope

**Project:** Proof-of-Action (PoA)  
**Technical Name:** Evidence Integrity & Intelligence Layer (EIIL)  
**Document:** Backend Scope  
**Status:** Active Development  
**Version:** 1.0

---

## 1. Purpose

The Proof-of-Action backend is an **evidence intelligence and verification layer** designed to analyze field evidence submitted in the context of public infrastructure and government development activities.

The backend receives evidence such as photographs and, eventually, other evidence formats, and evaluates whether the evidence is **internally consistent, relevant, correlated with project context, and worthy of further review**.

The backend does not attempt to determine truth from a single AI model.

Instead, it combines multiple independent signals:

```text
Evidence
   ↓
File Integrity
   ↓
Metadata
   ↓
Cryptographic Fingerprint
   ↓
Perceptual Similarity
   ↓
Visual Similarity
   ↓
Location
   ↓
Time
   ↓
Project Context
   ↓
Claim
   ↓
Cross-Evidence Relationships
   ↓
Fusion
   ↓
Integrity + Risk
   ↓
Explainability
   ↓
Human Review
```

The core objective is:

> **Make existing field evidence more trustworthy by analyzing how multiple pieces of evidence agree, disagree, or relate to each other.**

---

# 2. What the Backend Is

The backend is the **core intelligence and data layer** of PoA.

It is responsible for:

- Evidence ingestion.
- Evidence storage.
- Evidence validation.
- Evidence metadata extraction.
- Cryptographic hashing.
- Perceptual hashing.
- Visual/semantic similarity.
- Duplicate detection.
- Geospatial analysis.
- Temporal analysis.
- Claim matching.
- Vision analysis.
- Cross-project correlation.
- Evidence relationships.
- Anomaly detection.
- Multi-signal fusion.
- Integrity scoring.
- Risk scoring.
- Explainability.
- Human review workflows.
- Audit logging.
- Authentication and authorization.
- API access for external systems.

The backend must function independently of the frontend.

---

# 3. What the Backend Is Not

The backend is **not**:

- A generic image upload service.
- A simple EXIF checker.
- A GPS verification application.
- A reverse image search engine.
- A single AI fraud detector.
- A generic computer-vision platform.
- A replacement for government monitoring systems.
- A replacement for field inspections.
- A system that automatically declares fraud from one anomaly.
- A system that assumes missing metadata means fraud.
- A system that treats AI-generated content detection as the complete verification problem.

PoA should provide **evidence intelligence**, not pretend to provide absolute truth.

---

# 4. System Boundary

The backend sits between existing evidence-producing systems and human/government decision-makers.

```text
┌─────────────────────────────┐
│ Existing Government Systems │
│                             │
│ Mobile Apps                 │
│ Web Portals                 │
│ Monitoring Systems         │
│ Field Inspection Systems   │
└──────────────┬──────────────┘
               │
               │ Evidence / Project Data
               ▼
┌─────────────────────────────────────┐
│              PoA Backend             │
│                                     │
│ API                                 │
│ Evidence Ingestion                  │
│ Evidence Storage                    │
│ Analysis Engines                    │
│ Evidence Graph                      │
│ Fusion Engine                       │
│ Review Engine                       │
│ Audit Layer                         │
└──────────────────┬──────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │ Human / Organization │
        │ Decision Makers      │
        └──────────────────────┘
```

PoA should be designed as an **API-first intelligence layer**.

---

# 5. Primary Backend Responsibilities

## 5.1 Evidence Ingestion

The backend must safely receive evidence from clients and external systems.

Responsibilities:

- Create evidence records.
- Generate upload URLs.
- Accept evidence uploads.
- Place uploads into quarantine storage.
- Validate files.
- Verify actual file type.
- Verify file size.
- Detect corrupt files.
- Calculate SHA-256.
- Move validated evidence into trusted storage.
- Create an immutable evidence identity.

Initial supported evidence:

```text
Image
```

Future evidence:

```text
Video
PDF
JSON
GPS/Location records
Sensor data
Documents
```

---

# 6. Evidence Storage

The backend is responsible for maintaining evidence objects and their lifecycle.

Development:

```text
MinIO
```

Production:

```text
S3-compatible object storage
```

Storage must distinguish between:

```text
QUARANTINE
    ↓
VALIDATED
    ↓
TRUSTED
```

Original evidence must be preserved.

Derived artifacts may include:

```text
thumbnails
normalized images
analysis artifacts
feature representations
```

The backend must never silently replace the original evidence.

---

# 7. Evidence Identity

Every evidence object must have multiple identifiers.

### Application Identity

```text
evidence_id
```

### Cryptographic Identity

```text
SHA-256
```

### Perceptual Identity

```text
pHash
```

### Semantic Identity

```text
embedding
```

These serve different purposes.

```text
SHA-256
→ Exact byte-level identity

pHash
→ Visual similarity

Embedding
→ Semantic/visual similarity
```

None of these alone proves authenticity.

---

# 8. Metadata Intelligence

The backend extracts and analyzes available metadata.

Potential metadata:

- Camera manufacturer.
- Camera model.
- Lens.
- Capture timestamp.
- Creation timestamp.
- Modification timestamp.
- GPS latitude.
- GPS longitude.
- GPS altitude.
- GPS timestamp.
- Orientation.
- Image dimensions.
- Software.
- Color information.
- Other available EXIF fields.

Metadata is treated as a **signal**, not ground truth.

For example:

```text
Photoshop metadata
```

does not automatically mean:

```text
Fraud
```

Instead, the backend should evaluate it in context with other signals.

---

# 9. Duplicate Intelligence

The backend must identify relationships between evidence items.

Duplicate detection operates in layers.

## Level 1 — Exact Duplicate

```text
SHA-256
```

Detects identical byte sequences.

## Level 2 — Perceptual Duplicate

```text
pHash
```

Useful for:

- Resizing.
- Compression.
- Minor transformations.

## Level 3 — Semantic Similarity

```text
Image Embeddings
+
pgvector
```

Used to identify visually/semantically similar evidence.

## Level 4 — Local Feature Verification

Potentially:

```text
SIFT
ORB
```

Used to verify suspicious candidate matches.

The backend must distinguish:

```text
DUPLICATE
```

from:

```text
SIMILAR
```

and:

```text
CORROBORATING
```

---

# 10. Geospatial Intelligence

The backend analyzes evidence location relative to project context.

Inputs may include:

```text
Evidence GPS
Project coordinates
Project geofence
Activity location
Other evidence locations
GPS accuracy
```

Capabilities:

- Distance calculation.
- Geofence verification.
- Location consistency.
- Spatial clustering.
- Cross-project location comparison.
- Impossible travel detection.

Example:

```text
Evidence GPS
     ↓
Project geofence
     ↓
Distance
     ↓
Location consistency score
```

Possible anomalies:

```text
GPS_MISSING
LOCATION_MISMATCH
LOW_GPS_ACCURACY
IMPOSSIBLE_TRAVEL
```

GPS is treated as evidence, not unquestionable truth.

---

# 11. Temporal Intelligence

The backend analyzes evidence against project and activity timelines.

Inputs:

```text
Capture timestamp
Project start
Project completion
Activity dates
Milestone dates
Other evidence timestamps
```

Capabilities:

- Timeline validation.
- Capture-before-project detection.
- Capture-after-completion detection.
- Activity sequence validation.
- Timestamp consistency.
- Repeated timestamp detection.
- Cross-evidence temporal correlation.

Possible anomalies:

```text
TIMESTAMP_MISMATCH
TIMELINE_CONTRADICTION
IMPOSSIBLE_SEQUENCE
```

---

# 12. Project Context

Evidence cannot be meaningfully evaluated without context.

The backend therefore manages:

```text
Project
Activity
Claim
Evidence
```

Relationship:

```text
Project
  ↓
Activity
  ↓
Claim
  ↓
Evidence
```

Example:

```text
Project:
Village Solar Lighting

Activity:
Street Light Installation

Claim:
Solar street lights installed at specified location

Evidence:
Photograph
```

This context enables meaningful analysis.

---

# 13. Claim Intelligence

A claim describes what an evidence item is expected to demonstrate.

Example:

```text
"Solar street lights have been installed."
```

The backend may transform this into structured expectations:

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

Claim intelligence may use:

- Rules.
- Structured templates.
- NLP.
- LLM assistance.

LLMs must not independently determine whether the claim is true.

They may assist with:

- Claim extraction.
- Claim normalization.
- Explanation generation.
- Reviewer assistance.

---

# 14. Vision Intelligence

Vision analysis is responsible for extracting useful visual signals.

Initial capabilities:

- Image quality.
- Blur detection.
- Resolution analysis.
- Exposure analysis.
- Scene classification.

Later capabilities:

- Object detection.
- Object counting.
- Scene understanding.
- Before/after comparison.
- Scheme-specific visual verification.

Example:

```text
Claim:
Solar street light installation

Vision:
Pole detected
Solar panel detected
Light detected
```

The output becomes a **claim consistency signal**, not an automatic conclusion.

---

# 15. Authenticity / Manipulation Signals

PoA may use multiple methods to identify potential manipulation.

Possible signals:

- Metadata inconsistencies.
- Compression artifacts.
- Image forensic analysis.
- Provenance information.
- External manipulation detectors.
- Future internal ML models.

Architecture:

```text
                ┌───────────────────┐
                │ Authenticity      │
                │ Signal Layer      │
                └─────────┬─────────┘
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          Metadata     Forensics    External
                                   Detector
             │            │            │
             └────────────┼────────────┘
                          ▼
                    Fusion Engine
```

No single detector is authoritative.

---

# 16. Evidence Graph

The Evidence Graph is a core component of PoA.

It represents relationships between evidence and its surrounding context.

Conceptually:

```text
PROJECT
   │
   ├── ACTIVITY
   │      │
   │      └── CLAIM
   │
   └── EVIDENCE
          │
          ├── LOCATION
          ├── TIME
          ├── METADATA
          ├── SIMILAR EVIDENCE
          ├── DUPLICATE EVIDENCE
          ├── ANOMALIES
          └── REVIEW
```

Relationships may include:

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

The Evidence Graph allows PoA to reason about evidence **as a network rather than isolated files**.

---

# 17. Cross-Project Intelligence

PoA must be capable of comparing evidence beyond a single project.

Example:

```text
Project A
    │
    └── Evidence X
             │
             │ high similarity
             ▼
Project B
    │
    └── Evidence Y
```

The backend should investigate:

- Similar images.
- Reused evidence.
- Similar scenes.
- Geographic conflicts.
- Temporal conflicts.
- Cross-project relationships.

Example anomaly:

```text
CROSS_PROJECT_REUSE
```

This is one of the primary areas where PoA can differentiate itself from basic geo-tagged photo collection systems.

---

# 18. Corroboration

Similarity is not automatically suspicious.

Multiple independent pieces of evidence may legitimately show the same asset.

Example:

```text
Evidence A
     │
     ├── same project
     │
Evidence B
     │
     └── same location
```

This may represent:

```text
CORROBORATION
```

rather than:

```text
DUPLICATION
```

The backend must therefore model both positive and negative relationships.

---

# 19. Anomaly Detection

The backend generates standardized anomalies.

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

LOW_IMAGE_QUALITY
CLAIM_MISMATCH
OBJECT_MISSING

MANIPULATION_SIGNAL
```

Each anomaly must contain:

```text
type
severity
confidence
source
explanation
```

An anomaly is **not equivalent to fraud**.

---

# 20. Integrity Score

Integrity measures:

> **How internally consistent is the evidence with the available information?**

Potential signals:

```text
GPS consistency
Temporal consistency
Duplicate relationships
Metadata consistency
Authenticity signals
Visual consistency
Claim consistency
Evidence completeness
```

Example:

```text
Integrity = 84
```

This does not mean:

```text
84% probability that the work happened
```

It represents the consistency of the evidence available to PoA.

---

# 21. Risk Score

Risk answers:

> **How much attention should this evidence receive?**

Risk may depend on:

- Severity of anomalies.
- Cross-project reuse.
- Location conflicts.
- Timeline conflicts.
- Duplicate relationships.
- Claim mismatch.
- Confidence.
- Project importance.
- Evidence completeness.
- Historical reviewer outcomes.

Example:

```text
Integrity: 72
Risk: 81
```

This means the evidence may contain enough concerns to require investigation even though some signals are consistent.

---

# 22. Fusion Engine

The Fusion Engine combines independent signals.

Conceptually:

```text
GPS
        │
Temporal│
        │
Metadata│
        │
Duplicate
        ├──────► Fusion Engine
Vision  │
        │
Claim   │
        │
Authenticity
        │
Completeness
        ▼
Integrity + Risk
```

The initial implementation should use deterministic/rule-based fusion.

Weights must be:

- Configurable.
- Versioned.
- Testable.
- Calibratable.

The backend must never hide how a score was produced.

---

# 23. Explainability

Every important score must have an explanation.

The backend should be able to answer:

```text
Why was this evidence flagged?
```

Example:

```text
HIGH RISK

Reasons:

1. Evidence is outside the project geofence.
2. A highly similar image exists in another project.
3. Capture time conflicts with the activity timeline.
4. Metadata indicates possible post-processing.
```

Explanations should be derived from actual analysis results.

No fabricated explanations.

---

# 24. Human Review

PoA is a decision-support system.

It must provide humans with enough information to investigate evidence.

Reviewer information should include:

- Original evidence.
- Integrity score.
- Risk score.
- Signal breakdown.
- Anomalies.
- Similar evidence.
- Location.
- Timeline.
- Metadata.
- Claim.
- Explanation.
- Related evidence.

Reviewer actions:

```text
APPROVE
REJECT
FLAG
REQUEST_RESUBMISSION
REQUEST_FIELD_INSPECTION
OVERRIDE
```

Human decisions are authoritative within the configured workflow.

---

# 25. Audit System

All important actions must be auditable.

Examples:

```text
Evidence uploaded
Evidence accessed
Analysis started
Analysis completed
Analysis failed
Score generated
Review opened
Review decision
Reviewer override
Evidence downloaded
State changed
Project changed
Claim changed
```

Audit records should include:

```text
actor
action
resource
timestamp
request_id
previous state
new state
reason
metadata
```

Audit history should not be silently overwritten.

---

# 26. Authentication

The backend must authenticate users and integrations.

Potential mechanisms:

```text
OAuth2
OIDC
JWT
API keys for machine integrations
```

Authentication and authorization must remain separate concepts.

---

# 27. Authorization

The backend must implement role and permission controls.

Initial roles:

```text
CITIZEN
REVIEWER
SUPERVISOR
PROGRAM_ADMIN
AUDITOR
```

Permissions should include capabilities such as:

```text
evidence.upload
evidence.read
evidence.analyze

review.read
review.decide
review.override

project.create
project.update

audit.read
```

Access must be checked at the resource level.

---

# 28. API Responsibilities

The backend exposes versioned APIs.

Base:

```text
/api/v1/
```

Initial API groups:

```text
/evidence
/projects
/activities
/claims
/reviews
/audit
```

Core endpoints include:

```http
POST /api/v1/evidence/uploads
POST /api/v1/evidence/{id}/complete

GET  /api/v1/evidence/{id}
POST /api/v1/evidence/{id}/analyze
GET  /api/v1/evidence/{id}/analysis
GET  /api/v1/evidence/{id}/similar
GET  /api/v1/evidence/{id}/anomalies
GET  /api/v1/evidence/{id}/graph

POST /api/v1/projects
GET  /api/v1/projects
GET  /api/v1/projects/{id}

GET  /api/v1/reviews/queue
POST /api/v1/reviews/{id}/decision

GET /api/v1/audit/events
```

The API must be usable without the PoA frontend.

---

# 29. Asynchronous Processing

Expensive operations must not block HTTP requests.

Architecture:

```text
API
 ↓
Redis
 ↓
Worker
 ↓
Analysis Engine
 ↓
Database
```

Potential jobs:

```text
VALIDATE_EVIDENCE
EXTRACT_METADATA
CALCULATE_PHASH
GENERATE_EMBEDDING
RUN_DUPLICATE_ANALYSIS
RUN_GEO_ANALYSIS
RUN_TEMPORAL_ANALYSIS
RUN_VISION_ANALYSIS
RUN_CLAIM_ANALYSIS
RUN_FUSION
```

Each job must be trackable.

---

# 30. Observability

The backend must expose enough information to understand its own operation.

Track:

- Request IDs.
- Job IDs.
- Analysis IDs.
- Processing duration.
- Errors.
- Worker status.
- Queue depth.
- Database performance.
- Storage failures.
- Model execution failures.

Production observability may eventually include:

```text
OpenTelemetry
Prometheus
Grafana
```

---

# 31. Security Scope

Security is part of the backend, not an optional later feature.

The backend must protect:

- Evidence files.
- User identities.
- Project information.
- Review decisions.
- Audit records.
- API credentials.
- Model artifacts.

Security requirements include:

- Authentication.
- Authorization.
- Rate limiting.
- Input validation.
- Secure file uploads.
- Secret management.
- Audit logging.
- Dependency security.
- Container security.
- Database security.
- Object storage access controls.

---

# 32. Evidence Privacy

Evidence may contain sensitive information.

The backend should therefore support:

- Controlled access.
- Signed/private object URLs.
- Access logging.
- Data retention policies.
- Secure deletion policies where permitted.
- Separation of original and derived evidence.

Public access to original evidence should never be assumed.

---

# 33. Machine Learning Scope

Machine learning is **not the first milestone**.

The initial system should be:

```text
Deterministic rules
+
Computer vision
+
Similarity
+
Evidence relationships
+
Fusion
```

Once sufficient human review data exists, ML can be introduced.

The first recommended ML objective is:

> **Predict review priority.**

Not:

> **Automatically determine fraud.**

Potential features:

```text
GPS score
Temporal score
Metadata score
pHash similarity
Embedding similarity
Duplicate count
Vision score
Claim score
Anomaly count
Distance from project
Software metadata
```

Potential models:

```text
XGBoost
LightGBM
Scikit-learn
```

Deep learning should be introduced only when justified by data and benchmark results.

---

# 34. Model Governance

Every model must be versioned.

Store:

```text
model_name
model_version
rule_version
analysis_timestamp
```

Example:

```text
vision-model-v1.0
embedding-model-v1.1
fusion-rules-v2
```

An analysis result must remain reproducible after a model is updated.

---

# 35. Testing Scope

The backend must include:

## Unit Tests

Test individual engines.

## Integration Tests

Test:

```text
API
+
Database
+
Storage
+
Redis
+
Workers
```

## End-to-End Tests

Test the complete evidence lifecycle.

## Benchmark Tests

Evaluate:

```text
duplicate detection
similarity
GPS detection
temporal detection
claim matching
fusion
```

## Security Tests

Test:

```text
authentication
authorization
file uploads
IDOR
rate limits
malformed input
```

---

# 36. Benchmark Dataset

The backend intelligence must eventually be evaluated against a controlled dataset.

Initial classes:

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

Metrics:

```text
Precision
Recall
F1
False Positive Rate
False Negative Rate
```

No claims about accuracy should be made without measured results.

---

# 37. Production Scope

Production deployment must support:

```text
FastAPI
PostgreSQL
PostGIS
pgvector
Redis
S3-compatible storage
Background workers
Authentication
RBAC
Audit
Monitoring
Backups
CI/CD
```

The system should allow independent scaling of:

```text
API
Workers
Embedding processing
Vision processing
```

---

# 38. Integration Scope

PoA should eventually integrate with existing systems through:

```text
REST APIs
Webhooks
SDKs
API keys
OIDC/OAuth
```

Example:

```text
Existing Government Application
             ↓
       PoA API
             ↓
      Evidence Analysis
             ↓
      Result / Webhook
```

PoA should not require an organization to completely replace its existing monitoring application.

---

# 39. Future Scope

The following are deliberately outside the initial MVP but may be added later.

## C2PA

Cryptographically verifiable content provenance.

```text
Capture
 ↓
C2PA
 ↓
Evidence
 ↓
PoA Analysis
```

## Secure Capture

A dedicated mobile capture application with:

- GPS.
- Timestamp.
- Device identity.
- Offline capture.
- Secure signing.
- C2PA provenance.

## Video Analysis

Potential capabilities:

- Frame-level analysis.
- Temporal consistency.
- Video provenance.
- Duplicate detection.

## Additional Evidence

```text
PDF
JSON
Documents
Sensors
Satellite imagery
IoT data
```

## Advanced ML

Potential future models:

- Learned anomaly detection.
- Review-priority prediction.
- Scheme-specific visual models.
- Graph-based intelligence.

---

# 40. Explicitly Out of Scope

The following should NOT be built as part of the initial backend:

- [ ] A custom blockchain.
- [ ] A new cryptocurrency/token.
- [ ] A universal "AI truth detector".
- [ ] Automatic fraud prosecution.
- [ ] Fully autonomous government decisions.
- [ ] A custom search engine.
- [ ] A custom map provider.
- [ ] A massive general-purpose vision model.
- [ ] Neo4j before PostgreSQL graph capabilities are insufficient.
- [ ] Kubernetes before deployment complexity requires it.
- [ ] Microservices before clear scaling boundaries exist.
- [ ] Training large AI models before sufficient data exists.
- [ ] Building the frontend before API contracts stabilize.

---

# 41. Architecture Principles

## Principle 1 — Evidence First

The original evidence is the primary object.

Everything else is derived from it.

---

## Principle 2 — Multiple Independent Signals

No single signal should determine the final outcome.

```text
GPS
+
Time
+
Metadata
+
Duplicate
+
Vision
+
Claim
+
Context
```

is stronger than:

```text
One AI model
```

---

## Principle 3 — Context Matters

An anomaly without context is weak.

Example:

```text
Edited image
```

may be harmless.

But:

```text
Edited image
+
wrong GPS
+
cross-project duplicate
+
timeline contradiction
```

is substantially more concerning.

---

## Principle 4 — Integrity ≠ Risk

Integrity measures evidence consistency.

Risk determines investigation priority.

They must remain separate.

---

## Principle 5 — AI Assists; It Does Not Magically Decide

AI can:

```text
Extract
Classify
Compare
Summarize
Rank
Explain
```

Human reviewers remain responsible for consequential decisions.

---

## Principle 6 — Every Result Must Be Explainable

If PoA produces:

```text
Risk = 83
```

the system must be able to explain:

```text
Why?
Which signals?
Which evidence?
Which anomalies?
Which versions?
```

---

## Principle 7 — Reproducibility

An analysis result must be traceable to:

```text
Input evidence
+
Analysis engines
+
Model versions
+
Rule versions
+
Configuration
+
Timestamp
```

---

## Principle 8 — Don't Fake Intelligence

The backend must never return simulated:

```text
similarity
confidence
accuracy
risk
AI detection
```

unless the value came from an actual implemented analysis.

---

# 42. Backend Success Criteria

The backend is successful when it can take:

```text
A real field photograph
```

and produce:

```text
Evidence Identity
        +
Secure Storage
        +
Metadata
        +
SHA-256
        +
pHash
        +
Embedding
        +
Duplicate Relationships
        +
GPS Analysis
        +
Temporal Analysis
        +
Vision Signals
        +
Claim Consistency
        +
Cross-Project Relationships
        +
Anomalies
        +
Integrity Score
        +
Risk Score
        +
Explainability
        +
Human Review
        +
Immutable Audit Trail
```

while remaining:

```text
Secure
Auditable
Reproducible
Explainable
API-first
Scalable
Testable
```

---

# 43. Final Backend Definition

The Proof-of-Action backend is not fundamentally an image-analysis backend.

It is an:

> **Evidence Integrity & Intelligence Layer**

Its core capability is taking fragmented evidence and turning it into a structured, explainable network of signals and relationships.

The intended transformation is:

```text
RAW EVIDENCE
     ↓
STRUCTURED EVIDENCE
     ↓
MULTI-SIGNAL ANALYSIS
     ↓
EVIDENCE RELATIONSHIPS
     ↓
CROSS-PROJECT INTELLIGENCE
     ↓
ANOMALIES
     ↓
FUSION
     ↓
INTEGRITY + RISK
     ↓
EXPLAINABLE REVIEW
     ↓
HUMAN DECISION
     ↓
AUDITABLE OUTCOME
```

That is the scope of the PoA backend.