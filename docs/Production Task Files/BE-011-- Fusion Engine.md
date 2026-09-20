# BE-011 — Fusion Engine

Project: Proof-of-Action / Evidence Integrity & Intelligence Layer (EIIL)
Milestone: BE-011
Area: Backend — Fusion Engine
Branch: Backend
Status: Implementation Specification
Depends On: BE-001 → BE-010
Primary Goal: Implement the first production version of the deterministic, versioned Fusion Engine that combines existing evidence-derived signals into separate Integrity Assessment and Review Priority outputs.

---

# 1. Objective

Implement the first production version of the PoA Fusion Engine.

BE-011 consumes structured observations and relationships already produced by:

- BE-004 — Fingerprinting
- BE-006 — Duplicate Intelligence
- BE-007 — Project / Activity / Claim / Geospatial Context
- BE-008 — Temporal Intelligence
- BE-009 — Vision Intelligence
- BE-010 — Evidence Graph

The Fusion Engine transforms those inputs into two distinct outputs:

1. Integrity Assessment
2. Review Priority

These outputs must remain independent.

The Fusion Engine must:

- consume real existing analytical outputs;
- use deterministic and configurable rules in V1;
- preserve missing/unknown states;
- avoid treating missing evidence as negative evidence;
- preserve provenance;
- preserve methodology/version information;
- persist the exact assessment produced by an execution;
- support reprocessing through new fusion runs;
- remain explainable through structured contributing signals;
- expose results through the existing FastAPI API;
- integrate with BE-001 → BE-010 without breaking prior behavior.

BE-011 must not become:

- a fraud detector;
- an authenticity detector;
- a truth engine;
- a machine-learning model;
- an LLM-based reasoning system;
- a review workflow;
- an audit ledger;
- an authorization system.

---

# 2. Architectural Position

The pipeline becomes:

Evidence
   │
   ├── Fingerprinting
   ├── Duplicate Intelligence
   ├── Temporal Intelligence
   ├── Geospatial Context
   └── Vision Intelligence
          │
          ▼
     Evidence Graph
          │
          ▼
      BE-011 Fusion
          │
          ├── Integrity Assessment
          │
          └── Review Priority
                    │
                    ▼
              Future Review
                 BE-013

BE-011 consumes existing signals.

It does not replace the analytical systems that produced them.

---

# 3. Locked Architectural Principles

The following principles are mandatory.

## 3.1 Integrity Assessment and Review Priority are separate

The Fusion Engine must produce two different outputs.

### Integrity Assessment

Represents the structured assessment of available evidence-integrity signals.

It must not be represented as:

- fraud probability;
- authenticity probability;
- truth probability;
- guilt probability.

### Review Priority

Represents how much reviewer attention should be allocated.

It is an operational prioritization signal.

It must not be interpreted as:

- likelihood of fraud;
- proof of wrongdoing;
- truth ranking;
- authenticity ranking.

Do not collapse these into one score.

---

# 4. No Truth Engine

BE-011 must not determine whether a claim is objectively true.

For example:

SUPPORTS + high temporal consistency + valid GPS

must not become:

"claim is true"

Likewise:

CONTRADICTS + duplicate relationship + geospatial inconsistency

must not become:

"fraud occurred"

The system produces structured automated assessments that remain subject to future human investigation and decision.

---

# 5. Deterministic V1

V1 fusion must be deterministic.

The same:

- input observations;
- graph relationships;
- methodology version;
- configuration;
- source states;

must produce the same fusion output.

Do not introduce:

- LLM reasoning;
- random scoring;
- neural fusion;
- ML prediction;
- external AI APIs.

Machine learning belongs to a later milestone.

---

# 6. Required Inputs

BE-011 consumes existing information only.

Potential input sources include:

## BE-006

- SHA-256 exact identity
- pHash distance
- embedding similarity
- duplicate match type
- duplicate relationship state

## BE-007 / Spatial Context

- project association
- activity association
- claim association
- evidence location
- spatial relationships
- configured geospatial consistency signals where already available

Do not create a second geospatial engine.

## BE-008

- temporal relationship
- timestamp comparison result
- elapsed interval
- claim temporal window
- known/unknown temporal state

Do not duplicate BE-008 comparison logic.

## BE-009

- object detections
- detection counts
- classes
- confidence values
- analysis status
- model/configuration provenance

Do not reinterpret YOLO confidence as truth.

## BE-010

- SUPPORTS relationships
- CONTRADICTS relationships
- ASSOCIATED_WITH relationships
- DUPLICATE_OF relationships
- TEMPORALLY_RELATED_TO relationships
- graph relationships connecting evidence, claims and analytical outputs
- relationship status
- relationship provenance
- analysis run lineage

The Fusion Engine should consume graph relationships rather than directly coupling every future subsystem to every analytical implementation.

---

# 7. Signal Model

BE-011 should introduce a normalized internal signal representation.

Conceptually:

FusionSignal
------------
signal_type
value/state
source
source_entity_id
analysis_run_id
method
method_version
observed_at
confidence
explanation_context

The exact schema may differ.

However, signals must preserve their provenance.

A signal must never appear to have been generated by fusion when it actually came from another subsystem.

