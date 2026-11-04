# BE-012 — Explainability Engine

Project: Proof-of-Action / Evidence Integrity & Intelligence Layer (EIIL)
Milestone: BE-012
Area: Backend — Explainability
Branch: Backend
Status: Implementation Specification
Depends On: BE-001 → BE-011
Primary Goal: Implement a deterministic, provenance-aware Explainability Engine that converts existing analytical signals, graph relationships, fusion outputs, and their lineage into structured, traceable explanations without introducing an LLM, changing analytical results, or making new substantive judgments.

---

# 1. Objective

Implement the first production version of the PoA Explainability Engine.

BE-012 sits after BE-011 Fusion.

It consumes existing:

- analytical observations;
- Evidence Graph relationships;
- Fusion Signals;
- Integrity Assessments;
- Review Priorities;
- analysis/fusion run provenance;
- methodology and configuration versions.

It produces a structured explanation of:

- what signals contributed;
- where those signals came from;
- which relationships were used;
- which inputs were unknown/unavailable;
- how the Fusion Engine combined them;
- why the resulting automated assessment and review priority were produced.

The Explainability Engine must answer:

> "How did the system arrive at this automated result?"

It must not answer:

> "Is the result objectively true?"

Human interpretation and final substantive decisions remain outside BE-012.

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
        Fusion
          │
          ├── Integrity Assessment
          └── Review Priority
                    │
                    ▼
             BE-012 Explainability
                    │
                    ├── Explanation
                    ├── Signal Contributions
                    ├── Provenance
                    ├── Input Lineage
                    └── Deterministic Reasoning Trace
                              │
                              ▼
                       Future BE-013 Review

BE-012 consumes previous outputs.

It does not replace them.

---

# 3. Locked Architectural Principles

The following are mandatory.

## 3.1 Explainability is not a new analytical engine

BE-012 must not:

- recalculate pHash;
- calculate embeddings;
- rerun YOLO;
- rerun temporal analysis;
- perform new geospatial calculations;
- discover duplicate relationships;
- perform fusion again.

It explains existing results.

---

# 4. Explainability Is Deterministic

Given the same:

- fusion run;
- fusion configuration;
- signal snapshot;
- graph relationships;
- methodology version;

the generated explanation must be deterministic.

The system must not depend on:

- LLM output;
- randomness;
- temperature;
- external AI APIs;
- nondeterministic ordering.

---

# 5. No LLM

Do not use:

- OpenAI API;
- Ollama;
- Qwen;
- local language models;
- prompt-based reasoning;
- generative AI;

to generate explanations.

BE-012 explanations must be generated from structured persisted facts.

---

# 6. No ML

Do not introduce:

- classifiers;
- regression models;
- neural networks;
- learned explanation models.

Explainability is a deterministic presentation and lineage layer.

---

# 7. No New Truth Determination

The Explainability Engine must never produce a new statement such as:

"the claim is true"

or:

"fraud occurred"

or:

"the evidence is authentic"

unless that statement is an exact representation of an already existing authorized human decision.

BE-012 is not authorized to create substantive determinations.

---

# 8. Explanation Layers

BE-012 should expose multiple levels of explanation.

## Level 1 — Result Summary

What automated output was produced.

Example:

Integrity Assessment:
MIXED

Review Priority:
HIGH

This is descriptive.

---

## Level 2 — Signal Summary

Which signals contributed.

Example:

- SUPPORTS relationship: positive
- CONTRADICTS relationship: negative
- temporal consistency: positive
- duplicate similarity: negative

---

## Level 3 — Contribution

How each signal affected the fusion calculation.

Example:

Signal:
DUPLICATE_SIMILAR

Normalized value:
-0.75

Configured weight:
0.30

Contribution:
-0.225

---

## Level 4 — Provenance

Where the signal came from.

Example:

Source:
BE-006 Duplicate Intelligence

Analysis Run:
<UUID>

Method:
duplicate_detection

Method Version:
...

---

