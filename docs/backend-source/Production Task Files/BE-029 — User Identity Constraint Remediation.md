# BE-029 — User Identity Constraint Remediation

**Project:** Proof-Of-Action (PoA)  
**Task ID:** BE-029  
**Category:** Backend / Database / Identity / Data Integrity  
**Priority:** High  
**Status:** Not Started  
**Depends On:** BE-028  
**Blocks:** Production Identity Integrity / Authentication Hardening

---

# 1. TASK OBJECTIVE

Resolve the unresolved user-identity constraint issue discovered during BE-027 and BE-028.

The current PoA backend has a mismatch between the ORM declarations and the actual identity model:

- `User.username` is declared unique at the ORM level.
- `User.email` is declared unique at the ORM level.
- The actual PostgreSQL schema does NOT enforce uniqueness on either field.
- Existing databases contain duplicate username/email values.
- The actual enforced identity key is:

    UNIQUE(identity_provider, external_subject)

BE-028 established that username/email are not currently used by the application as the authoritative authentication identity key.

Therefore, BE-029 must NOT blindly add:

    UNIQUE(username)

or:

    UNIQUE(email)

to the existing database.

The primary objective is to determine the correct product identity policy and then make the ORM, database schema, validation behavior, tests, and documentation agree with that policy.

---

# 2. CRITICAL CONTEXT FROM BE-028

BE-028 established the following facts.

## 2.1 Database uniqueness

The database currently has:

- no unique constraint on `users.username`
- no unique constraint on `users.email`

The existing indexes on those fields are non-unique.

---

## 2.2 Existing duplicate data

BE-028 measured:

- `pofa_test`: one duplicate group containing 19 rows
- `pofa_dev`: one duplicate group containing 40 rows

These are real existing records.

They must NOT be deleted, merged, or modified automatically.

---

## 2.3 Actual identity key

The existing enforced identity key is:

    UNIQUE(identity_provider, external_subject)

The existing identity implementation was introduced through BE-016.

`external_subject` was backfilled from the user ID during that migration.

---

## 2.4 Application lookup behavior

BE-028 inspected the authentication/application logic and found no evidence that users are looked up by username or email as the authoritative identity key.

`create_user` already normalizes:

    strip()
    strip().lower()

BE-028 also found that case-folding and `+tag` variants did not create additional duplicate groups.

---

## 2.5 Important unresolved condition

`pofa_test` contains duplicate users whose:

    external_subject = NULL

Therefore the existing identity constraint does not currently resolve those duplicate records.

This MUST be investigated before choosing a remediation strategy.

---

# 3. PRIMARY SAFETY RULE

## NEVER DELETE OR MERGE USERS AUTOMATICALLY.

This task involves identity data.

A mistake here could:

- break authentication
- orphan foreign-key relationships
- alter audit history
- change ownership of projects/evidence
- invalidate sessions
- break external-provider mappings
- corrupt historical records

Therefore:

**Data preservation takes priority over making a database constraint pass.**

If the correct remediation cannot be proven safe:

    STOP

and report the blocker.

Do not improvise.

---

# 4. REQUIRED PRODUCT DECISION

Before changing the database schema, establish which of the following policies is actually intended.

## OPTION A — Username/email are identity attributes

Under this policy:

- username must be unique
- email must be unique
- duplicate values must be remediated
- database-level uniqueness must eventually be enforced

This requires a controlled data migration.

---

## OPTION B — Username/email are display/profile attributes

Under this policy:

- username is not an authentication identity key
- email is not an authentication identity key
- multiple users may technically share those values if the product permits it
- the ORM must not incorrectly claim database uniqueness
- the real identity remains:

    (identity_provider, external_subject)

Under this policy, remove the incorrect uniqueness declarations from the ORM if that accurately reflects the intended product behavior.

---

# 5. DO NOT GUESS THE PRODUCT POLICY

The coding agent must NOT decide Option A or Option B based solely on personal preference.

Inspect:

- authentication implementation
- frontend registration/login flows
- user profile behavior
- identity-provider integration
- existing API schemas
- user creation logic
- authorization logic
- existing documentation
- previous identity-related migrations

If the repository clearly establishes the policy, use that evidence.

If the repository does NOT establish the policy:

    STOP

and report:

    "Product-owner identity decision required."

Do not make a schema change simply to remove the blocker.

---

# 6. PHASE 1 — COMPLETE IDENTITY AUDIT

Before changing anything, inspect all code paths involving:

- `User.username`
- `User.email`
- `identity_provider`
- `external_subject`

Search for:

