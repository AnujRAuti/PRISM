# BE-025 Stage E — Hardening Results

Milestone: BE-025 Organization, Role Assignment & Administrative Control Plane
Branch: `Backend` · Baseline commit: `75c52b68` (BE-024 accepted) · Prior gate: Stage D (PASS)
Stage gate: task file §17 (Stage E — Hardening)

---

## 1. What this gate required, and how it was satisfied

§17 demands that fifteen failure shapes be *tested*, and forbids substitutes: no
mocked administrative behaviour, no fabricated "unavailable dependency" tests,
fault injection must leave the infrastructure restored, and the audit chain must
be re-verified afterwards.

Everything below was produced by running the real FastAPI application under
uvicorn against the real PostgreSQL 15 + PostGIS + pgvector container with
`AUTH_MODE=enforcing`, and by stopping/starting the real test containers.

Two tracks:

| Track | Method | Result |
|---|---|---|
| §14 regression re-run after the fix in §4 | `pytest` against `pofa_test` (`-p no:randomly`) | 16 targeted + 152 regression (1 pre-existing skip) + 77 slow suites, 0 failures |
| Live hardening probe | Standalone harness: 12 sections, 162 assertions, real contention, real outages, injected audit failure | **162 / 162 PASS** |

One genuine production defect was found at this gate (**F-SE-01**, audit
integrity under concurrency), fixed, and re-verified — §4. No test, assertion or
permission was weakened to reach green (§8 records every harness correction).

---

## 2. Environment (measured, not assumed)

Printed by the probe itself on every run:

```
env: database=pofa_test revision=o5p6q7r8s025
     server=15.13 (Debian 15.13-1.pgdg120+1) auth_mode=enforcing
     roles=['ADMINISTRATOR', 'API_CLIENT', 'CITIZEN', 'FIELD_OFFICER', 'REVIEWER', 'SUPERVISOR']
```

```
$ docker ps --format '{{.Names}} | {{.Status}}'
pofa_db     Up  (postgis 3.4.2 + pgvector 0.7.4, :5432)
pofa_redis  Up  (:6379)
pofa_minio  Up  (:9000)

$ backend/.venv312_clean/Scripts/python.exe -V
Python 3.12.0  (AMD64)
```

`TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test`
is exported for every pytest command; the standalone harness sets `DATABASE_URL`
explicitly and prints `current_database()` per run.

**Environment incident (recorded, not hidden).** Between probe runs 7 and 8 the
host was suspended for ~17 h and the Docker Desktop daemon was not running when
the next run started, so the run died immediately with
`psycopg2.OperationalError: connection refused` and
`containers up after restoration: []`. Classification: **environment**, not
production, not test. Recovery was verified before resuming: the engine was
started, all three containers came back under their restart policies, and
`pofa_test` was re-checked (revision `o5p6q7r8s025`, zero `stageE` residue,
67 GLOBAL assignments, ledger 14,075 rows). Nothing was patched around: the
failed run is reported as a failed run (§8, run table).

---

## 3. Commands executed (verbatim, reproducible)

```bash
export TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test
PY=backend/.venv312_clean/Scripts/python.exe

# targeted suite, then the §14 regression list verbatim, then the slow suites
"$PY" -m pytest tests/integration/test_be025_admin_control_plane.py -q -p no:randomly
for S in tests/unit/test_authorization.py tests/unit/test_integration.py \
         tests/unit/test_migrations.py tests/unit/test_audit_ledger.py \
         tests/unit/test_audit_guard.py tests/unit/test_preflight.py \
         tests/unit/test_test_target.py tests/integration/test_authorization.py \
         tests/integration/test_be025_admin_control_plane.py \
         tests/integration/test_audit_ledger.py tests/integration/test_be007_contracts.py; do
  "$PY" -m pytest "$S" -q -p no:randomly
done
"$PY" -m pytest tests/integration/test_governance.py tests/integration/test_publication.py \
  tests/integration/test_retention.py tests/integration/test_review_case.py -q

# live hardening probe (starts its own uvicorn on :8155, enforcing auth, pofa_test)
backend/.venv312_clean/Scripts/python.exe -u "$TEMP/poa_stageE/probe_e2.py"

# contention measurement, run before and after the F-SE-01 fix
backend/.venv312_clean/Scripts/python.exe -u "$TEMP/poa_stageE/diag3.py"

# independent post-fault verification (read-only)
DATABASE_URL=$TEST_DATABASE_URL backend/.venv312_clean/Scripts/python.exe \
  "$TEMP/poa_stageE/postverify.py"
```

