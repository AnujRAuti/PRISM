BE-013 — Review Priority & Case Generation Boundary

Production Task File
Milestone: BE-013
Status: Ready for implementation
Depends on: BE-001 → BE-012
Primary dependencies: BE-011 Fusion Engine, BE-012 Explainability
Recommended commit: BE-013: implement review case generation

1. Objective

Implement the backend layer that converts existing intelligence outputs into reviewable work items.

BE-013 introduces the first investigation workflow boundary:

Signals and assessments may indicate that something deserves human attention; BE-013 turns that condition into a Review Case.

BE-013 must not determine whether evidence is true, fraudulent, authentic, manipulated, or legally sufficient.

The responsibility boundary is:

BE-006 Duplicate Intelligence
BE-007 Project / Claim / Location
BE-008 Temporal Intelligence
BE-009 Vision Observations
BE-010 Evidence Graph
        ↓
BE-011 Fusion Engine
        ↓
Integrity Assessment + Review Priority
        ↓
BE-012 Explainability
        ↓
BE-013 Case Generation
        ↓
Review Case
        ↓
Future reviewer workflow

BE-013 therefore consumes existing persisted outputs rather than rebuilding analytical logic.

2. Architectural Boundary

BE-013 introduces the Review Case domain object defined by the frozen architecture.

A Review Case is the primary human-review unit.

A case may originate from:

system-generated intelligence;
an authorized user;
a citizen report;
an external system.

For this milestone, the system-generated path is primary.

Manual/citizen/external origins must be represented in the data model where appropriate, but their complete workflows are outside this milestone.

3. Core Principles
3.1 Case generation is not truth determination

The system must never interpret case creation as:

fraud detected

or:

evidence proven false

or:

claim rejected

Instead:

intelligence condition
        ↓
review-worthy condition
        ↓
case created

A case means:

A human review workflow has been initiated because configured conditions indicate that investigation may be useful.

4. Review Case Model

Create a review_cases table.

Minimum fields:

Identity
id
UUID primary key
Scope
project_id
nullable where architecture requires non-project-originated cases
claim_id
nullable
evidence_id
nullable
fusion_run_id
nullable
Origin

Enum:

SYSTEM_SIGNAL
AUTHORIZED_USER
CITIZEN_REPORT
EXTERNAL_SYSTEM
Lifecycle
OPEN
ASSIGNED
INVESTIGATING
DECISION_PENDING
RESOLVED
ESCALATED

Do not create a single generic status that combines workflow state and outcome.

Priority

Store the review priority derived from BE-011.

Do not recompute the BE-011 score.

Suggested fields:

priority_band
priority_value
priority_source
priority_config_version

The persisted values must identify which fusion run produced them.

Assignment

Nullable:

assigned_to
assigned_at

Do not implement full RBAC/authorization in BE-013.

Authorization remains a later boundary.

Human decision

Nullable:

decision
decision_rationale
decided_by
decided_at

Decision vocabulary:

SUPPORTED
CONTRADICTED
INCONCLUSIVE
INSUFFICIENT_EVIDENCE

A decision is not generated automatically by BE-013.

Escalation

Nullable:

escalated_to
escalated_at
escalation_reason

Escalation must not overwrite the previous assignment or decision.

Timestamps
created_at
updated_at
resolved_at
5. Case Generation Policy

Introduce a versioned deterministic Case Generation Policy.

The policy determines whether an existing intelligence result should create a case.

It must not introduce a new scoring system.

Example policy inputs:

priority_band
assessment
signal states
conflict presence
configured thresholds

Example policy:

URGENT → generate case
HIGH   → generate case
NORMAL → configurable
LOW    → normally no automatic case

The exact defaults must be represented as configuration rather than hard-coded throughout service logic.

6. Policy Versioning

Create a persisted policy/configuration model.

Suggested:

case_generation_configurations

Fields:

id
version
name
enabled
configuration
created_at

The configuration must be immutable after creation.

A new policy means a new version.

Do not mutate historical configuration records.

7. Case Generation Run

Case generation must be traceable.