- equality comparisons
- lookup queries
- filters
- unique checks
- registration
- login
- OAuth callbacks
- session creation
- token generation
- password authentication
- user creation
- user updates
- admin user management
- API serializers
- frontend API calls

Create a map of every identity-related usage.

---

# 7. IDENTITY LOOKUP CLASSIFICATION

For every user lookup found, classify it as:

### Authoritative identity lookup

Used to determine which actual account belongs to a person/provider identity.

Example:

    identity_provider + external_subject

### Profile lookup

Used only to display/search information.

Example:

    username
    email

### Administrative lookup

Used by admins/support tools.

### Non-identity filtering

Used for reporting/searching.

Document the classification.

---

# 8. AUTHENTICATION IDENTITY

Confirm exactly how the application establishes identity.

Answer:

1. What field identifies the external provider?
2. What field identifies the provider's subject?
3. Is `(identity_provider, external_subject)` globally unique?
4. Can a user have multiple providers?
5. Can one provider identity map to multiple users?
6. Can one user have multiple provider identities?
7. What happens when `external_subject` is NULL?
8. Are NULL external subjects valid?
9. Are NULL external subjects temporary or permanent?
10. Can locally created users exist without an external identity?

Do not change identity semantics during this task unless required and explicitly justified.

---

# 9. NULL EXTERNAL SUBJECT INVESTIGATION

This is mandatory.

Find all users where:

    external_subject IS NULL

Determine:

- total count
- duplicate username groups
- duplicate email groups
- identity provider values
- creation source
- whether those users can authenticate
- whether they are test fixtures
- whether they are seeded records
- whether they represent legacy accounts

Determine why `external_subject` is NULL.

Do not simply populate it with arbitrary values.

---

# 10. DUPLICATE GROUP CHARACTERIZATION

For every duplicate username/email group, identify:

- user IDs
- username
- email
- identity provider
- external subject
- created_at
- updated_at
- account status
- authentication status
- number of referencing rows

Do NOT dump unnecessary personal information into logs.

Use counts and IDs where sufficient.

---

# 11. FOREIGN-KEY IMPACT ANALYSIS

Before considering any merge/remediation, identify every table referencing `users.id`.

Build a dependency map.

For each foreign key determine:

- table
- column
- number of affected rows
- whether reassignment is possible
- whether the relationship is historical
- whether deletion would cascade
- whether the record must remain tied to the original user

Pay particular attention to:

- projects
- evidence
- reviews
- audit events
- submissions
- authentication records
- ownership records

---

# 12. AUDIT LEDGER REQUIREMENT

User identity remediation MUST preserve audit history.

Do not rewrite historical audit records merely to make user references point to a canonical account unless that is explicitly required and safely designed.

The following must remain valid:

    Audit ledger integrity

After any proposed migration:

- validate audit chain
- compare event counts
- verify no historical event disappears
- verify no unexpected actor references are changed

If audit integrity changes unexpectedly:

    STOP.

---

# 13. OPTION A — UNIQUE IDENTITY ATTRIBUTES

If the product decision is:

    username/email MUST be unique

then follow this section.

---

# 14. OPTION A — DUPLICATE REMEDIATION DESIGN

Before modifying data, create a deterministic remediation plan.

For each duplicate group define:

### Canonical account selection

A canonical user must be selected using explicit evidence.

Potential signals may include:

1. Valid authenticated external identity
2. Verified account
3. Active account
4. Existing provider identity
5. Number of legitimate references
6. Creation timestamp

Do NOT invent priority rules without documenting them.

If two accounts are equally legitimate:

    STOP

and escalate the conflict.

---

# 15. OPTION A — FOREIGN-KEY REASSIGNMENT

If duplicate accounts must be merged:

1. Identify every referencing row.
2. Determine whether each relationship may safely move.
3. Reassign only relationships proven to belong to the canonical account.
4. Preserve historical audit semantics.
5. Verify all foreign keys afterward.

Do NOT use:

    ON DELETE CASCADE

as a shortcut.

Do NOT delete the duplicate user until all dependencies have been understood and migrated.

---

# 16. OPTION A — AUTHENTICATION RECONCILIATION

If duplicate users have different external identities:

DO NOT merge them automatically.

Determine whether:

- both identities belong to the same real user
- they are separate legitimate accounts
- provider identities can be transferred
- provider identity uniqueness would be violated

If ownership cannot be established:

    STOP.

---

# 17. OPTION A — EMAIL NORMALIZATION

Determine the product's canonical email policy.

Possible policy:

    strip whitespace
    lowercase
    store canonical form

Do not automatically apply provider-specific transformations such as:

    remove dots
    remove +tags