---

# 8. Signal States

Signals must distinguish between positive, negative, neutral and unavailable/unknown states where applicable.

Recommended conceptual vocabulary:

- POSITIVE
- NEGATIVE
- NEUTRAL
- UNKNOWN
- UNAVAILABLE
- CONFLICTING

The implementation may use an equivalent representation.

The critical requirement is:

UNKNOWN must not silently become NEGATIVE.

UNAVAILABLE must not silently become NEGATIVE.

---

# 9. Missing Data

Missing evidence is not negative evidence.

Examples:

Missing EXIF
Missing GPS
Missing temporal metadata
No duplicate match
No vision detections
No supporting relationship

must not automatically reduce the integrity assessment.

The Fusion Engine must preserve uncertainty explicitly.

For example:

GPS missing

must result in:

GPS signal = UNKNOWN

not:

GPS signal = NEGATIVE

Likewise:

No duplicate relationship

does not automatically mean:

duplicate signal = positive integrity.

The absence of a detected relationship is not automatically evidence in either direction.

---

# 10. Input Eligibility

The Fusion Engine must not consume invalid analytical results.

Examples:

FAILED analysis run

must not contribute a successful signal.

UNAVAILABLE analysis capability

must not be treated as a clean positive result.

COMPLETED with zero observations

must remain a legitimate completed input state.

The Fusion Engine must distinguish:

- successful observation with value;
- successful analysis with zero observations;
- failed analysis;
- unavailable capability.

---

# 11. Analysis Run Dependency

Every fusion execution must itself be represented as an Analysis Run or an equivalent versioned fusion execution record consistent with the existing architecture.

The execution must preserve:

- capability
- input reference
- methodology/version
- configuration
- started_at
- completed_at
- status
- provenance

Recommended capability:

`fusion`

Reprocessing must create a new execution.

Do not overwrite a previous fusion execution.

---

# 12. Fusion Configuration

Fusion logic must be configurable.

Do not hardcode every weight or threshold directly into service logic where configuration storage is appropriate.

A configuration should identify:

- configuration ID/version;
- signal weights;
- thresholds;
- enabled signal types;
- minimum evidence requirements;
- priority rules;
- methodology version.

The exact storage mechanism may be introduced as part of BE-011.

Do not introduce a heavyweight configuration platform.

PostgreSQL-backed configuration is sufficient for V1.

---

# 13. Fusion Method Version

Every fusion output must identify the methodology used.

Example:

method:
    deterministic_signal_fusion

method_version:
    fusion-v1

The methodology version must be persisted with the resulting assessment.

If configuration changes materially, future runs must preserve the new version rather than changing historical outputs.

---

# 14. Integrity Assessment Model

Create a dedicated persisted model for the Integrity Assessment.

Conceptual structure:

IntegrityAssessment
-------------------
id
target_type
target_id
status
assessment_value
method
method_version
configuration_version
analysis_run_id
signal_summary
created_at
updated_at

The exact field names may differ.

The assessment must reference the object being assessed.

Likely targets include:

- CLAIM
- EVIDENCE

The implementation must choose the supported V1 target explicitly.

Do not create a vague global score disconnected from a domain object.

---

# 15. Integrity Assessment Output

The output should communicate the state of available evidence-integrity signals.

The exact vocabulary must be defined before implementation.

A recommended deterministic vocabulary is:

- SUPPORTED
- MIXED
- CONTRADICTED
- INSUFFICIENT_EVIDENCE
- UNKNOWN

However, these values must not be interpreted as final human decisions.

They are automated fusion states.

Do not use:

- TRUE
- FALSE
- FRAUD
- AUTHENTIC
- FAKE
- GUILTY
- INNOCENT

---

# 16. Review Priority Model

Create a separate persisted Review Priority representation.

Conceptual structure:

ReviewPriority
--------------
id
target_type
target_id
priority
priority_score
method
method_version
configuration_version
analysis_run_id
signal_summary
created_at
updated_at

Priority may be represented through an ordinal vocabulary such as:

- LOW
- NORMAL
- HIGH
- URGENT

The exact vocabulary must be defined deliberately.

A numeric score may be used internally if necessary.

However, the score must represent review allocation priority, not fraud likelihood.

---

# 17. Review Priority Must Not Become Fraud Ranking

This is a critical architectural boundary.

A record with:

priority_score = 0.95

must not be documented as:

"95% chance of fraud"

It means only that the deterministic review-priority methodology produced a high-priority operational signal.

API documentation and database semantics must preserve this distinction.

---

# 18. Signal Combination

Fusion should combine existing signals according to a deterministic configuration.

Conceptual example:

Signal A: SUPPORTS
Signal B: temporal consistency
Signal C: valid spatial relationship
Signal D: duplicate conflict

Fusion may produce:

Integrity Assessment:
MIXED

Review Priority:
HIGH

The result must be derived from actual persisted signals.

Do not fabricate values when a signal does not exist.

---

# 19. Contradictory Signals

Conflicting signals must be preserved.

Example:

Evidence supports Claim

while:

another evidence relationship contradicts Claim.

The Fusion Engine must not silently discard one signal.

The resulting assessment should represent the configured conflict handling policy.