## Level 5 — Input Lineage

The actual entities involved.

Example:

Evidence A
→ DUPLICATE_OF
→ Evidence B

or:

Evidence A
→ SUPPORTS
→ Claim X

The explanation should allow the consumer to navigate from result → signal → source → entity.

---

# 9. Explanation Must Be Structured

The primary BE-012 output must be machine-readable.

Do not make a natural-language paragraph the canonical explanation.

Structured output should contain fields such as:

- target;
- fusion run;
- assessment;
- review priority;
- signals;
- contributions;
- provenance;
- relationships;
- unknown/unavailable inputs;
- methodology;
- configuration;
- generated timestamp.

A human-readable summary may be generated from the same structured facts.

The structured representation remains authoritative.

---

# 10. Explanation ≠ Audit

BE-012 does not implement the audit ledger.

Audit belongs to:

BE-014 — Audit.

BE-012 may reference:

- execution timestamps;
- run IDs;
- provenance;

but must not create the dedicated tamper-evident audit chain.

---

# 11. Explanation ≠ Review

BE-012 does not implement:

- review cases;
- reviewer assignments;
- decisions;
- evidence requests;
- escalation;
- reviewer overrides.

Those belong to BE-013.

---

# 12. Explanation ≠ Fusion

The Explainability Engine must not modify:

- Integrity Assessment;
- Review Priority;
- fusion score;
- fusion state;
- fusion configuration.

It reads and explains the existing fusion result.

---

# 13. Canonical Explanation Target

The primary explanation target should be:

Fusion Run

A fusion run is the authoritative execution from which the explanation is generated.

Potential endpoint:

GET /api/v1/explanations/fusion/{fusion_run_id}

This avoids ambiguity about which historical assessment is being explained.

---

# 14. Latest Explanation

A convenience endpoint may expose the latest explanation for a target.

Potential:

GET /api/v1/explanations/{target_type}/{target_id}

This should resolve the latest eligible fusion execution and then generate/retrieve its explanation.

It must not silently choose arbitrary historical results.

---

# 15. Historical Explanation

A historical explanation endpoint may expose previous explanations.

Potential:

GET /api/v1/explanations/fusion/{fusion_run_id}

is sufficient because every fusion run is independently identifiable.

Do not create a second unexplained historical state model unnecessarily.

---

# 16. Explanation Run

BE-012 should decide explicitly whether explanations are:

1. generated synchronously on request from immutable fusion inputs; or
2. persisted as versioned Explanation Runs.

The preferred V1 approach is:

Generate deterministic explanations from persisted fusion data and optionally persist a versioned explanation record for reproducibility.

If persisted, use a model such as:

ExplanationRun
-------------
id
fusion_run_id
status
method
method_version
created_at
completed_at
error

The architecture must preserve the relationship:

Fusion Run
    ↓
Explanation Run

---

# 17. Explanation Method Version

Every persisted explanation must identify its methodology.

Example:

method:
    deterministic_fusion_explanation

method_version:
    explanation-v1

If explanation formatting or semantic generation changes materially, a new methodology version must be used.

Historical explanations must remain attributable to their original version.

---

# 18. Explanation Provenance

Every explanation must preserve:

- fusion run ID;
- fusion methodology;
- fusion configuration version;
- signal source;
- source entity;
- source analysis run;
- graph relationship ID where applicable;
- explanation methodology/version.

Provenance answers:

"Where did this explanation come from?"

It does not establish truth.

---

# 19. Signal Contribution Model

The explanation should expose each signal contribution.

Conceptual:

ExplanationSignal
-----------------
signal_type
state
raw_value
normalized_value
weight
contribution
source
source_entity_id
source_analysis_run_id
method
method_version
included
reason

The exact schema may differ.

The important requirement is that the explanation must trace a result back to actual persisted fusion inputs.

---

# 20. No Recalculation Drift

BE-012 should preferably use the values already persisted by BE-011.

For example, if BE-011 persisted:

