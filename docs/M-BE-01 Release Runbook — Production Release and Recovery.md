# M-BE-01 Release Runbook — Production Release and Recovery

Status: **not started**. No production write of any kind has occurred. This document is
the executable sequence for the release window; every gate has an explicit abort
condition, and an aborted gate stops the release rather than being worked around.

Deadline context: backend milestone 29 October 2026 18:00 IST; 30 October reserved for
frontend integration, end-to-end validation and submission.

## 0. Candidate identity (what must be deployed)

| Item | Value | How it was proven |
| --- | --- | --- |
| Source commit | `26a37aa8b1d7e03762afa2055074480a013d81c2` (= `origin/Backend` at candidate build) | `git rev-parse` |
| Image | `poa-backend:mbe01-wt1` = `sha256:8db260831078a1d0853f013dd03afd0fb75dd735ea73eab7f6ab5048fbfe1c1f` | `docker inspect` |
| Image ↔ source | 134/134 `backend/` modules byte-identical to the worktree (re-verified 27 Oct) | `mbe01_backend_digest.py` → `VERDICT: … = True` |
| Transfer object | `D:/CODING/Scratch/deploy1/poa-backend-mbe01-wt1.tar`, 704,616,448 bytes, sha256 `9c597ea651ca803dcfdafc0b0286cf55bd562841751bbb258b67f53d5f2ac333` | `sha256sum` |
| Schema target | `w3x4y5z6a033` (adds `PROJECT_CREATED`, 97-value audit vocabulary) | alembic history |
| Production schema today | `v2w3x4y5z032` (last known; must be re-read on the VM before anything else) | portal/VM inspection |

Rules that never bend:

- The image that runs in production is the image that was tested. If any source byte
  changes, rebuild, re-verify (`mbe01_backend_digest.py`, preflight, behavioural) and
  re-sign this table. Never rebuild on production and label it the tested candidate.
- `pofa_dev` is not touched at any point.
- `pofa_test` is already at `w3x4y5z6a033`; it is a test database, not a target.
- No database, Redis, MinIO or raw API port is ever opened to the internet.
- The migration is forward-only (`w3x4y5z6a033.downgrade()` raises by design), so the
  rollback object is the fresh backup plus the previous image, not a schema downgrade.

## 1. Gate A — VM and access (owner)

Abort if any answer is wrong.

1. Owner starts `poa-submission-vm` (resource group `poa-submission-rg`, India South
   Central, Standard B2s v2). Until this point the VM stays deallocated.
2. Read the **current** public IP from the portal. The last known address
   (`172.198.77.149`) timed out on SSH and must not be assumed.
3. Confirm the public IP resource is allocation **Static** (portal → the public IP
   resource → Configuration). A Dynamic address changes on restart and would invalidate
   both the TLS hostname and the certificate.
4. Confirm NSG `poa-submission-vm-nsg` inbound rules:
   - priority `300`, name `SSH`, TCP 22, source **owner's current public IP `/32`**,
     Allow. If the saved source is `Any`, the owner corrects it in the portal (edit the
     rule → Source = IP addresses → `<their-ip>/32` → Save). Never widen it.
   - add/confirm priority `310`, name `HTTP-HTTPS`, TCP 80 and 443, source `Any`, Allow.
   - confirm **no** rule allows 5432, 6379, 9000, 9001, 8000 or 5433.
5. `ssh azureuser@<current-ip>` answers. Record `git -C <repo> rev-parse HEAD`,
   `docker images --digests`, `psql -c "select version_num from alembic_version"`
   (target must be `poa_prod`, revision `v2w3x4y5z032`), and the **presence only** of
   `AUTH_OIDC_*` keys in the VM `.env` (names, never values).

Abort conditions: SSH unreachable; public IP not static; NSG rule 300 not restricted to
the owner's `/32`; database name is not `poa_prod`; revision is not `v2w3x4y5z032`.

## 2. Gate B — deliver the tested image

1. From this machine: `sha256sum poa-backend-mbe01-wt1.tar` → must equal
   `9c597ea6…ac333`.
2. `scp poa-backend-mbe01-wt1.tar azureuser@<ip>:/var/tmp/`
3. On the VM: `sha256sum` the received file → same value (transfer integrity).
4. `docker load -i poa-backend-mbe01-wt1.tar`
5. `docker inspect --format '{{.Id}}' poa-backend:mbe01-wt1` →
   `sha256:8db260831078a1d0853f013dd03afd0fb75dd735ea73eab7f6ab5048fbfe1c1f`.
   This digest is the proof that the loaded image is the tested one.

Abort condition: any checksum or image id mismatch. Disk check first
(`df -h`): the tarball is ~704 MB and the image ~3 GB compressed-ish; the VM has been
observed with limited space before.