The probe, diagnostics and launcher scripts are deliberately outside the
repository (`$TEMP/poa_stageE/`) and are **not** part of the BE-025 commit.

---

## 4. Production defect found and fixed at this gate

### F-SE-01 — audited administrative mutations read their target row without a lock

**FOUND.** Contention bursts (same requests, same build, before the fix —
`diag3b.out`, and the E5/E6 evidence in probe run 5) produced ledger rows that
described transitions that had not happened:

| Shape | Measured before the fix |
|---|---|
| 8 concurrent `PATCH /users/{id}/status` | 6 events, all 8 requests 200; **three events claimed `before=ACTIVE`** while another writer had already committed `SUSPENDED`/`DISABLED`; delta chain broken (`chained=False`) |
| 4 concurrent *identical* `PATCH /projects/{id}/scope` | **4 `PROJECT_SCOPE_CHANGED` events for one real change** |
| 4 concurrent `DELETE …/roles/{id}` on one assignment | **4 × HTTP 204** and **4 `ROLE_REVOKED` events** for a row that existed once — three phantom revocations of an already-deleted assignment |
| 2 concurrent *conflicting* scope moves | 1 event whose `before` did not match the committed predecessor |

Why: every audited mutation in `backend/services/authorization.py` computes a
`before`/`after` delta from an unlocked `db.query(...).one_or_none()`. Under
`READ COMMITTED` two writers read the same predecessor, both report it, both
commit, and a revocation can delete a row a concurrent revocation already
removed while still answering "success" and auditing it. The hash chain itself
never broke (`verify_chain()` stayed valid throughout — sequence and hashes were
consistent); the corruption was in the *content* of the events, which is exactly
what an audit ledger exists to be right about. Stage B §8 had specified
"concurrent revoke × revoke … exactly one succeeds" and "no partial admin
mutations", so this was a defect against the accepted design, not a new
requirement.

**FIXED.** One helper in `backend/services/authorization.py`, applied to the six
audited mutation reads — the same `with_for_update()` convention already used by
`backend/repositories/{governance,publication,dispute,correction,fusion}.py` and
`backend/services/retention.py`:

```python
def _lock_row(db: Session, model, row_id: str):
    """Read one row under a row lock for an audited mutation.

    Every audited mutation here computes a ``before``/``after`` delta, so the
    read must serialize with concurrent writers to the same row: an unlocked
    read lets two writers both report the same predecessor, lets a writer audit
    a transition another transaction already committed, and lets a revocation
    delete a row that a concurrent revocation already removed.
    """
    return (db.query(model).filter(model.id == row_id)
            .with_for_update().one_or_none())
```

Applied at `revoke_assignment` (:506), `update_organization` (:550),
`update_unit` (:577), `set_user_status` (:614), `change_project_scope` (:683),
`change_project_owner` (:752). Creation paths were left alone: their
idempotency comes from unique constraints and was already measured correct.
Scope: one production file, no new dependency, no schema or migration change, no
permission changed, no endpoint or schema touched, ledger rows still
append-only, BE-023 audit guard intact.

**VERIFIED.** Identical bursts after the fix (`diag3c.out`, then probe runs
6 → 10 on the live server):

| Shape | Measured after the fix |
|---|---|
| 8 concurrent status writes | `events=7 accepted=8`, `chained=True`, `self_transitions=0`, persisted status equals the last committed delta, sequence numbers strictly increasing (14323…14327) |
| 4 concurrent identical scope sets | `events=1` — "four concurrent identical scope sets audit exactly one transition" |
| 4 concurrent revocations of one assignment | `codes=[204, 404, 404, 404]`, `ROLE_REVOKED=1`, row gone — "no phantom ROLE_REVOKED is written for a lost revocation race" |
| 2 conflicting scope moves | `codes=[200, 200]`, one consistent final scope, `events=1`, deltas chain from the committed predecessor |
| 2 live admins revoking each other | `codes=[204, 409]`, `remaining=1`, exactly one `ROLE_REVOKED` — the last-admin guard genuinely engaged |

