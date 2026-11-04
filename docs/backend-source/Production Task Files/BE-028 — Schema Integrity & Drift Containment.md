# BE-028 — Schema Integrity & Drift Containment

**Project:** Proof-Of-Action (PoA)  
**Task ID:** BE-028  
**Category:** Backend / Database / Schema / Migrations / Integrity  
**Priority:** High  
**Status:** Not Started  
**Depends On:** BE-027  
**Blocks:** Future production database hardening and schema-dependent backend work

---

# 1. TASK OBJECTIVE

Resolve and contain the database-schema integrity and migration-drift risks identified during BE-027.

BE-027 established that the PoA backend foundation is already substantially mature:

- FastAPI backend
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- PostGIS
- pgvector
- 70 ORM models
- 21 Alembic revisions
- Single migration chain
- Existing production-style test infrastructure
- Existing audit ledger validation

BE-027 identified three important schema/infrastructure problems:

### B-1 — HIGH
`User.username` / `User.email` declare uniqueness at the ORM/model level, but the currently migrated database schema does not enforce the corresponding uniqueness constraints.

Existing live data contains duplicates.

This means simply adding a unique constraint could fail or could require destructive/ambiguous data remediation.

### B-2 — MEDIUM
`alembic check` currently reports **16 unreviewed schema-drift operations**.

These operations must be investigated and classified rather than blindly migrated.

### B-3 — MEDIUM
There is currently no effective automated gate preventing additional ORM/database schema divergence from accumulating.

---

# 2. PRIMARY GOAL

By the end of BE-028, the repository must have a clearly understood and controlled relationship between:

    SQLAlchemy ORM models
              |
              v
        Alembic metadata
              |
              v
       Alembic migrations
              |
              v
       PostgreSQL schema

The task must establish which differences are:

- legitimate historical differences
- intentional database-only objects
- ORM-only declarations
- migration omissions
- actual schema drift
- unsafe/unresolved differences

The goal is NOT simply:

    "Make alembic check return zero"

The goal is:

    "Make schema state intentional, explainable, reproducible, and protected against future accidental drift."

---

# 3. CRITICAL SAFETY RULE

## DO NOT perform destructive data remediation automatically.

In particular:

**Do NOT delete, merge, rename, or arbitrarily modify duplicate users merely to satisfy uniqueness constraints.**

The existing development/production-like database contains real data.

Before any destructive or potentially destructive migration:

1. Quantify the affected records.
2. Identify the duplicate groups.
3. Determine how those records are referenced.
4. Determine whether the records represent separate legitimate identities.
5. Determine whether an application-level identity policy exists.
6. Design a deterministic remediation strategy.
7. Document the strategy.
8. Stop and request approval before executing destructive remediation.

If uniqueness cannot safely be enforced during this task, document the blocker instead.

A correct unresolved blocker is preferable to corrupted data.

---

# 4. SOURCE OF TRUTH

Use the repository as the source of truth.

Inspect:

- SQLAlchemy models
- Alembic migrations
- Current database schema
- Existing tests
- Existing application behavior
- Existing authentication/identity logic
- Existing seed data
- Existing database constraints
- Existing migration conventions

Do not assume that:

    ORM model == database schema

The entire purpose of this task is to determine where they differ and why.

---

# 5. ENVIRONMENT SAFETY

There are at least two important database contexts:

### Real development database

Previously identified as:

    pofa_dev

This database contains existing data and MUST NOT be reset.

### Scratch/test database

BE-027 demonstrated that a fresh schema can be built from the migration chain.

Continue using an isolated scratch database for destructive migration experiments.

Never run:

- database reset
- drop database
- destructive migration
- duplicate cleanup
- constraint enforcement

against `pofa_dev` unless explicitly approved.

---

# 6. PHASE 1 — REPOSITORY AUDIT

Before changing anything, inspect:

### Models

Find:

- `User`
- all fields marked unique
- primary keys
- foreign keys
- indexes
- check constraints
- relationship definitions
- nullable/non-nullable fields

### Migrations

Inspect all Alembic revisions.