normalized_value = -0.75
weight = 0.30
contribution = -0.225

BE-012 should explain those values.

It should not independently recompute:

normalized_value

using a new formula.

This prevents:

Fusion says one thing
Explanation says another thing.

---

# 21. Fusion Snapshot as Source

If BE-011's input snapshot contains sufficient information to reconstruct the explanation, it should be treated as the primary explanation input.

Where additional graph provenance is required, the explanation may resolve the referenced entities.

Do not depend on mutable current state when explaining a historical fusion run if the original snapshot contains the required information.

---

# 22. Historical Stability

A historical explanation must remain stable even if:

- new graph relationships are created;
- newer fusion runs exist;
- a new configuration becomes active;
- new analysis results are produced.

Explanation of:

Fusion Run #1

must continue to describe:

Fusion Run #1.

It must not silently change because Fusion Run #2 exists.

---

# 23. Invalidated Inputs

If an upstream relationship or signal has subsequently been:

- SUPERSEDED;
- INVALIDATED;

the historical explanation must preserve the fact that it contributed to the original fusion run.

The explanation may explicitly show:

status_at_fusion_time

and:

current_status

if that distinction is available.

Do not rewrite historical reasoning.

---

# 24. Unknown and Unavailable Inputs

The explanation must explicitly show important unknown/unavailable signals.

Example:

GPS:
UNKNOWN

Reason:
No location was available for the evidence.

The explanation must not state:

"GPS failed"

unless the source actually recorded a failure.

Distinguish:

UNKNOWN
UNAVAILABLE
NOT_APPLICABLE
NOT_GENERATED

according to BE-011 semantics.

---

# 25. Missing Data Explanation

The system should explain the semantic effect of missing data.

Example:

"Temporal consistency was not evaluated because the required source timestamp was unavailable."

This must be generated from structured state/reason information.

Do not invent reasons that are not present in source data.

---

# 26. Conflict Explanation

If BE-011 produced:

Integrity Assessment:
MIXED

because both positive and negative signals existed,

the explanation should expose the contributing conflict.

Example:

Positive:
SUPPORTS

Negative:
CONTRADICTS

The explanation should show:

- source relationship;
- relationship ID;
- relationship status;
- contribution;
- methodology.

Do not merely say:

"Conflicting evidence exists"

without identifying the structured sources.

---

# 27. Review Priority Explanation

The explanation must distinguish Review Priority from Integrity Assessment.

Example:

Review Priority:
HIGH

Explanation:

Priority was increased by:
- active contradiction signal;
- duplicate conflict;
- configured priority contribution.

It must not say:

"High fraud probability."

---

# 28. Assessment Explanation

Likewise:

Integrity Assessment:
MIXED

should be explained through the actual configured assessment rule.

Example:

Positive and negative evidence signals were both present.

Do not introduce a new semantic interpretation.

---

# 29. Rule Trace

BE-012 should expose which deterministic fusion rule produced the final assessment.

Example:

Rule:
POSITIVE_AND_NEGATIVE_SIGNALS → MIXED

or:

Rule:
NEGATIVE_SIGNALS_ONLY → CONTRADICTED

The rule identifier/version must come from the BE-011 methodology/configuration.

Do not create a second competing assessment rule.

---

# 30. Threshold Trace

Where BE-011 uses thresholds, expose:

- threshold name;
- threshold value;
- observed value;
- comparison result.

Example:

duplicate_similarity_threshold:
0.85

observed:
0.91

comparison:
TRIGGERED

Do not recalculate using different thresholds.

---

# 31. Weight Trace

Where weighted aggregation is used, expose:

signal
normalized value
configured weight
contribution

Example:

SUPPORTS
normalized = +1.000
weight = 0.250
contribution = +0.250

This allows the user to inspect how the result was constructed.

---

# 32. No Probability Language

Unless the underlying methodology explicitly implements calibrated probability, BE-012 must not use:

- probability;
- likelihood;
- confidence percentage;
- chance of fraud;
- probability of authenticity.

