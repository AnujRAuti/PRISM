---
name: dependency-security-audit
description: Inventory third-party dependencies, map them to known CVEs, judge reachability and exploitability, and produce an upgrade or mitigation plan with an SBOM.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: low
---

# Dependency Security Audit

## 1. Purpose

Know what third-party code is in the build, which versions are vulnerable, whether the vulnerability is reachable in your usage, and what to do about it. This skill covers SBOM generation, vulnerability matching, false-positive filtering (dev-only, unreachable, non-exploitable configuration), patch strategy, and supply-chain hygiene (lockfiles, integrity, typosquat checks).

**Scope:** analysis of artifacts you build. No exploitation of third-party services.

## 2. Activation Conditions

- Before a release, or on a recurring schedule (weekly/daily).
- A CVE alert arrives (Dependabot, Renovate, OSV, GitHub Advisory).
- Adding a new dependency or major version bump.
- Compliance requirements for SBOMs (EO 14028, EU CRA, customer questionnaires).
- Keywords: dependency audit, CVE, SBOM, supply chain, vulnerable package, typosquat, lockfile, transitive dependency.

## 3. When Not to Use

- Source-code logic flaws (use sast-analysis).
- Container OS packages (use container-security, though overlap exists).
- Secrets exposure (use secret-detection).
- License compliance only (different tooling and legal review).

## 4. Required Context

1. Language ecosystems and lockfiles present (`package-lock.json`, `poetry.lock`, `go.sum`, `Cargo.lock`, `pom.xml`).
2. Build vs. runtime separation (which deps ship to production).
3. Deployment model (container image tag + digest, serverless bundle).
4. Risk tolerance/timeline policy per severity (e.g. critical ≤ 48 h).
5. Whether the vulnerable code path is actually used (reachability).

## 5. Operating Procedure

1. **Generate an inventory**: direct dependencies, then full transitive tree, then SBOM.
2. **Resolve exact versions** from lockfiles—not from manifests with ranges.
3. **Match against vulnerability sources**: OSV, GitHub Advisory Database, vendor advisories.
4. **Filter noise**: dev-only deps, unreachable code, non-default vulnerable configurations, platform-specific code not shipped.
5. **Assess exploitability** for each surviving finding: is the vulnerable function called with attacker-influenced input? Are there preconditions (e.g. requires `parse_unknown=True`)?
6. **Rank** by severity, exposure (internet-facing?), and patch availability.
7. **Choose a response**: upgrade (preferred), patch/fork (temporary), configuration mitigation, replace, or documented acceptance with expiry.
8. **Upgrade safely**: read the changelog for breaking changes, run the full test suite, verify the patch version actually appears in the lockfile.
9. **Automate**: Dependabot/Renovate with grouped updates, an OSV scan in CI, and a policy gate for new critical CVEs.
10. **Track** the remediation deadline per finding and close with evidence (scan output plus lockfile diff).

## 6. Tools and Technologies

| Ecosystem | Tools |
|---|---|
| Python | `pip-audit`, `safety`, `poetry export` + OSV |
| Node/TS | `npm audit`, `pnpm audit`, `yarn npm audit` |
| Go | `govulncheck` (reachability-aware) |
| Rust | `cargo audit`, `cargo deny` |
| Java | OWASP Dependency-Check, `gradle dependencyUpdates` |
| Multi | `osv-scanner`, `trivy fs`, `grype`, `syft` (SBOM) |
| Automation | Dependabot, Renovate |
| Policy | `cargo deny`, OPA/Conftest on SBOM |

## 7. Practical Implementation

**Generate SBOM and scan (multi-ecosystem):**

```bash
syft dir:. -o spdx-json=sbom.spdx.json
grype sbom:sbom.spdx.json --fail-on high
osv-scanner --lockfile=package-lock.json --lockfile=poetry.lock
```

**Python with reachability context:**

```bash
pip-audit -r requirements.txt --strict --desc
# fix a single package
pip-audit -r requirements.txt --fix --dry-run
```

**Go: reachability-aware vuln check (only reports actually-called vulnerable symbols):**

```bash
go install golang.org/x/vuln/cmd/govulncheck@latest
govulncheck ./...
```