Create:

case_generation_runs

Suggested fields:

id
fusion_run_id
configuration_id
method
method_version
input_snapshot
status
created_at
completed_at
error

Statuses:

RUNNING
COMPLETED
FAILED

Method:

deterministic_case_generation

Version:

case-generation-v1

The run must record enough information to reconstruct why a case was or was not generated.

8. Idempotency / Duplicate Case Prevention

Repeated processing of the same Fusion Run must not create duplicate active cases.

Recommended invariant:

one active system-generated case per fusion run

Enforce this at the database level.

Do not depend solely on Python checks.

Concurrent requests must be safe.

For example:

10 concurrent generation requests
        ↓
1 case
9 requests observe existing case

The exact response semantics may be:

201 → newly created case
200 → existing case

if using a materialization endpoint.

9. Case Deduplication Across Runs

Do not blindly create a second case merely because a claim receives another fusion run.

BE-013 must distinguish:

Same Fusion Run
same fusion_run_id
→ same case
New Fusion Run
new fusion_run_id
→ potentially new case

Whether a new run should create a new case must be governed by the case-generation policy.

Do not implement complex case merging in V1.

10. Case Source Lineage

Every system-generated case must retain lineage to:

Review Case
    ↓
Case Generation Run
    ↓
Fusion Run
    ↓
Fusion Signals
    ↓
Evidence / Claim
    ↓
Analysis Runs / Graph Relationships

At minimum, the case must directly reference:

case_generation_run_id
fusion_run_id
target type
target ID
project ID where applicable

The case must not duplicate the entire fusion dataset.

11. Input Handling

BE-013 must consume persisted BE-011 values.

It may read:

Integrity Assessment
Review Priority
priority band
priority value
assessment
fusion configuration
fusion signals
fusion run status

It must not recalculate:

signal weights;
normalized values;
fusion score;
integrity assessment;
review priority.
12. Failed / Incomplete Inputs

Case generation must reject unusable fusion runs.

FAILED fusion run
→ no case
→ CASE_GENERATION_UNAVAILABLE / appropriate error
RUNNING fusion run
→ no case
→ generation unavailable until completed
COMPLETED with no signals

Must be handled according to the persisted assessment/priority.

Do not interpret absence of signals as fraud or contradiction.

Missing assessment

Reject generation rather than inventing a decision.

Missing priority

Reject generation rather than calculating a replacement score.

13. Case Creation Rules

Case creation should be deterministic.

Example:

IF fusion_run.status != COMPLETED
    → unavailable

IF assessment missing
    → unavailable

IF review_priority missing
    → unavailable

IF policy disabled
    → no case

IF policy conditions satisfied
    → create case

ELSE
    → no case

The policy result should be explicit.

Recommended result states:

CASE_CREATED
CASE_ALREADY_EXISTS
NOT_ELIGIBLE
UNAVAILABLE
14. Explainability Integration

Every automatically generated case must be explainable through BE-012.

The case should reference the Fusion Run rather than creating another explanation engine.

Reviewer-facing APIs should be able to resolve:

Case
 ↓
Fusion Run
 ↓
Explanation

Do not duplicate explanation text inside the case unless required for immutable snapshot purposes.

If a case-generation snapshot is stored, it must contain only the relevant persisted facts and policy result.

15. Case Snapshot

Persist an immutable generation snapshot.

Example conceptual structure:

{
  target_type,
  target_id,
  project_id,
  fusion_run_id,
  assessment,
  priority_band,
  priority_value,
  policy_version,
  eligibility_result,
  triggering_conditions
}

The snapshot is not a replacement for authoritative domain records.

It exists to preserve:

What the system knew when this case was generated.

16. Human Decision Boundary

BE-013 may expose fields and endpoints for human decisions, but automatic case generation must never populate them.

The system must not automatically set:

SUPPORTED
CONTRADICTED
INCONCLUSIVE
INSUFFICIENT_EVIDENCE

based on fusion output.

Fusion assessment:

SUPPORTED
CONTRADICTED
MIXED
UNKNOWN
INSUFFICIENT_EVIDENCE

