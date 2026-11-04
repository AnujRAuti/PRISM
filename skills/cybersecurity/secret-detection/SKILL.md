---
name: secret-detection
description: Find, triage, and remediate leaked credentials in git history, working trees, and CI logs—without exposing secret values—then rotate and prevent recurrence.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: high
---

# Secret Detection

## 1. Purpose

Discover credentials that should not exist in repositories: API keys, tokens, private keys, database URLs with passwords, and `.env` files. Then handle them safely—triage by validity, rotate, purge history where warranted, and add preventive controls. The critical discipline is that detection output must never itself become a new leak.

**Scope:** repositories and artifacts you own or are authorized to scan. Never scan third-party repos' secrets for use.

## 2. Activation Conditions

- Before making a repository public or accepting external contributors.
- A commit added a suspicious string (key-like pattern, `.env`, `id_rsa`).
- Security review, due diligence, or incident triage.
- Setting up pre-commit and CI controls.
- Keywords: leaked secret, API key, token, credential leak, gitleaks, trufflehog, .env committed, rotate keys, git history.

## 3. When Not to Use

- General code review (use secure-code-review).
- Managing secrets at runtime (vault/KMS design) — related but distinct.
- When the "secret" is a public identifier by design (publishable Stripe key, Firebase client config, OAuth client ID). Verify before raising alarms.

## 4. Required Context

1. Repository access (read-only clone) and whether history scanning is allowed.
2. Which cloud/provider accounts the exposed keys belong to (for rotation).
3. Whether the repo is public or has ever been public/forked.
4. Existing secret-management system (Vault, AWS Secrets Manager, SOPS, GitHub Actions secrets).
5. Incident policy: who must be notified, and the rotation SLA.

## 5. Operating Procedure

1. **Scan the working tree first** (fast): `trufflehog filesystem . --only-verified`, `gitleaks detect --no-git`.
2. **Scan full history** with `--log-opts=--all`; this is where old leaks live.
3. **Triage each hit**: pattern match (possible false positive) → validation (is it live?) → scope (what can it access?).
4. **Never print the secret value** in reports, chat, or tickets. Record a truncated fingerprint: first 4 and last 4 characters plus a SHA-256 of the value.
5. **Classify severity** by capability: cloud root/admin key > CI deploy key > read-only analytics token > test key.
6. **Rotate immediately** through the provider console/API; rotation is the fix, deletion of the commit is secondary.
7. **Assess exposure window**: was the repo public? for how long? who forked it? check provider audit logs for use.
8. **Purge history only after rotation** and with authorization (`git filter-repo`), then force-push and invalidate clones.
9. **Add prevention**: pre-commit hooks, CI scanning, `.gitignore` rules, secret scanning push protection.
10. **Move the value** to a proper store and update code to read from env/injection at deploy time.
11. **Document** the incident timeline and postmortem actions.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| `gitleaks` | Fast regex-based scan with entropy and allowlists |
| `trufflehog` | Verification against live providers (uses the credential—careful) |
| GitHub secret scanning + push protection | Platform prevention |
| `detect-secrets` (Yelp) | Baseline-based scanning |
| `git filter-repo` | History rewriting |
| `git-secrets` | Pre-commit hooks (AWS patterns) |
| Vault / SOPS / cloud secret managers | Storage |
| `pre-commit` | Hook orchestration |

## 7. Practical Implementation

**Gitleaks scan and report (no secret values in output):**

```bash
gitleaks detect --source . --log-opts="--all" --report-format json --report-path leaks.json
# leaks.json contains Secret fields — treat as sensitive; do not commit
python - <<'PY'
import json, hashlib
for leak in json.load(open("leaks.json")):
    s = (leak.get("Secret") or "")
    fp = hashlib.sha256(s.encode()).hexdigest()[:12] if s else "-"
    print(f"{leak['RuleID']:28} {leak['File']}:{leak.get('StartLine')} sha256:{fp} len={len(s)}")
PY
```

**TruffleHog (verification is a live check—only run on your own credentials):**

```bash
trufflehog git file://. --only-verified --no-update --json > verified.json
```

**Pre-commit hook (`.pre-commit-config.yaml`):**

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ["--baseline", ".secrets.baseline"]
```

```bash
pre-commit install
pre-commit run --all-files
```

**CI scan gate:**

```yaml
- name: gitleaks
  run: gitleaks detect --source . --redact --exit-code 1 --verbose
```

**History purge (after rotation, with authorization):**

```bash
pip install git-filter-repo
git clone --mirror https://git.example.com/team/app.git app.git
cd app.git
git filter-repo --path secrets/prod.env --invert-paths
# then: coordinate force-push, invalidate CI tokens, notify all clones
git push --force --all && git push --force --tags
```

**Safe container/CI usage:**

```bash
# read secrets at runtime, never bake into image
docker run --env-file /dev/null -e DB_PASSWORD="$(vault kv get -field=password secret/db)" app
```

## 8. Quality Standards

- No secret value appears in any report, log, or chat message produced during the audit.
- Every finding has: location, type, validity status, capability, and rotation status.
- Rotation precedes history rewriting, always.
- Prevention controls (pre-commit + CI) are in place before the task closes.
- Public-repo exposure is treated as compromised even if "deleted 5 minutes later".
- Evidence of rotation includes provider timestamps, not just claims.

## 9. Verification and Testing

```bash
gitleaks detect --source . --redact --exit-code 1         # expect: no leaks found
git log --all -p -S 'AKIA' | head                        # spot-check AWS key patterns
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest detect --source /repo --redact
```

Post-rotation checks: old key returns `401/403` from the provider; new key works from the deployment environment; pre-commit blocks a test commit containing a fake key.

## 10. Security Considerations

- Detection output is sensitive. Store reports in an access-controlled location and delete them after rotation.
- `trufflehog --only-verified` sends the credential to the provider to validate; do this only for keys you own and only from a trusted network.
- Do not exfiltrate found secrets to third-party bots, pastebins, or AI services.
- Assume any secret in a public repo or shared CI log is compromised; also revoke derived credentials (refresh tokens, sessions).
- Check provider audit logs for abuse during the exposure window, especially for cloud keys (crypto mining is common within minutes).
- Force-pushes do not remove clones, forks, or cached views—treat the secret as permanently public.

## 11. Failure Handling

- **Provider has no revoke API:** rotate by creating a new key, deploying it, then deleting the old one after verification.
- **Secret is used in many systems:** maintain a rotation matrix (system → env var → owner) and rotate in dependency order.
- **Cannot rewrite history (protected branch, many forks):** rotate and accept that the secret is public; document the decision.
- **False positives overwhelm the scan:** maintain a baseline file and targeted allowlists with reasons, not global disable.
- **Developer committed a `.env` with many values:** treat every value as compromised; rotate in batch.

## 12. Expected Deliverables

1. Scan report with redacted fingerprints and locations.
2. Triage table: finding, validity, capability, severity, owner.
3. Rotation evidence per secret.
4. History-purge record (if performed) with authorization reference.
5. Prevention configuration (pre-commit, CI, push protection).
6. Incident summary and follow-up actions.

## 13. References

- Gitleaks — https://github.com/gitleaks/gitleaks
- TruffleHog — https://github.com/trufflesecurity/trufflehog
- detect-secrets — https://github.com/Yelp/detect-secrets
- git-filter-repo — https://github.com/newren/git-filter-repo
- GitHub secret scanning — https://docs.github.com/en/code-security/secret-scanning
- NIST SP 800-57 (key management) — https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- OWASP Secrets Management Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
