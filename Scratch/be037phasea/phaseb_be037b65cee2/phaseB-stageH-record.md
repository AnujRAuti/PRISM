# BE-037 Phase B — Stage H record: audit ledger integrity and database security

Run `be037b_20261013T062257Z_65cee2` · prefix `be037b65cee2` · executed 2026-10-13
against the **disposable** stack only (db `996ee2c6da35`, api `4f8c81a56b01`,
client `e98bb071c6c8`). No protected resource was read for writes or modified; the
live containers, `pofa_dev` and `pofa_test` were not touched by this stage.

Stage H question, in the task file's own terms: does the integrated system keep an
append-only audit ledger that it can *verify*, *protect from mutation*, and
*correctly classify when broken* — measured through the running service rather than
a unit test?

Verdict: **PASS with two findings (BE-037B-H1, BE-037B-H3), one scope note (H2) and
one deliberate NOT RUN.** 47 of 47 checks passed across the three scored runs
(A 28, B2 14, F 5). Run B1's 29 rows were superseded: four of them were vacuous and
one was mis-scoped, and that history is kept in §5 rather than quietly dropped.

---

## 1. Results by run

| Run | What it measured | Result | Evidence |
|---|---|---|---|
| A | Chain verification over the real API: whole, bounded, anchored, checkpoint, baselines, authorization, app-path append + re-verify | **28/28** | `stageH-02-api-verify.txt` |
| B1 | Runtime privilege matrix as `be037b_rt`, real statements | 25/29 — **4 rows unusable** (§5) | `stageH-03-privilege-matrix.txt` |
| B2 | Corrected matrix + escalation chain, each refusal asserted against its expected error class | **14/14** | `stageH-05-privilege-matrix-recheck.txt` |
| C | The second wall, from the owner side, inside rolled-back transactions | all as expected | `stageH-06-owner-trigger-proof.txt` |
| E | Tamper **detection** and gap **classification**, live, then reversed | 3 phases measured | `stageH-09`, `stageH-11`, `stageH-13` |
| F | Catalogue-view access, business-table write scope, RLS presence, trigger presence | **5/5** | `stageH-14-dbsecurity-edges.txt` |
| close | Final ledger state | 87 rows, head 87, `valid=true`, `status=clean`, 0 probe rows | `stageH-15-closing-state.txt` |

Supporting measurements: `stageH-00-ledger-state.txt` (16 event types over 82 events
at stage start), `stageH-01-ledger-ddl.txt` (the real DDL: trigger is
`BEFORE UPDATE OR DELETE`, CHECK has the 94-value domain), `stageH-04-recheck-grants.txt`
(ACL after run B1), `stageH-07-append-timing.txt` (when the next live append was due,
so the demo window could avoid it), `stageH-10`/`stageH-12` (the two owner deletions).

## 2. What is now proven about the integrated system

**Verification works on real traffic.** The ledger at stage start held 82 events
from Stages E–G application paths; at close it held 87, all produced by real HTTP
calls and worker activity. `GET /api/v1/audit/verify` returned
`{valid: true, checked_events: 86..87, first_sequence: 1, last_sequence: 87, failures: []}`,
a bounded walk `?from_sequence=5&to_sequence=12` returned exactly 8 events, and
`?to_sequence=0` was rejected 422 by validation instead of being ignored.

**The anchor is published, not implied.** `/audit/verify/anchored` returned
`writer_policy: "controlled_continuation"` and a checkpoint
`{rows, min_sequence, max_sequence, tail_event_hash, tail_previous_hash}` whose tail
hash changed to the new head after an application write — the anti-TRUNCATE digest
is real and moves with the chain.

**Append through the application path is correct and continuous.** One
`POST /api/v1/auth/users` advanced the head 86 → 87; the new row's
`previous_hash` equals the previous checkpoint `tail_event_hash`
(`7ac9e36c…` → row 87), `hash_algorithm=SHA-256`, `ledger_version=audit-v1`, and the
row is retrievable through `/api/v1/audit/events?…&resource_id=…`. The chain stayed
`valid=true` with no failures.