unless the application explicitly defines that behavior.

BE-028 established that +tag/case variants did not create additional duplicate groups, but that does NOT automatically establish the future normalization policy.

---

# 18. OPTION A — USERNAME NORMALIZATION

Determine:

- case sensitivity
- whitespace behavior
- allowed characters
- whether username comparisons are normalized

Do not silently change existing usernames.

If normalization is required, create a migration plan and test collisions first.

---

# 19. OPTION A — PRECONSTRAINT VALIDATION

Before creating a unique constraint:

Run duplicate detection against the target normalized values.

The result must be:

    zero duplicate groups

If not:

    DO NOT create the constraint.

---

# 20. OPTION A — UNIQUE CONSTRAINT IMPLEMENTATION

Only after duplicate remediation is complete:

Add database-level uniqueness.

The exact implementation should follow PostgreSQL/Alembic best practices.

For large production tables, consider whether:

    CREATE UNIQUE INDEX CONCURRENTLY

is appropriate.

Do not assume it is required.

Measure the table size and deployment requirements first.

---

# 21. OPTION A — ORM ALIGNMENT

After database uniqueness is established:

Ensure:

- SQLAlchemy model
- Alembic migration
- PostgreSQL schema
- API validation

all agree.

No layer should falsely claim a uniqueness guarantee that another layer does not enforce.

---

# 22. OPTION B — PROFILE ATTRIBUTES

If the product decision is:

    username/email are NOT identity keys

then the ORM currently overstates the database contract.

In that case:

- remove incorrect `unique=True` declarations
- preserve non-unique indexes if useful
- preserve current user data
- preserve actual identity constraint
- add tests proving `(identity_provider, external_subject)` remains authoritative

Do NOT add database uniqueness.

---

# 23. OPTION B — DOCUMENT THE IDENTITY MODEL

Document clearly:

    User identity:
    (identity_provider, external_subject)

    Username:
    profile/display/search attribute

    Email:
    profile/contact/search attribute

The exact terminology must reflect the actual product decision.

---

# 24. OPTION B — API VALIDATION

If username/email are non-unique:

Do not perform validation that incorrectly rejects duplicate values.

For example:

    username already exists

must not be treated as an error unless the product explicitly requires uniqueness.

Validation must match the actual database/product contract.

---

# 25. IDENTITY CONSTRAINT TESTS

Regardless of Option A or B, add tests proving the actual identity contract.

At minimum:

### Same provider + same external subject

Must NOT create two users.

Expected:

    uniqueness violation / existing identity resolution

---

### Different provider + different external subject

Must be allowed if the product supports multiple providers.

---

### Same username

Behavior must match the chosen policy.

---

### Same email

Behavior must match the chosen policy.

---

### NULL external subject

Behavior must be explicitly defined.

Do not leave it accidental.

---

# 26. MIGRATION TESTING

Any migration must be tested on a scratch database.

Required sequence:

    base
      |
      v
    alembic upgrade head
      |
      v
    apply BE-029 migration
      |
      v
    run identity tests
      |
      v
    verify schema
      |
      v
    verify data integrity

If a downgrade exists:

    downgrade
      |
      v
    verify
      |
      v
    upgrade again

Do NOT perform destructive migration testing against `pofa_dev`.

---

# 27. LIVE DEVELOPMENT DATABASE

`pofa_dev` is protected.

Before any operation:

Verify the target database.

Never rely solely on:

    DATABASE_URL

if there is any possibility it points somewhere unexpected.

Before migration, record:

- database name
- schema
- migration revision
- user count
- relevant duplicate counts

After migration, compare.

---

# 28. P0 DATA-SAFETY CHECKS

Before and after any data migration compare:

- user count
- project count
- evidence count
- review count
- audit event count
- foreign-key counts
- duplicate groups
- NULL external subjects
- identity constraint count

Unexpected changes require investigation.

---

# 29. ROLLBACK REQUIREMENT

Any data migration must have a tested rollback strategy.

Do not claim rollback merely because an Alembic `downgrade()` exists.

Actually test the migration on a clone/scratch dataset.

Verify:

- row counts
- references
- identity mappings
- constraints
- audit integrity

---

# 30. TESTING REQUIREMENTS

Run at minimum:

    pytest -q tests/unit

    pytest -q tests/integration

    pytest -q -m "not integration" tests

    alembic check

Also run the identity-specific tests introduced by BE-029.

The BE-028 baseline currently includes:

    Unit:
    420 passed, 1 skipped

    Integration:
    281 passed, 1 failed