No container registry exists, so `docker save`/`load` over SSH **is** the delivery path.
Do not install Buildx or any build tooling on the VM.

## 3. Gate C — fresh backup, checksum, restore proof (before any schema write)

Target is `poa_prod` on the VM's own PostgreSQL (`pofa_db` container), **not** `pofa_dev`
and not `pofa_test`.

1. Timestamp and dump:
   `docker exec pofa_db pg_dump -U postgres -Fc poa_prod > /var/tmp/poa_prod-<UTC>.dump`
2. Record byte size and `sha256sum` of the dump; copy it off the VM (scp back to this
   machine) and record its sha256 again — both must match.
3. Restore proof into an isolated database on the VM:
   `docker exec -i pofa_db createdb -U postgres poa_restore_probe`
   `docker exec -i pofa_db pg_restore -U postgres --no-owner --no-privileges
   --exit-on-error poa_restore_probe < /var/tmp/<dump>`
   then count a few known tables (row counts must equal the source's), then
   `docker exec pofa_db dropdb -U postgres poa_restore_probe`.
4. Record the pre-migration snapshot: `alembic_version`, per-table row counts for the
   audit ledger and core tables, the audit vocabulary count (expect 96), and the
   `PROJECT_CREATED` absence.

Abort condition: checksum mismatch, restore failure, or row-count mismatch.

The 17 October dump is the rehearsal source only. It is **not** the release recovery
point; the fresh dump above is.

## 4. Gate D — schema migration `v2w3x4y5z032` → `w3x4y5z6a033`

1. On the VM, in the repo checkout, with the **migration identity**
   (`POA_MIGRATION_DATABASE_URL` = `poa_migrator`, never the runtime role):
   `docker compose run --rm migrate` (runs `alembic upgrade head`).
   The `migrate` service sits behind the `tools` profile and is never started by `up`.
2. Verify:
   - `select version_num from alembic_version` → `w3x4y5z6a033`
   - audit vocabulary → 97 values; `PROJECT_CREATED` present
   - per-table row counts identical to the Gate C snapshot (migration is additive:
     no pre-existing row changes, no new tables besides the expected ones)
   - `alembic check` → exit 0 (the known policy-suppressed `u1v2w3x4y031` autogenerate
     artifact is the only tolerated note)
3. Idempotence check: re-running the upgrade must be a no-op (already proven in
   rehearsal: re-run exits 0 at the same revision).

Abort condition: any verification mismatch. Recovery: restore from the Gate C dump and
re-run; **do not** attempt `alembic downgrade` (refuses by design) and do not `--stamp`.

Rehearsal evidence already held: `mbe01_migration_rehearsal.log` (73/73 tables
identical, rc=0, downgrade refused) and `mbe01_deploy_rehearsal.py` **20/20** including
the rollback path.

## 5. Gate E — configuration (owner-entered values, names recorded here only)

In the VM `.env` (owner types these; they are public provider metadata, but they do not
belong in chat or in Git):

```
AUTH_OIDC_ENABLED=true
AUTH_OIDC_ISSUER=https://tuaeujvuuanadqvykugw.supabase.co/auth/v1
AUTH_OIDC_JWKS_URI=https://tuaeujvuuanadqvykugw.supabase.co/auth/v1/.well-known/jwks.json
AUTH_OIDC_AUDIENCE=authenticated
AUTH_OIDC_ALGORITHMS=ES256
AUTH_OIDC_IDENTITY_PROVIDER=supabase
```

Also required in production `.env`: `ENVIRONMENT=production`, `AUTH_MODE=enforcing`,
`AUTH_DEV_TOKENS_ENABLED=false`, a real `JWT_SECRET`, `CORS_ALLOW_ORIGINS` set to the
single HTTPS frontend origin (§7), and `POA_DATABASE_URL` pointing at the least
privileged `poa_runtime` role. The config validator refuses an insecure JWT secret, a
non-enforcing auth mode, enabled dev tokens or wildcard CORS — fail-closed before
startup.

Failure semantics worth knowing: with `AUTH_OIDC_ENABLED=true` and any value missing the
candidate **refuses to boot** (that is correct), and with `AUTH_OIDC_ALGORITHMS` left at
the `RS256` default it boots and refuses every reviewer. Set all six.

**Gate E check (must pass before Gate F, run from the directory holding the `.env`):**

```
python -m backend.security.oidc_preflight --expected-project-ref tuaeujvuuanadqvykugw
```

This is the gate that a syntactically valid configuration cannot pass by looking valid.
It fetches the provider's real published key set and answers three questions the boot
validator cannot: does the issuer host belong to *this* Supabase project (a real,
working project that is not the one under review would verify tokens for different
people), is the issuer on that provider's auth path, and can the published keys actually
verify a token under the configured algorithm.

Exit codes: `0` every check passed; `1` a check failed; `2` the configuration is
consistent but something could not be verified (typically `probe_token`, because no real
reviewer token was supplied). `2` does not authorise the release on its own — pair it
with Gate H's real signed-in request.

Measured on 2026-10-28 against this project's live endpoints, from the candidate
interpreter:

| configured algorithm | result |
| --- | --- |
| `ES256` (the value above) | all checks PASS; one usable key `ab0ac6ae-93be-441c-9196-7b2fade15af0` (`EC/ES256`); `probe_token` BLOCKED, no real token — exit `2` |
| `RS256` (the shipped default) | `usable_keys` FAIL: "no published key is usable under RS256; the provider publishes EC/ES256" — exit `1` |

A mistyped project ref is caught the same way: `tueaeujvuuanadqvykugw` (one extra letter)
returned `project_identity FAIL: issuer is project 'tuaeujvuuanadqvykugw' but the release
expects 'tueaeujvuuanadqvykugw'`, exit `1`.

**Abort condition:** any exit `1` at this gate stops the release. Do not proceed on the
reasoning that the values "look right"; fix the endpoint or the algorithm, then re-run.
The report names key identifiers and algorithms only — never key material, and never a
token. If a real token is used for `probe_token`, pass it as a file
(`--token-file`), never as a command-line argument.

## 6. Gate F — deploy the candidate

1. Point the compose services at the tested tag (the compose file currently pins
   `poa-backend:be037a`): set `image: poa-backend:mbe01-wt1` for `api`,
   `analysis_worker`, `notification_worker`, `retention_worker`, `webhook_worker` and
   `migrate`. This is a tag reference, not a build — never `docker compose build` on the
   VM.
2. `docker compose up -d --no-build` (api + four workers).
3. Expect the readiness healthcheck to probe `/healthz` (not `/health`): a container that
   reports `healthy` while the database is down would be a regression of the fix in
   `docker-compose.yml`.
4. Confirm: `docker ps` — api and all four workers `Up`, api health `healthy`
   after `start_period` (45 s budget for the ~20 s ML-stack boot).

Abort condition: any container restart-looping or never becoming healthy.

## 7. Gate G — HTTPS ingress (no domain: sslip.io + Caddy)

Topology: **one HTTPS hostname** serving the frontend and proxying `/api/v1` to the API
on loopback. This matches the frontend exactly (`VITE_API_BASE_URL=/api/v1`, same
origin), so CORS needs no wildcard — `CORS_ALLOW_ORIGINS` is set to the single origin
`https://api.<static-ip>.sslip.io`.

1. Install Caddy (single binary/package; no build toolchain needed).
2. `/etc/caddy/Caddyfile`:

```
:443 {
	encode gzip
	root * /srv/poa/frontend
	try_files {path} /index.html
	file_server

	# `handle`, NOT handle_path: the backend routes keep the /api/v1 prefix,
	# so the prefix must NOT be stripped.
	handle /api/v1/* {
		reverse_proxy 127.0.0.1:8000
	}
}

http:// {
	redir https://{host}{uri} 308
}
```

3. Frontend assets: build the frontend image **with** `VITE_API_BASE_URL=/api/v1`,
   `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` present (Vite bakes `VITE_*`
   at build time; the publishable key is a browser-visible client credential by design),
   serve `dist/` from `/srv/poa/frontend`. Never build with a service-role/secret key —
   pattern-scan `dist/` for `sb_secret_`/`service_role` before shipping it.
4. Host firewall: allow only TCP 80 and 443 inbound (plus the restricted SSH rule). The
   API stays bound to `127.0.0.1:8000`; 5432/6379/9000/9001 remain unpublished.
5. Certificate: Caddy obtains/renews Let's Encrypt certificates automatically for the
   sslip.io hostname; if ACME HTTP-01 fails (sslip.io quirks), fall back to Caddy's
   internal CA **only** for a test pass and record that a trusted certificate still
   needs a real domain — do not call that production-ready.

**HTTPS path verification (must pass before the release is called verified):**

```
curl -si https://api.<ip>.sslip.io/                      | head -1   # 200, SPA
curl -si https://api.<ip>.sslip.io/api/v1/auth/me        | head -1   # 401 anonymous
curl -si https://api.<ip>.sslip.io/healthz               | head -1   # 200
curl -si "https://api.<ip>.sslip.io/api/v1/../auth/me"   | head -1   # must NOT reach the API
```

The last probe is the prefix check: `handle` must not strip `/api/v1`. A request that
resolves as if the prefix had been stripped is a gate failure.

Abort condition: no trusted certificate (unless the owner explicitly accepts the
internal-CA limitation and records it), any path assertion failing, or any datastore
port reachable from the internet.

## 8. Gate R — production reviewer provisioning (explicit, auditable, owner-approved)

This is the only step that writes an identity row into production, and it runs **after**
Gate C's proven backup and Gate D's verified migration. Automatic user provisioning stays
disabled: a token whose `sub` has no linked row is refused with 401 and that behaviour is
re-proven below.

Owner approval line (filled in during the release window):

```
Approved by: ______________   UTC: ______________   Scope: one reviewer row, least privilege
```

1. Bootstrap problem, stated plainly: with dev tokens disabled, no API caller can
   authenticate until one user row is linked to the real Supabase `sub`, so the *first*
   link cannot be made through the API. It is therefore made as a single audited SQL
   statement executed with the migration identity inside this window:
   - **Option 1 (preferred):** link the existing production administrator row:
     `UPDATE users SET identity_provider='supabase', external_subject='<real sub>'
     WHERE id='<existing admin id>';`
   - **Option 2:** insert one reviewer row with `identity_provider='supabase'`,
     `external_subject='<real sub>'`, `status='active'`, plus its role assignment.
   The `<real sub>` is the `sub` claim of the owner's reviewer account, read from a real
   sign-in session (an identifier, not a secret). Record: the statement, the `users` row
   count before/after (changes only by this approved step), and an audit ledger entry
   describing the provisioning action with the releasing operator as actor.
2. Least privilege: the reviewer receives only the PoA reviewer role and its scope — no
   GLOBAL `user.manage`, no `role.manage`, no project-ownership powers.
3. Verify live over HTTPS:
   - owner signs in through the frontend; `GET /api/v1/auth/me` returns the mapped
     principal with the expected roles/permissions;
   - positive authorization: reviewer reads evidence and its own projects;
   - negative authorization: 403 on a privileged route (e.g. `POST /auth/users`), 404/403
     on another organization's project, `GET /metrics` 401 without `metrics.read`;
   - **no auto-provisioning:** an unlinked `sub` still answers 401, and the `users` count
     is unchanged by that attempt.

Abort condition: owner approval not given, `sub` unavailable, or any negative
authorization probe returning anything but 401/403/404.

## 9. Gate H — live smoke tests (all must pass on the deployed HTTPS origin)

1. `curl https://…/healthz` → 200 with `postgresql`, `redis`, `storage` healthy;
   `curl https://…/ready` → 200.
2. Anonymous → 401 on every protected route (spot-check `/auth/me`, `/projects`,
   `/evidence`, `/audit`).
3. Reviewer sign-in → project list loads; upload one evidence file → quarantine accepted;
   review decision recorded **with the caller as actor** in the audit ledger.
4. `GET /metrics` → 401 without `metrics.read`.
5. Worker containers: all four `Up`, no error flood in `docker logs --since 10m`.
6. Dependency failure drill (safe, reversible): `docker stop pofa_db` briefly →
   `/healthz` and `/ready` turn 503 within one probe interval and the container reports
   `unhealthy`; `docker start pofa_db` → recovers to `healthy`. This is the property the
   compose healthcheck fix exists for; if `/health` is what flips, the fix is not in
   production.
7. `docker stop -t 10 pofa_api` → clean SIGTERM shutdown (exit 0), then start again.
8. Log stream reviewed for leaked tokens/secrets (grep for `eyJ`, `sb_secret_`,
   `service_role`).

Abort condition: any failed item. Recovery per §10.

## 10. Recovery (what to do when a gate fails)

- **Before Gate D:** restore the Gate C dump into `poa_prod` and stop. Nothing has
  changed; the service still runs the old image.
- **After Gate D, before Gate F:** schema is additive and forward-only. The old image
  serves and writes against the migrated schema (proven 20/20 in the rehearsal), so the
  safe recovery is: keep the old image running, verify row counts, and investigate with
  the fresh dump as the recovery object. No downgrade.
- **After Gate F:** point the compose services back at the previous image tag
  (`poa-backend:be037a`) and `docker compose up -d --no-build`. Old-code/new-schema is
  the supported pairing; new-code/old-schema is not.
- **If the schema state looks wrong:** stop. Do not `--stamp`, do not downgrade. Restore
  from the verified dump and re-run Gate D from the top.
- In every case: append-only audit history is preserved (it is never rewritten), record
  what was observed, and re-run the affected gate rather than skipping it.

## 11. Evidence to record during the release

Timestamped outputs of: Gate A state capture; Gate B checksums and image id; Gate C dump
size/sha256/restore-proof row counts; Gate D revision + vocabulary + row counts +
`alembic check`; Gate E key *names* present (never values); Gate F `docker ps` and
health states; Gate G path assertions; Gate R approval line, `users` counts and probes;
Gate H smoke results. These go into the milestone report as measured results, clearly
separated from anything merely rehearsed.
