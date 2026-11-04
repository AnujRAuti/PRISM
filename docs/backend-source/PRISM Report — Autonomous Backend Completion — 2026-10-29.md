# PRISM — Autonomous Production-Grade Backend Completion: Final Evidence Report

Date: 2026-10-29 · Branch: `Backend` · Mission brief: PRISM (supersedes M-BE-01)
Every number below was measured in this session. Nothing is inferred from an earlier report.

---

## 1. Verdict

**NOT CLEARED FOR PRODUCTION DEPLOYMENT.**

Two sentences on why, because "not cleared" here is narrow and specific:

* **The backend code is complete and verified.** All work that could be done without an
  owner-only credential or a shared-infrastructure change is finished, tested, and committed.
* **Production is not ready because two things outside the code have not happened:** no
  token issued by the real identity provider has ever been verified end-to-end (it needs a
  real reviewer account, which only the owner can create), and nothing has been deployed —
  the Azure VM is still running an older checkout, an older image, and a database that is one
  migration behind with **zero user rows**.

Per the brief's instruction ("if a production gate fails, stop safely and report the exact
measured blocker rather than pretending the deployment passed"), the release was **not**
attempted. No production data was put at risk. No untested code was deployed.

| Gate | Status | Measured reason |
|---|---|---|
| Production config fails closed | **PASS** | 13/13 boot matrix cases, incl. every forbidden posture refused with a named reason |
| OIDC issuer is the intended project | **PASS** | live preflight: `project_identity` = `tuaeujvuuanadqvykugw` |
| JWKS publishes a usable key | **PASS** | exactly 1 key, EC P-256 / ES256, `kid=ab0ac6ae-93be-441c-9196-7b2fade15af0` |
| Algorithm configured matches provider | **PASS for ES256 / FAIL for RS256** | `AUTH_OIDC_ALGORITHMS=RS256` refuses at `usable_keys`: "no published key is usable under RS256" |
| Container boots with the six OIDC values | **PASS** | 14/14 checks, exit 0, against the release image |
| Token **accept** path with a real token | **BLOCKED** | no provider-issued token exists to test with; project has 0 users on `poa_prod` |
| Schema builds from an empty database | **PASS** | 10/10 proof, 0 → 73 base tables |
| Release image carries exactly the committed code | **PASS** | 135/135 backend modules byte-identical |
| Full test suite | **PASS** | 1095 passed / 1 skipped / 0 failed |
| Migrated production database | **NOT DONE** | owner-gated; `poa_prod` still at `v2w3x4y5z032` |
| Deployed and reachable over HTTPS | **NOT DONE** | no domain, no certificate, ports 80/443 closed |

---

## 2. Root causes found and fixed

Nine real defects. Each row says what was wrong, why it mattered, and what proves the fix.