The 7-of-8 result is correct, not a loss: `set_user_status` returns without
auditing when the requested status already equals the stored one
(`authorization.py:617-618`), and under serialization one of the eight writes
becomes that no-op. A deterministic sequential control in the same section
proves the accounting: three serialized writes append exactly three events
(`before=7 after=10`).

---

## 5. Re-verification after the fix (§14 gate rule: re-run everything)

Run against the post-fix build. Every suite exited 0.

| Suite | Result | Duration |
|---|---|---|
| `tests/integration/test_be025_admin_control_plane.py` | 16 passed | 43.75 s |
| `tests/unit/test_authorization.py` | 17 passed | 1.57 s |
| `tests/unit/test_integration.py` | 19 passed | 1.58 s |
| `tests/unit/test_migrations.py` | 8 passed | 0.75 s |
| `tests/unit/test_audit_ledger.py` | 10 passed | 1.48 s |
| `tests/unit/test_audit_guard.py` | 20 passed | 3.16 s |
| `tests/unit/test_preflight.py` | 23 passed, 1 skipped | 0.15 s |
| `tests/unit/test_test_target.py` | 9 passed | 0.08 s |
| `tests/integration/test_authorization.py` | 17 passed | 55.93 s |
| `tests/integration/test_be025_admin_control_plane.py` (in-list re-run) | 16 passed | 39.83 s |
| `tests/integration/test_audit_ledger.py` | 10 passed | 52.70 s |
| `tests/integration/test_be007_contracts.py` | 3 passed | 13.57 s |
| governance + publication + retention + review-case | 77 passed | 311.42 s |

**No existing authorization test failed at this gate**, so §14's stop-and-classify
rule was never triggered: nothing in `tests/` was edited during Stage E.
(The `test_preflight.py` skip is the pre-existing BE-023 skip when the optional
ML target is absent — unchanged from Stage D.)

---

## 6. Live hardening probe — 162 checks, 0 failures

`probe_e10.log`, 12 sections plus a final integrity section. Timings are from
the shared keep-alive harness on loopback; the DB was at 1,369 users and the
ledger at ~14,400 events during the run.

**E1 — malformed IDs (143 probes over every UUID-bearing admin route).**
`5xx=[]`, `accepted=[]`, `p50=0.035 s max=0.239 s` (no hang). Per-value results:
`not-a-uuid`, `1`, `null`, `NaN`, `-1`, `00000000-…-000g`, `'); DROP TABLE
users; --`, `%27%20OR%201%3D1`, full-width `１２３４５６７８９０`, a 200-char
overlong UUID, `…40000 extra`, `*` → **422**; `550e8400-…-446655440000/../etc/passwd`
→ **404** (well-formed prefix, path resolved to no resource). `users=1354`,
`assignments=77` survived unchanged; a SQL-shaped email was stored literally
(`201 x'); drop table users;--@stagee.example.com`) and `users` still existed.

**E2 — malformed / oversized / adversarial payloads (20 checks).** Missing
`code`, blank name, whitespace-only code, 257-char name, 129-char code, non-object
body, invalid enum status, empty status patch, unknown/missing `scope_type`,
2000-entry scope list, unparseable body → **422**; 256-char name → **201** at the
boundary. All six scope-matrix violation shapes refused with 422, `matrix=0`,
and `assignments` unchanged (`before=77 after=77`). A 2 MB JSON body returned
**201 in 0.14 s** with `rows_delta=1`; the undeclared oversized field never
reached the schema (`organization columns=['code','created_at','id','name',
'status','updated_at']`) nor the response echo (`keys=['code','id','name','status']`).

