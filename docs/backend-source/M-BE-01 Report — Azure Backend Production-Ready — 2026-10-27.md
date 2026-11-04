# M-BE-01 Report — Azure Backend Production-Ready — 2026-10-27

Milestone deadline: 29 October 2026 18:00 IST. 30 October is reserved for frontend
integration, validation and submission.

## 1. Verdict

**The backend is NOT production-ready yet.**

Everything that could be measured against the exact release candidate was measured, on
this machine and on disposable infrastructure, and it passed: the candidate image is
built and byte-proven against the worktree, the complete armed test suite runs green at
the correct alembic head, the three P0 evidence-ingestion defects are closed with
regression tests, the whole production sequence (migrate → verify → swap → fail →
recover) is rehearsed end to end against a copy of the real production data, the reviewer
sign-in configuration is verified against the owner's live Supabase endpoints in a
container started in the production posture (§6A), and the frontend's mock login is gone —
replaced by real Supabase email/password with the real access token on every request, and
its own 36 passing tests (§7A).

Eleven of the nineteen criteria in §3 are **PASS**. Eight are **BLOCKED**, and they trace
to exactly two causes outside this machine:

1. **The production VM does not answer.** SSH to `172.198.77.149:22` timed out on six
   separate measurements during this session — the last one, after every other criterion was
   closed, was `ssh -o BatchMode=yes -o ConnectTimeout=12 azureuser@172.198.77.149` →
   `connect to host 172.198.77.149 port 22: Connection timed out`. No container registry
   exists to push to instead.
   This blocks step 2d (deliver the image), step 7 (HTTPS ingress), step 9 (the
   fresh pre-migration backup), step 10 (apply `w3x4y5z6a033` to `poa_prod`) and step 11
   (deploy and verify the live service). No production database, file or service was
   changed, and no production claim is made.
2. **No reviewer account exists in the Supabase project yet.** The project itself is now
   named and its configuration is verified (§6A): the candidate boots with the owner's six
   `AUTH_OIDC_*` values, fetches the live JWKS, and refuses every forged or mismatched
   token. What is still unmeasurable is the *accept* half — a token Supabase actually
   minted for a real reviewer — because that needs an account in the project and the
   project's publishable key in the browser. This blocks step 5c (a real reviewer access
   token and its identity mapping) and step 6c (signing in through the frontend in a real
   browser), and step 6b stays open only because the deployed hosting origin is the
   owner's to state.

No authorization was weakened, no test was skipped, deleted or softened to reach this
result, and `pofa_dev` was not modified.

## 2. Release candidate register

| Item | Measured value |
| --- | --- |
| Release source commit | `26a37aa8b1d7e03762afa2055074480a013d81c2` (= `origin/Backend`) |
| Source tree | `d98bfac83c1525eea938f2af746265afddc2566c` |
| Other refs | `origin/fullstack 9aebbb62`, `origin/frontend 06d4bea6`, `origin/main d72e17a7` |
| Working tree | 6 tracked modifications (5 `backend/` files + `docker-compose.yml`), 2 new test files, 72 insertions / 10 deletions — **uncommitted** |
| Candidate image | `poa-backend:mbe01-wt1` = `sha256:8db260831078a1d0853f013dd03afd0fb75dd735ea73eab7f6ab5048fbfe1c1f`, linux/amd64, 704,594,640 bytes |
| Image labels | `poa.source.commit=26a37aa8…`, `poa.source.tree=d98bfac8…`, `poa.uncommitted=true`, `poa.worktree.sha256=4a43b289…` |
| Transfer artifact | `D:/CODING/Scratch/deploy1/poa-backend-mbe01-wt1.tar`, 704,616,448 bytes, sha256 `9c597ea651ca803dcfdafc0b0286cf55bd562841751bbb258b67f53d5f2ac333` |
| Schema revision under test | `w3x4y5z6a033` (adds `PROJECT_CREATED`; 97-value enforced audit vocabulary) |
| Reviewer identity provider | `https://tuaeujvuuanadqvykugw.supabase.co/auth/v1`, audience `authenticated`, algorithm `ES256`; published key set = one EC P-256 key, `kid=ab0ac6ae-93be-441c-9196-7b2fade15af0` (§6A). The retained HS256 key publishes no `oct` entry, so this verifier can never use it |
| Frontend branch state | `fullstack` at `9aebbb62` **plus uncommitted** sign-in work (9 files changed, 4 added) in worktree `D:/CODING/Scratch/mbe01-frontend` (§7A) |
| `pofa_test` | at `w3x4y5z6a033` (advanced and verified 2026-10-17) |
| `poa_prod` | at `v2w3x4y5z032`, **not touched**; re-inspection blocked (VM unreachable) |
| Production image in use | `poa-backend:be037a` on the VM — re-inspection blocked; recorded as stale (predates OIDC + `PROJECT_CREATED`) |
| Armed suite | 1,040 passed / 1 skipped / 0 failed against the final tree (see §4) |
| Off-host production dump used for rehearsal | `poa_prod-20261017T153144Z.dump`, 270,156 bytes, sha256 `09c51a3b1726b56f1c6490afa9e7198e…` (checksum asserted before every run) |

## 3. Criterion matrix