The known integration failure is:

    test_be025_admin_control_plane.py:535

This failure must NOT be weakened, skipped, deleted, or modified simply to make BE-029 pass.

If the baseline changes, explain why.

---

# 31. SCHEMA DRIFT GATE

BE-028 established a schema-drift containment gate.

BE-029 must not bypass it.

After identity/schema changes:

Run the drift gate.

Ensure the resulting schema state is intentional.

If `alembic check` changes:

- explain every change
- update the documented baseline only if justified
- never blindly update the baseline to hide an unintended migration

---

# 32. AUDIT LEDGER VALIDATION

Re-run the audit-chain validation after all identity work.

Expected:

    valid = true

Compare event counts before and after.

Any unexpected audit mutation is a blocker.

---

# 33. SECURITY REQUIREMENTS

Identity data is security-sensitive.

Do NOT log:

- passwords
- access tokens
- refresh tokens
- OAuth secrets
- full authentication headers
- sensitive provider credentials

Do not include unnecessary email addresses/usernames in committed diagnostic output.

---

# 34. PERFORMANCE REQUIREMENTS

Do not run uncontrolled full-table updates against large databases.

Before a data migration:

- estimate affected rows
- estimate query cost
- inspect indexes
- determine lock behavior
- determine transaction size

If batching is required, design it explicitly.

---

# 35. DOCUMENTATION

Create:

    docs/BE-029 User Identity Constraint Remediation Results.md

The document must include:

## 1. Product Decision

State:

    Option A — username/email are identity attributes

or:

    Option B — username/email are profile attributes

Include the evidence supporting the decision.

---

## 2. Existing Identity Model

Document:

    identity_provider
    external_subject

and explain how they identify users.

---

## 3. Duplicate Analysis

Include:

- duplicate group counts
- affected record counts
- NULL external subject findings
- relevant foreign-key impact

Do not expose unnecessary personal data.

---

## 4. Remediation

Describe exactly what was changed.

If no data was changed, say so.

---

## 5. Database Changes

Document:

- constraints
- indexes
- migrations

---

## 6. Application Changes

Document:

- model changes
- validation changes
- authentication changes
- API changes

---

## 7. Tests

List exact commands and exact results.

---

## 8. Data Safety

Explicitly state:

- whether `pofa_dev` was modified
- whether users were deleted
- whether users were merged
- whether foreign keys were reassigned
- whether audit records changed

---

## 9. Rollback

Document tested rollback behavior.

---

## 10. Remaining Risks

List unresolved issues.

---

## 11. Next Task

Recommend the next backend task based on actual results.

Do NOT implement it automatically.

---

# 36. FILES THAT MAY CHANGE

Depending on the selected policy:

Potential files include:

    backend/db/models.py

    backend/core/...

    backend/auth/...

    backend/api/...

    alembic/versions/<new_revision>.py

    tests/unit/...

    tests/integration/...

    docs/BE-029 User Identity Constraint Remediation Results.md

    docs/Production Task Files/BE-029 — User Identity Constraint Remediation.md

Only modify files that are actually required.

---

# 37. FILES THAT MUST NOT BE MODIFIED UNNECESSARILY

Do not modify:

- frontend UI
- evidence intelligence
- ML pipeline
- geofence implementation
- reviewer dashboard
- analytics
- mobile code
- unrelated database models
- unrelated migrations
- audit-chain implementation
- Docker configuration
- WSL configuration

Do not combine BE-029 with unrelated backend tasks.

---

# 38. GIT DISCIPLINE

Before making changes:

    git status

There may be unrelated working-tree changes from previous processes.

Preserve them.

Do NOT:

    git add .

    git add -A

    git clean

    git reset --hard

Stage only BE-029 files explicitly.

Do not revert unrelated documentation changes.

Do not push unless explicitly requested.

---

# 39. STOP CONDITIONS

Immediately stop if:

### Product ambiguity

- It is impossible to determine whether username/email should be unique.
- Authentication semantics are ambiguous.
- Multiple legitimate identities cannot be distinguished.

### Data ambiguity

- Duplicate users cannot be deterministically classified.
- Two external identities appear to represent the same account but ownership cannot be proven.
- Foreign-key ownership cannot be established.

### Migration risk

- Unique constraint creation would fail.
- Data migration would require deleting users.
- Data migration would require modifying audit history.
- Migration would cause unexpected cascades.
- Rollback cannot be demonstrated.

### Integrity

- Audit ledger becomes invalid.
- Row counts change unexpectedly.
- Identity references become orphaned.
- Schema drift becomes unexplained.

When any stop condition occurs:

    STOP