Confirm:

- revision chain
- current head
- branching
- merge revisions
- historical schema changes
- manually created constraints
- database-only operations
- migration omissions

### Database

Inspect the actual PostgreSQL schema.

Compare:

- tables
- columns
- types
- nullability
- defaults
- primary keys
- foreign keys
- unique constraints
- unique indexes
- check constraints
- regular indexes
- PostGIS objects
- pgvector objects
- extensions

Do not modify anything during this audit phase.

---

# 7. PHASE 2 — INVESTIGATE B-1

## User uniqueness mismatch

The ORM declares uniqueness for:

- `User.username`
- `User.email`

But the migrated database does not currently enforce equivalent uniqueness.

First determine the exact model declarations.

Then inspect the actual database.

Produce a factual comparison:

| Field | ORM says unique | DB enforces unique | Duplicate data exists |
|---|---:|---:|---:|
| username | ? | ? | ? |
| email | ? | ? | ? |

Do not infer the answer.

Measure it.

---

# 8. DUPLICATE DATA AUDIT

Identify duplicate usernames.

Conceptually:

    GROUP BY username
    HAVING COUNT(*) > 1

Identify duplicate emails.

Conceptually:

    GROUP BY email
    HAVING COUNT(*) > 1

For every duplicate group determine:

- duplicate value
- number of records
- user IDs
- account status
- references from other tables
- creation timestamps
- authentication/provider information if available
- whether the records appear to represent the same identity

Do not expose sensitive user data in logs or reports unnecessarily.

The final report should summarize counts and affected IDs where appropriate, without dumping personal information.

---

# 9. NULL / EMPTY VALUE ANALYSIS

Determine whether `username` and `email` contain:

- NULL values
- empty strings
- whitespace-only values
- case variants
- normalized duplicates

For example:

    User@example.com
    user@example.com

may or may not be considered duplicates depending on the application's identity policy.

Do not decide the policy arbitrarily.

Inspect the existing authentication implementation first.

---

# 10. AUTHENTICATION IMPACT

Determine how the application identifies users.

Inspect:

- login flow
- registration
- OAuth/provider identities
- email verification
- username lookup
- password authentication
- session/token creation
- user lookup helpers

Answer:

1. Is email an identity key?
2. Is username an identity key?
3. Are both required to be unique?
4. Is case sensitivity meaningful?
5. Are multiple authentication providers supported?
6. Could two database users legitimately share either field?

This determines whether the ORM declarations reflect an actual business invariant or merely an outdated model assumption.

---

# 11. DO NOT FORCE UNIQUENESS YET

If duplicate data exists:

**Do NOT immediately create:**

    UNIQUE(username)

or:

    UNIQUE(email)

on the live database.

First determine whether the data can safely satisfy the constraint.

If remediation is required, create a documented remediation proposal.

The proposal must include:

- affected records
- reason for duplication
- canonical-record selection rules
- foreign-key reassignment requirements
- authentication/session implications
- rollback strategy
- verification strategy

Then STOP before executing destructive remediation.

---

# 12. PHASE 3 — INVESTIGATE B-2

Run the repository's current:

    alembic check

Capture the complete set of reported operations.

The current baseline is:

    16 unreviewed drift operations

Do not assume all 16 are real problems.

Classify every operation.

---

# 13. DRIFT CLASSIFICATION

Every Alembic drift operation must be placed into one of these categories:

### Category A — Legitimate migration

The ORM/schema change is intentional and should exist in a migration.

Action:

- create migration if appropriate
- test it on scratch DB

---

### Category B — Historical / intentional database difference

The difference exists intentionally and should remain.

Action:

- document why it exists
- prevent the drift check from becoming misleading if possible

---

### Category C — ORM metadata mismatch

The model does not accurately describe the intended database schema.

Action:

- determine correct source of truth
- modify ORM model if appropriate
- test impact

---

### Category D — Database migration omission

The ORM correctly describes the intended schema, but migrations failed to represent it.

Action:

- create a proper Alembic migration
- test upgrade/downgrade behavior where applicable