and human decision:

SUPPORTED
CONTRADICTED
INCONCLUSIVE
INSUFFICIENT_EVIDENCE

are separate concepts.

Do not collapse them.

17. Assignment Boundary

BE-013 may implement basic assignment state transitions.

Allowed lifecycle:

OPEN
  ↓
ASSIGNED
  ↓
INVESTIGATING
  ↓
DECISION_PENDING
  ↓
RESOLVED

Escalation:

OPEN / ASSIGNED / INVESTIGATING / DECISION_PENDING
        ↓
    ESCALATED

Do not implement unrestricted status mutation.

Invalid transitions must return structured errors.

18. Resolution

A case may only become:

RESOLVED

after a human decision exists.

Therefore:

RESOLVED + decision = valid
RESOLVED + no decision = invalid

A case cannot be automatically resolved by the case-generation engine.

19. Reopening

V1 may support reopening a resolved case if required by the state model.

If implemented:

RESOLVED
    ↓
OPEN

The previous resolution must remain historically visible.

Do not overwrite the previous decision.

If reopening is deferred, document it explicitly rather than silently implementing a partial workflow.

20. Escalation

Escalation must preserve:

original case;
original assignment;
previous lifecycle history;
previous human decisions.

Escalation is a workflow action, not a new intelligence assessment.

21. Case History

Create a dedicated case history table:

review_case_events

Each event should contain:

id
case_id
event_type
from_status
to_status
actor_id
metadata
created_at

Examples:

CASE_CREATED
ASSIGNED
UNASSIGNED
INVESTIGATION_STARTED
DECISION_PENDING
DECISION_RECORDED
ESCALATED
RESOLVED
REOPENED

The history must be append-only.

Do not modify historical events.

This is domain workflow history, not the BE-023-style tamper-evident audit ledger. Do not implement a cryptographic audit chain here.

22. API

Implement:

Generate case
POST /api/v1/review-cases/from-fusion/{fusion_run_id}

Expected behavior:

201 → new case
200 → existing case
422 → fusion unavailable / missing required inputs
Get case
GET /api/v1/review-cases/{case_id}
List cases
GET /api/v1/review-cases

Support deterministic pagination.

Optional filters:

project_id
status
priority_band
origin
assigned_to
Case history
GET /api/v1/review-cases/{case_id}/history
Assignment
POST /api/v1/review-cases/{case_id}/assign
Start investigation
POST /api/v1/review-cases/{case_id}/investigate
Decision
POST /api/v1/review-cases/{case_id}/decision

Required:

decision
rationale

Decision must be human-supplied.

Escalate
POST /api/v1/review-cases/{case_id}/escalate

Required:

reason
Resolve
POST /api/v1/review-cases/{case_id}/resolve

Must require an existing human decision.

23. Schemas

Create:

backend/schemas/review_case.py

Include:

ReviewCaseCreate
ReviewCaseResponse
ReviewCaseListResponse
ReviewCaseHistoryResponse
CaseDecisionRequest
CaseAssignmentRequest
CaseEscalationRequest
CaseGenerationResponse

Use strict enums.

Reject unknown/invalid lifecycle values.

24. Service Layer

Create:

backend/services/review_case.py

Responsibilities:

load Fusion Run;
verify completed state;
load assessment/priority;
load active case-generation configuration;
evaluate policy;
create generation run;
create/reuse case;
create case history event;
enforce state transitions;
record decisions;
record escalation;
resolve cases.

The service must not contain:

fusion calculations;
vision inference;
duplicate calculations;
temporal calculations;
geospatial calculations;
LLM calls.
25. Repository Layer

Create:

backend/repositories/review_case.py

Responsibilities:

case persistence;
generation run persistence;
configuration persistence;
case history persistence;
deterministic list queries;
case lookup;
active-case uniqueness enforcement.

Use database constraints wherever possible.

26. Models

Modify:

backend/db/models.py

Add:

ReviewCase
CaseGenerationConfiguration
CaseGenerationRun
ReviewCaseEvent

