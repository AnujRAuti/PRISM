---
name: sast-analysis
description: Run, tune, and triage static application security testing—Semgrep, CodeQL, bandit, gosec—to produce high-signal findings integrated into CI without noise.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: low
---

# SAST Analysis

## 1. Purpose

Use static analysis to find security defects in source code systematically, with rules that match the project's stack and a triage process that removes false positives. The goal is a CI gate with a low false-positive rate that developers trust. This skill covers tool selection, rule configuration, baseline adoption on existing code, triage, and fixing findings.

**Scope:** static analysis of code you own. No execution against running systems.

## 2. Activation Conditions

- Adding security scanning to a repository or CI pipeline.
- Triaging a scan report with many findings.
- Writing custom rules for a project-specific sink (e.g. internal `safe_query` wrapper).
- Reviewing a dependency-free codebase for injection classes.
- Keywords: SAST, static analysis, Semgrep, CodeQL, bandit, gosec, lint security, false positive, taint analysis.

## 3. When Not to Use

- Runtime/black-box testing (use api-security-testing).
- Dependency CVEs (use dependency-security-audit).
- Secrets detection (use secret-detection).
- Rules with no semantic support for the language—results will be noise.

## 4. Required Context

1. Languages present and their build systems.
2. Existing CI configuration and where a scan step can run.
3. Current baseline: has the code ever been scanned? How many findings?
4. Framework idioms (does the ORM parameterize? is there a crypto wrapper?).
5. Team capacity for triage and a policy for blocking vs. non-blocking.

## 5. Operating Procedure