---

### Category E — Unsafe / unresolved

The operation affects existing data or infrastructure in a way that cannot safely be resolved during BE-028.

Action:

- document
- do not execute
- create follow-up task if required

---

# 14. DRIFT INVENTORY

Create a table similar to:

| # | Alembic operation | Object | Classification | Action | Risk |
|---|---|---|---|---|---|
| 1 | ... | ... | A/B/C/D/E | ... | Low/Med/High |
| 2 | ... | ... | ... | ... | ... |

All 16 operations must be accounted for.

Do not leave an unexplained drift operation.

---

# 15. SCRATCH DATABASE VALIDATION

Use an isolated scratch PostgreSQL database to test migration behavior.

The following must be proven:

    Empty database
        |
        v
    alembic upgrade head
        |
        v
    Expected schema
        |
        v
    Application startup
        |
        v
    Tests

Confirm:

- all migrations apply
- no migration requires manual intervention
- PostGIS works
- pgvector works
- tables are created
- indexes are created
- foreign keys are created
- constraints are created

Do not use `pofa_dev` for this destructive validation.

---

# 16. ALEMBIC HEAD VERIFICATION

Verify:

    alembic heads

There must be one intentional head.

If multiple heads exist:

- determine whether this is intentional
- inspect migration history
- do not blindly merge branches

The expected current baseline from BE-027 is:

    p6q7r8s9t026

If this has changed legitimately during repository development, report the actual value.

---

# 17. ALEMBIC HISTORY VERIFICATION

Verify:

    alembic history

Ensure:

- migration chain is continuous
- no unexplained branch exists
- no missing revision is referenced
- current head is reachable from base

Do not rewrite historical migrations.

Historical migration files are immutable unless there is an extraordinary reason and explicit approval.

---

# 18. MIGRATION DESIGN RULE

If a new migration is necessary:

- create a new revision
- preserve historical migrations
- provide deterministic upgrade behavior
- provide safe downgrade behavior where technically meaningful
- avoid data-destructive operations
- include comments where migration logic is non-obvious

Never modify an already-applied historical migration merely to make `alembic check` happy.

---

# 19. B-3 — DRIFT CONTAINMENT

After understanding the existing drift, establish an automated mechanism that prevents future accidental schema divergence.

The preferred outcome is a CI/test gate that executes the equivalent of:

    alembic check

against a properly prepared database/environment.

The exact implementation should follow the repository's existing CI/test architecture.

Do not add a massive CI framework for one command.

---

# 20. DRIFT CHECK REQUIREMENTS

The future gate should fail when:

- ORM models change without corresponding migration
- schema changes are detected unexpectedly
- migration metadata becomes inconsistent

The gate must NOT falsely fail because of known intentional database objects.

If `alembic check` cannot be made completely clean without unsafe changes, establish a documented baseline and containment strategy.

Do not simply suppress the entire check.

---

# 21. CI INTEGRATION

Inspect existing:

- GitHub Actions
- CI scripts
- Makefile
- PowerShell scripts
- package scripts
- pytest configuration
- deployment checks

Integrate schema drift detection into the most appropriate existing mechanism.

Do not create redundant CI systems.

The intended developer workflow should eventually resemble:

    change model
       |
       v
    generate migration
       |
       v
    review migration
       |
       v
    run tests
       |
       v
    alembic check
       |
       v
    commit

---

# 22. MIGRATION GENERATION POLICY

Do not automatically commit autogenerated migrations without inspection.

If autogeneration is used:

1. Generate candidate migration.
2. Inspect every operation.
3. Remove unintended operations.
4. Verify data safety.
5. Test upgrade.
6. Test downgrade where applicable.
7. Run application tests.
8. Run `alembic check`.

Autogenerated migration output is a proposal, not automatically correct truth.

---

# 23. MODEL-TO-DATABASE CONTRACT

Establish a documented contract:

### Models define

Application-level intended schema.

### Migrations define

Versioned schema transitions.

### Database defines

Currently deployed schema.

All three must eventually agree unless a documented intentional exception exists.