| # | Defect | Root cause | Fix | Verification |
|---|---|---|---|---|
| 1 | Production could boot with placeholder OIDC values | The shipped defaults (`example-issuer.invalid`, a placeholder JWKS URL) passed syntactic validation, so a production process could start and then reject every real reviewer | `backend/core/config.py` validators now fail closed in production on: OIDC disabled, dev tokens on, placeholder issuer/JWKS, issuer↔JWKS authority mismatch, wildcard CORS, missing required secrets, dev-mode auth | `Scratch/prism/config_boot_matrix.json`: **13/13**, each refusal returns exit code 3 naming the exact reason; 22 tests in `tests/unit/test_configuration_and_logging.py` |
| 2 | "Config is valid" was not the same as "it is *our* project" | Nothing checked that the issuer belongs to the Supabase project the deployment actually signs reviewers into | New `backend/security/oidc_preflight.py` + CLI: fetches `/.well-known/openid-configuration` and the live JWKS, derives the project ref from the issuer host, compares to `--expected-project-ref`, and rejects symmetric/foreign-algorithm keys | **16** tests in `tests/unit/test_oidc_preflight.py`; durable gate artifacts `oidc_gate_live_ES256.json` (10 PASS + 1 BLOCKED) and `oidc_gate_live_RS256.json` (**FAIL** at `usable_keys`) |
| 3 | Evidence bytes were reachable with only the base read permission | The sensitive-evidence read path checked project scope but not the additional `evidence:sensitive` permission, so an assigned ordinary reviewer could fetch sensitive originals | Enforced the additional permission on the byte path; a sensitive reader *outside* the assignment is still refused | `tests/integration/test_prism2_admin_write_refusals.py:198` and `:230` (6 tests total in the file) |
| 4 | Disabled/suspended principals and a dead provider were not refused at the HTTP layer | Principal-state checks were only exercised as isolated helper functions; an unreachable JWKS surfaced as a 500 | Disabled user token refused, disabled API-client credential refused, unreachable key set answers **401, not 500**, and all three write nothing | `tests/integration/test_prism2_principal_state.py` (**3** tests), each asserting `before == after` on row counts |
| 5 | Client-supplied identity could grant itself rights | Naming another person in a request body was treated as sufficient context | Actor is derived from the verified principal; a request that names a claimant grants that person nothing | `test_naming_a_claimant_grants_that_person_nothing` (`:334`) plus the existing attribution suites |
| 6 | Repository carried database dumps and secret files | `1c2eb039` committed **5 `pofa_dev` dumps** (`Scratch/be029/backups/*`, `be033`, `be034`, `be035`) and **2 `secrets.env`** files, plus a broken submodule pointer and a stale worktree registration | PRISM-4 untracked them and repaired the submodule/worktree state (`5d960086`) | `git ls-tree -r HEAD` now matches **0** for `*.dump` / `secrets.env`. **Still open:** the blobs remain reachable in local history — see §3 and §9 |
| 7 | **The production image was being built with database dumps and secrets inside it** | `.dockerignore` had no rule for `Scratch/`, `frontend/`, or `docs/`, and the Dockerfile does `COPY . .` — so the whole repository was sent as build context and baked into `/app`. Measured in the abandoned build: `/app/Scratch` = **792 MB, 2,755 files**, containing 5 `pofa_dev` dumps, 2 `secrets.env`, and a saved image tar. The build also never finished a layer (>10 min transferring context) | `.dockerignore` now excludes `Scratch/`, `frontend/`, `docs/`, `node_modules/`, `*.tar`, `*.dump` (`54e33b20`). The contaminated tag was untaged and deleted so it cannot be `docker save`d onto a server | Rebuild completed: context **14.59 MB**, image 697,454,469 bytes, exit 0 (`prism5_image_build.out`); `poa-backend:mbe01-wt1` separately confirmed clean |
| 8 | A fresh production database had never been built from nothing | Every migration test ran against an already-migrated database, so a broken early revision could hide forever | `Scratch/prism/prism5_empty_db_proof.py` — creates a new database, proves it is empty, runs the chain to head, measures the result, checks drift, rebuilds a second schema and compares structural digests | **10/10**: 0 → 73 base tables, 765 columns, 320 constraints, 265 indexes, 859 routines, 1 non-internal trigger, extensions `plpgsql, postgis, vector`, catalogue seeded 6 roles / 70 permissions / 131 grants, no autogenerate drift, all digests equal |
| 9 | The rollback contract was undocumented and untested | `downgrade base` is *refused by design* at the two append-only audit-vocabulary revisions; nothing pinned which revisions refuse, so a silent change would have turned "restore from backup" into a partial, half-applied rollback | `tests/unit/test_migrations.py` now walks every revision file and asserts the refusing set is **exactly** `v2w3x4y5z032` + `w3x4y5z6a033` | 9 tests; the empty-DB proof independently shows the refusal is atomic (rc=1, 73 tables still present, version still at head) |
| 10 | The verification harness itself was wrong in two ways | (a) `mbe01_oidc_boot.py` wrote its evidence to a directory that does not exist on this machine, so a **14/14 PASS run exited 1 having written nothing**; (b) a container exec returning no stdout crashed with `IndexError` instead of recording a failed check | Evidence path anchored to the script's own directory; `container_json()` retries and reports `rc`/stderr | Gate re-run clean: 14/14, **exit 0** (`prism5_boot_gate.out`), JSON evidence written |
| 11 | A believed blocker was the wrong diagnosis | "Port 22 is firewalled" had been recorded in the M-BE-01 report after six timeouts | PRISM-7 started the VM and re-measured: 22 answered in **0.62 s**. The cause was a **deallocated** VM, not ingress rules | `prism7_azure_probe.py` now measures reachability + an `github.com:443` egress control + live inventory + provider metadata + bind addresses in one read-only run |

