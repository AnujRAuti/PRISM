# BE-029 — User Identity Constraint Remediation: PLAN

Task file: `docs/Production Task Files/BE-029 — User Identity Constraint Remediation.md`

Status: **PLAN ONLY — nothing has been executed.** The only work performed so far is
read-only measurement (`SELECT` under `set_session(readonly=True)`) against
`pofa_test` and `pofa_dev`, plus code reading. No model was edited, no migration was
written, no row was inserted, updated, deleted or merged, and the BE-028 drift gate
was not touched.

> **Dated pointer (2026-10-10) — the paragraph above describes the moment this plan was written and
> is now superseded.** Everything the plan gated has since been executed, on **Option A**, against
> `pofa_test`, disposable clones, and — after separate owner approval — live `pofa_dev`. The executed
> record is `docs/BE-029 User Identity Constraint Remediation Results.md` (§1–§13 the original
> execution, §14 the closure pass: Phases A–I, the two BE-030 feasibility measurements, and §14.12's
> blocked list). Specifically:
>
> * The four **Category E** baseline entries named below were resolved by BE-029's own migrations
>   (`r8s9t0u1v028` archive + retirement, `s9t0u1v2w029` unique identity indexes); the drift baseline
>   now carries only the Alembic dialect-options pair (results §14.7), not `users.username` /
>   `users.email`.
> * **OQ-5 was answered and shipped** — a duplicate username/email now returns 409 with a field-level
>   message, keyed on the violated database object (results §13.1).
> * **OQ-3 (`external_subject`) remains open.** No value was backfilled and no rule was invented
>   (results §14.3); it is still the product-owner decision this plan said it was.
> * **BE-030 now has a task file** (`BE-030 — Audit Ledger Append-Only Enforcement & Chain
>   Integrity.md`), written from measurements rather than from this plan's assumptions, and it is
>   **blocked on its own D-1/D-2 decisions** — §43's instruction to stop rather than roll into the
>   next task still stands.

Priorities are the task file's §43 order, **not** BE-028's order — they differ, and
the difference matters here:

```
Correct identity model > Data preservation > Authentication integrity
    > Database constraints > Migration cleanliness > Convenience
```

Prerequisite state: BE-028 is committed (`0763afe3 BE-028 Complete`) and its
containment gate is live, with `users.username` / `users.email` sitting in the
documented baseline as four **Category E** entries
(`tests/schema_drift_baseline.py:72-97`). BE-029 must resolve those four entries —
by satisfying them (Option A) or by deleting the false declaration that produces
them (Option B). Leaving them is not an available outcome (§31: "never blindly
update the baseline to hide an unintended migration" — and equally, never leave a
blocker open once it can be closed honestly).

---

# 1. Section coverage map

| Task-file § | Where this plan addresses it | Executed? |
| --- | --- | --- |
| §6 §7 identity audit + lookup classification | §2, §3 below | **Read-only evidence gathered** |
| §8 authentication identity (10 questions) | §4 below | **Answered from evidence** |
| §9 NULL `external_subject` investigation | §5 below | **Measured** |
| §10 duplicate group characterization | §6 below | **Measured** |
| §11 foreign-key impact analysis | §7 below | **Measured, full FK surface** |
| §12 §32 audit ledger requirement | §8 below | **Measured (0 involvement)** |
| §4 §5 product decision | §9 — **STOP: decision required** | Not decided |
| §13–§21 Option A | §10 | Planned, blocked on §9 gate |
| §22–§24 Option B | §11 | Planned |
| §25 identity tests (either option) | §12 | Planned, can start immediately |
| §26–§29 scratch testing / dev-DB protocol / P0 checks / rollback | §13 | Planned |
| §30–§34 baselines, drift gate, security, performance | §14 | Planned |
| §35–§40 docs, file boundaries, git discipline, DoD | §15–§18 | Planned |
| §41 §42 acceptance + final report | §19 | Planned |

---

# 2. Phase 1 — complete identity audit (§6): every identity-related usage

Exhaustive, from `grep` over `backend/` for `username`, `email`, `identity_provider`,
`external_subject` plus reading every hit. Nothing else in the backend touches them.