**Authorization actually binds.** `ADMINISTRATOR` → 200; authenticated
`FIELD_OFFICER` (no `audit.read`) → **403 Forbidden**; the same request with no
token → 200, which is the inherited dev-mode anonymous bypass
(BE-037B-G2), recorded as a finding and not as a Stage H pass.

**The baseline registry behaves as designed.** Omitted baseline and `?baseline=none`
give the identical fail-closed classification (`status: clean`, empty known list,
`baseline_version: 0`). The blessed `pofa-dev-pre-be030-test-cleanup` name is
accepted, reports version 1, and **does not adopt anything on this ledger**
(`known_historical_gaps: []`). An invented name is refused 422 with the registered
list echoed back rather than silently downgraded to `none`.

**The runtime identity cannot mutate the ledger — measured, not predicted.** As
`be037b_rt`, from inside the api container using the DSN already in its environment,
every one of these was refused with the reason stated:

| Attempt | Server response |
|---|---|
| `UPDATE audit_ledger_events …` | `permission denied for table audit_ledger_events` |
| `DELETE FROM audit_ledger_events …` | `permission denied for table audit_ledger_events` |
| `TRUNCATE TABLE audit_ledger_events` | `permission denied for table audit_ledger_events` |
| `DROP TABLE` / `ALTER TABLE … ADD COLUMN` / `DROP TRIGGER` | `must be owner of table/relation audit_ledger_events` |
| `CREATE OR REPLACE FUNCTION audit_ledger_refuse_mutation()` | `permission denied for schema public` |
| `CREATE TABLE public.be037b_probe` | `permission denied for schema public` |
| `SET ROLE be037b_owner` | `permission denied to set role "be037b_owner"` |
| `SET ROLE postgres` | `role "postgres" does not exist` |
| `ALTER ROLE be037b_rt SUPERUSER` | `must be superuser to alter superuser roles…` |
| `SELECT`/`UPDATE alembic_version` | `permission denied for table alembic_version` |
| `SELECT rolname, rolpassword FROM pg_authid` | `permission denied for table pg_authid` |

Identity and attributes were measured per role: `current_user = session_user =
be037b_rt`, and `rolsuper, rolcreaterole, rolcreatedb, rolbypassrls =
False, False, False, False`. The ledger ACL is exactly
`{be037b_owner=arwdDxt/be037b_owner, be037b_rt=ar/be037b_owner}` — insert+select.