A deterministic score remains a deterministic score.

---

# 33. Human-Readable Summary

A human-readable explanation may be provided.

Example:

"The claim received a MIXED integrity assessment because active graph relationships included both supporting and contradicting evidence. Review priority was HIGH due to the configured contradiction and duplicate-conflict contributions."

This text must be generated from structured facts.

It must not contain additional reasoning that does not exist in the structured explanation.

---

# 34. Summary Generation

Summary generation must be deterministic.

The same structured explanation must produce the same summary.

Avoid:

- LLM generation;
- random templates;
- current-time-dependent wording;
- speculative language.

Template-based generation is acceptable.

---

# 35. Explanation Vocabulary

The explanation engine may use controlled vocabulary such as:

- CONTRIBUTED_POSITIVE
- CONTRIBUTED_NEGATIVE
- CONTRIBUTED_NEUTRAL
- UNKNOWN_INPUT
- UNAVAILABLE_INPUT
- CONFLICTING_INPUT
- NOT_APPLICABLE
- NOT_GENERATED
- RULE_TRIGGERED
- RULE_NOT_TRIGGERED

The exact vocabulary may follow existing BE-011 conventions.

Do not introduce unnecessary synonyms.

---

# 36. Explanation Schema

Potential top-level response:

{
    explanation_id,
    fusion_run_id,
    target,
    integrity_assessment,
    review_priority,
    methodology,
    configuration,
    summary,
    signals,
    rules,
    provenance,
    generated_at
}

Exact Pydantic representation may differ.

The schema must remain explicit.

---

# 37. API

Potential endpoints:

GET /api/v1/explanations/fusion/{fusion_run_id}

GET /api/v1/explanations/{target_type}/{target_id}

Optional:

POST /api/v1/explanations/fusion/{fusion_run_id}

Only introduce POST if explanations are explicitly persisted/materialized.

Do not create unnecessary mutation endpoints.

---

# 38. API Validation

Handle:

- invalid UUID;
- unknown fusion run;
- invalid target type;
- unknown target;
- failed fusion run;
- missing fusion outputs;
- invalid explanation version.

A failed fusion run must not receive a successful explanation.

---

# 39. Failed Fusion Explanation

If:

Fusion Run = FAILED

BE-012 must not invent an assessment explanation.

The API should return an explicit state such as:

EXPLANATION_UNAVAILABLE

with the underlying failure reference.

Do not convert failure into a successful explanation.

---

# 40. Zero-Signal Fusion

If:

Fusion Run = COMPLETED

and:

Integrity Assessment = INSUFFICIENT_EVIDENCE

the explanation should explicitly show:

- zero usable positive/negative signals;
- unknown/unavailable inputs where applicable;
- the deterministic rule that produced INSUFFICIENT_EVIDENCE.

Do not fabricate supporting evidence.

---

# 41. Database Design

If explanations are persisted, potential tables include:

explanation_runs
explanation_signals
explanation_rules

However, avoid unnecessary duplication.

BE-012 should preferably reference existing:

- fusion_runs;
- fusion_signals;
- integrity_assessments;
- review_priorities.

Do not copy entire evidence or graph tables.

---

# 42. Explanation Run Model

If persisted:

explanation_runs
----------------
id UUID PK
fusion_run_id UUID FK
status
method
method_version
summary
created_at
completed_at
error

Historical records must remain available.

---

# 43. Explanation Signal Model

If persisted:

explanation_signals
-------------------
id UUID PK
explanation_run_id UUID FK
signal_type
state
source
source_entity_id
source_analysis_run_id
raw_value
normalized_value
weight
contribution
reason
created_at

Only persist fields actually required for reproducibility.

---

# 44. Explanation Rule Model

If persisted:

explanation_rules
-----------------
id UUID PK
explanation_run_id UUID FK
rule_id
rule_version
triggered
parameters
result
created_at

This allows deterministic rule tracing.

