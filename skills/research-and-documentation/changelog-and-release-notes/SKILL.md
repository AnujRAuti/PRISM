---
name: changelog-and-release-notes
description: Communicate change to users—Keep a Changelog structure, semver discipline, audience-specific release notes, migration guides, and automated drafting from commits.
metadata:
  domain: research-and-documentation
  version: 1.0.0
  risk: low
---

# Changelog and Release Notes

## 1. Purpose

Tell users what changed, what it means for them, and what they must do. Release communication fails when the changelog is a copy of `git log` ("fix stuff", "refactor"), when breaking changes are buried, or when there are three inconsistent sources of truth. This skill covers changelog structure, semantic versioning intent, writing for different audiences, migration guides, and automation that drafts rather than dumps.

**Scope:** your own release communication. Do not disclose unpatched vulnerabilities in release notes before coordinated disclosure; do not include customer identifiers in internal changelogs.

## 2. Activation Conditions

- Releasing a version of a library, API, CLI, or hosted product.
- Breaking change requires user action.
- Support is repeatedly asked "what changed?" or "why did this stop working?".
- Version numbers are applied inconsistently.
- Keywords: changelog, release notes, semantic versioning, semver, breaking change, migration guide, deprecation, keep a changelog, conventional commits, release drafter, upgrade notes.

## 3. When Not to Use

- Internal commit history (that is `git log`).
- Marketing announcements (different purpose and channel).
- Documentation of current behavior (use technical-writing / api-documentation).

## 4. Required Context

1. Artifact type: library, service API, CLI, mobile app, or hosted product.
2. Audience: developers integrating, end users, or internal operators.
3. Versioning policy and current version.
4. Compatibility commitments and deprecation windows.
5. Release cadence and automation available.

## 5. Operating Procedure

1. **Adopt Keep a Changelog + SemVer** as the baseline: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, and `MAJOR.MINOR.PATCH`.
2. **Write entries for users, not authors**: what changed in their terms, why it matters, and what to do.
3. **Make breaking changes impossible to miss**: a `### Breaking` heading at the top with a migration link, and a MAJOR bump.
4. **Maintain `Unreleased` continuously** so the changelog is written when the change is fresh, not reconstructed at release.
5. **Draft from conventional commits** with automation, but require human editing: commit subjects are inputs, not output.
6. **Split audiences** where needed: developer changelog (API/library) versus product release notes (end users).
7. **Include upgrade instructions for every breaking or behavior-changing item**, with a before/after snippet.
8. **Link to the change**: PR, issue, or docs page, so readers can go deeper.
9. **State security fixes** clearly without revealing exploit detail before coordinated disclosure.
10. **Publish with the release** and keep a permanent archive; link the changelog from the README, docs home, and package metadata.
11. **Verify at release time** that the changelog matches the actual diff: no undocumented breaking change ships.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Format | Keep a Changelog 1.1.0, Conventional Commits |
| Automation (JS) | Changesets, semantic-release, release-please |
| Automation (Python) | `towncrier`, `commitizen`, `python-semantic-release` |
| Automation (Go/Rust) | `goreleaser` changelog, `cargo-release`, `git-cliff` |
| Drafting | GitHub release drafter, `git-cliff` templates |
| Verification | `conventional-changelog` lint, diff review of public API |

## 7. Practical Implementation

**Changelog structure (Keep a Changelog):**

```markdown
# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `GET /v1/orders/{id}/refunds` lists refunds with cursor pagination. (#8812)

### Fixed
- Refunds above the remaining balance now return `422 /validation` instead of `500`. (#3456)

## [2.14.0] — 2026-11-04

### Breaking
- `POST /v1/orders` now requires the `Idempotency-Key` header. Requests without it
  return `400 /missing-idempotency-key`.
  **Action required:** send a unique key per distinct request (see the
  [migration guide](docs/migrate/idempotency.md)).

### Added
- Order creation supports up to 100 lines (was 20).
- `Retry-After` header on `429` responses.

### Changed
- `total_cents` is now computed server-side and ignores any client-supplied value.

### Deprecated
- `POST /v1/orders/legacy` — sunset 2027-01-31; use `POST /v1/orders`.

### Security
- Updated `cryptography` to 43.0.3 to address a known advisory. No user action required.

## [2.13.2] — 2026-10-21

### Fixed
- Cursor pagination no longer duplicates rows when orders are created between pages. (#3311)
```