| Location | Code | Kind |
| --- | --- | --- |
| `db/models.py:44` | `username = Column(String(128), unique=True, index=True, nullable=False)` | **Declaration only** — and the declaration is false (§10 of BE-028; confirmed again here) |
| `db/models.py:45` | `email = Column(String(256), unique=True, index=True, nullable=False)` | Declaration only, likewise false |
| `db/models.py:50` | `external_subject = Column(String(512), nullable=True)` | Nullable identity material |
| `db/models.py:51` | `identity_provider = Column(String(128), nullable=False, default="local", server_default="local")` | Provider discriminator |
| `db/models.py:60-61` | `UniqueConstraint("identity_provider", "external_subject", name="uq_user_identity_subject")` | **The only real identity constraint** |
| `db/models.py:203` (`Project.owner`) | `ForeignKey("users.id")` + `relationship("User")` | Identity used as an ownership subject, **by `id`** |
| `repositories/authorization.py:46-47` | `get_user(db, user_id)` → `filter(User.id == user_id)` | **Authoritative lookup — by `id` only** |
| `repositories/authorization.py:50-62` | `insert_user(...)` writes username, email, `display_name or username`, external_subject, identity_provider, `status="ACTIVE"` | Write path. **No duplicate check of any kind.** |
| `services/authorization.py:194-204` | `resolve_user_principal(db, user_id)` → `get_user(db, user_id)`; `display_name or username` used **only** as the display label | **Authoritative principal resolution — by `id`** |
| `services/authorization.py:297-318` | `create_user`: `username, email = username.strip(), email.strip().lower()`; `external_subject=external_subject or str(uuid4())` | Normalisation at the service boundary; never queries by either value |
| `api/v1/endpoints/auth.py:151-171` | `POST /auth/users` → `auth_service.create_user(...)` | Creates users; **no uniqueness pre-check, no IntegrityError mapping** |
| `api/v1/endpoints/auth.py:194-226` | `GET /auth/users` (`list_users`) — `db.query(User).order_by(User.created_at, User.id)`, `limit`/`offset` only | **No search by username or email** |
| `api/v1/endpoints/auth.py:229-252` | `PATCH /auth/users/{user_id}/status` | Only mutable user field exposed. **username/email are write-once.** |
| `schemas/authorization.py:60-65` | `UserCreate`: `username: str = Field(min_length=1, max_length=128)`, `email: str = Field(min_length=3, max_length=256)` | **`email` is a plain string, not `EmailStr`** — no format validation anywhere |
| `schemas/authorization.py:68-77` | `UserResponse` serialises `username`, `email`, `identity_provider` | Email is returned by the API but never consumed as identity |
| `security/authentication.py:38-70` | `resolve_principal`: bearer token is `dev-user-<user-uuid>` → `resolve_user_principal(db, subject)` where **subject is the user's own id** | The only user-facing credential path. **Never mentions username/email.** |

Explicit negative results (searched, none found): `.username ==`, `.email ==`,
`filter_by(username…)`, `filter_by(email…)`, `login`, `register`, `oauth`,
`callback`, `password` verification, `sessions` table, `refresh_token` table, and any
provider-linking join table. `password` / `refresh_token` appear in `backend/` **only**
inside redaction keyword lists (`observability/redaction.py:11,16`,
`services/audit_ledger.py:53,58`, `db/models.py:2717` publication-prohibited fields).

---

# 3. §7 — identity lookup classification

| Lookup | Classification | Evidence |
| --- | --- | --- |
| `User.id` (`get_user`, `resolve_user_principal`, every FK) | **Authoritative identity lookup** | All access to "who this account is" flows through `id` |
| `identity_provider` + `external_subject` | **Authoritative *external* identity key, declared but currently inert** | `uq_user_identity_subject` exists; nothing *queries* by it yet — it only constrains |
| `username` | **Profile / display attribute** | Used in exactly one expression: `display_name or username` (`services/authorization.py:203`, `repositories/authorization.py:57`) |
| `email` | **Contact / profile attribute** | Written at creation; serialised in `UserResponse`; never read for a decision |
| `status` / `is_active` | **Non-identity filtering** (account state) | `resolve_user_principal` branches on them, not on username/email |
| Admin tools (`list_users`) | **Administrative lookup** by `created_at, id` pagination | No search parameters exist |

**The classification is one-sided.** There is no *authoritative* username/email
lookup to preserve, and no code that would break if uniqueness were dropped. What
would break if uniqueness were *added* is also measured: nothing in the application,
but the existing 19 + 40 rows would block the constraint (BE-028 proved the index
creation fails).

---

# 4. §8 — the ten authentication-identity questions, answered

1. **What field identifies the external provider?** `identity_provider` —
   `String(128) NOT NULL`, `default`/`server_default = "local"`. Measured distinct
   values in live data: **`local` only**, in both databases.
2. **What field identifies the provider's subject?** `external_subject` —
   `String(512)` **nullable**.
3. **Is `(identity_provider, external_subject)` globally unique?** A constraint
   exists: `uq_user_identity_subject :: UNIQUE (identity_provider, external_subject)`
   (verified via `pg_get_constraintdef` in both DBs). But `external_subject` is
   **not globally unique by design** — the model comment at `models.py:49-50` says
   so explicitly, and the constraint is a *composite*. Crucially it is a plain
   PostgreSQL `UNIQUE`, whose default is **NULLS DISTINCT**, so it does not constrain
   any row with `external_subject IS NULL` (see §5).
4. **Can a user have multiple providers?** **No.** The pair is stored inline on the
   user row; there is no user↔provider join table. One row = exactly one provider
   subject. A person with two provider identities must occupy two `users` rows.
5. **Can one provider identity map to multiple users?** **No** — for non-NULL
   subjects the unique constraint forbids it. **Yes for NULL subjects**, which is
   unconstrained by definition, but NULL is not "a provider identity".
6. **Can one user have multiple provider identities?** **No** (same schema reason
   as 4). This is a real design limitation to document, not to fix in BE-029
   (§8: "Do not change identity semantics during this task unless required and
   explicitly justified").
7. **What happens when `external_subject` is NULL?** The identity constraint is
   skipped for that row. The user is still fully reachable and functional by `id`
   (`resolve_user_principal` → `get_user`), can own projects and hold role
   assignments, and can authenticate through the id-bearing token path. Nothing
   marks the row as provisional.
8. **Are NULL external subjects valid?** Schema-wise yes (nullable, no CHECK).
   Practically they are the **overwhelming majority**: 2,098/2,098 in `pofa_test`,
   1,009/1,094 in `pofa_dev`.
9. **Temporary or permanent?** **Permanent.** The only code that ever writes
   `external_subject` is `insert_user` at creation (`services/authorization.py:312`,
   which *defaults it to a fresh uuid4* — i.e. it never produces NULL) and the one-off
   BE-016 migration backfill (`alembic/versions/i9d0e1f2g016_be016_auth_authorization.py:44-45`).
   Nothing updates it afterwards (grep for `external_subject =` finds no UPDATE path
   outside that migration). A NULL subject is therefore a *permanent* state produced
   only by bypassing the service layer.
10. **Can locally created users exist without an external identity?** **Yes**, and
    essentially all of them do. `identity_provider` defaults to `local`, while every
    row created by direct ORM construction (`User(username=…, email=…)` — the pattern
    used by every integration test and by the historical fixture that created the
    duplicates) leaves `external_subject` NULL.

**Consequence the task file's §8 makes unavoidable:** the declared authoritative
identity key currently identifies **0 of 2,098 users in `pofa_test`**. Any Option-A
plan that treats `(identity_provider, external_subject)` as "the real identity, so
username/email don't need to be unique" (§22/§23's Option-B framing of it) is
describing a constraint that has never actually constrained anything in that database.
That must be stated in the results doc, whichever option is chosen.