| Step | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Freeze inputs; inspect working tree, branches, deploy config | **PASS** | §2; `git status`/`git diff --stat`/`git rev-parse` on 2026-10-27 |
| 2a | Build a unique candidate outside the VM; record SHA + digest | **PASS** | `poa-backend:mbe01-wt1`, id + size + labels above |
| 2b | Verify OIDC and audit-event code is really in the image | **PASS** | 134/134 `backend/` modules byte-identical to the worktree; preflight 10/10 and behavioural 17/17 — **both re-captured against this candidate image on 2026-10-27**, not inherited from the earlier `rc-26a37aa8` run; the same harness scores 5/10 against the pre-Stage-02 image, proving the checks can fail |
| 2c | Store it for controlled transfer (no private registry exists) | **PASS** | `docker save` tar + sha256 (§2) |
| 2d | Deliver it to the production target | **BLOCKED** | SSH port 22 timed out ×6 (last re-probe after all other criteria closed); no registry to push to |
| 3 | Verify outstanding quarantine / retry-idempotency / evidence-ownership / attribution requirements; fix release-blocking defects with regression tests | **PASS** | Register rows 2.1, 2.2, 2.6 fixed in the worktree with 9 HTTP-layer tests (§5); deploy probe defect fixed with 2 pinning tests (§8) |
| 4 | Run the complete suite against the exact candidate and correct head; explain the remaining skipped test | **PASS** | 1,040/1/0 against the final tree on `w3x4y5z6a033`; the single skip named and explained (§4) |
| 5a | Confirm the provider key type is compatible with the verifier; test accept/reject cases | **PASS** | key-type probe 7/7 (§6); `AUTH_OIDC_ENABLED=true` with an incomplete config refuses to boot (exit 1), and the same config flag off boots (exit 0) |
| 5b | Identify the real Supabase project without guessing; configure issuer/JWKS/audience; verify both endpoints directly | **PASS** | Owner named the project and its signing algorithm (§6A); the live issuer and JWKS URLs were fetched and the published EC key matches the configured `ES256`; the candidate boots in enforcing posture with those six values, indexes the live `kid`, and its config echo confirms them |
| 5c | Test a **real reviewer access token** and its identity mapping | **BLOCKED** | Needs one reviewer account in the Supabase project plus a linked user row; Owner input. Every other half of accept/reject is measured (14/14 enforcing matrix, 16/16 provider-key probe, 39 in-repo OIDC tests), so this is a missing account, not unverified code |
| 6a | Map the frontend's API calls onto the regenerated OpenAPI contract and classify every mismatch | **PASS** | 155 paths / 181 operations regenerated from the candidate; 37 matched / 1 root-only / 1 missing, each classified (§7) |
| 6b | Identify the frontend's exact hosting origin and configure CORS for approved real origins only | **BLOCKED** | The branch's own config is same-origin (`VITE_API_BASE_URL=/api/v1` plus `nginx.conf` `location /api/`), so no CORS change is required for that topology; the deployed origin is the owner's to state, and it is not guessed |
| 6c | Replace the mock username/password login with Supabase email/password and send the real access token | **BLOCKED** | The code change is complete and verified on the `fullstack` branch (§7A): mock identity removed at every layer, real bearer on every request, 401 → sign-out, 36/36 frontend tests, lint and build green. A real browser sign-in still needs the project's publishable key in `frontend/.env.local` (created, empty, gitignored) and the reviewer account from 5c |
| 7 | Secure HTTPS ingress; API stays internal; no DB/Redis/MinIO exposure; restricted admin access | **BLOCKED** | VM unreachable; no domain exists |
| 8 | Rehearse migration + deployment in isolation, including failure handling | **PASS** | Migration rehearsal log + deploy rehearsal **20/20** (§8) |
| 9 | Immediately before production changes: verify the exact DB, fresh backup, checksum, restore proof, rollback strategy | **BLOCKED** | Requires the VM. Prior off-host dump is checksum-asserted and restore-proven; strategy in §9 |
| 10 | Apply `w3x4y5z6a033` to `poa_prod`; verify revision, 97 types, data preserved, `alembic check` | **BLOCKED** | Gated on step 9 and on VM access |
| 11 | Deploy the tested image; verify auth/authz/evidence-review workflow/worker health/metrics protection/restart/logs | **BLOCKED** | Gated on steps 2d and 10. Every one of these checks is already proven against the candidate on disposable infra, except a reviewer actually signing in — which is gated on 5c, so it must be re-run live rather than assumed |
| 12 | Record release evidence, digest, revision, limitations, and whether each criterion passed | **PASS** | This report + the artifact list in §11 |

## 4. The complete suite against the exact candidate and head

All runs used the armed disposable harness (`D:/CODING/Scratch/deploy1/armfull.py`), so
the 13 infrastructure-gated obligations execute instead of skipping, and neither
`pofa_dev` nor `pofa_test` is written.

| Tree state | Result | Duration |
| --- | --- | --- |
| committed `26a37aa8` | 1,029 passed / 1 skipped / 0 failed | 26:29 |
| + the three P0 ingestion fixes and their 9 tests | 1,038 passed / 1 skipped / 0 failed | 19:52 |
| + the `docker-compose.yml` probe fix and its 2 pinning tests (**final tree**) | 1,040 passed / 1 skipped / 0 failed | 8:40 |

The arithmetic is exact at every step: 1,029 + 9 = 1,038 and 1,038 + 2 = 1,040, with the
same single skip throughout. The suite runs against the worktree, which §5 proves is the
code the candidate image carries (134/134 modules byte-identical), on a disposable
database at `w3x4y5z6a033`. The final log shows counts only rather than the skip's reason
because the harness's `-rf` overrides the `-rs` passed to it; the reason was therefore
measured by the targeted re-runs below.

**The one skipped test, named and explained.** It is
`tests/unit/test_preflight.py::test_ml_missing_never_becomes_available_without_importer`.
It was identified by measurement, not assumption: the armed run reports only a count, so
the five files capable of skipping were re-run with `-rs` (61 passed / 1 skipped), then
that file alone (23 passed / 1 skipped), and the file contains exactly one `pytest.skip`
call. Its condition is in the test itself (`tests/unit/test_preflight.py:111-118`):

```python
report = classify_ml(env={}, importer=lambda name: object())
# The real environment has no ML here; either outcome is acceptable, but
# it must never be AVAILABLE while something is missing.
if report.state is MLState.AVAILABLE:
    pytest.skip("ML stack genuinely installed in this environment")
```

The test feeds the ML preflight classifier an empty environment and an importer that
succeeds for every module, then asserts the classifier does not report `AVAILABLE`. Unlike
its neighbours, this test does **not** stub `importlib.util.find_spec`, so the verdict comes
from the real interpreter — and the interpreter that runs the suite
(`backend/.venv312_repro`) genuinely has the ML stack (`torch`, `torchvision`,
`ultralytics` all resolve). An `AVAILABLE` verdict there is correct behaviour rather than
the defect the test hunts for, and the test says so instead of asserting it. The skipped
assertion is covered by its two stubbed siblings, which force `UNAVAILABLE` and `FAILED`
and do run.