---

# 24. CONSTRAINT ANALYSIS

Audit all important model/database constraints.

Focus especially on:

- Unique constraints
- Primary keys
- Foreign keys
- Check constraints
- NOT NULL
- Indexes

Do not attempt to fix every historical discrepancy blindly.

Prioritize correctness and safety.

---

# 25. USER UNIQUENESS REMEDIATION DESIGN

If B-1 cannot be safely fixed during BE-028, produce a dedicated remediation plan.

The plan must answer:

### Duplicate detection

How are duplicates identified?

### Canonical selection

How is the surviving user determined?

Possible signals:

- active account
- authenticated identity
- oldest account
- verified email
- most referenced user

Do not select a rule without evidence.

### Reference migration

Which tables reference the duplicate user?

How would those foreign keys be reassigned?

### Authentication

What happens to:

- sessions
- refresh tokens
- provider IDs
- passwords
- verification state

### Rollback

How can the migration be reversed?

### Verification

How do we prove no references were lost?

This remediation may become a separate task:

    BE-029 — User Identity Constraint Remediation

if necessary.

---

# 26. CASE SENSITIVITY

Determine whether username/email uniqueness should be:

- case-sensitive
- case-insensitive
- normalized before storage

Do not implement case-insensitive uniqueness simply because it is common elsewhere.

Use the existing PoA authentication/business logic as the basis.

If the answer cannot be established safely:

- document the ambiguity
- do not alter identity semantics in BE-028

---

# 27. DATA BACKUP / ROLLBACK

For any migration that touches existing data:

- define rollback strategy
- test on scratch data
- identify affected tables
- verify row counts before/after
- verify foreign-key integrity
- verify application startup

Do not claim rollback safety without testing it.

---

# 28. DATABASE DIFF VERIFICATION

After implementing legitimate schema changes:

Run a fresh comparison between:

    ORM metadata

and:

    migrated scratch database

The desired result is:

    No unexplained differences

If differences remain, every difference must be documented.

---

# 29. TESTING REQUIREMENTS

At minimum, run:

### Unit tests

    pytest -q tests/unit

Expected baseline from BE-027:

    420 passed
    1 skipped

Any change from that baseline must be explained.

---

### Integration tests

    pytest -q tests/integration

BE-027 baseline:

    275 passed
    1 failed

The known failure is:

    test_be025_admin_control_plane.py:535

This was identified as a pre-existing volume-sensitive assertion.

Do not weaken, skip, delete, or modify this test merely to make BE-028 green.

If it changes, explain why.

---

### Migration tests

Test:

    base -> head

on a scratch database.

If downgrade is supported:

    head -> base

or through the affected revision.

Do not downgrade the real development database.

---

### Drift check

Run:

    alembic check

The result must be reported exactly.

If it is zero:

    PASS

If known intentional differences remain:

    PASS WITH DOCUMENTED BASELINE

If unexplained differences remain:

    FAIL / BLOCKED

Do not fake a pass.

---

# 30. REGRESSION TESTING

Verify:

- backend startup
- health endpoint
- database connectivity
- basic project CRUD
- authentication behavior
- existing audit functionality
- existing migration behavior

Do not introduce unrelated feature work.

---

# 31. AUDIT LEDGER PROTECTION

BE-027 established:

    valid: true
    checked_events: 28582
    failures: []

Re-run the audit-chain validation after any database changes.

The expected requirement is:

    valid: true

If audit integrity changes unexpectedly:

**STOP.**

Do not continue until the cause is understood.

---

# 32. DATA SAFETY CHECKS

For any migration touching existing tables, compare before/after:

- row counts
- primary-key counts
- foreign-key integrity
- null counts
- duplicate counts
- important indexes
- constraints

For user-related remediation, additionally compare:

- user count
- references to affected users
- authentication/provider records
- audit references

---

# 33. PERFORMANCE CONSIDERATIONS

Do not create expensive full-table operations against large live tables without measuring them.

For future uniqueness enforcement, determine whether:

- index creation is safe
- concurrent index creation is needed
- table locks are acceptable
- migration downtime is acceptable

Do not blindly add a unique index to a large table containing duplicates.

---

# 34. DOCUMENTATION

Create/update:

    docs/BE-028 Schema Integrity and Drift Containment Results.md

The document must contain:

## 1. Executive Summary

What was discovered and what was changed.

## 2. B-1 Findings

Detailed user uniqueness findings.

## 3. Duplicate Data Analysis

Counts and affected relationships.

Do not unnecessarily expose personal information.

## 4. B-2 Findings

All 16 drift operations and their classification.

## 5. Schema Changes

Every migration added/modified.

## 6. B-3 Containment

Explain how future drift is detected.

## 7. Testing

Exact commands and results.

## 8. Data Safety

What was tested and what was deliberately not touched.

## 9. Blockers

Anything unresolved.

## 10. Recommended Next Task

Based on the actual result.

---

# 35. REQUIRED FINAL DELIVERABLES

At completion, the repository should contain only the changes actually justified by the investigation.

Potential deliverables:

- New Alembic migration(s), if required
- Schema/model corrections, if safe
- Drift-check automation
- Tests
- Documentation
- User uniqueness remediation plan if unresolved

Do NOT create speculative migrations.

---

# 36. EXPLICITLY OUT OF SCOPE

Do NOT implement:

- Evidence intelligence
- pHash
- EXIF analysis
- ML risk scoring
- OCR
- Geofence algorithms
- Reviewer workflow
- Audit-chain redesign
- Analytics
- Mobile application
- AI agent functionality
- New authentication system
- UI redesign
- Database technology migration
- ORM replacement
- PostgreSQL version upgrade
- PostGIS version upgrade
- pgvector upgrade

Do not combine BE-028 with unrelated backend feature work.

---

# 37. PROHIBITED ACTIONS

Do NOT:

- Drop `pofa_dev`
- Reset `pofa_dev`
- Delete duplicate users
- Merge users automatically
- Modify user foreign keys without a reviewed plan
- Rewrite historical Alembic migrations
- Delete migration revisions
- Use `git reset --hard`
- Use `git clean`
- Delete unrelated working-tree changes
- Revert the 27 documentation deletions left from the previous process
- Run `git add .`
- Run `git add -A`
- Commit unrelated changes
- Push to the remote
- Modify unrelated PoA features

The existing working tree may contain unrelated changes.

Preserve them.

---

# 38. GIT DISCIPLINE

Before making changes:

    git status

Identify existing changes.

Do not stage unrelated changes.

When BE-028 is complete, stage only files belonging to BE-028 by explicit filename.

Do NOT use:

    git add .

or:

    git add -A

The commit should contain only BE-028 work.

Do not push unless explicitly requested.

---

# 39. STOP CONDITIONS

STOP and report if:

### Database safety

- Duplicate remediation requires destructive changes.
- Foreign-key reassignment is ambiguous.
- Authentication identity semantics are unclear.
- A migration could lose data.

### Migration safety

- Historical migrations need modification.
- Multiple migration heads appear unexpectedly.
- Alembic detects a destructive operation that was not intentionally requested.
- Autogenerated migration contains unexpected operations.

### Infrastructure

- Scratch database cannot reproduce the schema.
- PostGIS/pgvector migration behavior is broken.
- CI cannot safely execute the drift check.

### Integrity

- Audit-chain validation fails.
- Existing integration behavior regresses.
- Row counts unexpectedly change.
- Existing database data is modified unexpectedly.

When a stop condition occurs:

**Do not improvise. Report the exact blocker and wait for approval.**

---

# 40. DEFINITION OF DONE

BE-028 is complete only when:

## B-1

- [ ] User uniqueness declarations have been audited.
- [ ] Actual DB constraints have been measured.
- [ ] Duplicate username data has been measured.
- [ ] Duplicate email data has been measured.
- [ ] Authentication semantics have been inspected.
- [ ] NULL/empty/case variants have been analyzed.
- [ ] A safe remediation decision exists.
- [ ] No destructive remediation was performed without approval.