The conflict policy must be deterministic.

Do not resolve conflicts using undocumented heuristics.

---

# 20. Signal Weighting

V1 may use deterministic weighted aggregation.

Example conceptual structure:

weighted_score =
    Σ(signal_value × configured_weight)

However:

- weights must be configuration;
- signal states must be normalized;
- unknown data must not automatically receive a negative value;
- unavailable inputs must not be treated as negative;
- methodology version must be persisted.

Do not claim statistical probability unless the system actually implements calibrated probabilistic modeling.

---

# 21. No Fake Confidence

BE-011 must not generate arbitrary confidence values simply because confidence is expected by an API.

If a confidence measure is introduced, it must represent a genuinely defined quantity.

Do not call:

- weighted score;
- rule score;
- priority score;

a "confidence probability".

Unless calibrated probabilistic semantics are implemented, avoid probability language entirely.

---

# 22. Signal Normalization

Different analytical systems produce different numeric domains.

Examples:

pHash distance:
0...N

Embedding similarity:
-1...1

YOLO confidence:
0...1

Temporal elapsed time:
seconds/minutes/hours

These must not be combined directly.

Each signal must be normalized through a documented deterministic transformation.

The transformation must preserve its:

- input range;
- output range;
- thresholds;
- methodology version.

---

# 23. Signal Definitions

Each signal used by fusion must have a defined semantic meaning.

Example:

## Duplicate signal

High pHash similarity may indicate visually similar evidence.

It does not mean fraud.

## Temporal signal

Temporal consistency indicates whether available timestamps satisfy the relevant configured temporal relationship.

It does not prove authenticity.

## Spatial signal

Spatial consistency indicates whether observed location relationships satisfy configured spatial rules.

It does not prove that the image was actually captured at that location unless that is independently established.

## Vision signal

Object detections identify model-observed visual patterns.

They do not establish semantic truth.

---

# 24. Evidence-Claim Fusion

The primary V1 fusion target should be explicitly defined.

Recommended target:

CLAIM

The engine gathers evidence associated with a claim and combines relevant signals.

Example:

Claim X

Evidence A
  SUPPORTS Claim X

Evidence B
  CONTRADICTS Claim X

Evidence C
  TEMPORALLY_RELATED_TO Evidence A

Fusion must operate over actual graph relationships.

Do not duplicate the claim/evidence relationship model.

---

# 25. Evidence-Level Fusion

Evidence-level fusion may be supported only where there is a concrete V1 use case.

Examples:

Evidence A
  duplicate conflicts;
  temporal anomaly;
  uncertain spatial context.

The implementation must avoid creating redundant assessment systems.

Prefer claim-level fusion where the business meaning is clearer.

The final supported target set must be documented before implementation.

---

# 26. Graph Integration

BE-011 should consume BE-010 through a service/repository abstraction.

Preferred flow:

Analysis outputs
      ↓
Evidence Graph
      ↓
Fusion Signal Extraction
      ↓
Fusion Engine
      ↓
Assessment + Review Priority

Do not directly manipulate graph tables from the fusion service.

Do not bypass the Evidence Graph merely because the original subsystem is easier to access.

---

# 27. Provenance

Every contributing signal must preserve its source.

At minimum:

- source subsystem;
- source entity;
- analysis run if applicable;
- method;
- method version.

The resulting fusion execution must preserve:

- input signal references;
- fusion methodology;
- configuration version.

Fusion provenance answers:

"How was this assessment produced?"

It does not answer:

"Is the assessment objectively true?"

---

# 28. Assessment History

Assessment history must be preserved.

Suppose:

Fusion Run #1
→ assessment = SUPPORTED

Later:

Fusion Run #2
→ assessment = MIXED

The system must retain both executions.

Do not overwrite Run #1.

The current state may be determined through the latest valid run or another explicitly defined mechanism.

History remains queryable.

---

# 29. Reprocessing

Reprocessing must create a new fusion execution.

Example:

Run #1
method_version = fusion-v1

Run #2
method_version = fusion-v2

Both executions remain traceable.

Do not mutate historical analysis runs.

Do not retroactively change old assessment values.

---

# 30. Assessment Lifecycle

Assessments may require explicit status.

Recommended vocabulary:

- ACTIVE
- SUPERSEDED
- INVALIDATED

If used, lifecycle transitions must preserve history.

Invalidating an assessment does not delete the original execution.

The implementation must distinguish:

- current;
- historical;
- invalidated.

---

# 31. Zero-Signal Case

A fusion execution with no usable signals must not fabricate an assessment.

Example:

No temporal data
No spatial data
No duplicate analysis
No relevant graph relationships

The engine may produce:

INSUFFICIENT_EVIDENCE

only if that state is defined as the correct deterministic result.

It must not produce:

SUPPORTED

simply because the engine completed successfully.

---

# 32. Failed Fusion

A failed fusion execution must remain:

FAILED

It must not create a successful assessment.

Do not persist partial successful results as if the entire fusion execution succeeded.

Where partial execution is supported, the semantics must be explicit and versioned.

---

# 33. Transactional Integrity

Assessment persistence should be transactionally safe.