---

# 5. §9 — NULL `external_subject` investigation (mandatory)

| Measure | `pofa_test` | `pofa_dev` |
| --- | --- | --- |
| Total users | 2,098 | 1,094 |
| `external_subject IS NULL` | **2,098 (100%)** | **1,009 (92.2%)** |
| `external_subject = id::text` (BE-016 backfill shape) | 0 | 85 |
| `external_subject` set **and** `<> id::text` | **0** | **0** |
| Duplicate `username` groups among NULL rows | 1 | 1 |
| Duplicate `email` groups among NULL rows | 1 | 1 |
| `identity_provider` values present | `local` | `local` |

**Why it is NULL — established, not guessed.** Two independent facts close this:

* `subject_other = 0` in *both* databases. If `services.authorization.create_user`
  had ever been used, its `external_subject or str(uuid4())` default would have
  produced non-NULL, **non-id** values. Zero such rows exist ⇒ **no user in either
  database was created through that service path.**
* The 85 non-NULL rows in `pofa_dev` are all exactly `id::text`, the shape of the
  BE-016 migration backfill. `pofa_dev`'s duplicate group demonstrates the cohort
  split directly: 35 members created 2026-09-13→09-20 carry `subject = id::text`
  *and* a populated `display_name`; the 5 members created 2026-09-24→09-25 have both
  NULL. Both columns were backfilled in the same migration
  (`…be016_auth_authorization.py:44-48`), so the pattern is
  "existed before BE-016 ran here" vs "created after it, by direct ORM insert".

**Can those NULL users authenticate?** Yes — authentication is keyed on the user's
`id` (`dev-user-<uuid>` → `resolve_user_principal` → `get_user(User.id == …)`), not on
`external_subject`. NULL subjects do not disable an account; they only make it
invisible to a provider-based lookup that does not exist yet.

**Are they test fixtures / seeded / legacy?** All three, split by cohort: the NULL
cohort is fixture-generated (every integration test creates users by direct ORM
construction with unique names); the `= id::text` cohort is legacy backfilled rows.
No evidence of any human-originated account in either cohort.

**§9's warning respected:** "Do not simply populate it with arbitrary values." This
plan therefore does **not** backfill `external_subject` silently under either option.
If it is backfilled at all, it must be an explicit, separately approved decision with
its own collision analysis — recorded as open question OQ-3 in §20.

---

# 6. §10 — duplicate group characterization

**One group per database**, same signature, and the group is fully self-identifying.

| Attribute | `pofa_test` | `pofa_dev` |
| --- | --- | --- |
| Group key | `username='testuser'`, `email='test@example.com'` | same |
| Members | **19** | **40** |
| `identity_provider` | `local` ×19 | `local` ×40 |
| `external_subject` | NULL ×19 | `id::text` ×35, NULL ×5 |
| `display_name` | NULL ×19 | set ×35, NULL ×5 |
| `status` | `ACTIVE` ×19 | `ACTIVE` ×40 |
| `is_active` | true ×19 | true ×40 |
| Authentication status | **no credential exists to be inactive** — see §4 | same |
| `created_at` range | 2026-09-25 13:28:44 → 2026-10-06 16:26:29, **all distinct** | 2026-09-13 13:18:19 → 2026-09-25 11:00:22, **all distinct** |
| `updated_at` | distinct per row (tracks creation) | same |
| Referencing rows per member | exactly 1 (`projects.owner_id` → one project named `testproj`, which owns exactly 1 `evidence` row named `foo.jpg`) | same, ×40 |
| Rows where `testuser-%` / `test-%@example.com` / `testproj-%` survive | **0 / 0 / 0** | **0 / 0 / 0** |

Per §10 and §33, member UUIDs and the fixed fixture literals are the only identifiers
reported; no personal data is exposed — `test@example.com` is an RFC-reserved example
domain and a hard-coded constant in `tests/integration/test_migration_and_crud.py:19-22`.

**Provenance, from the repository itself.** The current version of that test documents
its own history (`test_migration_and_crud.py:19-22`): *"The test used to insert a fixed
`testuser` / `test@example.com` pair, which kept 'succeeding' only because the database
does not enforce the uniqueness the ORM declares — and left another duplicate behind on
every run."* BE-027 made it self-cleaning (task #47); the zero-survivor measurement
above shows the fix holds, and the leftovers' timestamps space out one-per-test-run.

**Therefore:** each colliding row is one **orphaned fixture triple**
(user + `testproj` project + `foo.jpg` evidence), not a candidate human identity. The
group is deterministic to classify, which is what §39's "duplicate users cannot be
deterministically classified" stop condition is asking for.

---