**E3 — missing resources, revoked access, stale authority.** Every absent
resource → 404 (never 500, never 200). A freshly granted organization admin reads
its own org (200) and cannot see a foreign one (404). Revocation takes effect on
the very next request (`revoke=204 write=403 list=403`) with exactly one
`ROLE_REVOKED`; revoking again is a deterministic 404; re-granting restores
authority immediately (`regrant=201 read=200`). A refused cross-org write left
**0** `ORGANIZATION_UPDATED` events.

**E4 — pagination boundaries.** `total=1356`, `limit` cap 100 honoured, default
50 when omitted, boundary map `{'0':422,'-1':422,'1':200,'100':200,'101':422,
'1000':422,'abc':422,'1000000000':422,'1.5':422}`; offsets `-1`/`abc` → 422,
`1356`/`1856` → empty page carrying `total=1356`. Paging is lossless and stable
(`walked=150 expected=150 unique=150`, overlapping windows agree:
`page2_matches=True cap100_matches=True`). Catalogue routes accept their
documented bound and reject beyond it; a scoped admin's page and total cover only
its own organization; cross-org unit listing is 404 with no count oracle.

**E5 — duplicates and contention (28 checks).** 8-way duplicate assignment →
`{200:7, 201:1}`, one row, one `ROLE_ASSIGNED`. 6-way same-code organization and
unit → `{201:1, 422:5}`, one row, losers appended nothing. Concurrent status
writes: see §4. Conflicting and identical scope moves: see §4. Revocation race:
see §4. An unscoped project stays invisible (404) to a non-GLOBAL admin. No
transport loss (`[]`).

**E6 — last-GLOBAL-administrator contention (destructive, restored).** Four-way
revoke of one assignment → `[204,404,404,404]`, one `ROLE_REVOKED`. With exactly
two live GLOBAL administrators isolated by the harness, mutual revocation →
`[204, 409]`, `remaining=1`, one event. As the sole administrator, self-revoke,
self-disable and self-suspend are **all 409** and write **no** audit event; the
last administrator retains its grant and can still administer ordinary users. The
68-row GLOBAL snapshot was restored (`restored=69 snapshot=68`) and GLOBAL
authority verified working again.

**E7 — unauthorized, cross-organization, escalation (14 checks).** 55
admin-route attempts across five non-admin principals: **zero** succeeded, all
403, no 5xx. Ten concurrent cross-org writes stayed a uniform 404 and left the
foreign organization untouched. Self-promotion to GLOBAL → 403; granting
ADMINISTRATOR without GLOBAL `role.manage` → 403; granting into a foreign
organization → 404 (invisible, not enumerable). Anonymous, malformed and
non-bearer credentials → 401. A **suspended** administrator and a **disabled**
GLOBAL administrator are both denied (`401 {"detail":"Invalid credentials"}`) —
status is re-read per request, so a revoked or suspended admin cannot act.
`GET /me` still returns the caller's own principal (200, matching id,
`principal_type=USER`) with exactly the documented `PrincipalResponse` keys and
no `username` leak.

**E8 — partial transaction failure / audit failure (in-process injection).**
With the audit boundary made to raise, `create_organization`, `assign_role` and
`set_user_status` each raised `RuntimeError` and rolled back completely: **0**
organization rows, **0** assignment rows, status `ACTIVE -> ACTIVE`, and the
ledger count unchanged (`before=14358 after=14358`) — domain mutation and audit
event commit or roll back in the same transaction. Removing the fault restored
normal serving (201) and auditing resumed for real writes (1 event). No
audit-mutating route exists in the served OpenAPI surface (`[]`).
**Chain re-verified after injection: valid, 14,359 events.**

**E9 — dependency outages (real `docker stop` / `docker start`).**
Redis down: `GET /ready` → **503** `{"status":"unhealthy", …}`, authenticated
admin reads unaffected (200), authorization not weakened (403 / 401 — no bypass
appears), an admin write still committed fully (201, 1 row) because Redis is not
on the administrative write path; restored → **200 healthy**. MinIO down: org and
role writes both 201 (object storage is not on this path). **PostgreSQL down:**
three admin writes → `[401, 401, 401]` — fail-closed, because authenticating a
principal requires the DB; **no write reported success and no 5xx was produced**,
and **0** organization rows were left behind. The same server process recovered
after `docker start pofa_db` in **2.2 s** (`pool_pre_ping`), revision unchanged,
**chain valid over 14,362 events**, the next admin write committed and was
audited exactly once, and all three containers were up again
(`['pofa_db','pofa_minio','pofa_redis']`).