A completed fusion execution and its resulting assessment/priority outputs must not leave inconsistent partial state.

For example:

If assessment persistence succeeds but review priority persistence fails,

the system must not incorrectly report a fully successful fusion execution.

Use transactional boundaries appropriate to the existing SQLAlchemy architecture.

---

# 34. API

Provide an API to execute fusion for a supported target.

Potential endpoint:

POST /api/v1/fusion/{target_type}/{target_id}

The API should:

- validate target type;
- validate target UUID;
- verify target exists;
- execute or enqueue fusion according to existing analysis-job architecture;
- return execution information;
- preserve idempotency semantics.

The exact synchronous/asynchronous choice must conform to the existing backend architecture.

---

# 35. Fusion Execution Status API

Provide a way to retrieve fusion execution status.

Potential endpoint:

GET /api/v1/fusion/runs/{run_id}

It should expose:

- run ID;
- target;
- status;
- methodology version;
- configuration version;
- timestamps;
- error where applicable.

Do not expose internal secrets.

---

# 36. Assessment Retrieval API

Provide an endpoint to retrieve the latest assessment.

Potential:

GET /api/v1/fusion/{target_type}/{target_id}

Response should contain:

- target;
- integrity assessment;
- review priority;
- methodology version;
- configuration version;
- analysis run reference;
- assessment timestamp;
- signal summary.

The default response must not include massive raw evidence payloads.

---

# 37. Historical Retrieval

Provide access to previous fusion executions/results.

Potential:

GET /api/v1/fusion/{target_type}/{target_id}/history

Support:

- pagination;
- ordering;
- status filtering where appropriate.

Do not expose unlimited history in a single request.

---

# 38. API Error Handling

Use existing backend error conventions.

Handle:

- invalid UUID;
- unsupported target type;
- unknown target;
- no eligible signals;
- invalid configuration;
- invalid methodology version;
- analysis failure;
- database errors.

Do not turn execution failures into HTTP success responses.

---

# 39. API Documentation

OpenAPI must document:

- Integrity Assessment;
- Review Priority;
- Fusion Run;
- signal representation;
- configuration/version fields;
- statuses;
- error responses.

Documentation must explicitly state:

Review Priority is an operational prioritization signal and is not a fraud probability.

Integrity Assessment is an automated evidence-integrity assessment and is not a final human determination.

---

# 40. Database Design

Potential tables:

fusion_runs
integrity_assessments
review_priorities
fusion_signals

Exact naming may differ.

Do not duplicate graph relationships unnecessarily.

A fusion run should reference the inputs rather than copying entire graph records.

---

# 41. Fusion Run Model

Conceptual:

fusion_runs
-----------
id UUID PK
target_type
target_id
status
method
method_version
configuration_version
input_snapshot
started_at
completed_at
error
created_at

`input_snapshot` may be useful for deterministic reproducibility.

However, avoid storing unrestricted duplicate payloads if references plus versions are sufficient.

The final implementation must make it possible to understand what inputs were used.

---

# 42. Integrity Assessment Model

Conceptual:

integrity_assessments
---------------------
id UUID PK
fusion_run_id FK
target_type
target_id
assessment_status
assessment_value
signal_summary
created_at

Historical rows must be preserved.

Do not maintain only one mutable row per target unless the full historical lineage is separately preserved.

---

# 43. Review Priority Model

Conceptual:

review_priorities
-----------------
id UUID PK
fusion_run_id FK
target_type
target_id
priority
priority_score
signal_summary
created_at

`priority_score` is optional.

If used, its mathematical meaning must be documented.

It must never be described as a fraud probability.

---

# 44. Signal Storage

Signal storage should preserve enough detail to reproduce the assessment.

Conceptual fields:

fusion_run_id
signal_type
source
source_entity_id
source_analysis_run_id
state
raw_value
normalized_value
method
method_version
metadata

Do not store fake values to fill missing fields.

---

# 45. Foreign Keys

Use real database foreign keys where meaningful.

Examples:

fusion_signals.fusion_run_id
integrity_assessments.fusion_run_id
review_priorities.fusion_run_id

Foreign key deletion behavior must preserve historical fusion records.

Do not allow accidental deletion of historical fusion outputs simply because an upstream row changes.

---

# 46. Indexes

Provide indexes based on actual query patterns.

At minimum consider:

fusion_runs(target_type, target_id)
fusion_runs(status)
fusion_runs(created_at)

integrity_assessments(target_type, target_id)
integrity_assessments(fusion_run_id)

review_priorities(target_type, target_id)
review_priorities(fusion_run_id)

fusion_signals(fusion_run_id)
fusion_signals(signal_type)

Do not add speculative indexes.

---

# 47. Configuration Storage

V1 configuration may be database-backed.

Conceptual:

fusion_configurations
---------------------
id UUID PK
version
name
enabled
weights
thresholds
rules
created_at
created_by

The exact implementation may differ.

Configuration changes must be versioned.

Historical fusion runs must continue to reference their original configuration version.

---

# 48. Configuration Validation

Configuration must be validated before a fusion run can execute.

Validate:

- weight ranges;
- threshold ranges;
- supported signal types;
- supported statuses;
- required rule parameters;
- methodology version compatibility.