**Node: audit production deps only:**

```bash
npm audit --omit=dev --audit-level=high
npm ls minimist            # see who pulls a transitive dep
npm explain minimist
```

**Rust: deny policy (`deny.toml`):**

```toml
[vulnerability]
version = 2
deny = ["unmaintained"]

[licenses]
allow = ["MIT", "Apache-2.0", "BSD-3-Clause"]
```

```bash
cargo deny check advisories licenses
```

**CI gate (GitHub Actions):**

```yaml
name: deps
on:
  pull_request:
  schedule: [{cron: "0 6 * * *"}]
permissions: {contents: read}
jobs:
  osv:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: google/osv-scanner-action/osv-scanner-action@v1
        with:
          scan-args: |-
            --lockfile=./package-lock.json
            --lockfile=./requirements.txt
```

**Typosquat / confusion check before adding a dependency:**

```bash
# Compare against the canonical package; check downloads, repo link, maintainer history
curl -s https://pypi.org/pypi/requests/json | jq -r '.info.home_page, .info.project_urls'
npm view express repository.url maintainers time.created
```

## 8. Quality Standards

- Findings are resolved from lockfiles, not version ranges.
- Every CVE entry states reachability verdict and evidence.
- Fixes are verified by re-scanning the same SBOM.
- No unmanaged "ignored vulnerabilities" list; exceptions have owners and expiry dates.
- SBOMs are generated per release and stored with the artifact.
- New dependencies pass a hygiene check (maintainers, repo, age, download counts, license).

## 9. Verification and Testing

```bash
grype sbom:sbom.spdx.json -o table
govulncheck ./...            # expect "No vulnerabilities found" for fixed packages
npm audit --omit=dev; echo "exit=$?"
git diff -- package-lock.json | grep -E '^\+.*"(version|resolved)"'
pytest -q && npm test -- --run    # full suite after upgrade
```

Evidence: before/after scan output, lockfile diff showing the patched version, and green tests.

## 10. Security Considerations

- Do not install a package to inspect it; read metadata and source from the registry or a vendored copy instead.
- `npm audit fix --force` and similar commands can introduce breaking changes or downgrade security—review diffs.
- Verify lockfile integrity fields (`integrity`, `go.sum`, `Cargo.lock` checksums) are committed and reviewed; an unexpected hash change is a supply-chain signal.
- Watch for dependency confusion: internal package names must be scoped and registry-configured to prevent public substitution.
- Package install scripts execute arbitrary code (`npm` postinstall, `pip` build backend): use `--ignore-scripts` in CI where possible and vet first-time installs.
- Prefer pinned, reproducible installs; avoid `latest` in production.

## 11. Failure Handling

- **No patched version available:** apply configuration mitigation, vendor a patch with a documented diff, or replace the dependency; set a review date.
- **Upgrade breaks tests:** read the changelog for behavioral changes; pin the nearest safe version and schedule the breaking upgrade separately.
- **Transitive dependency is the culprit:** use overrides/resolutions (`npm overrides`, `pip` constraints, `cargo update -p`) and verify with `npm ls`/`pip show`.
- **Scanner disagrees with vendor:** check whether the advisory applies to the exact range; OSV records include affected version ranges—read them.
- **Too many findings at once:** fix internet-facing, high-CVSS, reachable issues first; batch the rest into a scheduled PR.

## 12. Expected Deliverables

1. Dependency inventory with direct/transitive split.
2. SBOM (SPDX or CycloneDX) stored with the release.
3. Vulnerability findings with reachability verdicts.
4. Remediation plan with deadlines by severity.
5. Applied upgrades and lockfile diffs.
6. CI automation and policy configuration.

## 13. References

- OSV — https://osv.dev/ and https://google.github.io/osv-scanner/
- GitHub Advisory Database — https://github.com/advisories
- NVD — https://nvd.nist.gov/
- `pip-audit` — https://pypi.org/project/pip-audit/
- `govulncheck` — https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck
- `cargo audit` — https://rustsec.org/
- Syft / Grype — https://github.com/anchore/syft , https://github.com/anchore/grype
- CycloneDX — https://cyclonedx.org/specification/overview/
- SLSA — https://slsa.dev/