**Entry-writing rules with good and bad examples:**

```markdown
BAD:  "Fix bug"
BAD:  "Refactor checkout service"
BAD:  "Update dependencies"
GOOD: "Refunds above the remaining balance return 422 instead of 500. (#3456)"
GOOD: "Checkout p99 latency reduced from 2.4s to 0.4s by moving session state to Redis."
GOOD: "Upgraded cryptography to 43.0.3 to address CVE-XXXX-YYYYY; no action required."
```

**Conventional Commits enabling automation:**

```text
feat(orders): support up to 100 lines per order
fix(refunds): reject amounts above remaining balance
feat(api)!: require Idempotency-Key on order creation     # ! marks breaking
```

```python
# scripts/changelog_from_commits.py — DRAFT generator; humans edit the result
import re, subprocess
from collections import defaultdict

TYPES = {"feat": "Added", "fix": "Fixed", "perf": "Changed", "refactor": "Changed",
         "docs": None, "test": None, "chore": None, "build": None, "ci": None}

pattern = re.compile(r"^(?P<type>\w+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<subject>.+)$")
out = defaultdict(list)

log = subprocess.run(["git", "log", "--no-merges", "--format=%s|%h", "v2.13.2..HEAD"],
                     capture_output=True, text=True, check=True).stdout

for line in log.strip().splitlines():
    subject, sha = line.rsplit("|", 1)
    m = pattern.match(subject)
    if not m:
        continue
    section = "Breaking" if m["bang"] else TYPES.get(m["type"])
    if not section:
        continue
    scope = f"**{m['scope']}:** " if m["scope"] else ""
    out[section].append(f"- {scope}{m['subject']} ({sha})")

for section in ["Breaking", "Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]:
    if out[section]:
        print(f"### {section}")
        print("\n".join(out[section]))
        print()
```

Automation produces a starting draft; a human rewrites each line for user impact and removes internal-only noise.

**Changesets (monorepo, per-change files):**

```markdown
---
"@acme/orders-client": major
"@acme/api-types": minor
---

Require `Idempotency-Key` on order creation.

Requests without the header now fail with `400 /missing-idempotency-key`.
Send a unique key per distinct request; replaying the same key with an identical
body returns the original response.
```

```bash
npx changeset          # author a change file with the PR
npx changeset version  # bumps versions + writes CHANGELOG entries at release
```

**towncrier fragment (Python):**

```ini
# pyproject.toml
[tool.towncrier]
package = "orders_api"
filename = "CHANGELOG.md"
directory = "changes"
title_format = "{version} ({project_date})"

[[tool.towncrier.type]]
directory = "breaking"
name = "Breaking"
showcontent = true

[[tool.towncrier.type]]
directory = "added"
name = "Added"
showcontent = true
```

```text
changes/3456.bugfix.md  ->  "Refunds above the remaining balance now return 422 instead of 500."
```

**Migration guide (linked from a breaking entry):**

```markdown
# Migrating to 2.14: required Idempotency-Key

## What changed
`POST /v1/orders` rejects requests without an `Idempotency-Key` header.

## Who is affected
Any client creating orders.

## Before
```bash
curl -X POST https://api.example.com/v1/orders -H "Authorization: Bearer $KEY" -d '{...}'
```

## After
```bash
curl -X POST https://api.example.com/v1/orders \
  -H "Authorization: Bearer $KEY" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{...}'
```

## Choosing a key
Use one key per distinct logical request. Reusing a key with a **different** body
returns `409 /idempotency-mismatch`. Store the key alongside your retry logic so
retries reuse it.

## Timeline
- 2.14.0 (2026-11-04): header required; missing header → 400.
- 2.13.x: header accepted and ignored.
```