## B-2

- [ ] `alembic check` output has been captured.
- [ ] All 16 baseline drift operations have been classified.
- [ ] Every operation has a documented disposition.
- [ ] Legitimate migration changes have been implemented where safe.
- [ ] Unsafe changes have been documented rather than forced.

## B-3

- [ ] Future schema drift has an automated detection mechanism.
- [ ] The mechanism is integrated with the existing project workflow.
- [ ] It does not silently suppress legitimate drift.

## Database

- [ ] Scratch DB can migrate from base to head.
- [ ] PostgreSQL works.
- [ ] PostGIS works.
- [ ] pgvector works.
- [ ] No historical migration was rewritten.
- [ ] Real development data remains intact.

## Regression

- [ ] Unit tests run.
- [ ] Integration tests run.
- [ ] Known BE-027 integration failure remains understood.
- [ ] Health endpoint works.
- [ ] Project CRUD works.
- [ ] Audit ledger remains valid.

## Documentation

- [ ] BE-028 results document exists.
- [ ] B-1 is documented.
- [ ] B-2 is documented.
- [ ] B-3 is documented.
- [ ] Migration changes are documented.
- [ ] Remaining blockers are documented.

---

# 41. ACCEPTANCE TEST

The following sequence must be reproducible:

    1. Create a completely isolated scratch PostgreSQL database.

    2. Run the complete Alembic migration chain.

    3. Confirm migration reaches the current head.

    4. Confirm PostgreSQL/PostGIS/pgvector functionality.

    5. Run schema inspection.

    6. Run `alembic check`.

    7. Confirm every reported operation is classified.

    8. Run backend tests.

    9. Verify health endpoint.

    10. Verify Project CRUD.

    11. Verify authentication-related behavior where affected.

    12. Verify audit-chain integrity.

    13. Confirm `pofa_dev` was not modified by destructive testing.

    14. Confirm no unrelated working-tree changes were staged.

    15. Produce the BE-028 results document.

---

# 42. FINAL REPORT FORMAT

When finished, report:

## BE-028 Schema Integrity & Drift Containment Report

### 1. B-1 — User Uniqueness

- ORM state:
- Database state:
- Duplicate username count:
- Duplicate email count:
- Authentication implications:
- Remediation status:
- Is a destructive migration required?

### 2. B-2 — Migration Drift

- Initial `alembic check` result:
- Number of operations:
- Classification of each operation:
- Changes implemented:
- Changes deferred:

### 3. B-3 — Drift Containment

- Automated check added:
- Where it runs:
- Failure behavior:
- Manual developer workflow:

### 4. Database

- Scratch database migration:
- PostgreSQL:
- PostGIS:
- pgvector:
- Migration head:

### 5. Tests

Report exact commands and exact results.

Do not round or invent numbers.

### 6. Data Safety

Explicitly state:

- Whether `pofa_dev` was modified.
- Whether any user data was modified.
- Whether any destructive migration was executed.
- Whether audit data changed.

### 7. Files Changed

List every file changed.

### 8. Blockers

List unresolved issues.

### 9. Technical Debt

List remaining schema/migration concerns.

### 10. Recommended Next Task

Recommend the next task based on evidence from the implementation.

**Do not implement the next task automatically.**

---

# 43. FINAL INSTRUCTION

BE-028 is a **schema integrity and migration safety task**, not a cleanup task.

The desired outcome is not:

    "make Alembic green at any cost"

The desired outcome is:

    "know exactly why the ORM, migrations, and database differ,
     safely correct what can be corrected,
     explicitly document what cannot,
     and prevent the problem from silently growing."

Prioritize:

    data safety
        >
    schema correctness
        >
    migration reproducibility
        >
    drift detection
        >
    testability
        >
    convenience

Inspect first.

Measure before modifying.

Never destroy data to make a test pass.

Never rewrite migration history to hide drift.

Never silently suppress schema differences.

If a safe fix cannot be proven, stop and report it.

Do not proceed to the next BE task until BE-028 is genuinely complete.