It is not a hidden failure and it is not a release risk: the deployment does not inherit
this machine's environment. Measured inside the candidate image itself,
`import torch, torchvision` succeeds with `torch 2.8.0+cpu` and
`torchvision 0.23.0+cpu` — the CPU builds the image installs — so the analysis path has
its dependencies in the artifact that ships, independent of any skip here.

## 5. Candidate verification (step 2/3) and the P0 defects that were closed

**Image content, proven rather than labelled.** `mbe01_backend_digest.py` hashed every
application module under `backend/` on both sides: **134 modules in the worktree, 134 in
the image, 134 byte-identical, 0 differing, 0 only-in-image, 0 only-in-worktree.** The
five modified files are individually hash-matched inside the image, and the same checks
score **5/10 against the pre-Stage-02 image** — every byte comparison failing there — which
proves the comparison can detect a wrong image instead of always agreeing.

**Behaviour, against a database created empty by the image's own alembic** (17/17,
re-captured against this candidate in `imagetest_behaviour_mbe01_wt1.log`):
73 tables at head, anonymous caller refused with 401, a permission-less user refused with
403, an org-scoped caller creating a project with the owner taken from its principal and
read back at 200, a cross-project write refused with 403 and **zero rows written
afterwards**, a GLOBAL delegation accepted, and exactly two `PROJECT_CREATED` ledger rows
both carrying the caller as `actor_id`.

**Release-blocking defects closed in this milestone** (acceptance-audit-register rows,
each proven at the HTTP layer in `tests/integration/test_stage02_evidence_ingestion_guards.py`):

| Register row | Defect | Fix | Tests |
| --- | --- | --- | --- |
| 2.1 (authorization) | `POST /integrations/evidence` wrote a caller-supplied `project_id` behind a resource-less `require("external_data.write")`, so a grant in one project could drop external evidence into another organization's project | the target must be inside the caller's visible projects; an unreachable target answers **404**, never a code that confirms the project exists | 3 (cross-project refusal, project-bound client vs platform-wide target, unlinked upload still allowed) |
| 2.2 (attribution) | every upload wrote its `EVIDENCE_UPLOADED` ledger row with `actor_id=None` even though each caller held a verified principal | the caller's principal id is threaded into `ingest_evidence` at all four call sites | 2 (direct upload, external ingestion) |
| 2.6 (contract honesty) | `Idempotency-Key` was advertised on the route and never read, so a retry after a lost response created a second evidence row and a second quarantine object | deterministic replay for API-client credentials; conflicting reuse refused; a human caller that sends the header is **refused rather than quietly unguarded**, because the key store's `client_id` is a NOT NULL FK to `api_clients` (read off the database, not inferred) | 4 |

Non-vacuity discipline was applied to every refusal: each denial is paired with the same
caller and the same permission succeeding against a target it does control, and every
denial re-counts the rows afterwards — a refusal that still wrote the row would otherwise
look identical to a correct refusal.