**End-user release notes (different voice from the developer changelog):**

```markdown
## What's new in version 4.8

**Faster checkout.** Payments now complete in under half a second, even during sales.

**Clearer refund errors.** If you try to refund more than is left on an order,
the app now tells you the remaining amount instead of showing a generic error.

**Security update.** We updated a library used to protect your data. Nothing you
need to do.

Known issue: exporting more than 10,000 rows can take up to a minute; a fix is
planned for 4.9.
```

**Release-time verification checklist:**

```text
[ ] Changelog section exists for this version (not still under Unreleased)
[ ] Every breaking change is under Breaking, with a MAJOR bump
[ ] Public API diff reviewed (openapi-diff / typedoc / cargo public-api)
[ ] Migration guide linked for each breaking change
[ ] Security entries checked with the security owner for disclosure timing
[ ] Version numbers consistent across package.json/pyproject.toml/Cargo.toml/tags
[ ] `Unreleased` reset to empty after the release
```

## 8. Quality Standards

- Every release has a dated changelog entry with sections that match the change type.
- Breaking changes are in `Breaking` at the top, with migration instructions and a MAJOR bump.
- Entries describe user impact and required action; no "misc fixes" or "refactor".
- Security entries are reviewed for disclosure timing before publication.
- `Unreleased` is maintained continuously and cleared at release.
- Automation drafts entries; a human edits before publishing.
- Version numbers match across all manifests and tags.
- Changelog is linked from README and package metadata and archived permanently.

## 9. Verification and Testing

- Diff the public API surface (`openapi-diff`, `cargo public-api`, `typedoc --emit none` diff) against the changelog: every breaking diff has an entry.
- Run `changeset status` / `towncrier check` in CI to ensure a change file exists for user-visible changes.
- Lint commit subjects against Conventional Commits in CI.
- Have a support engineer read the release notes and ask what is missing.
- Verify links in the changelog resolve (link checker).

## 10. Security Considerations

- Do not publish vulnerability details, proof-of-concept steps, or affected-version specifics before the coordinated disclosure date; coordinate wording with the security owner.
- Changelog automation reads git history—ensure commit messages do not contain internal hostnames, ticket details with customer names, or secrets.
- Do not list internal service names or infrastructure changes in public notes; keep an internal operations changelog separately.
- Deprecation notices should state the security rationale only when disclosure is appropriate.
- Signed releases and provenance attestations belong in release notes only if actually produced (never claim signing that does not happen).

## 11. Failure Handling

- **Changelog reconstructed at release from commits:** add a CI check requiring a change file per PR (changesets/towncrier), or enforce `Unreleased` updates in review.
- **Breaking change slipped into a MINOR:** the API diff check catches it; ship a follow-up with a proper version and a migration guide, and fix the release process.
- **Two sources of truth disagree:** pick one (the changelog) and generate the other (GitHub release) from it.
- **Users surprised by behavior change:** behavior changes need an `### Changed` entry even when the API signature is unchanged; treat them as user-visible.
- **Noise drowns signal:** exclude chore/ci/docs from user-facing notes; group internal items into one line.

## 12. Expected Deliverables

1. `CHANGELOG.md` in Keep a Changelog format with `Unreleased`.
2. Versioning policy and bump rules.
3. Per-release migration guides for breaking changes.
4. Conventional commit / changeset workflow config.
5. Draft-generation script or tool configuration.
6. Release checklist and API-diff verification.
7. Audience-specific release notes template.

## 13. References

- Keep a Changelog 1.1.0 — https://keepachangelog.com/en/1.1.0/
- Semantic Versioning 2.0.0 — https://semver.org/
- Conventional Commits 1.0.0 — https://www.conventionalcommits.org/en/v1.0.0/
- Changesets — https://github.com/changesets/changesets
- towncrier — https://towncrier.readthedocs.io/
- release-please — https://github.com/googleapis/release-please
- git-cliff — https://git-cliff.org/
- CVE/NVD (for security references) — https://nvd.nist.gov/