**E10 — retry behaviour.** Repeated identical assignment `201,200,200` with one
row and one `ROLE_ASSIGNED`; retried duplicate organization create still yields
one organization; a refused 404 retries as a deterministic 404;
`PATCH organizations/{id}` twice with the same body → `200, 200` and the event
count moved `1 -> 2 -> 2`: the real change audited once, the identical retry
audited **nothing**, and **0** ledger rows for that resource carry
`before = after`; revocation retry `204, 404` with one `ROLE_REVOKED`.

**E11 — limits and boundary sizes.** 256-char name + 128-char code → **201**;
257 chars → 422 before touching the DB; unicode + emoji + bidi-marker display name
stored intact; embedded NUL/control characters → 422 (refused, not 5xx, not
corruptly stored); 30 sequential unit creates under one organization all 201 and
all visible (`total=30 items=30`); `offset=1000000` → empty page with the true
total; `organization_id: 2**40` and explicit nulls → 422; scope matrix `0`
violations.

**E12 — measured latency (recorded, not optimized; each sample must also return
the expected status).**

| Path | p50 | p95 | max | n | codes |
|---|---|---|---|---|---|
| `GET /users?limit=100` | 58.5 ms | 61.6 ms | 61.6 ms | 20 | `[200]` |
| `GET /organizations` (scoped admin) | 45.7 ms | 49.0 ms | 49.0 ms | 20 | `[200]` |
| `GET /users/{id}` | 35.9 ms | 43.6 ms | 43.6 ms | 20 | `[200]` |
| `POST /users/{id}/roles` (idempotent hit) | 70.3 ms | 79.2 ms | 79.2 ms | 20 | `[200]` |
| last-admin guard refusal (advisory lock) | 47.8 ms | 53.2 ms | 53.2 ms | 20 | `[409]` |

The guard row is honest contention on the advisory lock: the harness temporarily
reduced the plane to one administrator (`kept=1 removed=69`), all 20 attempts
returned 409, none disabled it, none wrote an event (`events=0->0`), and all 70
GLOBAL assignments were restored and re-verified working. 12-way contended
idempotent assignment: `wall=0.49 s`, `histogram={200: 12}`, per-request
40.8 ms against a 69.6 ms sequential median, one assignment row at the end —
contention is not pathological. Read-only chain verification over the whole
14,400-event ledger: **valid in 3,857 ms**.

**E-final.** Chain valid (`first=1 last=14400 failures=[]`); **no audit row lost**
(`rows=14400 == maxSeq=14400`) across every fault injected in this gate;
scope matrix intact (`violations=0`); no audit payload or metadata matches
`password|secret|access_key|apikey`.

---

## 7. §17 coverage matrix

| §17 required test | Where proven |
|---|---|
| malformed IDs | E1 (143 probes, all UUID-bearing routes) |
| malformed payloads | E2 (20 checks) + E11 (boundary sizes, unicode, control chars) |
| missing resources | E3 (uniform 404, no 5xx, no success) |
| duplicate operations | E5 (assignment/org/unit), E10 (repeated creates, retried 404) |
| concurrent operations | E5, E6, E12 (8×, 6×, 4×, 2×, 10×, 12× bursts) + §4 before/after |
| unauthorized operations | E7 (55 route attempts, 5 principals; 401/403/404/422 only) |
| cross-organization access | E3, E4, E7 (404 indistinguishability, no count oracle, uniform under concurrency) |
| privilege escalation | E7 (self-promote, ADMINISTRATOR without GLOBAL, grant into foreign org), E2 (extra fields ignored) |
| revoked access | E3 (next-request effect, re-grant), E7 (suspended/disabled admin) |
| partial transaction failures | E8 (three service paths, all-or-nothing), E9 (DB outage leaves 0 rows) |
| audit failures | E8 (injected audit-store failure; ledger unchanged; chain re-verified) |
| database failure (safely testable) | E9 (real `docker stop pofa_db`, fail-closed 401, pool recovery 2.2 s) |
| rollback | E8 (`s.rollback()` verified by unchanged row counts and unchanged ledger) |
| retry behaviour | E10 (idempotent 201→200, deterministic 404, no-op update audits nothing) |
| pagination boundary cases | E4, E11 (limit 0/1/100/101/1000/non-numeric, offset beyond total, lossless paging) |
| "restore infrastructure afterward" | §10 (containers restored after every fault; residue 0) |
| "re-verify the audit chain after fault injection" | E8, E9, E12, E-final + §10 independent `verify_chain()` |
| "do not fake unavailable dependency tests" | No simulated outages: Redis/MinIO/PostgreSQL were physically stopped and started; no `Mock`, no skipped substitute |