---

## 3. Git result

* Branch `Backend`. **12 commits ahead of `origin/Backend`, none pushed.**
* Since `origin/Backend`: 570 files changed, +316,233 / −34.
* The mission's "approximately 540 changes" is resolved exactly. Commit `1c2eb039`
  ("backend completion #1") = **546 files, 312,624 insertions**, split **542 `Scratch/`,
  3 `frontend/`, 1 `backend/`** — i.e. it was almost entirely verification evidence, not
  application code. It also carried the 5 dumps and 2 `secrets.env` files (row 6 above),
  all removed from tracking in `5d960086`.
* `git branch -r --contains 1c2eb039` is empty: **that commit has never been pushed.**
* Commit chain this session: `c097ebf8` PRISM-1 → `1a313ce8` PRISM-2 → `a453ebb4` PRISM-3 →
  `5d960086` PRISM-4 → `10680fea` PRISM-5 (migrations) → `f5f5f197` PRISM-7 → `df38fbae`
  PRISM-6 → `54e33b20` PRISM-5 (build context) → `2f6529b4` PRISM-5 (image proof) → this report.
* No history was rewritten. No force-push. No shared branch touched. `pofa_dev` was not
  modified at all this session.

**The one thing to decide before any push:** `1c2eb039` is inside the unpushed range, so a
plain `git push` would upload `pofa_dev` dumps and two secret files to the remote — they stay
recoverable from history even though the files are no longer tracked. This is an owner
decision, and the options (§9) are deliberately left unexecuted.

---

## 4. Authentication result

**Enforcing posture, measured in a running container** (`poa-backend:prism-54e33b20`,
`AUTH_MODE=enforcing`, dev tokens off, the six `AUTH_OIDC_*` values set) — 14/14:

| Check | Result |
|---|---|
| Disposable schema reached release head | PASS `w3x4y5z6a033` |
| Boots with the six values, `/health` | PASS 200 `{"status":"ok"}` |
| `/ready` all dependency legs | PASS application/postgresql/redis/storage all healthy |
| Running process holds the six values | PASS enforcing, `dev_tokens=false` |
| Live JWKS reachable **from inside** the container | PASS indexes `ab0ac6ae-93be-441c-9196-7b2fade15af0` |
| Anonymous `/auth/me` | PASS 401 "Authentication required" |
| Development bearer token while provider enabled | PASS 401 |
| HS256 token | PASS 401 |
| Forged ES256 token **carrying the live kid** | PASS 401 |
| Unknown kid | PASS 401 |
| Wrong issuer | PASS 401 |
| Forged token `POST /projects` | PASS 401 — write refused |
| Nothing auto-provisioned | PASS users `before=0 after=0` |
| Refusals name distinct reasons | PASS `ALGORITHM_REFUSED=2, UNKNOWN_KEY_ID=2, TOKEN_REJECTED=6` |

The brief's §5 minimum coverage maps to real, non-vacuous tests (each asserts the row exists
and names the layer that refused it):

| Required case | Where it is proven |
|---|---|
| Anonymous refused | boot gate + `tests/integration/test_stage02_context_route_authz.py` |
| Invalid tokens refused | 5 token variants above; `test_stage02_oidc_verification.py` (19 tests) |
| No-permission denied | `test_prism2_admin_write_refusals.py` |
| Disabled and suspended principals denied | `test_prism2_principal_state.py:236`, `:281` |
| Project-scoped access permits the assigned project | `test_stage02_reviewer_identity.py` (12 tests) |
| Reviewer cannot reach a project outside their assignment | `:230` + Stage 02-3b scope tests |
| Cross-org / cross-project denied | Stage 02-3b resource-scope tests |
| Client-supplied IDs/roles/scope cannot forge authorization | `:334`, `test_stage02_actor_attribution.py` |
| Error responses do not leak internals | `tests/unit/observability/test_redaction.py` |
| **Sensitive evidence endpoints enforce their additional permissions** | `:198`, `:230` (fixed this session) |
| API-level, not helper-level | all of the above are HTTP-level against a live app |