1. **Inventory languages** (`cloc`, `github-linguist`) and choose tools: Semgrep (multi-language, fast, easy custom rules), CodeQL (deep dataflow, heavier), plus language-specific (`bandit`, `gosec`, `staticcheck`).
2. **Start with a curated ruleset**, not "all rules": `p/security-audit`, `p/owasp-top-ten`, `p/secrets` for Semgrep; `security-and-quality` for CodeQL.
3. **Run in report-only mode** first; record the baseline count.
4. **Triage into three buckets**: true positive (fix), false positive (suppress with justification), needs-context (manual review).
5. **Suppress narrowly** with inline comments containing a reason and an owner, never file-wide disable.
6. **Write custom rules** for project sinks and safe wrappers so the tool understands your abstractions.
7. **Set the gate**: block only on `ERROR`-severity, security-relevant rules; warn on the rest. Ratchet gradually.
8. **Integrate**: PR annotations (SARIF upload), nightly full scan, and a dashboard.
9. **Fix findings** in priority order: injection and authz first, then crypto, then info-level.
10. **Review the rule pack quarterly**; remove rules that only generate noise, add rules for new recurring bugs.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| Semgrep OSS/Pro | Multi-language, fast, custom rules |
| CodeQL | Deep taint analysis (Java, JS/TS, Python, Go, C#) |
| `bandit` | Python security linter |
| `gosec` | Go security linter |
| `staticcheck` | Go correctness + security-adjacent |
| `eslint-plugin-security` | JS/TS |
| `cppcheck` / `clang-tidy` | C/C++ |
| `clippy` | Rust |
| SARIF | Standard output format for CI UIs |
| GitHub code scanning | SARIF ingestion and PR annotations |

## 7. Practical Implementation

**Semgrep baseline run:**

```bash
pip install semgrep
semgrep --config p/security-audit --config p/owasp-top-ten \
  --sarif --output sast.sarif --severity ERROR .
semgrep --config p/secrets --json --output secrets.json .
```

**Custom rule: forbid f-string SQL (Python):**

```yaml
rules:
  - id: py-sql-fstring
    languages: [python]
    severity: ERROR
    message: >-
      SQL built with an f-string. Use parameterized queries ($1 / %s placeholders).
    metadata:
      cwe: ["CWE-89: SQL Injection"]
      owasp: ["A03:2021 Injection"]
    patterns:
      - pattern-either:
          - pattern: $CUR.execute(f"...")
          - pattern: $CUR.execute("..." + $X)
          - pattern: $CUR.execute("...".format(...))
          - pattern: $CUR.executemany(f"...")
```

**Custom rule: recognize a safe wrapper (suppress downstream findings):**

```yaml
rules:
  - id: py-safe-path-ok
    languages: [python]
    severity: INFO
    message: safe_join() enforces containment; no traversal possible here.
    patterns:
      - pattern: safe_join(...)
```

**Inline suppression with justification:**

```python
cursor.execute(query)  # nosemgrep: py-sql-fstring -- query is a static constant from migrations
```

**Bandit config (`pyproject.toml`):**

```toml
[tool.bandit]
exclude_dirs = ["tests", "migrations"]
skips = ["B101"]           # assert_used: fine in non-production test helpers
```

```bash
bandit -r src -c pyproject.toml -f sarif -o bandit.sarif
```

**GitHub Actions with SARIF upload:**

```yaml
name: sast
on: [pull_request, push]
permissions:
  contents: read
  security-events: write
jobs:
  semgrep:
    runs-on: ubuntu-latest
    container: {image: semgrep/semgrep}
    steps:
      - uses: actions/checkout@v4
      - run: semgrep scan --config p/security-audit --sarif --output semgrep.sarif .
      - uses: github/codeql-action/upload-sarif@v3
        with: {sarif_file: semgrep.sarif}
```

**CodeQL workflow (extract):**

```yaml
- uses: github/codeql-action/init@v3
  with:
    languages: python, javascript-typescript
    queries: security-and-quality
- uses: github/codeql-action/analyze@v3
```

## 8. Quality Standards

- Every suppression has a reason and an owner; no blanket disables.
- The gate blocks only on high-confidence security rules to keep trust.
- Baseline counts are tracked over time (findings must trend down).
- Custom rules reference the CWE they detect.
- Sarif output is uploaded so findings appear inline on the PR.
- True positives are fixed with a regression test, not just patched silently.

## 9. Verification and Testing

- Write a deliberately vulnerable fixture in a test file and confirm the rule fires (`semgrep --test`).
- Confirm the fixed code no longer triggers the rule.
- Verify suppression syntax works (run with and without `nosemgrep`).
- Check the CI gate blocks a PR containing a known-bad pattern, and passes a clean PR.
- Review SARIF in the code-scanning UI for correct file/line mapping.

## 10. Security Considerations

- Semgrep/CodeQL may upload code to a cloud service depending on configuration; verify data handling and use self-hosted/OSS modes for private code.
- Do not paste proprietary code into web-based rule playgrounds.
- Scan artifacts (SARIF) may reveal file paths and code snippets; restrict repository access accordingly.
- Untrusted PRs can modify scanner configs to disable rules: run scanning on the base branch configuration for `pull_request_target` workflows, and never give fork PRs secrets.
- Treat a sudden finding spike as suspicious (possible malicious code injection), not just noise.

## 11. Failure Handling

- **Hundreds of baseline findings:** adopt a baseline file (`--baseline-commit`) and block only on new findings; fix the old ones on a schedule.
- **Too many false positives:** reduce to high-confidence rule packs, add safe-wrapper rules, and document project conventions so rules can be tuned.
- **Scanner cannot parse the build:** provide a compile database (`bear -- make`, `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`) or use a build-mode that works.
- **Rule does not understand a framework:** write a custom rule modeling the framework's safe/unsafe APIs.
- **Slow scans:** restrict to changed paths in PRs, run full scans nightly.

## 12. Expected Deliverables

1. Tool and ruleset selection with rationale.
2. Scanner configuration committed to the repo.
3. Baseline report and triage decisions.
4. Custom rules for project-specific patterns.
5. CI integration with SARIF upload and gating policy.
6. Fix commits and regression tests for confirmed findings.
7. A short runbook for maintainers: how to handle a new finding.

## 13. References

- Semgrep documentation — https://semgrep.dev/docs/
- Semgrep rule syntax — https://semgrep.dev/docs/writing-rules/overview/
- CodeQL documentation — https://codeql.github.com/docs/
- GitHub code scanning — https://docs.github.com/en/code-security/code-scanning
- Bandit — https://bandit.readthedocs.io/
- gosec — https://github.com/securego/gosec
- SARIF specification — https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
- CWE — https://cwe.mitre.org/