Use foreign keys with deliberate RESTRICT behavior where historical lineage must remain valid.

Do not cascade-delete analytical lineage.

27. Migration

Create:

alembic/versions/f6a7b8c9d013_be013_review_cases.py

Parent:

e5f6a7b8c012

Requirements:

single Alembic head;
upgrade tested live;
downgrade tested live;
appropriate indexes;
uniqueness constraints;
lifecycle CHECK constraints;
FK constraints.
28. Suggested Indexes

At minimum:

review_cases(project_id)
review_cases(status)
review_cases(priority_band)
review_cases(assigned_to)
review_cases(fusion_run_id)
review_cases(created_at)
review_case_events(case_id, created_at)
case_generation_runs(fusion_run_id)

For active system-generated cases, use a partial unique constraint/index where supported.

29. Concurrency Requirement

The following must be tested:

10 concurrent
POST /review-cases/from-fusion/{same_run}

Expected:

1 created case
9 existing-case responses

Database state:

exactly 1 active system-generated case

Do not rely on application-level locks.

30. State Transition Validation

Valid transitions must be explicit.

Example:

OPEN → ASSIGNED
OPEN → ESCALATED

ASSIGNED → OPEN
ASSIGNED → INVESTIGATING
ASSIGNED → ESCALATED

INVESTIGATING → DECISION_PENDING
INVESTIGATING → ESCALATED

DECISION_PENDING → RESOLVED
DECISION_PENDING → ESCALATED

ESCALATED → ASSIGNED
ESCALATED → INVESTIGATING

RESOLVED → OPEN   [only if reopening is implemented]

Invalid transitions must not modify the database.

31. Human Decision Rules

Decision endpoint requirements:

Decision required
decision != null
rationale != empty
Decision vocabulary
SUPPORTED
CONTRADICTED
INCONCLUSIVE
INSUFFICIENT_EVIDENCE
No automatic decisions

Case generation cannot populate these fields.

History

Decision creation generates a case event.

A later decision change must preserve the previous decision in history.

32. Review Priority Semantics

BE-013 must preserve the meaning established in BE-011:

Review Priority is an allocation signal for human attention.

It is not:

fraud probability;
authenticity probability;
truth probability;
severity score;
legal risk score.

Do not rename it into any of those concepts.

33. Assessment Semantics

Do not reinterpret:

SUPPORTED
CONTRADICTED
MIXED
UNKNOWN
INSUFFICIENT_EVIDENCE

These remain BE-011's deterministic Integrity Assessment vocabulary.

A case can exist with:

UNKNOWN

or:

INSUFFICIENT_EVIDENCE

if the configured case-generation policy allows it.

The existence of a case must never itself imply contradiction or wrongdoing.

34. Explainability Requirement

A generated case must be able to resolve:

case
→ generation run
→ fusion run
→ explanation

Integration test must verify the complete lineage.

Example:

GET /review-cases/{case_id}

{
  ...
  "fusion_run_id": "...",
  "case_generation_run_id": "...",
  "priority_band": "HIGH"
}

Then:

GET /explanations/fusion/{fusion_run_id}

must provide the explanation of the analytical result that caused the case.

35. Tests

Create:

tests/unit/test_review_case.py
tests/integration/test_review_case.py
Unit tests

At minimum:

policy eligibility;
disabled policy;
priority-band conditions;
assessment conditions;
completed fusion run;
running fusion run rejected;
failed fusion run rejected;
missing assessment rejected;
missing priority rejected;
deterministic policy result;
configuration version recorded;
state transitions;
invalid transitions;
decision validation;
empty rationale rejection;
resolution without decision rejected;
escalation;
case history creation;
no automatic human decision;
no fusion recalculation.
36. Integration Tests

Use real PostgreSQL.

Test:

Case generation
completed fusion run
→ case generated
Idempotency
same fusion run
→ one case
Concurrency
10 concurrent requests
→ one case
History

Verify:

case creation
→ assignment
→ investigation
→ decision pending
→ decision
→ resolution

creates appropriate append-only events.