Do not make the system "green" through destructive shortcuts.

Report the exact blocker.

---

# 40. DEFINITION OF DONE

BE-029 is complete only when:

## Product

- [ ] Identity policy has been explicitly established.
- [ ] Evidence supporting the policy is documented.

## Identity

- [ ] Actual authentication identity is documented.
- [ ] `identity_provider + external_subject` behavior is tested.
- [ ] NULL external-subject behavior is understood.
- [ ] Username/email semantics are explicitly defined.

## Data

- [ ] Duplicate groups have been measured.
- [ ] Foreign-key dependencies have been measured.
- [ ] No user was deleted without explicit approval.
- [ ] No ambiguous account was merged.
- [ ] No audit history was corrupted.

## Database

If Option A:

- [ ] Duplicate data has been safely remediated.
- [ ] Database uniqueness is enforced.
- [ ] ORM and database agree.

If Option B:

- [ ] ORM uniqueness declarations no longer incorrectly claim uniqueness.
- [ ] Database remains non-unique for username/email.
- [ ] Actual identity constraint remains enforced.

## Tests

- [ ] Identity tests pass.
- [ ] Unit tests pass or baseline difference is explained.
- [ ] Integration tests pass or baseline difference is explained.
- [ ] Migration tests pass.
- [ ] Drift gate passes.
- [ ] Audit ledger remains valid.

## Documentation

- [ ] BE-029 results document exists.
- [ ] Identity decision documented.
- [ ] Data remediation documented.
- [ ] Schema changes documented.
- [ ] Tests documented.
- [ ] Remaining risks documented.

---

# 41. ACCEPTANCE TEST

The final system must demonstrate the following.

### Identity

    Provider A + Subject X
        |
        v
    User A

Attempt:

    Provider A + Subject X
        |
        v
    MUST NOT create another User

---

### Different identity

    Provider A + Subject X

    Provider B + Subject Y

Behavior must match the documented product policy.

---

### Username

Test duplicate username behavior.

The result must exactly match the selected Option A/B policy.

---

### Email

Test duplicate email behavior.

The result must exactly match the selected Option A/B policy.

---

### Existing data

Verify that:

- existing users remain intact
- projects remain intact
- evidence remains intact
- reviews remain intact
- audit events remain intact

---

### Database

Verify:

    alembic upgrade head

    alembic check

    schema drift gate

---

### Audit

Verify:

    audit_chain.valid == true

---

# 42. FINAL REPORT FORMAT

When finished, provide:

## BE-029 User Identity Constraint Remediation Report

### 1. Product Decision

State Option A or Option B.

### 2. Identity Model

Explain the authoritative identity key.

### 3. Initial Data State

Report measured duplicate/null counts.

### 4. Changes Made

List every meaningful change.

### 5. Database

List:

- migrations
- constraints
- indexes
- schema changes

### 6. Application

List:

- model changes
- validation changes
- authentication changes
- API changes

### 7. Data Migration

If performed:

- rows affected
- canonical-selection method
- foreign keys reassigned
- rollback verification

If not performed:

- explicitly state why.

### 8. Tests

Report exact commands and exact results.

Do not invent PASS results.

### 9. Audit Integrity

Report:

- event count before
- event count after
- validation result

### 10. Schema Drift

Report:

- `alembic check`
- drift gate
- remaining documented baseline

### 11. Files Changed

List every changed file.

### 12. Blockers

List unresolved issues.

### 13. Technical Debt

List deferred work.

### 14. Recommended Next Task

Recommend the next task based on actual implementation results.

Do not implement the next task automatically.

---

# 43. FINAL INSTRUCTION

BE-029 is an **identity-data integrity task**.

It is NOT permission to clean up users aggressively.

The correct priority is:

    Correct identity model
        >
    Data preservation
        >
    Authentication integrity
        >
    Database constraints
        >
    Migration cleanliness
        >
    Convenience

The authoritative identity must be based on evidence from the existing PoA system.

Do not assume username/email are identity keys.

Do not assume they are merely display attributes either.

Determine the product policy first.

If the policy is ambiguous:

    STOP.

If duplicate records cannot be safely reconciled:

    STOP.

If a migration could corrupt authentication, foreign keys, or audit history:

    STOP.

Never delete or merge users merely to make a uniqueness constraint pass.

Never rewrite historical migrations.

Never bypass the BE-028 schema-drift gate.

Never modify unrelated PoA functionality.

Inspect.

Measure.

Decide.

Test.

Only then migrate.

After BE-029 is genuinely complete, STOP and provide the final report.

Do not automatically begin BE-030.