Invalid configuration must fail clearly.

Do not silently clamp invalid configuration values.

---

# 49. Determinism Requirement

Fusion must be deterministic.

Run the same target twice using the same:

- source graph state;
- analytical inputs;
- methodology version;
- configuration;

and the result must be identical.

Timestamp metadata naturally changes between executions, but the actual assessment calculation must not depend on runtime randomness.

---

# 50. Ordering Determinism

If multiple signals have equal priority or equal weights, aggregation/order must remain deterministic.

Avoid relying on undefined database row ordering.

Use explicit ordering where signal iteration affects the result.

---

# 51. Numerical Stability

If numeric scores are used:

- define their valid range;
- normalize inputs;
- avoid floating-point comparison assumptions where exact threshold behavior matters;
- define rounding rules;
- persist the final computed score.

Do not expose more precision than the methodology meaningfully supports.

---

# 52. Rule Evaluation

Fusion rules should be represented in a structured deterministic manner.

For example:

Signal:
TEMPORAL_CONSISTENCY

State:
POSITIVE

Weight:
0.25

Another:

Signal:
DUPLICATE_CONFLICT

State:
NEGATIVE

Weight:
0.40

The final aggregation must be reproducible from the stored configuration.

Do not create opaque chains of nested `if` statements without documenting the resulting methodology.

---

# 53. Conflict Policy

A conflict-handling policy must be explicit.

Example:

SUPPORTS
+
CONTRADICTS

may produce:

MIXED

rather than silently selecting one.

The policy should also define how:

- UNKNOWN;
- UNAVAILABLE;
- conflicting;
- absent;

signals participate.

---

# 54. Signal Absence

The system must distinguish:

1. signal evaluated and positive;
2. signal evaluated and negative;
3. signal evaluated and neutral;
4. signal unavailable;
5. signal unknown;
6. signal not applicable;
7. signal not generated.

These states must not collapse into one null condition when they have different semantics.

The exact vocabulary may differ, but the distinction must remain available to the fusion logic.

---

# 55. No Negative-by-Default

A missing signal must not receive a hidden default such as:

- -1;
- 0 when 0 means negative;
- false when false means contradiction.

Use explicit unknown/unavailable states.

---

# 56. No Double Counting

The Fusion Engine must avoid counting the same underlying signal multiple times merely because it appears through several graph paths.

Example:

One duplicate analysis result

creates:

- DuplicateMatch
- DUPLICATE_OF relationship
- graph provenance relationship

These must not automatically count as three independent signals.

The fusion input extraction layer must identify semantic signal identity.

---

# 57. Analysis Run Deduplication

When the same analytical execution produces multiple graph records representing one underlying fact, fusion must preserve the semantic distinction.

Use analysis_run_id and source entity relationships to identify unique signal provenance.

Do not double-weight identical facts simply because they are stored in multiple tables.

---

# 58. Cross-Project Fusion

Cross-project inputs may contribute to fusion only where they are already represented as valid graph relationships.

BE-011 must not independently discover cross-project relationships.

The engine must not:

- merge projects;
- merge claims;
- merge evidence;
- infer shared ownership.

Cross-project relationships remain intelligence signals.

Authorization enforcement belongs to BE-015, but the data model and APIs must remain compatible with future filtering.

---

# 59. Project Scope

Fusion queries should be target-scoped.

For a claim:

- gather relationships relevant to that claim;
- gather evidence connected to that claim;
- gather relevant analytical relationships;
- do not load unrelated graph data.

Avoid performing unrestricted full-graph scans.

---

# 60. Query Strategy

Use PostgreSQL queries and indexes.

Do not:

- load the complete graph into Python;
- recursively traverse arbitrary graph depth;
- introduce graph databases;
- create Redis graph storage.

BE-011 should operate on bounded relevant inputs.

---

# 61. Performance

V1 should remain simple.

Measure where practical:

- signal extraction time;
- fusion computation time;
- assessment persistence time;
- total fusion execution time.

Use real measurements.

Do not invent benchmark numbers.

State the environment and dataset size for measured benchmarks.

---

# 62. No Premature Optimization

Do not introduce:

- distributed fusion;
- graph caching;
- event-stream fusion;
- vector fusion;
- graph neural networks;
- Elasticsearch;
- external rule engines;
- ML inference infrastructure.

These are outside BE-011.

---

# 63. Service Architecture

Create a dedicated service such as:

backend/services/fusion.py

Responsibilities:

- collect eligible signals;
- normalize signals;
- validate configuration;
- evaluate deterministic rules;
- calculate assessment;
- calculate review priority;
- persist execution/results;
- preserve provenance;
- handle lifecycle.

Do not put fusion logic directly in API routes.

---

# 64. Repository Architecture

If repository separation is used:

backend/repositories/fusion.py

Responsibilities:

- persist fusion runs;
- retrieve target inputs;
- persist signal snapshots;
- persist assessments;
- persist review priority;
- retrieve historical outputs.

Keep business logic in the service layer.

---

# 65. Input Adapters

Where useful, introduce small adapters for existing subsystems.

Examples:

DuplicateSignalAdapter
TemporalSignalAdapter
VisionSignalAdapter
GraphSignalAdapter