Failed fusion

Verify:

FAILED fusion
→ no case
Historical lineage

Verify case continues referencing the original fusion run even after later runs exist.

Explanation lineage

Verify:

case
→ generation run
→ fusion run
→ explanation
Cross-project

Verify cross-project evidence relationships do not cause BE-013 to bypass project identity semantics.

Do not introduce authorization logic merely for this test.

37. Full Regression

Required before completion:

pytest

Expected:

0 failed

Also run:

alembic upgrade head

then:

alembic downgrade <previous_revision>

then:

alembic upgrade head

Confirm:

single Alembic head
38. API Runtime Verification

Verify against the actual running stack:

PostgreSQL
PostGIS
Redis
MinIO
FastAPI

Verify:

case generation;
duplicate generation;
case retrieval;
listing;
history;
assignment;
investigation;
decision;
escalation;
resolution.

Do not consider mocked-only tests sufficient.

39. Performance

Measure:

Case generation

At least:

n >= 20

Report:

average latency;
minimum;
maximum;
target complexity;
whether database/network time is included.
Concurrent generation

Measure the 10-request idempotency test.

Do not invent performance numbers.

40. Data Integrity Checks

After integration testing verify:

0 orphaned review cases
0 orphaned case-generation runs
0 orphaned case events
0 invalid lifecycle values
0 duplicate active system-generated cases
0 cases without valid lineage

Also verify:

RESOLVED cases have decisions

and:

automatic generation never created human decisions
41. Anti-Shortcut Gates

The implementation is not complete if it:

creates a case directly from a raw signal without fusion;
calculates a new score;
recalculates BE-011 priority;
recalculates integrity assessment;
interprets priority as probability;
automatically decides a case;
marks evidence fraudulent;
detects authenticity/deepfakes;
invokes an LLM;
adds ML;
creates a new graph engine;
modifies BE-006 through BE-012 analytical semantics;
bypasses persisted Fusion Runs;
silently creates duplicate cases;
relies only on Python for uniqueness;
deletes previous case history;
overwrites human decisions;
introduces RBAC;
introduces the tamper-evident audit ledger.
42. Explicit Non-Goals

BE-013 does not implement:

reviewer dashboard UI;
full investigation workspace;
RBAC;
authentication;
organization authorization;
citizen portal;
evidence requests;
notifications;
email;
SMS;
audit ledger;
ML;
LLM;
fraud detection;
authenticity detection;
deepfake detection;
truth determination;
new fusion signals;
new scoring;
explainability logic;
analytics dashboards.

Those remain separate milestones.

43. Required Files
Create
backend/services/review_case.py
backend/repositories/review_case.py
backend/schemas/review_case.py
backend/api/v1/endpoints/review_case.py

alembic/versions/f6a7b8c9d013_be013_review_cases.py

tests/unit/test_review_case.py
tests/integration/test_review_case.py
Modify
backend/db/models.py
backend/api/v1/router.py
Delete
none
44. Completion Contract

BE-013 is complete only when all of the following are true:

Review Case domain exists.
Case-generation policy is versioned.
Case-generation runs are persisted.
Fusion Run is the authoritative analytical input.
No analytical logic is duplicated.
Case creation is deterministic.
Same Fusion Run cannot create duplicate active cases.
Concurrent creation is database-safe.
Case lineage is preserved.
Case history is append-only.
Lifecycle transitions are validated.
Human decisions remain human actions.
Resolution requires a decision.
Explainability remains accessible through Fusion Run lineage.
Failed/incomplete fusion runs cannot create successful cases.
Alembic upgrade/downgrade succeeds.
Unit tests pass.
Integration tests pass against real PostgreSQL.
Full regression passes.
Runtime API verification succeeds.
No prohibited scope has leaked into BE-013.
Git commit is created only after verification.
45. Recommended Commit
BE-013: implement review case generation

Final architectural boundary:

BE-011 calculates intelligence. BE-012 explains intelligence. BE-013 turns configured intelligence conditions into an auditable human-review workflow item. It does not decide the outcome.