---

## 8. Harness defects found and fixed (classification)

Every failure at this gate was first classified before anything changed. §14's
rule ("do not weaken the test to make it pass") was honoured: no shipped test was
edited, and each probe expectation was replaced by an invariant that is *equal or
stronger* — usually with a deterministic serialized control added beside it.

| Probe run | Outcome | Failures and classification |
|---|---|---|
| run 3 | aborted | **Operational (mine):** I mistook a notification for a crash and killed the run's own uvicorn; the harness's `finally` teardown still left 0 residue |
| run 4 | FATAL | **Test:** `UnicodeEncodeError` — Windows cp1252 console cannot print the full-width/bidi evidence; fixed with `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` |
| run 5 | 87 checks / 70 pass | **Test:** `code()` returned −1 for every `httpx.Response`, so all eight bursts looked like transport failures; per-request clients caused socket churn. Same run produced the genuine **F-SE-01** evidence |
| diag2 | — | **Test:** confirmed the `code()` defect against a live server (responses were `200 OK`) |
| diag3b / diag3c | — | F-SE-01 **before / after** measurements on identical bursts |
| run 6 | 101 / 97 | **Test** ×3: `UUID`-vs-`str` comparison made a correct single-scope result look torn; `PrincipalResponse` has no `username`, so a correct `/me` looked like a denial; an absolute lifetime event count on a shared organization ignored an earlier legitimate rename. **Test** ×1 FATAL: the E8 subject was created *inside* the injected-fault window |
| run 7 | not started | **Environment/operational (mine):** `MSYS_NO_PATHCONV` broke path conversion; no DB contact |
| (incident) | — | **Environment:** Docker daemon not running after host suspension; restored and verified (§2) |
| run 8 | 154 / 148 | **Test** ×6: readiness probed `/health/ready` (real route is `/ready`); a DB outage demanded 5xx although 401 fail-closed is correct; the E10 absolute count (again); the E6 mutual race left a **third** live administrator so both 204s were legitimate; E12 latency asserted only timing (so a 401 storm "passed"); the E12 "guard refusal" item was mislabelled — disabling one of 67 admins is *allowed*, and it disabled the probe's own actor |
| run 9 | 161 / 160 | **Test:** the boundary organization's code was the constant `'S'×128`, outside the `STGE%` teardown filter, so run 8 left it behind and run 9's identical create was correctly answered **422 duplicate code**. Fixed twice over: per-run unique 128-char code, and teardown now deletes every tracked id (its pattern sweep became a second pass) |
| run 10 | **162 / 162 PASS** | — |

The residue from run 8 exposed by run 9 was deleted explicitly (one
`organizations` row, verified to have no unit/project/assignment references);
**no audit row was touched** — the ledger is append-only and still is.

---

## 9. Findings preserved, not fixed

Recorded as accepted behaviour of the milestone; none is a security failure and
fixing them is outside §17's scope:

1. **Duplicate organization/unit code → 422, not 409.** `Organization code
   already exists: …` is raised as a `ValueError` and mapped to 422, while the
   last-administrator conflict is 409. Deterministic and documented in
   `openapi.json`; changing the code would alter a shipped contract, so it is
   preserved.
2. **No application-wide request-body size cap.** A 2 MB JSON body is accepted
   (0.14 s, one row) and Pydantic silently drops undeclared fields, so the risk
   is schema widening — measured absent. Bounding the body is a platform-wide
   decision, not a BE-025 one.