# 7. §11 — foreign-key dependency map for `users.id`

Every FK column in the schema referencing `users(id)`, with its rule and the count of
rows pointing at the duplicate ids (measured with `= ANY(:ids::uuid[])`):

| Table.column | on delete | rows overall (test/dev) | rows → duplicate ids | reassignment possible? | historical? |
| --- | --- | --- | --- | --- | --- |
| `projects.owner_id` | NO ACTION | 1,053 / 584 non-null | **19 / 40** | Yes, trivially — but those projects are themselves residue | No |
| `user_role_assignments.user_id` | **CASCADE** | 659 / 872 | **0** | n/a | n/a |
| `activities.actor_id` | NO ACTION | 6 / 0 | **0** | n/a | n/a |
| `claims.claimant_id` | NO ACTION | 90 / 0 | **0** | n/a | n/a |
| `review_decisions.reviewer_id` | NO ACTION | 0 / 0 | **0** | n/a | n/a |
| `audit_events.actor_id` | NO ACTION | 0 / 0 | **0** | n/a | n/a |
| `notifications.recipient_id` | NO ACTION | 0 / 0 | **0** | n/a | n/a |
| `notification_preferences.user_id` | NO ACTION | 0 / 0 | **0** | n/a | n/a |
| `field_sessions.user_id` | RESTRICT | 0 / 0 | **0** | n/a | n/a |
| `field_assignments.user_id` | RESTRICT | 0 / 0 | **0** | n/a | n/a |
| `field_capture_operations.user_id` | RESTRICT | 0 / 0 | **0** | n/a | n/a |
| `field_assignments.created_by` / `.revoked_by` | NO ACTION | 0 / 0 | **0** | n/a | n/a |
| `field_capture_operations.resolved_by` | NO ACTION | 0 / 0 | **0** | n/a | n/a |