A JSON structure may be sufficient instead of a separate table if the existing architecture favors snapshots.

Choose based on actual query/use cases.

---

# 45. Snapshot Strategy

The explanation should be reproducible from immutable/versioned data.

Recommended approach:

Fusion Run
    ↓
Input Snapshot
    ↓
Explanation

The explanation should not depend solely on:

"whatever the graph looks like today."

Historical explanation must remain historically accurate.

---

# 46. Relationship References

When an explanation signal originates from BE-010, preserve:

- graph relationship ID;
- source node;
- target node;
- relationship type;
- relationship status;
- analysis run;
- method;
- method version.

Do not copy complete evidence records.

---

# 47. Analytical References

When a signal originates from:

BE-006
BE-008
BE-009

preserve the relevant:

- source entity;
- analysis run;
- method;
- method version.

The explanation must allow downstream consumers to trace the result back to the originating analytical execution.

---

# 48. Cross-Project Explanations

If a cross-project graph relationship contributed to fusion, the explanation must identify that fact.

Example:

Project A / Evidence A
→ DUPLICATE_OF
→ Project B / Evidence B

The explanation should preserve project/entity references according to currently available data.

It must not bypass future authorization controls.

Do not implement RBAC in BE-012.

---

# 49. Authorization Boundary

BE-012 must not implement BE-015 authentication/RBAC.

However, explanation APIs must be designed so authorization can later be applied.

Do not expose unrelated underlying evidence simply because an explanation references it.

Return references and structured provenance rather than raw evidence content.

---

# 50. Privacy

Do not expose:

- raw image bytes;
- storage credentials;
- signed storage credentials;
- unnecessary EXIF;
- private metadata unrelated to the explanation;
- unrelated project information.

Only return data required to understand the reasoning trace.

---

# 51. Explainability of Vision Signals

If vision contributed to fusion, explain:

- detection signal type;
- relevant class;
- count where used;
- source AnalysisResult;
- model/method version;
- relevant configuration.

Do not claim:

"YOLO proved that the object exists."

Use descriptive language such as:

"Vision analysis recorded N detections of class X."

---

# 52. Explainability of Duplicate Signals

If duplicate intelligence contributed:

Explain:

- match type;
- pHash distance if used;
- embedding similarity if used;
- source DuplicateMatch;
- source analysis run;
- relationship ID if applicable.

Do not recalculate similarity.

Do not describe similarity as proof of duplication unless BE-006's relationship semantics explicitly establish that relationship.

---

# 53. Explainability of Temporal Signals

If temporal intelligence contributed:

Explain:

- temporal signal state;
- relevant source;
- analysis run;
- comparison result;
- relevant temporal relationship.

Do not rerun timestamp extraction.

Do not invent timestamps.

---

# 54. Explainability of Spatial Signals

If spatial context contributed:

Explain:

- spatial signal;
- source evidence/project;
- relevant existing spatial fact;
- source methodology where available.

Do not introduce new geospatial calculations.

---

# 55. Explainability of Graph Relationships

Explain graph relationships using the relationship's actual:

- type;
- status;
- provenance;
- method;
- method version;
- analysis run;
- source;
- target.

Only ACTIVE relationships should normally contribute to the current fusion explanation.

Historical relationships may be displayed as historical context if they were part of the original fusion snapshot.

---

# 56. Superseded and Invalidated Relationships

The explanation must preserve historical contribution.

Example:

A SUPPORTS relationship contributed to Fusion Run #1.

Later:

relationship_status = INVALIDATED

The explanation for Run #1 must still show that the relationship contributed at that time.

A latest explanation for a new Fusion Run should not treat the invalidated relationship as active.

---

# 57. Deterministic Ordering

Explanation output must use explicit ordering.

Examples:

- signal_type;
- contribution magnitude;
- source entity ID;
- creation timestamp;
- deterministic tie-breaker.

Do not rely on database default ordering.

This is required for reproducible API output and testing.

---

# 58. No Duplicate Explanation Signals