Adapters should translate existing outputs into fusion signals.

They must not recalculate the original analytical result.

---

# 66. BE-006 Integration

The Fusion Engine must consume existing duplicate intelligence.

It may use:

- match type;
- pHash distance;
- embedding similarity;
- duplicate relationship;
- analysis run provenance.

It must not run another duplicate detector.

It must not create a new embedding.

It must not create a new pHash.

---

# 67. BE-008 Integration

The Fusion Engine must consume existing temporal intelligence.

It may use:

- temporal verdict;
- temporal relationship;
- relevant timestamp comparison;
- claim window relation.

It must not recreate:

- EXIF extraction;
- timestamp parsing;
- timestamp comparison;
- timezone normalization.

BE-008 remains the source of those semantics.

---

# 68. BE-009 Integration

The Fusion Engine may consume existing vision observations.

Examples:

- relevant class detected;
- class count;
- detection presence;
- configured threshold state.

However:

YOLO confidence is model confidence about detection, not evidence truth.

Do not directly treat:

confidence = 0.95

as:

integrity = 95%.

---

# 69. BE-007 Geospatial Integration

Where existing BE-007 spatial facts are available, fusion may consume them.

Examples:

- evidence associated with project;
- evidence location;
- evidence proximity;
- containment relation.

Do not implement new geospatial mathematics inside fusion where PostGIS/domain services already provide the fact.

Fusion consumes the signal.

---

# 70. BE-010 Relationship Integration

The Fusion Engine should use graph relationships as structured inputs.

Relevant examples:

Evidence → SUPPORTS → Claim
Evidence → CONTRADICTS → Claim
Evidence → DUPLICATE_OF → Evidence
Evidence → TEMPORALLY_RELATED_TO → Evidence
Evidence → ASSOCIATED_WITH → Claim

Relationship provenance and status must be respected.

SUPERSEDED and INVALIDATED relationships must not be treated as current ACTIVE relationships.

---

# 71. Relationship Status Filtering

Only eligible relationship statuses should contribute to active fusion.

At minimum:

ACTIVE

must be distinguishable from:

SUPERSEDED
INVALIDATED

Historical relationships may be useful for provenance/history but must not silently act as current signals.

---

# 72. Human Overrides

BE-011 must not implement a human override workflow.

The architecture may reserve a distinction between:

automated assessment

and future human decision/override.

Do not add reviewer workflow.

Do not let arbitrary API callers rewrite fusion outputs.

---

# 73. No Explainability Engine

BE-011 may store:

- signal summary;
- source references;
- methodology version;
- configuration version.

However, do not build the full BE-012 explainability engine.

Do not generate natural-language narratives as a required part of V1.

Structured reasoning inputs are sufficient.

---

# 74. No LLM

Do not use:

- OpenAI API;
- local LLMs;
- Ollama;
- Qwen;
- prompt-based reasoning;

for fusion.

The calculation must be deterministic and inspectable.

---

# 75. No ML

Do not train or deploy:

- XGBoost;
- LightGBM;
- scikit-learn classifiers;
- neural networks;

for the fusion output.

The future ML milestone is separate.

---

# 76. No Risk Score

Do not create fields such as:

risk_score
fraud_probability
fraud_score
authenticity_score
truth_score

in BE-011.

Review Priority is operational allocation.

Integrity Assessment is an automated assessment state.

They are not risk or fraud scores.

---

# 77. Security Boundary

BE-011 must not implement full authentication or RBAC.

However:

- APIs must be structured for future authorization;
- target IDs must be explicit;
- cross-project data must not be returned merely because graph links exist;
- repository/service boundaries should allow BE-015 to insert authorization checks.

---

# 78. Data Leakage Prevention

Fusion APIs must not return:

- raw image bytes;
- storage credentials;
- signed storage credentials;
- unnecessary EXIF;
- unrelated project records;
- internal secrets.

Only the inputs necessary to understand the fusion result should be exposed.

---

# 79. Audit Boundary

BE-011 must not implement the dedicated audit ledger.

However, fusion executions must retain enough provenance for BE-014 to audit later.

At minimum preserve:

- who/what initiated the run where supported;
- methodology;
- configuration;
- timestamps;
- input references;
- result references.

---

# 80. Migration

Create an Alembic migration for BE-011.

The migration must:

- create required fusion tables;
- add enums/check constraints where appropriate;
- create foreign keys;
- create indexes;
- be reversible;
- maintain a single Alembic head.

The migration must use the current BE-010 head as parent.

Do not create a second Alembic head.

Before implementation, inspect the live current Alembic head.

---

# 81. Testing Requirements

Testing must verify actual calculations and persistence.

## Unit tests

At minimum cover:

- signal normalization;
- unknown handling;
- unavailable handling;
- configuration validation;
- deterministic weighting;
- threshold logic;
- conflict handling;
- no-negative-by-default behavior;
- no-double-counting;
- assessment calculation;
- review priority calculation;
- method/version propagation;
- invalid configuration;
- zero-signal handling;
- failed-run handling.

Tests must assert exact expected outputs.

Do not merely assert that methods were called.

---

# 82. Integration Tests

Run against real PostgreSQL infrastructure.