**Deliberately not in this release** (each is an owner decision or a schema change, not a
code gap): quarantine lifecycle + read filter (register 2.3, needs a migration and a
backfill call), an uploader *column* on `evidence` (needs a migration), and retry dedupe
for `POST /evidence` (that route's header is not documented today). Any new migration
would move the alembic head off `w3x4y5z6a033`, which is the exact value step 10 verifies,
so these stay out of the release candidate.

## 6. Reviewer identity (step 5) — what the verifier requires, measured against the real code

The verifier anchors trust on the provider's published JWKS and refuses symmetric key
material by design. Measured against the real code path (`mbe01_keytype_probe.py`, 7/7):

- an **ES256** (`kty EC`, curve P-256) access token verifies end to end and its claims come back;
- an EC entry **is** indexed by `kid` (`ALLOWED_KEY_TYPES` covers RSA/EC/OKP);
- an `RS256`-only configuration refuses an ES256 token with `ALGORITHM_REFUSED`;
- a legacy **HS256 token signed with the Supabase project secret is refused** (the
  symmetric entry is never indexed, so a key-set that also carried a shared secret cannot
  be used to forge a token the service trusts);
- wrong audience and wrong issuer are still refused (`TOKEN_REJECTED`) on the ES256 path.

Two obligations follow, and §6A is where each one was checked against the live project
rather than assumed:

1. Supabase's legacy signing is HS256 with a symmetric project secret, which this verifier
   cannot and must not accept. The project must have **JWT signing keys** (ES256/RS256/EdDSA)
   enabled, and its published JWKS (`https://<ref>.supabase.co/auth/v1/.well-known/jwks.json`)
   is what `AUTH_OIDC_JWKS_URI` must point at.
2. `AUTH_OIDC_ALGORITHMS` must match the project's actual key type. The default is `RS256`.
   An ES256 project left on that default would refuse **every** reviewer with
   `ALGORITHM_REFUSED`, so this is a configuration obligation, not a nicety.

Verification that the deployment cannot get this wrong silently: with
`AUTH_OIDC_ENABLED=true` and no issuer configured, the candidate **refuses to start** —
exit code 1 with `auth_oidc_issuer must be set when auth_oidc_enabled is true`, and no
configured value echoed. The paired control (`AUTH_OIDC_ENABLED=false`) boots with exit
code 0, so the refusal is caused by the incomplete config and not by the environment.
`resolve_oidc_principal` deliberately has no auto-provisioning: a token whose subject has
no pre-created linked user is refused (`NO_LINKED_USER`), which is why a reviewer account
must be created by an administrator before their first sign-in.

## 6A. Reviewer identity against the real Supabase project (step 5b) — measured

The owner supplied the project and its signing algorithm, so the six values below are the
owner's, not inferred. Every one of them is public configuration — an issuer URL, a JWKS
URL, an audience, an algorithm name and a provider label — and none is a secret; the
project's service keys were never requested, read or printed.

```
AUTH_OIDC_ENABLED=true
AUTH_OIDC_ISSUER=https://tuaeujvuuanadqvykugw.supabase.co/auth/v1
AUTH_OIDC_JWKS_URI=https://tuaeujvuuanadqvykugw.supabase.co/auth/v1/.well-known/jwks.json
AUTH_OIDC_AUDIENCE=authenticated
AUTH_OIDC_ALGORITHMS=ES256
AUTH_OIDC_IDENTITY_PROVIDER=supabase
```

**The endpoints were verified directly, not assumed to exist.** Fetching
`/auth/v1/.well-known/openid-configuration` returns an `issuer` that is byte-identical to
`AUTH_OIDC_ISSUER` and a `jwks_uri` byte-identical to `AUTH_OIDC_JWKS_URI`
(`mbe01_oidc_discovery.json`, `mbe01_oidc_jwks.json`). The project publishes exactly **one**
signing key:

```
{"kty":"EC","crv":"P-256","alg":"ES256","use":"sig","kid":"ab0ac6ae-93be-441c-9196-7b2fade15af0"}
```

which confirms the owner's dashboard reading (active key = ECC P-256 ⇒ ES256) and matches
`AUTH_OIDC_ALGORITHMS=ES256` exactly. `mbe01_oidc_jwks.json` records the key *parameters*
only; no token or credential is written to any artifact in §11.

**Accept and reject, through the real verifier, against the real key set**
(`mbe01_real_oidc_probe.py`, **16/16**): the live `kid` is indexed under the configured
algorithm; a correctly-signed token from that key set is accepted and its claims come back;
and each of these is refused with its own reason code — a token carrying the live `kid` but
signed by a different key (`TOKEN_REJECTED`), an unknown `kid` (`UNKNOWN_KEY_ID`, with the
key set refetched at most once per cooldown window — measured at 0 extra fetches), wrong
issuer, wrong audience, an expired token, a token with no `exp` (all `TOKEN_REJECTED`), a
refresh token presented as an access token (`REFRESH_TOKEN`), and an HS256 token
(`ALGORITHM_REFUSED`, refused on the algorithm whitelist before any key lookup).

**The same posture, but as a deployed container** (`mbe01_oidc_boot.py`, **14/14**). A
disposable database created empty was migrated by the image's own alembic to
`w3x4y5z6a033`, and the candidate was started with the six values above plus
`AUTH_MODE=enforcing` and `AUTH_DEV_TOKENS_ENABLED=false`, and disposable Redis and MinIO so
that every `/ready` leg is genuinely healthy. Then, over HTTP:

- the running process *echoes* all six values, enforcing mode, dev tokens off — so the
  configuration is proven to have been loaded, not merely passed to `docker run`;
- the live JWKS is reachable **from inside the container** and indexes `ab0ac6ae…`;
- anonymous → 401; a `dev-user-<id>` bearer → 401; HS256 → 401; a **forged ES256 token that
  carries the live `kid`** → 401; unknown `kid` → 401; wrong issuer → 401; and a forged token
  cannot create a project (`POST /projects` → 401);
- **nothing was auto-provisioned**: `users` was counted before and after all eight refusals —
  `before=0 after=0`. That is the requirement "must not auto-provision privileged users"
  measured rather than asserted;
- the refusals log *distinct* reasons rather than one blanket error:
  `{"ALGORITHM_REFUSED": 2, "UNKNOWN_KEY_ID": 2, "TOKEN_REJECTED": 6}`. A single reason for
  everything would mean the tests were all failing for the same unrelated reason.

The in-repo OIDC suites were re-run against this configuration's head revision
(`tests/unit/test_stage02_oidc_verification.py` +
`tests/integration/test_stage02_reviewer_identity.py`): **39 passed** on disposable
`poa_disp_ptest`.

**Two consequences of the owner's key choice.**
`AUTH_OIDC_ALGORITHMS=ES256` is mandatory, not cosmetic: leaving the `RS256` default would
refuse *every* reviewer with `ALGORITHM_REFUSED`, and the config validator only accepts
RS*/ES*/PS* algorithms, so a wrong value cannot boot silently. And the **previous HS256 key
can stay** (the owner asked that it not be rotated or revoked): the published key set
contains no `oct` entry, so nothing in this verifier can use a symmetric secret, and the
HS256 refusal above shows the path is closed even if one appeared.

**What is still unmeasured** — and why it is the owner's to supply: the *accept* half with a
token **Supabase itself minted**. Everything up to that point is proven, but a real
access token requires an account in the project, and creating one is an owner action. That
is criterion 5c, and the exact procedure is §10 step 0.

## 7. Frontend contract map (step 6)

The contract was regenerated from the candidate itself (155 paths / 181 operations) and
compared with the committed snapshot (also 155 paths) and with the calls in
`frontend/src/services/api.js` on `origin/fullstack`.

**37 frontend calls matched, 1 root-mounted only, 1 missing:**

- `GET /metrics` is mounted at the root, not under `/api/v1`. It now requires
  `metrics.read`; the candidate answers **401** for an unauthenticated caller. That is
  correct by design (it is an operator endpoint), and it is why it appears as ROOT rather
  than OK: the frontend's `/api/v1` base URL cannot reach it at all.
- `GET /audit/anchors/{id}/verification` has **no matching backend operation**. The live
  contract exposes `/api/v1/audit/verify` and `/api/v1/audit/verify/anchored` and nothing
  else containing "anchor". Classification: **frontend-side gap, not a backend release
  blocker** — it 404s against any image, old or candidate, and the backend equivalent
  already exists. It belongs on the 30 October integration list.
- `POST /api/v1/integrations/evidence` is an operation the frontend never calls. Its two
  new refusals (400 for a key a human caller cannot hold, 404 for an out-of-scope project)
  are **not documented in the committed `openapi.json` snapshot**, which lists only
  `{201, 422}` for that route. Regenerating that hand-committed file is an owner commit
  decision.

Two integration facts that matter more than the route names:

1. **Project creation is request-shape compatible in one direction only.** The deployed-era
   image requires `owner_id` in the body — it answers
   `422 {"type":"missing","loc":["body","owner_id"]}` without it, measured in the rehearsal —
   while the candidate's schema declares `owner_id` optional and derives it from the
   caller. The frontend already sends `owner_id`, so the candidate accepts both shapes;
   the change is recorded because a rollback to the old image would break callers that
   adopted the derived form.
2. **The frontend had no real sign-in — closed the same day, see §7A.** This is what the
   contract map above was measured against: `api.js` read
   `localStorage.getItem('auth_token')`, and its `login` helper was a mock that wrote
   `dev-user-<username>`. Under the production posture (`AUTH_MODE=enforcing`,
   `AUTH_DEV_TOKENS_ENABLED=false`) every one of those requests is refused, which is exactly
   the failure that mock login hides in development. §7A records the replacement (Supabase
   email/password, real bearer token, mock removed at every layer, 36/36 tests). The two
   halves of the same owner input remain: the publishable key in the browser, and the
   `AUTH_OIDC_*` values in the production `.env` (§6A has them verified against a
   disposable run, and the VM's `.env` is untouched by design).
3. **CORS:** `VITE_API_BASE_URL=/api/v1` plus the frontend's own `nginx.conf`
   (`location /api/ { proxy_pass http://api:8000/api/; }`) means the browser makes
   same-origin requests, so **no CORS allowlist change is needed for that topology**.
   `CORS_ALLOW_ORIGINS` only becomes relevant if the frontend is hosted on a different
   origin than the API, and that origin is not something to guess.

## 7A. Frontend sign-in — implemented and verified, browser click-through is owner-gated

§7 recorded the P0 frontend gap: `login` was a mock that wrote `dev-user-<username>` into
`localStorage`, which the production posture refuses outright. That is now replaced on the
correct branch — `fullstack` (`9aebbb62`), worked in an isolated git worktree at
`D:/CODING/Scratch/mbe01-frontend` so the release candidate's `Backend` worktree stayed
byte-identical. The change is **uncommitted**, and `origin/fullstack` is unchanged.

| File | Change |
| --- | --- |
| `package.json` / lock | adds `@supabase/supabase-js` (the only new dependency) |
| `src/services/authConfig.js` | the configuration gate: names each missing required key instead of half-configuring |
| `src/services/supabaseClient.js` | lazy `createClient` with a persistent, auto-refreshing session under its own storage key; `supabaseConfigError()` derives from the gate, and a null client means *nobody can sign in* — no caller may substitute an identity |
| `src/services/authSession.js` | `decodeJwtClaims`, `tokenNeedsRefresh`, `currentAccessToken` (refreshes near expiry, signs out when a refresh is impossible), `describeSignInError` |
| `src/services/api.js` | the mock `login` is gone; the request interceptor is async and attaches the **real Supabase access token** as `Bearer`, sends no header when there is none, and a 401 signs the session out. `login` = `signInWithPassword` → `GET /auth/me` → returns the backend principal plus the provider email |
| `src/context/AuthContext.jsx` | `MOCK_USER` deleted; on load it clears the two legacy `localStorage` keys, restores the provider session, and re-reads `/auth/me` so the identity comes from the backend, not from the browser's memory; a session that maps to no backend account is refused with an explicit message |
| `src/components/auth/LoginForm.jsx` | email + password (username field and "remember me" removed); refuses to submit when the client is unconfigured and shows why |
| `Header.jsx`, `Dashboard.jsx`, `Profile.jsx` | read the principal from `AuthContext` instead of `localStorage`; logout calls the real sign-out; email renders "Not provided" rather than `user@example.com`, and "Member since" is only shown when the backend actually returned `created_at` (the fabricated `Date.now()` is gone) |

**Three fabricated identities were removed, and a fourth was invented by the old code** —
Profile's "Member since" fell back to the current time, so every reviewer appeared to have
joined today. Each removal is paired with an explicit "unknown" rendering instead of a
plausible value.

**Measurements.** `npm test` → **36 passed / 0 failed** (re-run for this report), of which
22 are the new `tests/auth-session.test.js`: the config gate names every missing key;
`decodeJwtClaims` decodes a real base64url ES256 payload and returns `null` for garbage;
`currentAccessToken` leaves a valid token untouched, refreshes near expiry, and signs out
rather than returning a stale bearer; the sign-in refusals carry a human-readable reason;
and a source scan asserts the removed patterns (`dev-user-`, `mock-token-`, `MOCK_USER`)
and `localStorage` token reads are gone from these files. `npm run build` succeeds, and
`oxlint` reports warnings only, no errors.

**The new tests found a real defect, which is the proof they are not decorative.**
`readSupabaseConfig` filtered `REQUIRED_KEYS` — the *environment variable names* — against
the result object, whose properties are named `url` and `publishableKey`. Every lookup was
therefore `undefined`, both keys always counted as missing, and `ready` could never become
true even with both values correctly set: every reviewer would have been told the client was
unconfigured forever. Rewritten with an explicit values map, then 22/22. The guard's
patterns were also checked against the pre-fix code
(`git show HEAD:… | grep -c 'dev-user-'` → non-zero), so the test can fail rather than
merely agreeing.

**Secret handling.** The project URL is public and is recorded in the tracked
`frontend/.env` with a comment saying so. The **publishable key is not in any file I wrote**:
`frontend/.env.local` exists, is gitignored by the branch's own `*.local` rule, and contains
an empty assignment plus a pointer to where the owner copies the value from
(Supabase dashboard → Project Settings → API). It was never requested in chat.

**What still blocks 6c**: the key in that file, one reviewer account (§6A), and then the
click-through itself. For that moment the candidate is already running with the real OIDC
configuration on a disposable database with zero users at `http://127.0.0.1:8011`
(loopback only; `python D:/CODING/Scratch/deploy1/mbe01_oidc_boot.py clean` tears it down).

## 8. Rehearsal of the production sequence, including failure handling (step 8)

Two halves, both against a disposable database restored from the owner-verified off-host
copy of the last production dump, so it starts at production's exact position. The
protected-name set (`poa_prod`, `pofa_dev`, `pofa_test`, …) is refused before any command
runs.

**Migration half** (`mbe01_migration_rehearsal.log`, re-run 2026-10-27):

```
start  : revision=v2w3x4y5z032 base_tables=73 vocabulary=96 PROJECT_CREATED=False ledger_rows=1
upgrade: Running upgrade v2w3x4y5z032 -> w3x4y5z6a033
after  : revision=w3x4y5z6a033 vocabulary=97 PROJECT_CREATED=True
row counts: 73/73 identical, changed=none, new tables=none
alembic check: rc=0 (only the known, policy-suppressed uq_user_role_scoped autogenerate artifact)
downgrade -1  : rc=1 RuntimeError("BE-039 cannot downgrade an append-only audit vocabulary")
                schema after refusal: revision=w3x4y5z6a033 vocabulary=97 ledger_rows=1
re-run upgrade: rc=0 revision=w3x4y5z6a033   (idempotent)
```

The migration is additive, forward-only, loses nothing, and a re-run after an
interruption is safe — which is what an operator needs.

**Deployment half** (`mbe01_deploy_rehearsal.py`, **20/20**):

- the deployed-era image serves `/health` and `/api/v1/ready` and answers authenticated
  reads on the pre-migration schema;
- the candidate applies `alembic upgrade head` **while the old app keeps running**; the
  vocabulary goes 96 → 97; no pre-existing row changes; the old app still serves 200 with
  no restart;
- the **rollback path works**: the old image writes successfully against the migrated
  schema (`201`, one row read back) — the schema cannot roll back, so this is the only
  safety net that exists;
- the candidate then takes over, creates a project over HTTP, appends `PROJECT_CREATED`
  with **the caller as actor**, and refuses an anonymous caller with 401;
- `docker stop -t 10` exits 0 and the log ends with `application.shutting_down` — clean
  SIGTERM shutdown, no non-zero exit;
- an injected misconfiguration (a `DATABASE_URL` pointing at a nonexistent database)
  turns **`/ready`, `/healthz` and `/api/v1/ready` all to 503 while `/health` stays 200 and
  the container keeps running** — which is the documented liveness/readiness contract, not
  a crash;
- the operator restores service with the previous image (`/health` 200) and **no rows are
  lost** (73 tables compared, all equal);
- `alembic check` reports no drift after the whole sequence.

**The deploy defect this found, and its fix.** `docker-compose.yml`'s `api` healthcheck
probed `/health` — dependency-agnostic liveness — so a database or Redis outage could
never make the container unhealthy; the orchestrator would be blind to it. The measured
contract (`mbe01_health_matrix.json`):

| State | `/health` | `/ready` | `/healthz` | `/api/v1/ready` |
| --- | --- | --- | --- | --- |
| all dependencies live | 200, 0.58s | 200, 2.54s | 200, 2.09s | 200, 1.26s |
| database unreachable | 200 | **503** (`postgresql=unhealthy`) | **503** | **503** |
| redis unreachable | 200 | **503** (`redis=unhealthy`) | **503** | 200 |

Two sub-findings: `/api/v1/ready` checks only Postgres (`backend/api/v1/endpoints/health.py:15-25`)
so it reports *ready* through a Redis outage — the root `/ready`/`/healthz` pair is the
correct probe; and the old `timeout: 5s` sat just above the measured 2.54s healthy answer,
which leaves no headroom for a slow-but-alive dependency.

The healthcheck now probes `/healthz` with `interval: 20s`, `timeout: 10s`,
`start_period: 45s`. It is pinned by two new tests
(`tests/unit/test_mbe01_compose_healthcheck_probe.py`) that **failed against the previous
file** (`/health` was probed; `5s` budget) and pass now — so the fix is measured, not
asserted. Verified further: `docker compose config --quiet` exits 0; the literal probe
command, read straight out of the compose file and executed inside the candidate image,
exits **0 with every dependency up and 1 with the database gone**
(`urllib.error.HTTPError: HTTP Error 503: Service Unavailable`) — both directions of the
control that Docker actually looks at (`mbe01_healthcheck_probe.py`, 2/2).

`docker-compose.yml` is **not baked into the image** (measured: absent at `/app`), so this
fix changes no image byte.

## 9. Rollback and recovery strategy for the production night

- **Before** anything writes: `pg_dump` `poa_prod` on the VM, copy it off-host, record its
  byte size and sha256, and **restore-prove** it into a disposable database (the same
  procedure already proven on 2026-10-17: 270,156 bytes, sha256 `09c51a3b…`, restored with
  `--no-owner --no-privileges --exit-on-error`). The milestone requires a fresh copy
  immediately before the migration; the 17 October dump is the rehearsal source, not the
  release recovery point.
- **Migration is forward-only.** `w3x4y5z6a033.downgrade()` raises by design; the rollback
  is therefore *application* rollback, not schema rollback: keep the previous image, and
  know that it still serves and writes against the migrated schema (proven in §8).
- **If the candidate fails to start**: point the service back at the previous image. The
  rehearsal measured exactly that path, including that no data is lost. The additive
  change means old-code/new-schema is the supported pairing; new-code/old-schema is not,
  which is why the migration must land before the image swap.
- **If the schema state is wrong after the upgrade**: stop, do not attempt a downgrade or a
  `--stamp`, and treat the verified dump as the recovery object.

## 10. Remaining gate procedure, in order

Two tracks. **Step 0 needs no VM** and is what closes criteria 5c and 6c; the numbered list
after it is the production sequence, which needs the VM.

### Step 0 — one real reviewer sign-in (owner actions, in order)

1. Put the project's **publishable key** into
   `D:/CODING/Scratch/mbe01-frontend/frontend/.env.local`, on the line that is already there
   and waiting. That file is gitignored, so the value stays on this machine — it never goes
   into chat, a commit, or the tracked `.env`. (It is a *client-side* credential: it cannot
   mint a trusted token; the service key is the secret, and nothing here needs it.)
2. In the Supabase dashboard, create **one** user (Authentication → Users → Add user) with an
   email and password you choose, and confirm email is marked verified. Copy that user's
   **UUID** (the `uid` column) — it is an identifier, not a secret.
3. Link it to a backend account. Against the candidate that is already running on
   `http://127.0.0.1:8011`, an administrator creates the user through
   `POST /api/v1/auth/users` with `identity_provider="supabase"` and
   `external_subject=<that uid>`, then grants the reviewer role/permissions. There is no
   self-service path by design (§6A: `NO_LINKED_USER`), and that is what makes this step an
   owner action rather than something I can invent an account for.
4. Sign in in a browser from that worktree (`npm run dev`) with the email and password from
   2. The expected result is a real principal in `/auth/me` — with the email coming from the
   provider session, never a fabricated one — and a reviewer-visible project list.
5. Tell me the outcome, or the exact message, and I will do the accept-half verification
   (§6A's remaining line): signature, issuer, audience, expiry, the identity mapping, and the
   authorization the principal actually holds.

Do **not** point step 0 at production. The Supabase project is now the real issuer, so a token
minted there is real; the backend it is sent to here is the disposable one, whose database
holds zero rows and whose name is refused by every protected-name guard.

### Production sequence, once the VM answers

1. Confirm the VM is running and reachable (Azure portal → the `poa-submission-vm`
   overview page → status, and its public IP; then `ssh azureuser@<ip>`). If the IP changed,
   that alone explains every timeout.
2. Record the VM's actual state before changing anything: `git rev-parse HEAD`,
   `docker images --digests`, `psql -c "select version_num from alembic_version"`, and
   whether any `AUTH_OIDC_*` keys exist in `.env` (presence only, never values).
3. Transfer the artifact from §2 (`scp` the tar), `docker load` it, and verify the loaded
   image id equals `sha256:8db26083…` — the digest is how "same bytes" is proven.
4. Take the fresh, checksummed, restore-proven backup (§9).
5. Apply the migration with the migration identity only: `alembic upgrade head`, then
   verify revision `w3x4y5z6a033`, the 97-value vocabulary, per-table row counts against the
   pre-migration snapshot, and `alembic check`.
6. Add the six `AUTH_OIDC_*` values from §6A to the VM's `.env` — the owner enters them, and
   although these six are public configuration rather than secrets, they still do not belong
   in chat or in a commit. Skipping this is silent in exactly one direction and loud in the
   other: with `AUTH_OIDC_ENABLED=true` and any value missing, the candidate **refuses to
   boot** (§6), and with `AUTH_OIDC_ALGORITHMS` left at the `RS256` default it boots and
   refuses every reviewer.
7. Point the runtime DSN at `poa_runtime` (never the owner role), start the candidate, and
   run the live verification list: anonymous 401, permission-less 403, the evidence-review
   workflow, `/metrics` 401 without `metrics.read`, `/healthz` 200, worker containers up,
   `docker stop` clean shutdown, and the log stream redacted.
8. Keep `8000` on loopback; do not publish 5432/6379/9000/9001; then — and only then — the
   domain + reverse proxy + HTTPS step, which needs its own owner decision about the domain.

Every one of those verifications already has a passing measurement against this candidate on
disposable infrastructure, so each is a re-run rather than a first attempt — **with one
exception**: a reviewer actually signing in. That is step 0, and until it is done, production
step 7 must be followed by a real sign-in before the deployment is called verified.

## 11. Evidence artifacts

All under `D:/CODING/Scratch/deploy1/` unless stated. Each is a command output, not a
narrative.

| Artifact | What it proves |
| --- | --- |
| `poa-backend-mbe01-wt1.tar` + sha256 | the candidate as a transferable, verifiable object |
| `mbe01_backend_digest.json` | 134/134 image↔worktree module digests |
| `be039/imagetest.py` | the image-verification harness (preflight + behavioural phases); re-run against `poa-backend:mbe01-wt1`, and **5/10 against the pre-Stage-02 image** with the same code, which proves the checks can fail |
| `imagetest_mbe01_wt1.log` | the candidate's 10/10 preflight: commit/tree labels, 97-type vocabulary, `oidc.py` and `w3x4y5z6a033` present, the 5 modified files byte-matched in-image |
| `imagetest_behaviour_mbe01_wt1.log` | the candidate's 17/17 behavioural run against a database the image's own alembic created empty |
| in-image dependency probe | `docker run --rm --entrypoint python poa-backend:mbe01-wt1 -c "import torch, torchvision; …"` → `torch 2.8.0+cpu`, `torchvision 0.23.0+cpu` (§4) |
| `mbe01_suite_26a37aa8.log`, `mbe01_suite_after_fixes.log`, `mbe01_suite_final_tree.log` | 1,029/1/0, 1,038/1/0, and the final-tree re-run |
| `mbe01_migration_rehearsal.log` | production-shaped migration, row counts, drift check, refusal to downgrade, idempotent re-run |
| `mbe01_deploy_rehearsal.py` / `.json` | the 20/20 deployment sequence, including rollback path and recovery |
| `mbe01_health_matrix.json` | the four operational paths across three dependency states, with timings |
| `mbe01_healthcheck_probe.py` / `.json` | the literal compose probe exiting 0 healthy and 1 under outage |
| `mbe01_keytype_probe.py` / `.log` | 7/7 OIDC key-type behaviour through the real verifier |
| `mbe01_oidc_discovery.json` | the provider's own discovery document — its `issuer` and `jwks_uri`, compared byte-wise with the configured values |
| `mbe01_oidc_jwks.json` | the live key set exactly as published: one EC/P-256 ES256 entry and its `kid`. Key parameters only — no token, no credential, no secret value appears in any artifact here |
| `mbe01_real_oidc_probe.py` / `.json` | 16/16 accept/reject through the real verifier **against the provider's published key** |
| `mbe01_oidc_boot.py` / `.json` | 14/14 enforcing boot matrix on the candidate image with the six real values, including the no-auto-provision row count and the distinct refusal reasons; `… clean` tears the disposable stack down |
| `D:/CODING/Scratch/mbe01-frontend` (git worktree, branch `fullstack`) | the frontend sign-in implementation, uncommitted; `frontend/tests/auth-session.test.js` holds its 22 tests (36/36 for the suite) |
| `mbe01_contract_map.txt`, `mbe01_live_openapi.json` | the regenerated contract and the frontend call map |
| `tests/integration/test_stage02_evidence_ingestion_guards.py` | the 9 regression tests for the three P0 defects |
| `tests/unit/test_mbe01_compose_healthcheck_probe.py` | the 2 tests pinning the healthcheck probe path and budget |

## 12. Known limitations carried into the release

- Production is unverified as of this report: `poa_prod` remains at `v2w3x4y5z032` and its
  image is the stale `poa-backend:be037a`. What changed since the earlier draft of this
  report is *why*: the OIDC values are no longer unknown (§6A verifies them against the live
  provider), so the only remaining reason production is unverified is that the VM answers no
  port-22 connection, and its `.env` still has no `AUTH_OIDC_*` keys.
- **The verifier has never seen a token Supabase actually minted.** Every accept-path
  measurement used a key *from the provider's published set*, signed locally by a key pair
  created seconds earlier — which is why the forged-token refusals are meaningful, and also
  why they cannot prove the provider's own claims (`aud`, `sub`, `exp`, any custom claim)
  arrive in the shape the mapping expects. This is the honest boundary of 5c.
- The frontend sign-in is **uncommitted** work in a worktree, and it has been tested at the
  unit and build level only — not by a human clicking through a real browser against a real
  session (6c). Vite also bakes `VITE_*` values at build time, so a frontend image built
  before the publishable key exists cannot gain it later without a rebuild.
- A disposable stack for that browser test is **left running on purpose**: database
  `poa_disp_oidc` (zero user rows, zero application rows) and container
  `poa_disp_oidc_api` on `127.0.0.1:8011`. Nothing is published — it is loopback only, and
  tearing it down is `python D:/CODING/Scratch/deploy1/mbe01_oidc_boot.py clean`. Earlier
  `poa_disp_*` databases and containers from previous milestones are also still present.
- The single suite skip is an ML-stack observation, not a defect (§4).
- Quarantine lifecycle + read filter, an uploader *column*, and `POST /evidence` retry
  dedupe are open because they need a migration or an owner decision (§5).
- Four other routes advertise `Idempotency-Key` and still drop it for non-API-client
  callers; changing their documented behaviour is an owner call, not a silent fix.
- Remaining `actor_id=None` write sites: the HTTP-triggered `evidence_graph.py:202,258` and
  `fusion.py:831` (system-path writers — `webhook_worker.py:259`, `retention.py:975,1054`,
  `governance.py:271`, `review_case.py:412` — are legitimately unattributed).
- No checksum/object reconciliation probe exists for stored evidence (audit register 2.4);
  5 `RetentionHold` rows still carry a NULL scope; `GET /publications/policies` is shadowed
  by a route-ordering collision.
- `pofa_dev` remains three revisions behind head — explicitly out of scope for this
  milestone ("do not modify `pofa_dev`").
- No private container registry exists, so delivery is a checksummed `docker save` artifact
  rather than a registry pull.
- No domain, therefore no HTTPS, therefore no secure public production deployment claim is
  possible yet.

## 13. Owner inputs requested

No secret value is ever asked for here. Two of the three items below are things **you place
into files or dashboards yourself**; I only need to know you did, plus the outcome.

1. **The VM** — unblocks 2d, 7, 9, 10, 11.
   Is `poa-submission-vm` running, and what is its current public IP and NSG state for
   port 22? SSH timed out on six measurements today. No credential is needed, only whether
   the machine is up and at which address (if the IP changed, that alone explains it).
2. **Reviewer sign-in** — unblocks 5c and 6c. Three small actions, in this order:
   a. Open `D:/CODING/Scratch/mbe01-frontend/frontend/.env.local` and paste the project's
      **publishable key** onto the empty line that is waiting there
      (Supabase dashboard → Project Settings → API → *Publishable key*). Git-ignored; never
      paste it into chat, and the *service* key is not needed and should not be used here.
   b. In Supabase → Authentication → Users, add **one** user with an email and password you
      choose, and copy its **uid** (a UUID; an identifier, not a secret).
   c. Say the word and I will link that uid to a backend account on the already-running
      disposable candidate (§10 step 0) — that step needs an administrator credential, which
      is yours — then you sign in once in a browser and report what appears.
3. **The frontend's real hosting origin**, once it is deployed somewhere — unblocks 6b.
   Until then the same-origin setup in §7 stands and no CORS change is made.

## 14. Non-negotiable rules — compliance

| Rule | Held |
| --- | --- |
| Never guess a Supabase project, token, frontend URL or domain | yes — the six `AUTH_OIDC_*` values were **supplied by the owner**, then verified against the provider's live discovery document and key set rather than trusted on sight (§6A); no reviewer token was ever invented, and the only frontend facts cited are read from the branch itself |
| Never reveal secrets in chat or logs | yes — disposable credentials were read from a 0600 state file and never printed; probe output shows only field *names*; the frontend `.env` was inspected by key name; the publishable key was never read or written by me — `.env.local` was created **empty**, with a pointer to where the owner pastes it |
| Never weaken authorization or bypass an unsuccessful test | yes — no test edited or deleted; the new tests were shown failing before the fix; the four rehearsal failures were explained by measurement, then the expectations were corrected to the *documented* contract, not relaxed; and the accept half is reported BLOCKED rather than closed with a locally-signed stand-in |
| Do not run write tests against production using synthetic projects | yes — every write happened in a disposable database; the protected-name set refused `poa_prod`/`pofa_dev`/`pofa_test` before any command |
| Do not modify `pofa_dev` | yes — untouched |
| Do not claim production-ready from local tests alone | yes — the verdict is NOT production-ready |
| If an external input is missing, ask one specific question and keep going | yes — §13 is now three concrete actions, and the independent work they did not block (the whole OIDC verification half and the entire frontend sign-in rewrite) was completed while waiting |
| If a production gate fails, stop safely and report the measured blocker | yes — steps 7/9/10/11 are reported as blocked with the exact measurement (six SSH timeouts), not as passed |