The same underlying fusion signal must not appear multiple times merely because:

- it has a graph relationship;
- it has a DuplicateMatch;
- it appears in the fusion snapshot.

Use the same signal identity/folding semantics defined by BE-011.

---

# 59. Explanation Completeness

The explanation should account for every material component of the fusion result.

At minimum:

- all included signals;
- excluded signals where exclusion materially affected the result;
- unknown/unavailable inputs relevant to the result;
- final assessment rule;
- priority rule;
- methodology version;
- configuration version.

Do not silently omit a signal that materially contributed.

---

# 60. Excluded Inputs

Where BE-011 intentionally excluded an input, explanation may show:

signal:
DUPLICATE_UNKNOWN

included:
false

reason:
UNKNOWN_STATE

The exact reason must come from actual fusion semantics.

Do not invent reasons.

---

# 61. Configuration Trace

The explanation must identify:

- configuration version;
- relevant weights;
- thresholds;
- enabled signals.

Avoid returning unrelated configuration fields.

---

# 62. Methodology Trace

The explanation must identify:

Fusion method:
deterministic_signal_fusion

Fusion version:
fusion-v1

Explanation method:
deterministic_fusion_explanation

Explanation version:
explanation-v1

This allows future methodology changes without rewriting historical explanations.

---

# 63. Reproducibility

A reviewer or future system should be able to reconstruct:

Fusion Run
    ↓
Inputs
    ↓
Signals
    ↓
Contributions
    ↓
Rules
    ↓
Assessment
    ↓
Priority

without requiring hidden model state.

This is the primary purpose of BE-012.

---

# 64. API Response Size

Explanation APIs must remain bounded.

Do not return:

- complete project datasets;
- complete graph datasets;
- all historical analysis results.

Use:

- pagination where historical lists exist;
- bounded signal counts;
- references instead of embedded raw entities.

---

# 65. Performance

V1 should remain simple.

Use:

- indexed fusion_run_id;
- indexed signal references;
- bounded graph lookups;
- PostgreSQL queries.

Do not introduce:

- graph databases;
- caching systems solely for explainability;
- Elasticsearch;
- distributed explanation engines.

---

# 66. No Premature Optimization

Do not implement:

- explanation caching infrastructure;
- vector search;
- semantic retrieval;
- LLM explanation;
- graph neural networks;
- distributed tracing systems solely for BE-012.

Existing provenance fields are sufficient.

---

# 67. Service Architecture

Create a dedicated service such as:

backend/services/explainability.py

Responsibilities:

- resolve fusion run;
- resolve persisted signals;
- construct deterministic explanation;
- resolve relevant provenance;
- construct rule trace;
- construct summary;
- optionally persist explanation run;
- expose structured result.

Do not put explanation logic directly in API routes.

---

# 68. Repository Architecture

If repository separation is used:

backend/repositories/explainability.py

Responsibilities:

- retrieve fusion runs;
- retrieve fusion signals;
- retrieve assessments;
- retrieve review priorities;
- retrieve graph provenance;
- persist explanation runs where applicable;
- retrieve historical explanation records.

Keep explanation/business logic in the service layer.

---

# 69. Schemas

Create:

backend/schemas/explainability.py

Schemas should cover:

- Explanation;
- ExplanationSignal;
- ExplanationRule;
- ExplanationProvenance;
- ExplanationTarget;
- ExplanationSummary;
- API errors where appropriate.

Use strict validation.

Do not expose internal ORM objects directly.

---

# 70. API Endpoint

Create:

backend/api/v1/endpoints/explainability.py

Register through:

backend/api/v1/router.py

Follow existing API conventions.

Use:

- structured errors;
- request IDs;
- existing pagination conventions;
- existing UUID validation.

---

# 71. Database Migration

If persistence is implemented, create an Alembic migration.

The migration must:

- use current BE-011 head as parent;
- create only required tables;
- create required constraints;
- create required indexes;
- be reversible;
- maintain one Alembic head.