Test:

## Claim fusion

Create:

Project
Claim
Evidence

Add:

Evidence → SUPPORTS → Claim

Run fusion.

Verify:

- fusion run persisted;
- assessment persisted;
- review priority persisted;
- provenance persisted.

## Contradiction

Create:

Evidence → CONTRADICTS → Claim

Run fusion.

Verify configured conflict/contradiction behavior.

## Multiple signals

Create a realistic combination of:

- support;
- contradiction;
- temporal relationship;
- duplicate relationship;
- vision observation where applicable.

Verify deterministic aggregation.

## Unknown signals

Provide missing/unknown inputs.

Verify they do not automatically reduce the assessment.

## Failed analysis

Create/identify a failed source analysis.

Verify it does not become a successful fusion signal.

## Zero observations

Use a completed analysis with zero observations.

Verify the run remains distinguishable and no fake signal is created.

## Reprocessing

Run fusion twice with the same configuration.

Verify two executions exist and historical output remains preserved.

## Configuration version

Run with configuration V1.

Create/update configuration V2.

Run again.

Verify each fusion execution retains its original configuration version.

## Idempotency

Repeated requests for the same deterministic fusion execution must not create uncontrolled duplicate results unless the API explicitly defines each request as a new execution.

The chosen execution/idempotency semantics must be documented.

## Cross-project

Use an authorized graph relationship crossing projects.

Verify fusion can consume the relationship without altering project ownership.

## Invalid target

Attempt fusion against:

- malformed UUID;
- unknown UUID;
- unsupported target type.

Verify proper 4xx behavior.

---

# 83. Regression Testing

After BE-011:

BE-001 → BE-010

must continue to function.

Run the complete existing test suite.

No completed milestone behavior should change unless a genuine BE-011 compatibility requirement exists.

---

# 84. Deterministic Test Fixtures

Fusion tests must use realistic actual data.

Do not use:

- arbitrary fake graph records detached from existing models;
- hardcoded "AI outputs" pretending to be real;
- fabricated analysis run IDs;
- fake similarity values presented as analytical results.

Where source analytical records are required, create them through their existing services/models or use fixtures that accurately represent persisted outputs.

---

# 85. Test Reproducibility

A fusion test that passes once but depends on:

- row insertion order;
- random UUID ordering;
- nondeterministic graph traversal order;
- current system time;

is unacceptable.

Where ordering affects computation, make the order explicit.

---

# 86. Database Integrity Checks

After integration/regression execution verify:

- no orphan fusion signals;
- no orphan assessments;
- no orphan review priority rows;
- no invalid statuses;
- no duplicate historical rows violating intended constraints;
- all fusion runs reference valid targets where enforced;
- configuration references remain valid.

---

# 87. Scope Audit

Before completion search the codebase for prohibited BE-011 scope.

Explicitly verify no implementation of:

- ML;
- LLM;
- fraud detection;
- deepfake detection;
- authenticity detection;
- review workflow;
- audit ledger;
- authentication;
- RBAC;
- explainability engine.

Prohibition mentions in documentation/tests are allowed.

Production implementation is not.

---

# 88. Performance Verification

Where infrastructure allows, measure:

- signal extraction;
- fusion calculation;
- persistence;
- total execution.

Use actual measurements.

Report:

- environment;
- database size;
- number of signals;
- sample count;
- mean/median where useful.

Do not invent performance values.

---

# 89. API Concurrency

Where the execution endpoint supports idempotency, test concurrent requests.

Example:

10 simultaneous identical requests

must behave according to the documented idempotency contract.

The database must provide the final correctness guarantee where required.

Do not rely solely on Python-level locking.

---

# 90. Transaction and Retry Behavior

Database race conditions must be handled correctly.

Where uniqueness constraints can race:

- catch expected integrity errors;
- resolve/retry appropriately;
- preserve transaction boundaries.

Do not convert database failures into success.

---

# 91. Files

Expected structure may include:

backend/
├── api/
│   └── v1/
│       └── endpoints/
│           └── fusion.py
│
├── schemas/
│   └── fusion.py
│
├── services/
│   └── fusion.py
│
├── repositories/
│   └── fusion.py
│
└── db/
    └── models.py

alembic/
└── versions/
    └── <BE-011 migration>

tests/
├── unit/
│   └── test_fusion.py
│
└── integration/
    └── test_fusion.py

Adapt to existing repository conventions.

Do not mechanically create duplicate architecture.

---

# 92. Existing Code Audit — Mandatory First Step

Before implementing anything, inspect:

backend/db/models.py
backend/services/
backend/repositories/
backend/api/v1/
backend/schemas/
backend/workers/
alembic/
tests/

Specifically identify:

- current AnalysisRun/AnalysisJob representation;
- AnalysisResult;
- DuplicateMatch;
- VisionDetection;
- temporal intelligence outputs;
- graph models;
- graph service;
- graph repository;
- existing pagination;
- existing UUID conventions;
- existing error conventions;
- existing async execution pattern;
- current Alembic head;
- configuration patterns.

Do not create duplicate models or utilities if equivalent infrastructure already exists.

---

# 93. Existing Architecture Must Be Preserved