**The accept path is BLOCKED, not passing.** The backend has verified zero tokens actually
issued by Supabase, because no such token exists: signing one in requires a real reviewer
account, and `poa_prod` has 0 user rows. I deliberately did not substitute a locally minted
token for this check — a token I signed proves nothing about the provider's key.

---

## 5. Test evidence

| Measurement | Result |
|---|---|
| Armed full suite (`Scratch/deploy1/armfull.py suite`) on head `w3x4y5z6a033` | **1095 passed, 1 skipped, 0 failed in 1674.83 s** |
| Arithmetic check | 1094 at `5d960086` + the new rollback-contract test = 1095 |
| The single skip | Standing skip present in every armed run (933/1/0 and 1,040/1/0 both carried exactly 1); this run's log does not name it — no `-rs` flag was passed |
| Byte-compile every module | `compileall exit=0 files=252` |
| Lint | **Honest answer: no linter is configured.** `requirements-dev.txt` contains only `pytest==9.1.1`. Nothing was invented to fill this row |
| Migration chain | single head `w3x4y5z6a033`, 28 revisions, root `bb4bf0dd8fb7` |
| Rollback contract | 9 tests in `tests/unit/test_migrations.py`; empty-DB proof shows the refusal is atomic |
| From-empty schema | 10/10 with the structural counts in §2 row 8 |
| Focused new tests | PRISM-1 22, PRISM-2 6 + 9, PRISM-3 16 |
| Frontend | `node --test` 36/36 across 9 suites, 0 fail, 493 ms; `vite build` OK in 13.86 s; oxlint 25 warnings / **0 errors** |

Failures were never weakened to reach green. This session's recorded run is the clean one above.
Full-suite attempts earlier in the mission failed on environment artifacts (the container engine
restarting underneath the disposable stack); those were re-run rather than worked around, and the
committed suite files carry a 0-failure result.

---

## 6. Database result

| Database | Revision | Distance to head | Data | Identity |
|---|---|---|---|---|
| `pofa_test` (local, suite) | `w3x4y5z6a033` | **at head** | seeded catalogue, 0 rows changed by the head upgrade | `postgres` (local container) |
| `pofa_dev` (local dev) | `t0u1v2w3x030` | **3 behind** | 1,055 users, 6,023 ledger rows — **untouched this session, by instruction** | app path runs as `poa_runtime` (BE-035 cutover) |
| `poa_prod` (**the VM's** production DB) | `v2w3x4y5z032` | **1 behind** | **1 ledger row, 0 users** | measured read-only over SSH |

Schema-drift discipline held: the drift check on a freshly built schema reports only the two
known, documented Alembic `nulls_not_distinct` artifacts on
`user_role_assignments.uq_user_role_scoped`, suppressed by the reviewed named policy in
`backend/db/schema_drift_policy.py`. The baseline was not widened to make the check pass.

Rollback consequence, stated plainly: because `v2w3x4y5z032` and `w3x4y5z6a033` raise on
purpose in `downgrade()`, **rolling a release back is a restore-from-backup, never
`alembic downgrade`.** `poa_prod` has a verified off-host backup and a proven restore
(BE-032R/M-BE-01 work); `pofa_dev` likewise. No dumps are in Git, and the ones that were are
untracked.

---

## 7. Azure result

Measured 2026-10-29 against `poa-submission-vm` (`Scratch/prism/prism7_azure_probe.json`),
read-only, after starting the VM through the Portal (an action the brief pre-authorised):

* **Reachability:** port 22 **OPEN in 0.62 s**; 80 and 443 **TimeoutError**; egress control
  `github.com:443` OPEN, so a timeout on the target cannot be blamed from my own network.
  The earlier "SSH is firewalled" finding was wrong — the VM was deallocated.
* **What is actually running:** booted 05:12, kernel `7.0.0-1017-azure`, checkout **`1e8ecd1`
  on `Backend` with 1 dirty file**, image **`poa-backend:be037a`**, containers `pofa_api` +
  4 workers + `pofa_db` + `pofa_redis` + `pofa_minio` all Up (self-recovered after the reboot).
* **Ingress:** binds are `0.0.0.0:22`, `[::]:22`, `127.0.0.1:8000`, `127.0.0.1:45689`,
  resolver 53. **Only the API publishes, and only on loopback.** 5432/6379/9000/9001 are not
  exposed. That part is correct.
* **Production blockers found on the box:** `.env` has 15 keys and **zero `AUTH_OIDC_*` keys**
  — the deployed backend cannot verify a single provider token; `poa_prod` is 1 revision
  behind with **0 users**; `docker buildx` is not installed, so the image must arrive by
  `docker save`/`docker load`; anonymous `/health`, `/ready` **and `/metrics` all return 200**
  from the VM's own loopback (the code fix for `/metrics` is committed but **this box is not
  running it**).