Do not modify old applied migrations.

---

# 72. Testing — Unit

At minimum test:

- explanation generation;
- deterministic ordering;
- signal contribution rendering;
- provenance rendering;
- methodology/version rendering;
- configuration rendering;
- rule rendering;
- unknown signal rendering;
- unavailable signal rendering;
- conflicting signal rendering;
- zero-signal explanation;
- failed fusion handling;
- historical stability;
- no duplicate signals;
- no probability language;
- summary determinism.

Tests must assert actual returned structures.

---

# 73. Testing — Integration

Against real PostgreSQL infrastructure test:

## Successful fusion

Create a real fusion run and retrieve its explanation.

Verify all major sections.

## Signal lineage

Verify a signal points to:

- correct source;
- correct entity;
- correct analysis run.

## Graph lineage

Verify graph relationship IDs and provenance appear correctly.

## Configuration

Verify configuration version is preserved.

## Historical run

Create two fusion runs.

Retrieve explanation for Run #1.

Create Run #2.

Verify Run #1 explanation remains unchanged.

## Invalidated relationship

Create relationship → fusion → explanation.

Invalidate relationship.

Verify historical explanation remains unchanged.

## Unknown inputs

Verify UNKNOWN signals are represented explicitly.

## Failed fusion

Verify no successful explanation is produced.

## Zero-signal fusion

Verify INSUFFICIENT_EVIDENCE is explained without fabricated signals.

## Cross-project

Verify cross-project source references are represented without changing ownership.

---

# 74. Full Regression

After BE-012:

BE-001 → BE-011

must continue to function.

Run the complete test suite.

No previous milestone should regress.

---

# 75. API Verification

Verify live:

- successful explanation;
- invalid fusion run;
- invalid UUID;
- failed fusion;
- historical fusion;
- latest target explanation;
- deterministic response ordering.

Use actual running infrastructure.

Do not rely solely on mocked HTTP tests.

---

# 76. Database Integrity

After integration tests verify:

- no orphan explanation runs;
- no orphan explanation signals;
- no invalid statuses;
- no invalid foreign keys;
- no duplicate explanation identities where uniqueness is intended;
- historical records remain intact.

---

# 77. Performance Verification

Where practical measure:

- explanation retrieval;
- signal assembly;
- provenance lookup;
- summary generation;
- end-to-end explanation generation.

Report:

- environment;
- number of signals;
- number of graph relationships;
- sample count.

Do not invent benchmark numbers.

---

# 78. Scope Audit

Before completion verify no implementation of:

- LLM;
- ML;
- fraud detection;
- deepfake detection;
- authenticity detection;
- truth determination;
- review workflow;
- human decision workflow;
- audit ledger;
- authentication;
- RBAC;
- new fusion logic.

Documentation prohibition mentions are allowed.

Production implementation is not.

---

# 79. Existing Code Audit — Mandatory First Step

Before implementation inspect:

backend/db/models.py
backend/services/fusion.py
backend/repositories/fusion.py
backend/schemas/fusion.py
backend/api/v1/endpoints/fusion.py
backend/services/evidence_graph.py
backend/repositories/evidence_graph.py
backend/schemas/evidence_graph.py
backend/api/v1/endpoints/evidence_graph.py
backend/workers/
alembic/
tests/

Specifically identify:

- fusion run model;
- fusion signal model;
- assessment model;
- priority model;
- input snapshot structure;
- signal identity;
- configuration representation;
- graph relationship provenance;
- existing API response conventions;
- current Alembic head.

Do not duplicate existing fusion structures.

---

# 80. Existing Architecture Must Be Preserved

Do not rewrite:

- BE-006 duplicate intelligence;
- BE-008 temporal intelligence;
- BE-009 vision intelligence;
- BE-010 evidence graph;
- BE-011 fusion engine.

BE-012 reads their outputs.

Only introduce compatibility changes genuinely required by explainability.

---

# 81. Anti-Shortcut Gate