Do not rewrite:

- BE-001 database foundation;
- BE-002 storage;
- BE-003 upload;
- BE-004 fingerprinting;
- BE-005 async jobs;
- BE-006 duplicate intelligence;
- BE-007 project/activity/claim/geo;
- BE-008 temporal intelligence;
- BE-009 vision intelligence;
- BE-010 evidence graph.

Fusion should consume these capabilities.

Only introduce compatibility changes genuinely required by BE-011.

---

# 94. Anti-Shortcut Gate

The following are explicit failures.

## Fake fusion

Do not return a preselected assessment regardless of inputs.

## Fake scoring

Do not hardcode a score such as:

0.75

for every record.

## Fake provenance

Do not invent upstream analysis run IDs.

## Fake normalization

Do not normalize unrelated values without documented semantics.

## Fake confidence

Do not call weighted scores probabilities.

## Missing-as-negative

Do not assign negative values to missing evidence.

## Double counting

Do not count the same analytical fact multiple times through multiple graph representations.

## Fake history

Do not overwrite previous fusion executions.

## Scope creep

Do not implement BE-012 or later milestones.

---

# 95. Definition of Done

BE-011 is complete only when all applicable requirements below are satisfied.

## Architecture

- Fusion Engine exists as a dedicated service.
- Integrity Assessment is distinct from Review Priority.
- V1 fusion is deterministic.
- Methodology version is persisted.
- Configuration version is persisted.
- Historical fusion executions are preserved.

## Inputs

- BE-006 signals can be consumed.
- BE-007 spatial/domain context can be consumed where applicable.
- BE-008 temporal signals can be consumed.
- BE-009 vision outputs can be consumed where applicable.
- BE-010 graph relationships can be consumed.

## Integrity

- Missing data is not treated as negative by default.
- FAILED upstream analyses do not become successful signals.
- COMPLETED with zero observations remains distinguishable.
- Contradictory signals are handled explicitly.
- Duplicate underlying signals are not double-counted.

## Outputs

- Integrity Assessment is persisted.
- Review Priority is persisted.
- Outputs reference the fusion execution.
- Outputs preserve methodology/configuration provenance.
- Outputs do not represent fraud probability or truth probability.

## API

- Fusion execution exists.
- Fusion run retrieval exists.
- Assessment retrieval exists.
- Historical retrieval exists where implemented.
- OpenAPI documentation exists.
- Validation errors are correct.

## Database

- Alembic migration exists.
- Correct migration parent is used.
- Single Alembic head remains.
- Migration upgrade works.
- Migration downgrade works where tested.
- Required constraints/indexes/FKs exist.

## Testing

- Unit tests pass.
- Integration tests pass against real infrastructure.
- Full regression suite passes.
- Actual calculation outputs are asserted.
- Concurrency/idempotency behavior is tested where applicable.

## Scope

No:

- ML;
- LLM;
- fraud detection;
- deepfake detection;
- authenticity detection;
- explainability engine;
- review workflow;
- audit ledger;
- authentication;
- RBAC.

---

# 96. Required Verification Report

Before declaring BE-011 complete, report:

## Implementation

- files created;
- files modified;
- files deleted;
- database changes;
- API changes.

## Fusion

- supported target types;
- supported signal types;
- signal-state vocabulary;
- normalization functions;
- weighting methodology;
- threshold methodology;
- conflict policy;
- unknown/unavailable behavior;
- no-double-counting mechanism.

## Provenance

- fusion run model;
- methodology version;
- configuration version;
- input lineage;
- historical execution behavior.

## Integration

- BE-006 integration;
- BE-007 integration;
- BE-008 integration;
- BE-009 integration;
- BE-010 integration.

## Tests

Report exact commands and results:

Unit:
Integration:
Full suite:
Alembic:
API verification:

Do not report tests as passed if infrastructure prevented execution.

---

# 97. Performance Report

Include actual measurements where possible:

Fusion input extraction:
Fusion calculation:
Assessment persistence:
Review priority persistence:
End-to-end fusion execution:

State:

- environment;
- dataset size;
- signal count;
- sample count.

Do not invent benchmark numbers.

If benchmarking is not possible because infrastructure is unavailable, state that explicitly.

---

# 98. Git Requirements

Implementation must be committed to:

Backend

Recommended commit message:

BE-011: implement fusion engine

Do not:

- force push;
- reset;
- rewrite history;
- delete branches;
- squash previous milestone history;
- remove completed BE-001 → BE-010 commits.

---

# 99. Final Acceptance Statement

BE-011 should result in a working deterministic Fusion Engine capable of consuming existing evidence-derived signals and producing:

Integrity Assessment
+
Review Priority

through:

real analytical inputs
+
explicit signal normalization
+
deterministic rules
+
versioned methodology
+
versioned configuration
+
provenance
+
historical fusion runs

while preserving the fundamental architecture:

The Fusion Engine combines structured evidence-intelligence signals into automated assessment and operational prioritization outputs. It does not determine truth, fraud, authenticity, or final human decisions.

The output of BE-011 becomes the structured assessment layer consumed by:

BE-012 — Explainability
BE-013 — Review

Do not implement BE-012+ during BE-011.