**A self-grant is inert.** The runtime's `GRANT UPDATE ON audit_ledger_events TO
be037b_rt` returns *without error*, but `has_table_privilege('be037b_rt', …, 'UPDATE')`
is still **false in that same transaction**, and a ledger `UPDATE` immediately after
is still refused `InsufficientPrivilege`. The statement grants nothing because the
grantor holds neither the privilege nor grant option; the same `GRANT` executed by
`be037b_owner` flips it `f → t` (and `REVOKE` flips it back), in a transaction that
was rolled back (`stageH-06`, H15c). Even with the sanctioned hatch GUC set in the
same session, the ledger `UPDATE` stays `permission denied` (H8q/H13b) — the hatch
silences the trigger, it does not buy a grant.

**The second wall is real.** For the only principal that *does* hold the privilege —
the table owner, which in this disposable cluster is also a cluster superuser — the
trigger still refuses mutation: `sqlstate=42501`, `append-only enforcement refuses
UPDATE on the audit ledger`, and the same for `DELETE`. With
`SET LOCAL poa.ledger_mutation_exception='on'` the update is allowed, which is the
intended remediation path. Everything in that run was inside one transaction ended
by `ROLLBACK`; post-rollback the ledger is 87 rows, head 87, row 1 still
`ORGANIZATION_CREATED`, ACL unchanged, runtime privileges `(f,f,f,t)`.

**Broken links are detected, and a gap is classified correctly.** Controlled damage
on the disposable ledger, tagged `action='be037b-forged-probe'` so removal selected
the rows by marker instead of a hand-carried sequence number:

| State | `valid` | `status` | reported |
|---|---|---|---|
| two forged rows appended (arbitrary hashes) | false | `new_anomaly` | `hard_anomalies: ["event_hash mismatch at sequence 88", "…89"]` |
| lower forged row removed by the owner+hatch path | false | `new_anomaly` | `new_gaps: ["sequence gap before 89 (expected 88)"]`, `known_historical_gaps: []` — under **both** the default and the blessed pofa-dev baseline |
| both forged rows removed | **true** | **`clean`** | all lists empty, 87 rows at head 87 |

The discrimination test is the middle row: a *foreign* gap is never blessed, because
the baseline is keyed to exact `(before, expected)` tuples and not to a gap count.

**Domain and uniqueness constraints hold at the database.** Four malformed
`event_type` values — out-of-domain, empty, injection-shaped
(`'USER_CREATED; DROP TABLE x--'`), and a lower-case spelling of a real value — were
each refused as `CheckViolation` naming `ck_audit_ledger_event_type_domain`. Re-using
an existing `sequence_number` is refused as `UniqueViolation` on
`uq_audit_ledger_sequence`, so the chain cannot be forked at the same height.

**Nothing uses row-level security.** Zero public tables have `relrowsecurity`, zero
policies exist. Tenant/organisation scoping is entirely an application-layer control,
which raises the value of the grant findings above: there is no RLS backstop behind
them.

## 3. Findings (reported, not fixed — owner decides)

**BE-037B-H1 — Medium — the database validates the ledger's *domain* and
*uniqueness*, not its *chain continuity*.** A principal with the ordinary runtime
identity can commit a syntactically valid ledger row whose `previous_hash` and
`event_hash` are arbitrary, or append at `max+5` to fabricate a gap, and PostgreSQL
accepts it; the `trg_audit_ledger_append_only` trigger is `BEFORE UPDATE OR DELETE`
only (`stageH-01-ledger-ddl.txt`), so there is no `BEFORE INSERT` validator. Chain
correctness on insert lives in `append_event` (the D-2-A immediate-predecessor
check), i.e. in the same process that a SQL-injection or compromised runtime
credential controls. Measured here: a direct runtime `INSERT` with `repeat('a',64)`
hashes was **ACCEPTED** (H13precursor), and the resulting break was reported
faithfully by the API afterwards. This is **detect, not prevent**: history cannot be
rewritten (grants + trigger, both proven), but false events can be injected and are
only surfaced when someone runs verification. The checkpoint digest published by
`/audit/verify/anchored` is what makes "nobody ran verification" itself detectable.
Owner decision: accept as designed, or add a `BEFORE INSERT` chain validator.

**BE-037B-H2 — Informational, scope limit of this stage.** In the disposable
cluster the migration/owner identity `be037b_owner` is the container's
`POSTGRES_USER`, i.e. a **cluster superuser**. That is an artifact of how the throwaway
cluster was bootstrapped and no application path ever uses it, but it means this
stack cannot demonstrate the append-only wall for a deployment where the runtime DSN
*is* the table owner — there the trigger would be the only defence against
UPDATE/DELETE and **no defence at all** against TRUNCATE. The requirement this
implies is already met on `pofa_dev` (BE-033/034/035: `poa_runtime` is not the owner)
and is restated here so it cannot be lost.

**BE-037B-H3 — Medium (design scope, not a Phase B defect).** The runtime identity
retains full DML on ordinary business tables: a raw `DELETE FROM organizations …`
and `UPDATE organizations …` both succeeded (each rolled back). Append-only protects
the audit ledger only; the evidence, claim, dispute and user rows the ledger
*describes* are mutable and deletable by anything holding the runtime credential.
Deleting such a row would leave its audit events intact but strand them. Reporting
the boundary, not proposing a fix.

**BE-037B-H4 — Low.** `has_table_privilege`-based assertions (Stage D) and real
statement execution disagreed in usefulness, not in outcome: only the executed
statement reveals *why* a mutation is refused. Stage H therefore measures statements
and asserts the error class, so a refusal for the wrong reason cannot be logged as a
pass (that discipline is what caught the run-B1 problems in §5).

## 4. NOT RUN, with reasons

* **`TRUNCATE audit_ledger_events` as the owner/superuser.** Not attempted, on
  purpose: the trigger does not fire for TRUNCATE, so the statement would have
  destroyed the disposable ledger unrecoverably and invalidated the rest of Phase B.
  Protection against TRUNCATE is F-05 non-ownership, which **was** measured from the
  runtime side (`permission denied for table audit_ledger_events`). Recorded as
  NOT RUN, not as a pass.
* **The full "attacker forges a row and then the app chains onto it" scenario.**
  Requires leaving the demo damage committed; Stage E reverses everything instead.
* **Any write against `pofa_dev` / `pofa_test`.** Their chains were measured
  read-only in BE-032R/BE-033/BE-035; nothing in Stage H re-touches them.
* **A `BEFORE INSERT` chain validator test.** Does not exist in the codebase
  (finding H1); testing its absence was done by direct insert acceptance instead.

## 5. Process notes — kept deliberately

* **Run B1 produced four VACUOUS passes and one mis-scoped expectation.** The
  ledger `INSERT` probes used `'a'*64`; PostgreSQL parses that as integer
  multiplication, so every one died with `invalid input syntax for type integer: "a"`
  — including the rows labelled "refused by the domain CHECK" and "refused for
  duplicate sequence". Those were refusals for an unrelated reason and are **not**
  evidence; they were re-measured in run B2 with `repeat('a',64)` and each refusal
  now asserts its expected error class (`CheckViolation` naming the constraint,
  `UniqueViolation` naming the index). Run B1's `pg_shadow` row was the same mistake
  (`column "rolpassword" does not exist`) and was replaced with the real
  `pg_authid` test. Run B1's "delete from an ordinary business table must be refused"
  asserted a denial the F-05 grant shape deliberately does not provide; that row was
  reclassified as the by-design capability it is (finding H3).
* **Run B1's `GRANT UPDATE … TO be037b_rt` reported ALLOWED and looked like a
  breach.** The follow-up ACL read showed `be037b_rt=ar` unchanged, so it had been
  rolled back with its transaction; the open question was whether it was effective
  *inside* the transaction, which run B2 answered (no) and run C explained by
  contrast (the owner's identical `GRANT` does flip it). The alarming-looking row was
  investigated to a mechanism instead of being reported or dropped as a verdict.
* **Savepoints were required, not decorative.** In run B1's escalation chain a
  refused statement aborts the PostgreSQL transaction, so each later statement would
  have failed with `current transaction is aborted` and produced a *false* "wall
  holds". Run B2 isolates each attempt with `SAVEPOINT`/`ROLLBACK TO`.
* **Controlled damage was bounded and reversed.** The forged-row demo ran 08:35–08:37
  with the next scheduled live worker append measured at 08:39:47
  (`stageH-07-append-timing.txt`), so no application event could interleave at the
  sequences being used. Forged rows were identified by the marker
  `action='be037b-forged-probe'`, removed by exactly that predicate, and the closing
  measurement confirms 87 rows, head 87, zero marker rows, `valid=true`.
* **Secret handling.** Every privilege statement ran inside the api container from a
  script fed over stdin, reading `os.environ["DATABASE_URL"]`; no DSN, password or
  token appears in any Stage H evidence file. The owner-side steps used `docker exec
  psql -U be037b_owner` over the container's local socket, which needs no credential
  in the command line.
* The Stage H probes are `probe_h1.py` (client), `probe_h2.py`/`probe_h2b.py`/
  `probe_h3.py`/`probe_h4.py` (api container) and
  `stageH-owner-trigger-proof.sql` (db container) in this directory.