The following are explicit failures.

## Fake explanation

Do not produce a generic paragraph regardless of inputs.

## Fake provenance

Do not invent analysis run IDs.

## Fake contribution

Do not recompute values differently from BE-011.

## Fake reasoning

Do not add conclusions not present in the structured source data.

## LLM shortcut

Do not use an LLM to generate the explanation.

## Historical mutation

Do not rewrite explanations when newer fusion runs appear.

## Truth shortcut

Do not turn automated assessment into a claim of truth/fraud/authenticity.

## Scope creep

Do not implement BE-013+.

---

# 82. Definition of Done

BE-012 is complete only when all applicable requirements below are satisfied.

## Architecture

- Dedicated Explainability service exists.
- Explainability consumes existing fusion outputs.
- Explanation is deterministic.
- Methodology version exists.
- Historical explanations remain stable.

## Explanation

- Result summary exists.
- Signal summary exists.
- Contributions exist.
- Provenance exists.
- Input lineage exists.
- Rule trace exists.
- Configuration trace exists.
- Unknown/unavailable states are explicit.
- Conflicts are explicit.

## Integrity

- No new analytical calculations.
- No recalculation drift.
- No fabricated provenance.
- No hidden missing-data assumptions.
- No probability claims without calibrated probabilistic methodology.

## API

- Fusion explanation retrieval exists.
- Latest target explanation exists where implemented.
- Validation errors are correct.
- OpenAPI documentation exists.
- Responses are bounded.

## Database

If persistence is used:

- Alembic migration exists.
- Correct parent is used.
- Single head remains.
- Upgrade works.
- Downgrade works where tested.
- Foreign keys and indexes exist.

## Testing

- Unit tests pass.
- Integration tests pass against real infrastructure.
- Full regression suite passes.
- Historical stability is tested.
- Deterministic ordering is tested.
- Provenance lineage is tested.

## Scope

No:

- LLM;
- ML;
- fraud detection;
- authenticity detection;
- truth engine;
- new fusion logic;
- review workflow;
- audit ledger;
- authentication;
- RBAC.

---

# 83. Required Verification Report

Before declaring BE-012 complete, report:

## Implementation

- files created;
- files modified;
- files deleted;
- database changes;
- API changes.

## Explanation

- explanation target;
- explanation methodology;
- signal representation;
- contribution representation;
- rule trace;
- provenance trace;
- configuration trace;
- historical behavior;
- unknown/unavailable behavior.

## Integration

- BE-006 lineage;
- BE-007 lineage;
- BE-008 lineage;
- BE-009 lineage;
- BE-010 graph lineage;
- BE-011 fusion lineage.

## Tests

Report exact commands and results:

Unit:
Integration:
Full suite:
Alembic:
API verification:

Do not report tests as passed if infrastructure prevented execution.

---

# 84. Performance Report

Include actual measurements where possible:

Explanation generation:
Signal assembly:
Graph provenance lookup:
API retrieval:
End-to-end explanation:

State:

- environment;
- number of signals;
- number of graph relationships;
- sample count.

Do not invent benchmark numbers.

---

# 85. Git Requirements

Implementation must be committed to:

Backend

Recommended commit message:

BE-012: implement explainability

Do not:

- force push;
- reset;
- rewrite history;
- delete branches;
- squash previous milestone history;
- remove completed BE-001 → BE-011 commits.

---

# 86. Final Acceptance Statement

BE-012 should result in a deterministic Explainability Engine capable of transforming existing Fusion Engine outputs into a structured, traceable explanation containing:

Result
+
Signals
+
Contributions
+
Rules
+
Provenance
+
Configuration
+
Input Lineage

while preserving the fundamental architecture:

The Explainability Engine explains how an automated assessment was produced from existing evidence-intelligence signals. It does not determine truth, fraud, authenticity, or final human decisions.

The output of BE-012 becomes the structured reasoning layer consumed by:

BE-013 — Review

Do not implement BE-013+ during BE-012.