Second level (the residue projects' own children): `evidence.project_id` (NO ACTION)
holds exactly 19 / 40 rows under the `testproj` projects, each `filename='foo.jpg'`,
and those evidence rows are **leaves** — no FK anywhere references `evidence.id` for
those rows. `projects.owner_id IS NULL`: 0. Orphaned owners: 0.

Two constraints in `pofa_dev`'s older chain (`field_*` FKs) do not exist there at all
— the 14-column surface is `pofa_test`-wide; the `pofa_dev` subset measured was 8
columns, all zero except `projects.owner_id`. Either way, the conclusion is identical.

**The one live hazard:** `user_role_assignments.user_id` is `CASCADE`. It currently
holds 0 rows for these ids, but a careless `DELETE FROM users` on a *future* dataset
would silently destroy authorisation rows. §15 of the task file says do not use
`ON DELETE CASCADE` as a shortcut; this plan turns that into an executable assertion
(§10 step A3: prove 0, then delete; abort otherwise).

---

# 8. §12 / §32 — audit ledger position

Read-only scan of `audit_ledger_events` (30,821 rows in `pofa_test`, 6,016 in
`pofa_dev`) for the duplicate id set:

* rows with `actor_id` in the set: **0**
* rows with `resource_type='users' AND resource_id` in the set: **0**
* chain state today: `pofa_test` `valid=True`, gap-free span 1 → 30,821.
  `pofa_dev` `valid=False`, 7 gaps / 36 missing sequences — **pre-existing**, dated
  2026-09-25, already documented by `diagnostics/audit_gap_diagnostic.sql`, and
  recorded as BE-028 blocker §9.3. Not BE-029's to fix; BE-029 must not *change* it.

So no historical audit event references any of the colliding rows, which means audit
history is preserved either way — but this must be **re-measured immediately before
any write**, because these numbers move as tests run. §12's "do not rewrite historical
audit records" is satisfied trivially here since there is nothing to rewrite.

---

# 9. §4 / §5 — the product decision, and why this plan stops on it

§5 forbids guessing the policy and requires STOP + reporting
**"Product-owner identity decision required."** when the repository does not
establish it. Applied honestly to this repository, that is the situation:

| Evidence direction | Supports |
| --- | --- |
| No login, no credentials, no registration, no OAuth callback, no lookup by username/email anywhere (§2, §4) | Option **B** (profile attributes) |
| `email` has no format validation at all (`schemas/authorization.py:62`: `min_length=3`, not `EmailStr`) — an email column the API will not check is not an email *identity* | Option **B** |
| `username`/`email` are write-once; only `status` is mutable (`auth.py:229`) | Neutral-to-**B** (identity keys you cannot change either way) |
| The ORM *declares* `unique=True` on both (`models.py:44-45`) — someone intended uniqueness at some point | Option **A**, as an *intent artifact*, with no implementation behind it |
| The one real identity key `(identity_provider, external_subject)` constrains **0 of 2,098** rows in `pofa_test` (§4 Q3/Q7-9) | Weakens **B**'s "the real identity remains …" claim unless that key is also repaired |
| A frontend/registration flow would need uniqueness; §5 asks to inspect frontend flows — **none exists that consumes these columns** | Option **B** |

**Verdict required by §5: the repository does not establish the policy.** A declared
constraint with no code behind it is not a policy; it is the exact drift BE-028 was
created to surface. So the decision is the user's, and this plan prepares both
branches without selecting one destructively.

Note the asymmetry that should inform the choice: **Option B is a two-line metadata
change with no data operation** (§11), whereas **Option A cannot be executed as
written** — see §10's gate. My evidence-based *proposal*, explicitly not a decision:
**Option B**, plus the §25 identity tests, plus a duplicate *detector*, plus an
open item that the declared identity key is currently inert.

| Option | Meaning per task file | Data touched | Drift end-state | Status |
| --- | --- | --- | --- | --- |
| **A** | username/email **are** identity attributes; uniqueness must be enforced | 19+19+19 (test) / 40+40+40 (dev) rows retired | 4 Category-E entries *satisfied* → gone | **Blocked** by §14 (no discriminator) — see §10 |
| **B** | username/email are profile attributes; ORM must stop claiming uniqueness | **None** | 4 Category-E entries *deleted* → gone | Ready to execute on approval |

---

# 10. Option A plan (§13–§21) — and the gate it hits immediately

### A0. Canonical selection (§14) — **STOP condition reached**

§14 requires an *evidence-based* canonical account and says: "If two accounts are
equally legitimate: STOP and escalate the conflict." The six signals §14 lists, tested
against the data:

| §14 signal | Discriminates? | Measurement |
| --- | --- | --- |
| 1. Valid authenticated external identity | **No** | Authentication is keyed on `id`; no credential references these columns |
| 2. Verified account | **No** | No verification column exists |
| 3. Active account | **No** | 100% `status='ACTIVE'`, 100% `is_active=true` in both groups |
| 4. Existing provider identity | **No** (test) / **partially** (dev) | 0/19 populated in `pofa_test`; 35/40 in `pofa_dev` — and that split is a BE-016 migration artifact marking *when a row existed*, not *who owns it* (§5) |
| 5. Number of legitimate references | **No** | Every member owns exactly 1 project, which is itself residue |
| 6. Creation timestamp | Syntactically yes | `created_at` is distinct for all members; oldest-wins would retire 18 (test) / 39 (dev) |

`created_at` is the only signal that produces a winner, and it records **when a test
run**, not when a person registered. Adopting it would be §14's forbidden "inventing
priority rules". ⇒ **Option A as specified cannot proceed to a merge.** The task file's
own stop condition applies and must be reported, not worked around.

**What unblocks A.** Not a merge rule — a different question. Because the rows are
provably synthetic (§6), Option A does not need *canonical selection* at all if the
product owner instead authorises **"retire identified synthetic fixture residue"**,
which is a garbage-collection decision about 3-row triples, not an arbitration between
identities. Three sub-decisions make A executable:

* **A-D1** — approve retiring the residue triples (user + `testproj` project +
  `foo.jpg` evidence) as fixture garbage, *or* keep exactly one row per group and
  retire the rest, *or* reject both (in which case A is impossible and B is the only
  honest outcome).
* **A-D2** — approve the change for `pofa_test` **and separately** for `pofa_dev`
  (§27 protects `pofa_dev`; BE-028 §5 protected it too). Declining dev leaves the two
  environments with *different* constraint states, which the drift gate will report as
  a difference — that is acceptable only if documented deliberately.
* **A-D3** — decide whether `external_subject` is repaired in the same task (§20,
  OQ-3). Enforcing username/email uniqueness while the declared identity key remains
  NULL for 100% of rows replaces one fiction with another.

### A1. Duplicate remediation design (§14), assuming A-D1 = retire-as-garbage

Deterministic detection, exact-value grouping, re-run before any write (BE-028's
numbers are a 2026-10-08 snapshot, not an assumption):

```sql
SELECT email, username, count(*) AS members,
       array_agg(id::text ORDER BY created_at, id) AS ids
FROM users
GROUP BY email, username
HAVING count(*) > 1;
```

Case-folding and `+tag` folding add **zero** groups today (§5 measurement), so no new
collation or expression index is proposed — and §17/§18 forbid importing provider
transformations the app doesn't define. The app's only normalisation is the service
layer's `strip()` / `strip().lower()`, and per §17 that is the policy to *document*,
not to retro-fit by rewriting stored values (§18: "Do not silently change existing
usernames").

### A2. Residue guard predicate — the abort mechanism

A run must **refuse** to touch anything that is not provably residue. Key the predicate
only on literals the leftover test itself wrote, never on backfill-dependent columns
(`display_name` / `external_subject` differ between the two DBs for reasons unrelated
to residue — that mistake would have spuriously aborted the real `pofa_dev` run on 35
rows):

```
username = 'testuser' AND email = 'test@example.com'
AND owns exactly one project, whose name = 'testproj'
AND that project's only children are evidence rows with filename = 'foo.jpg'
AND zero rows in every other FK column pointing at the user id
AND zero audit_ledger_events rows with the id as actor_id
    or as (resource_type='users').resource_id
```

Any member failing it ⇒ abort the whole run, escalate, no partial execution. Report
`display_name`, `external_subject`, `status`, `created_at` for every member as
*evidence*, never as conditions.

### A3. Foreign-key reassignment (§15)

For residue, reassignment is unnecessary; deletion order is forced by FK direction and
the NO ACTION rules: **evidence → projects → users**, one transaction per group,
`flush()` + FK validation before commit.

If a non-residue group is ever approved for a merge, the order is: measure every
reference count first; `UPDATE projects SET owner_id = :canonical WHERE owner_id =
:losing` re-counted against the measured expectation; verify **no** FK anywhere still
points at `:losing`; assert `user_role_assignments` count for `:losing` is **0 before
deleting** (never let the CASCADE do the work); only then delete. Historical
relationships that "must remain tied to the original user" (§11) —
`audit_ledger_events`, `activities`, `claims`, `review_decisions` — must never be
re-pointed; today they hold 0 rows for these ids, and that is re-verified, not assumed.

### A4. Pre-constraint validation (§19)

Run A1's query against the target normalised values; the result **must be zero
duplicate groups**. If it is not, do not create the constraint. This is a hard gate
inside the migration script, not a manual step.

### A5. Unique constraint implementation (§20), with §34's measurements

BE-028 already proved the index fails on this data today: both
`CREATE UNIQUE INDEX CONCURRENTLY` and the plain form errored on a scratch clone
(`D:/CODING/Scratch/be028/unique_index_attempt.log`). So ordering is forced — data
first, constraint second.

Table sizes measured 2026-10-08 (`pofa_test` / `pofa_dev`): `users` 2,098 / 1,094 ·
`projects` 1,053 / 584 · `evidence` 784 / 324 · `review_cases` 5 / 10 ·
`audit_ledger_events` 30,821 / 6,016. At these sizes `CONCURRENTLY` is **not**
appropriate: it cannot run inside a transaction, and its failure mode is an `INVALID`
index that must be detected and dropped manually. §20 says "do not assume it is
required" and to measure first — measured, therefore: plain `op.create_index(...,
unique=True)` in a revision that runs after the data revision. Two revisions, not one:

1. `…​_be029_retire_identity_residue` — data only, archive-then-retire (§A6), reversible.
2. `…​_be029_user_identity_unique` — the two unique indexes, `down_revision` → (1).

This keeps "duplicate remediation complete" and "constraint exists" separately
observable in `alembic history`, and lets the drift gate see the constraint appear only
once A4 would pass. Do **not** collapse them: a single revision that deletes-then-indexes
rolls the retirement back on an index failure and hides which step went wrong.

### A6. Rollback (§29)

`downgrade()` must be a *restore*, not a re-merge. Achieve that by construction:
copy full rows into `users_retired` / `projects_retired` / `evidence_retired` (with
`retired_at`, `retire_reason`, group key, and **the original ids**) before deleting.
Downgrade then drops the indexes and re-inserts the archived rows by their preserved
ids, so FK re-pointing is exact and heuristic-free. Prove it by
`upgrade → downgrade → upgrade` on the clone with the §13 fingerprint byte-identical.
A rollback that was not executed and compared is not a rollback claim.

### A7. ORM alignment (§21)

After A5, `models.py:44-45` stays as-is (its `unique=True` becomes true at last), the
four Category-E baseline entries are deleted **in the same change** (the gate's
two-directional rule requires it), and `alembic check` must show the `users` entries
gone. Any remaining difference is documented or fixed — never baselined to hide.

---

# 11. Option B plan (§22–§24) — no data operation

1. **`backend/db/models.py:44-45`** — keep `index=True`, drop `unique=True`, and put
   the policy where the reader will hit it: `username`/`email` are profile/contact
   attributes; authoritative identity is `(identity_provider, external_subject)`
   (matching `uq_user_identity_subject`) + `users.id`.
2. **No migration.** `ix_users_username` / `ix_users_email` already exist as plain
   btree indexes under exactly the names `index=True` produces. A migration here would
   be speculative (BE-028 §35). §36 lists `alembic/versions/<new_revision>.py` as a
   *potential* file; under B it is not needed, and that must be said explicitly in the
   results doc rather than producing an empty revision to look busy.
3. **Baseline** (`tests/schema_drift_baseline.py:72-97`) — delete the four Category-E
   `users` entries. Same change as step 1. `users` drift then becomes **0**; the only
   remaining baseline entries are the two `uq_user_role_scoped` nulls-not-distinct
   tooling artifacts (Category B), and `alembic check` still exits FAILED on them —
   reported as PASS-WITH-DOCUMENTED-BASELINE, never suppressed (§31).
4. **§24 API validation** — verified: no code path rejects duplicate username/email, so
   there is nothing to remove. `create_user` raises only on empty-after-strip input
   (`services/authorization.py:309-311`). Record this as "no change required", not as a
   change.
5. **§23 document the identity model** — in the results doc and in the model comment,
   using the task file's exact §23 shape, with the §4-Q3 caveat that the composite key
   is currently inert for NULL subjects.
6. **§25 identity tests** (§12 below) and the **duplicate detector** — under B,
   duplicates are *permitted by policy*, so the safety net is a detector that fails on
   any **new** duplicate group beyond the documented residue signature. Without it,
   Option B quietly re-enables the bug that created these 59 rows.
7. **Verification** — §13/§14 commands; no data step, so §27/§28/§29 reduce to "prove
   nothing moved".

---

# 12. §25 — identity-contract tests (mandatory under **either** option)

These tests assert the contract that *already exists* in the database, so they can be
written and run before the A/B decision. They require a scratch/target database they
can write to — **not** `pofa_dev`, and `pofa_test` only under the pytest harness that
already owns it.

| Test | Expected today | Value |
| --- | --- | --- |
| Same `identity_provider` + same `external_subject` inserted twice | **2nd must fail** (`uq_user_identity_subject`) | Proves §41's acceptance case. Needs a clean write target; also proves the API surfaces it as **409/422, not 500** — `POST /auth/users` currently has no IntegrityError mapping (`auth.py:151-171`), so this may expose a real defect. **(Planning-time claim, falsified by the follow-up: a blanket `IntegrityError`→409 mapping had existed since BE-016, and the defect was the reverse — unrelated integrity failures reported as duplicate identities. Narrowed to the three named identity objects; see Results §13.1.)** |
| Different provider + different subject | Allowed | §41 case 2 |
| Same provider + `NULL` subject, many rows | **Allowed today (NULLS DISTINCT)** | Makes the §4-Q7/8/9 hole *explicit and asserted* instead of accidental — this is §25's "NULL external subject behaviour must be explicitly defined. Do not leave it accidental." |
| Same `username` for two users | Allowed today (no DB constraint); service layer does not check | Behaviour pinned to whichever option is chosen |
| Same `email` for two users | Allowed today | same |
| `create_user` normalisation | `strip()` + `strip().lower()` on email, `strip()` on username | Locks §17's documented policy |
| Duplicate-group detector | only the documented residue signature | Regression net for both options |
| Drift gate stays green; baseline edited in the same change | — | §31 |

If a test contradicts the policy chosen in §9 (e.g. Option B while the second-insert
test expects a username collision), the *test* is written to the policy — the policy is
never bent to a convenient test.

---

# 13. §26–§29 — scratch protocol, protected-DB protocol, P0 checks, rollback

**§26 migration testing** (Option A only; Option B has no migration):

```
CREATE DATABASE pofa_be029_scratch TEMPLATE pofa_test
  → alembic upgrade head          (base → head on a fresh DB too, per BE-028 §15)
  → apply BE-029 revisions
  → run identity tests
  → verify schema (alembic check; signatures must match the in-place DB)
  → verify data integrity (fingerprint below)
  → downgrade → verify → upgrade again → fingerprint identical
```

Never destructive-test `pofa_dev` (§26, §27).

**§27 before any operation on a real database, record and compare:** database name
(from `current_database()`, never inferred from `DATABASE_URL`), schema, migration
revision, user count, duplicate counts. `DATABASE_URL` vs `TEST_DATABASE_URL` is a
known trap in this repository — every standalone script must export the URL it means,
and the plan requires an explicit `SELECT current_database()` print at the top of every
run so a mis-pointed script is visible in its own log.

**§28 P0 before/after comparison** (the fingerprint technique BE-028 used successfully):
user count, project count, evidence count, review count, audit event count, per-FK
reference counts, duplicate groups, NULL external-subject count, identity-constraint
inventory from `pg_constraint`. Starting values measured 2026-10-08, `pofa_test` /
`pofa_dev`: users 2,098 / 1,094 · projects 1,053 / 584 · evidence 784 / 324 ·
review_cases 5 / 10 · review_decisions 0 / 0 · claims 100 / 19 · activities 6 / 0 ·
user_role_assignments 659 / 872 · audit_ledger_events 30,821 / 6,016 · duplicate groups
1 / 1 · NULL external subjects 2,098 / 1,009. Option B must show **zero** change in
every number. Option A must show exactly −19/−19/−19 (test) at the data step and nothing
else. These values move as tests run, so the "before" column must be captured by the
migration script itself, not copied from this table.

**§29 rollback** — tested as described in A6, with the three-state fingerprint
comparison executed and recorded, not asserted.

---

# 14. §30–§34 — tests, gate, security, performance

**§30 commands and baselines** (from the committed BE-028 state):

| Command | Baseline to match |
| --- | --- |
| `pytest -q tests/unit` | 420 passed, 1 skipped |
| `pytest -q tests/integration` | 281 passed, 1 failed |
| `pytest -q -m "not integration" tests` | 695 passed, 1 failed, 1 skipped |
| `alembic check` | currently FAILED with 6 operations → must become 2 (B) or 2-with-constraints-satisfied (A) |
| `pytest tests/integration/test_schema_drift_gate.py tests/unit/test_migrations.py` | 14 passed |
| identity tests added by BE-029 | new, all green |

The 1 integration failure is
`test_be025_admin_control_plane.py::test_organization_lifecycle_noop_audit_and_isolation`
(line 535 pagination assertion) — **pre-existing, volume-sensitive, and not to be
weakened, skipped, deleted or modified** (§30). Any baseline change must be explained.
Run everything with `backend/.venv312_repro` and `TEST_DATABASE_URL` pointed at
`pofa_test`.

**§31 drift gate** — never bypassed. The gate is two-directional, so *resolving* drift
also fails it until the baseline is edited in the same change; that failure is the
mechanism working. If `alembic check` changes, every changed operation is explained,
and the baseline is updated only where the underlying schema/ORM state genuinely
changed.

**§33 security** — identity work here is metadata and analysis. No credential exists to
log. Diagnostic scripts print counts and UUIDs, and the only literal username/email
quoted in this plan is a fixture constant on a reserved example domain.

**§34 performance** — measured, so no uncontrolled full-table write is proposed:
`users` 2,098/1,094 rows, `projects` 1,053/584, and Option A's write set is 3 rows per
group member (≤120 rows total). Both `ix_users_username` and `ix_users_email` already
exist, so duplicate detection uses an existing index and costs no new object. Lock
behaviour: `CREATE UNIQUE INDEX` (non-concurrent) takes a write lock on a table of ~2k
rows — acceptable, and stated as the reason §20's CONCURRENTLY is not used here rather
than copied in by habit. If any future dataset makes these tables large, A5 must be
re-measured before being reused as a template.

---

# 15. §35 — results document outline

`docs/BE-029 User Identity Constraint Remediation Results.md`, with §35's exact eleven
parts: Product Decision (+ evidence, and *who* decided) · Existing Identity Model ·
Duplicate Analysis (counts and ids only, per §10/§33) · Remediation (or the explicit
sentence "no data was changed") · Database Changes · Application Changes · Tests (exact
commands, exact numbers) · Data Safety (explicit statements: was `pofa_dev` modified?
were users deleted? merged? FKs reassigned? audit records changed?) · Rollback (tested
behaviour) · Remaining Risks · Next Task (recommended, **not implemented**).

Must also carry forward, because they are true regardless of option: the declared
identity key is inert for NULL subjects (§4 Q3/Q7-9); `email` has no format validation;
a user cannot hold multiple provider identities; `POST /auth/users` does not map
IntegrityError; `pofa_dev`'s ledger has 7 pre-existing gaps; expression/GiST indexes are
invisible to Alembic's drift comparison.

---

# 16. §36 / §37 — file boundaries

Likely changed (Option B): `backend/db/models.py`, `tests/schema_drift_baseline.py`,
new `tests/integration/test_be029_identity_contract.py` (or added cases in the existing
integration style), `docs/BE-029 … Results.md`.
Likely changed (Option A): the above minus the baseline *deletion* semantics, plus two
new revisions under `alembic/versions/` and `backend/db/retire_*` script code.

Correction to the task file's §36 list, so nobody edits a path that doesn't exist: this
repository has **no `backend/auth/` and no `backend/core/config` identity surface**. The
relevant modules are `backend/security/authentication.py`,
`backend/services/authorization.py`, `backend/repositories/authorization.py`,
`backend/schemas/authorization.py`, `backend/api/v1/endpoints/auth.py`. §37's
"do not modify unnecessarily" list stands in full; in particular the audit-chain
implementation, evidence intelligence, ML, geofence, analytics, frontend, mobile and
Docker/WSL configuration are untouched, and BE-029 is not combined with any other task.

---

# 17. §38 — git discipline

`git status` was already run: the tree currently holds only the two untracked BE-029
documents (this plan + the task file). BE-028's files are committed (`0763afe3`), which
also committed the externally deleted `docs/BE-027 Backend Foundation Audit and
Results.md` — **not to be reverted or re-litigated** (standing instruction from BE-028,
and §38 again: "Do not revert unrelated documentation changes").

For BE-029: stage only by explicit filename; never `git add .` / `-A`; never `git clean`
/ `git reset --hard`; never stage venvs, caches, logs or scratch paths
(`D:/CODING/Scratch/**` stays out); **commit proposal presented for approval, not
executed**; **no push unless explicitly requested**.

---

# 18. §39 stop conditions + §40 Definition of Done

**STOP (report the exact blocker, do not improvise) if:** the policy cannot be
established — *already the case, hence §9's escalation*; duplicate records cannot be
deterministically classified; two external identities look like one account but
ownership can't be proven; FK ownership can't be established; unique-constraint creation
would fail; the migration would require deleting users without an explicit retirement
approval; audit history would change; unexpected cascades appear; rollback can't be
demonstrated; the ledger becomes newly invalid; row counts shift unexplained; identity
references orphan; drift becomes unexplained; or infrastructure fails mid-write.

**DoD:** identity policy explicitly established with documented evidence and a named
decider · authoritative identity documented and *tested* (`provider+subject`, NULL
behaviour) · username/email semantics explicitly defined · duplicate groups measured ·
FK dependencies measured · no user deleted without explicit approval · no ambiguous
account merged · no audit history corrupted · (A) data remediated + uniqueness enforced +
ORM/DB agree / (B) ORM no longer claims uniqueness + DB stays non-unique + real
constraint remains enforced · identity tests pass · unit/integration/migration baselines
met or explained · drift gate green · ledger valid · results doc complete with all
eleven parts.

---

# 19. §41 acceptance test + §42 report format

Acceptance (§41) restated as executable checks: Provider A + Subject X must not create a
second user · Provider A/Subject X vs Provider B/Subject Y behaves per policy ·
duplicate-username behaviour matches the chosen option exactly · duplicate-email likewise
· existing users/projects/evidence/reviews/audit events remain intact (counts, orphans,
chain) · `alembic upgrade head` + `alembic check` + drift gate all reported ·
`audit_chain.valid == true`.

Final report: §42's fourteen numbered parts, verbatim structure, exact measured numbers,
"Do not invent PASS results", and a Recommended Next Task that is **not** implemented
(§43: after BE-029 is genuinely complete, STOP; do not begin BE-030).

---

# 20. Open questions — answers required before any code

| ID | Question | Blocks |
| --- | --- | --- |
| **OQ-1** | **Option A or Option B?** (§4/§5) | Everything |
| **OQ-2** | If A: approve **retiring the 19/40 synthetic residue triples** as fixture garbage (A-D1)? Note §14's canonical-selection path is unusable here (§10 A0), so without this, A has no lawful route. | Option A entirely |
| **OQ-3** | Repair `external_subject` in BE-029 (`SET external_subject = id::text WHERE external_subject IS NULL`, the BE-016 shape, ± `NOT NULL`), or file it as a separate task? Today the declared identity key covers 0/2,098 rows in `pofa_test`. | §4 Q3/Q7-9 honesty, §23 doc |
| **OQ-4** | If A: is `pofa_dev` remediated in the same task (separate approval, §27) or left non-compliant and documented? | Option A scope |
| **OQ-5** | Should `POST /auth/users` map a `(provider, subject)` collision to 409/422 instead of a 500? (Found while planning §25's first test; it is arguably BE-029-adjacent, arguably scope creep per §37.) | §25 test #1 |
| **OQ-6** | Confirm the two untracked BE-029 docs may be committed with the code, or stay local. | §38 staging |

**Nothing in this plan is executed until OQ-1 is answered.** The §25 identity tests and
the duplicate detector are the only items that are option-independent, and they still
wait for approval because they are code changes.

`Inspect. Measure. Decide. Test. Only then migrate.` — and the decision in the middle of
that list is not mine to make.