* **Identity provider, fetched from inside the VM's network position:** issuer
  `https://tuaeujvuuanadqvykugw.supabase.co/auth/v1`, advertised algorithms
  `RS256,HS256,ES256`, but the JWKS publishes **exactly one key: EC P-256 / ES256**
  (`kid=ab0ac6ae-…`). That settles the brief's RS256-vs-ES256 discrepancy: **ES256 is the only
  algorithm this project can verify today**, and configuring RS256 makes the release gate fail.
* **Not verified and stated as such:** I could not re-capture the NSG rule set today (Portal
  blade timed out twice — §9). The NSG facts quoted in this report come from the committed
  runbook (`docs/M-BE-01 Release Runbook…`, NSG `poa-submission-vm-nsg`, priority 300 SSH TCP 22
  from the owner's `/32`, priority 310 HTTP-HTTPS) plus today's empirical port measurements.
  I opened no ports and changed no firewall rule.
* **No deployment was performed.** The candidate image was not transferred, `poa_prod` was not
  migrated, the VM's `.env` was not edited, and its stack was not restarted.

**Therefore: no public, HTTPS-served production backend exists.** There is no domain and no
certificate, and per the brief I will not call this production HTTPS.

---

## 8. Frontend result

* Worktree `Scratch/mbe01-frontend` at `f9e26d13`, branch `fullstack`, **clean** — the Supabase
  sign-in work is committed there (`d6aca7f4` feat(auth), `d1663c31` proxy → `127.0.0.1:8011`).
* The mock `dev-user-<username>` localStorage login is gone. The real path is in
  `frontend/src/services/api.js`: a request interceptor attaches the provider's own access
  token (refreshed near expiry), sends **no** `Authorization` header when there is no session,
  and a 401 **ends the session** instead of retrying with a stand-in identity. That is the
  behaviour the brief asked for, and it is what the 36 tests cover.
* Gate: 36/36 tests, production build succeeds, 25 lint warnings / 0 errors.
* **Three contract findings, none cosmetic:**
  1. **Evidence download cannot work as written**, for two independent reasons. `api.js:109`
     requests `responseType: 'blob'` while the endpoint returns JSON
     `{evidence_id, download_url}`; and the URL inside that JSON is presigned from
     `S3_ENDPOINT`, which `docker-compose.yml:30` sets to `http://minio:9000` — a
     docker-internal host on a port measured **unpublished** on the VM. Fixing the shape alone
     would still hand the browser an unresolvable host. This needs an architecture decision:
     stream the bytes through an authenticated backend endpoint, or proxy object storage
     publicly behind an allow-listed, expiring URL. I did not patch it, because the second
     option changes ingress.
  2. The mismatch is **latent, not live** — nothing in `src/` calls that download helper, so no
     user has hit it yet.
  3. The dev proxy target `127.0.0.1:8011` is **correct**, not stale — it is the port the
     disposable rehearsal API binds. A root-level `vite.config.js` committed at `f9e26d13` is
     0 bytes and meaningless (the app lives in `frontend/`); noted, not churned.
* **No frontend is deployed.** 80/443 time out and the only publishing container is the
  loopback API. Live browser sign-in against the real project is still **unverified** — it
  needs the reviewer account that the backend token test also needs.

---

## 9. Outstanding issues

**BLOCKED (needs an owner action, cannot be closed locally)**
1. **Real provider token accept path.** Needs a reviewer user to exist in the Supabase project
   and one real sign-in. Until then the ES256 gate's last line stays BLOCKED and no claim of
   working production authentication is made.
2. **Deploy to the VM** (checkout, `.env` OIDC keys, image transfer, `poa_prod` migration,
   restart). Shared-state changes; the brief forbids deploying untested code or risking
   production data to reach a green status.
3. **Domain + TLS + NSG truth.** No hostname and no certificate exist, so HTTPS cannot be
   claimed; and my fresh NSG capture failed (Portal timeouts), so the rule set is asserted from
   the runbook + empirical ports, not from a same-day artifact.

**Known gaps carried forward (not introduced this session, not silently closed)**
4. Presigned-download topology (§8 finding 1) — needs an owner architecture decision.
5. `pofa_dev` is 3 revisions behind head; running this code against it writes to tables whose
   vocabulary is not yet advanced there. Deliberately untouched.
6. Stage 02-4 quarantine lifecycle enforcement and read filter; Stage 02-5 idempotent retries
   + server-side evidence association; Stage 03-1 rate limiting / body caps / pool bounds /
   statement timeouts; Stage 03-2 dead-letter records; Stage 03-3 log rotation + object-backup
   proof. All still open task rows.
7. Owner-decision backlog from earlier milestones: OQ-3 (`external_subject` contract),
   TRUNCATE role policy, WSF-OBS-1 anchored-control polling, S8.
8. The image is 697 MB because the pinned ML stack (torch/transformers/ultralytics) is real,
   even though CPU-only torch already removed the multi-gigabyte CUDA layers. Cold-start time on
   a small VM is **unmeasured** — nothing was deployed to one.

**Git hazard requiring a decision before any push**
9. `1c2eb039`'s dumps and `secrets.env` are untracked at HEAD but **still reachable in local
   history** (the 1,778,724-byte dump blob is readable with `git cat-file`). Options, none
   executed: (a) never push that commit; (b) rebuild the unpushed range without it; (c) push
   and treat every credential in those files as burned and rotate. Any of these is the owner's
   call, and (b) is only safe precisely because nothing in the range has ever been pushed.

---

## 10. Operator checklist — one small step at a time

Plain language, backend/API only. **Never paste a secret into a chat window, a ticket, or a
screenshot.** Values that look like secrets belong in the VM's `.env` file, edited directly.

**Step 1 — Create one real reviewer (5 minutes, Supabase dashboard).**
Supabase → project `tuaeujvuuanadqvykugw` → **Authentication → Users → Add user** → email +
password (generate the password, save it in your password manager, do not send it to anyone).
This is the single action that unblocks the last BLOCKED test: it makes a token that *the
provider* signed.

**Step 2 — Tell me the account exists (no password needed).**
Say only "the reviewer user exists, email is `…`". I can then run the real-token accept/reject
matrix against the candidate backend and report whether signature, issuer, audience, expiry,
user mapping and authorization all verify — and prove the backend does **not** auto-provision
privileges.

**Step 3 — Give the VM its identity-provider settings (owner edits the file on the VM).**
SSH in, open `~/proof-of-action/.env`, and add these six lines. The first five are public
metadata about the project, not secrets; the sixth is a switch:
```
AUTH_OIDC_ENABLED=true
AUTH_OIDC_ISSUER=https://tuaeujvuuanadqvykugw.supabase.co/auth/v1
AUTH_OIDC_JWKS_URI=https://tuaeujvuuanadqvykugw.supabase.co/auth/v1/.well-known/jwks.json
AUTH_OIDC_AUDIENCE=authenticated
AUTH_OIDC_ALGORITHMS=ES256
AUTH_OIDC_IDENTITY_PROVIDER=supabase
```
Use ES256, not RS256 — the gate proves this project publishes an EC/ES256 key and refuses to
start under RS256. Then run the preflight **on the VM** and require verdict PASS:
`docker exec pofa_api python -m backend.security.oidc_preflight --expected-project-ref tuaeujvuuanadqvykugw`.

**Step 4 — Update the code on the VM (it is 1 commit-line behind and has 1 dirty file).**
First tell me what the dirty file is (`git status`, `git diff`) so we do not overwrite someone's
work. Then `git fetch` and check out the release commit — **only after decision #9 above is
made**, because the release range contains the commit with the dumps.

**Step 5 — Move the image (there is no `docker buildx` on the VM).**
Do not try to build there. From the build machine:
`docker save poa-backend:prism-54e33b20 -o <file>.tar`, transfer the tar, then
`docker load -i <file>.tar` on the VM. Keep that tar **outside** the repo — it is exactly the
kind of artifact that got committed before — and delete it after loading.

**Step 6 — Take a fresh backup of `poa_prod` before any schema change.**
`pg_dump` from inside `pofa_db`, copy the dump **off** the VM, checksum it, and prove a restore
into a throwaway database. Never `alembic downgrade` — two revisions refuse on purpose, so a
bad release is recovered by restoring this backup.

**Step 7 — Migrate, then restart, one service at a time.**
`docker compose run --rm migrate alembic upgrade head` (moves `poa_prod` from `v2w3x4y5z032` to
`w3x4y5z6a033` — this is the revision the new code requires before it will write), verify
`alembic_version`, then restart the API and the four workers. Re-measure: `/health`, `/ready`
all legs healthy, `/metrics` must now **refuse** an anonymous caller (on today's box it returns
200, which is the thing this step fixes).

**Step 8 — Decide how the app is reached from the internet.**
Until a domain and a valid certificate exist, the honest state is "reachable only over SSH
tunnel". Options: keep it private and tunnel; or buy/point a domain, issue a Let's Encrypt
certificate at a reverse proxy, and open **only** 80/443 while leaving 22 restricted to your
own `/32` (priority-300 rule already in the runbook). Do not open 5432, 6379, 9000 or 9001.
I will not call the deployment secure or HTTPS-complete before this step is done.

**Step 9 — Only after Step 8, verify from a browser.**
Sign in with the Step-1 reviewer account through the frontend and watch one real evidence
request end to end. This is the row I cannot do for you, and it stays unverified until then.

---

## 11. Evidence index (all committed)

| Artifact | What it proves |
|---|---|
| `Scratch/prism/config_boot_matrix.json` | 13/13 production fail-closed boot cases |
| `Scratch/prism/oidc_gate_live_ES256.json` / `_RS256.json` | live provider gate: 10 PASS + 1 BLOCKED / FAIL at `usable_keys` |
| `Scratch/prism/prism5_empty_db_proof.out` | 10/10 schema-from-nothing, atomic downgrade refusal, deterministic rebuild |
| `Scratch/prism/prism5_full_suite.out` | 1095 passed / 1 skipped / 0 failed |
| `Scratch/prism/prism5_compileall.out` | `exit=0 files=252` |
| `Scratch/prism/prism5_image_build.out` | build from `54e33b20`, context 14.59 MB, exit 0 |
| `Scratch/prism/prism5_image_source_digest.out` | image == HEAD backend, 135/135 |
| `Scratch/prism/prism5_boot_gate.out`, `Scratch/deploy1/mbe01_oidc_boot.json` | 14/14 container OIDC gate, exit 0 |
| `Scratch/prism/prism6_frontend_gate.out` | 36/36 tests, build OK, 0 lint errors |
| `Scratch/prism/prism7_azure_probe.{py,json,out}` | one-command read-only VM measurement |

Reproduce the whole release gate in four commands:
```
backend/.venv312_repro/Scripts/python.exe Scratch/prism/prism5_empty_db_proof.py
backend/.venv312_repro/Scripts/python.exe Scratch/deploy1/armfull.py suite
backend/.venv312_repro/Scripts/python.exe -m backend.security.oidc_preflight --expected-project-ref tuaeujvuuanadqvykugw
POA_IMAGE=poa-backend:prism-54e33b20 backend/.venv312_repro/Scripts/python.exe Scratch/deploy1/mbe01_oidc_boot.py run
```