3. **A PostgreSQL outage surfaces as 401, not 503.** Principal resolution reads
   the user row, so an unavailable DB authenticates as "Invalid credentials".
   Fail-closed and never a false success; distinguishing 503 would change
   BE-016 authentication semantics.
4. **Pre-existing logging defect (`BE-001` lineage).** Every audited write emits
   `--- Logging error --- ValueError: Formatting field not found in record:
   'request_id'` in the server log. Unrelated to BE-025, no data loss, no
   behavior change.
5. **Starlette deprecation warning** for `HTTP_422_UNPROCESSABLE_ENTITY`
   (`backend/security/authorization.py:84`), emitted by pre-existing code.
6. **Chain verification cost.** Full read-only `verify_chain()` over 14,400
   events takes ~3.9 s; it is an operator path, not a request path.
7. **Pre-existing `pofa_test` rows** from the Stage D probe
   (`org-life-*`, `org-moveA/B-*`, `org-client-*`, 9 organizations, created
   2026-09-28) were left as-is: they predate this gate and only shift list
   totals, which the probe reads dynamically.

---

## 10. Restoration, isolation and side-effect evidence

Infrastructure restored after fault injection (E9 stops real containers):

```
containers up after restoration: ['pofa_db', 'pofa_minio', 'pofa_redis']
$ docker ps --format '{{.Names}} | {{.Status}}'   # after the run
pofa_db | Up 29 seconds   pofa_redis | Up 35 seconds   pofa_minio | Up 34 seconds
```

Teardown of the probe's own rows (id pass + pattern pass) — every count zero,
GLOBAL administrator baseline preserved, and **no delete ever issued against
`audit_ledger_events`**:

```
teardown tracked api_clients              deleted=0
teardown tracked user_role_assignments    deleted=10
teardown tracked projects                 deleted=3
teardown tracked users                    deleted=23
teardown tracked organizational_units     deleted=31
teardown tracked organizations            deleted=13
teardown remaining users/orgs/units/projects/clients = 0
teardown remaining GLOBAL assignments = 67
```

Independent read-only verification after all fault injection
(`postverify.py`):

```
database: pofa_test        revision: o5p6q7r8s025
residue orgs/units/users/projects/clients: 0 0 0 0 0
GLOBAL assignments: 67       ledger rows/maxseq: (14400, 14400)
matrix violations: 0
chain valid: True  checked: 14400  first: 1  last: 14400  failures: []
```

Isolation — `pofa_dev` untouched, identical before and after Stage E:

```
pofa_dev | n4o5p6q7r022 | users=1094 | ledger=6016 | maxSeq=6052 | stageE rows=0
```

`tests/conftest.py` republishes `TEST_DATABASE_URL` as `DATABASE_URL` and refuses
to run without it; the standalone harnesses set `DATABASE_URL` explicitly and
print `current_database()` on every run.

Files changed at this gate: **one production file**
(`backend/services/authorization.py` — `_lock_row` and its six call sites) and
no test file. Everything else in the working tree is Stage C/D work still
uncommitted; the probe, diagnostics and launchers stayed outside the repository.

---

## 11. Stage E gate decision

**Stage E: PASS.**

- §17's fifteen hardening categories were each exercised against live code with
  measured evidence (§6, §7).
- One production defect (F-SE-01, concurrent audited mutations writing false
  deltas, redundant no-op transitions and phantom `ROLE_REVOKED` rows) is
  recorded **FOUND → FIXED → VERIFIED** with before/after measurements (§4).
- Full §14 regression re-run after the fix: every suite green, no shipped test
  modified, no existing authorization test failed (§5, §8).
- Fault injection left the infrastructure restored, the ledger append-only and
  intact — chain valid over 14,400 events with `rows == max sequence` and zero
  residue (§10).
- No hidden administrator bypass, no weakened permission, no fake admin
  behaviour, and no unauthorized operation succeeded anywhere in the run.

Awaiting approval before starting **Stage F** (§18 full verification matrix and
`docs/BE-025 Final Acceptance Report.md`).
