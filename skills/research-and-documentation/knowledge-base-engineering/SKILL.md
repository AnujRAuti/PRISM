---
name: knowledge-base-engineering
description: Build internal knowledge systems that stay findable and current—information architecture, doc ownership, search, freshness reviews, and deprecation of stale content.
metadata:
  domain: research-and-documentation
  version: 1.0.0
  risk: low
---

# Knowledge Base Engineering

## 1. Purpose

Make the right information findable in under a minute and provably current. Internal knowledge bases rot in a predictable way: content is duplicated across wikis and drives, everything is marked "current", search returns stale pages first, and nobody is accountable for updates. This skill covers information architecture, ownership and review cadence, search and metadata, freshness signals, and retirement of dead content.

**Scope:** your own organization's knowledge. Know what classification of data is allowed: never store credentials, customer PII beyond policy, or unpatched vulnerability details in broadly readable spaces.

## 2. Activation Conditions

- Repeated questions in chat that should be documented.
- Onboarding depends on asking specific people.
- Wiki has thousands of pages and low trust.
- Multiple sources of truth for the same process.
- Keywords: knowledge base, wiki, information architecture, taxonomy, docs ownership, freshness, search, runbook index, onboarding, Confluence, Notion, Obsidian, docs-as-code, deprecation.

## 3. When Not to Use

- Customer-facing product documentation (use technical-writing / api-documentation).
- Code comments and docstrings (use code-documentation).
- One-off answers that will not be reused.

## 4. Required Context

1. Existing tools (wiki, drive, repo docs) and who can edit them.
2. Audiences: engineers, support, sales, leadership.
3. Volume and growth rate of content.
4. Search capabilities and whether metadata is supported.
5. Compliance classification rules for stored content.

## 5. Operating Procedure

1. **Inventory before restructuring**: crawl existing pages, list owners, last-modified dates, and access counts. Most "knowledge base projects" fail by building a new space without retiring the old one.
2. **Define the taxonomy by task, not department**: "Deploy a service", "Handle a payment dispute", "Rotate a credential" — users search for what they are doing.
3. **Choose the canonical location per content type** and redirect or delete everything else. Two sources of truth guarantee drift.
4. **Assign an owner to every page** (a team, not a person) and record it in metadata.
5. **Add metadata that enables trust**: owner, last-reviewed date, review interval, status (`draft`/`active`/`deprecated`), applicable systems, and classification.
6. **Design for search**: strong titles (task + object), explicit keywords, and short intros that match how people phrase questions.
7. **Tie documentation to change**: runbooks and process docs are updated in the same PR/ticket as the change; link docs from the code and dashboards.
8. **Institutionalize freshness**: review cadence by class (runbooks quarterly, policies annually), a "last verified" field, and a scheduled review queue.
9. **Deprecate loudly**: banner at the top, link to the replacement, and archive after a grace period — never silently delete something others may have bookmarked.
10. **Measure usage**: search queries with no results, pages never opened, and repeated chat questions are your backlog.
11. **Close the loop**: move answers from chat into the KB when a question repeats three times, then reply with the link.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Platforms | Confluence, Notion, Outline, GitBook, Obsidian (local+vault), MkDocs/Docusaurus in-repo |
| Search | Native search, Algolia DocSearch, Typesense, `ripgrep` over docs-as-code |
| Metadata | Front matter, page properties, labels/tags |
| Automation | Link checkers, staleness reports via API, `lychee`, scheduled CI |
| Chat integration | Slack/Teams bot that answers with KB links |
| Migration | Export APIs, one-time crawler, redirect maps |

## 7. Practical Implementation

**Page front matter enforcing ownership and freshness:**

```markdown
---
title: Rotate the orders-api database credential
owner: payments-platform
status: active                  # draft | active | deprecated
last_reviewed: 2026-11-04
review_interval_days: 90
applies_to: [orders-api, orders-worker]
classification: internal
keywords: [rotation, database, credential, postgres, incident]
related: [runbook-db-failover, rfc-0142]
---

# Rotate the orders-api database credential

> **When to use:** scheduled rotation, or suspected credential exposure.
> **Time:** ~15 minutes. **Impact:** none if steps run in order.

...
```

**Staleness report (runs on a schedule, posts to the owning team):**

```python
# scripts/stale_docs.py — works with a docs-as-code repo; adapt for API-based wikis
import datetime as dt
import pathlib
import re
import sys

FM = re.compile(r"^---\n(.*?)\n---\n", re.S)

def parse_front_matter(text: str) -> dict[str, str]:
    m = FM.match(text)
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()
    return data

def report(root: pathlib.Path, today: dt.date) -> int:
    problems = 0
    for path in root.rglob("*.md"):
        fm = parse_front_matter(path.read_text(encoding="utf-8"))
        if not fm.get("owner"):
            print(f"MISSING OWNER: {path}")
            problems += 1
            continue
        reviewed = fm.get("last_reviewed")
        interval = fm.get("review_interval_days", "365")
        if not reviewed or not interval.isdigit():
            print(f"MISSING REVIEW METADATA: {path}")
            problems += 1
            continue
        due = dt.date.fromisoformat(reviewed) + dt.timedelta(days=int(interval))
        if today > due:
            print(f"STALE (due {due}): {path} [owner: {fm['owner']}]")
            problems += 1
    return problems

if __name__ == "__main__":
    sys.exit(1 if report(pathlib.Path("docs"), dt.date.today()) else 0)
```

```yaml
# CI: warn weekly, fail on pages that are >2 intervals overdue
- run: python scripts/stale_docs.py
  continue-on-error: false
```

**Search-miss analysis (the backlog that actually matters):**

```sql
-- Example: query the search analytics export for zero-result searches
SELECT query, count(*) AS attempts
FROM search_events
WHERE result_count = 0
  AND ts >= now() - interval '30 days'
GROUP BY query
ORDER BY attempts DESC
LIMIT 50;
```

Each recurring zero-result query becomes a page (or a redirect to an existing one).

**Task-oriented information architecture:**

```text
docs/
├── start-here/            # onboarding path, environment setup, first PR
├── runbooks/              # "something is broken now" (linked from alerts)
├── how-to/                # repeatable procedures (deploys, rotations, grants)
├── reference/             # facts to look up (service catalogue, ports, owners)
├── explanation/           # why the system works this way (links to RFCs/ADRs)
└── archive/               # deprecated, read-only, banner at top
```

**Deprecation banner with replacement link:**

```markdown
> ⚠️ **Deprecated (2026-10-01).** This page describes the legacy queue setup,
> decommissioned in v3. See [Event pipeline](/reference/event-pipeline).
> Archiving on 2027-01-01.
```

**Service catalogue entry (the page that answers "who owns this?"):**

```markdown
| Field | Value |
|---|---|
| Service | orders-api |
| Owner | @payments-platform |
| On-call | `#payments-oncall`, PagerDuty `payments-primary` |
| Repo | `github.com/acme/orders` |
| Runtime | Kubernetes, `ap-south-1`, 6 pods |
| Dependencies | Postgres `orders`, Redis `sessions`, RabbitMQ `events` |
| Dashboards | `grafana/orders` |
| Runbooks | [DB failover](/runbooks/db-failover), [Queue backlog](/runbooks/queue-backlog) |
| SLOs | 99.9% availability, p99 < 400 ms |
```

**Chat-to-KB loop:**

```text
Rule: when the same question is answered in chat for the third time,
1. The answerer writes or updates the KB page (15 min timebox).
2. They reply in the channel with the link, not the answer.
3. The pinned message in the channel points at the index page.
```

**Link and structure validation:**

```bash
lychee --no-progress "docs/**/*.md"          # broken links
markdownlint-cli2 "docs/**/*.md"             # structure/style
find docs -name "*.md" -size +200k           # pages that should be split
```

## 8. Quality Standards

- Every page has an owner (team), status, last-reviewed date, and classification.
- One canonical location per topic; duplicates redirected or archived.
- Titles describe a task or a lookup key, not an internal project code.
- Runbooks are reachable from the alert that references them.
- Stale pages are surfaced automatically and fixed on a cadence.
- Deprecated content is bannered with a replacement link and archived after a grace period.
- Search zero-results are reviewed monthly and drive new pages.
- Access follows classification; no secrets or unrestricted PII in shared spaces.

## 9. Verification and Testing

- **Findability test**: ask three people to find the answer to a real question with a timer; target under 60 seconds.
- Run the staleness script; confirm the report matches manual spot checks.
- Verify runbook links from alerts/dashboards resolve to the correct page.
- Search test: query the top ten user phrasings; confirm the right page appears in the top three results.
- Deletion audit: confirm archived pages are linked from the archive index, not silently gone.

## 10. Security Considerations

- Classify every page; secrets, production credentials, and customer PII do not belong in general-purpose wikis.
- If a credential was ever stored in a page, treat it as exposed: rotate it, then purge (history included).
- Restrict runbooks containing privileged commands to the teams that need them; a public runbook is an operational weapon.
- Vulnerability details and incident postmortems may need restricted access until fixed.
- Audit who can edit canonical pages; broad edit rights on security procedures invite accidents.
- Exports and backups of the KB inherit its sensitivity; set retention and access accordingly.

## 11. Failure Handling

- **Nobody uses the new structure:** they are still finding the old pages. Redirect, delete, or move the old content; do not run two systems.
- **Pages marked current but wrong:** freshness metadata plus reviewer assignment; make "verify" a concrete recurring task, not a hope.
- **Search is poor:** improve titles and keywords first; only then consider a new search engine.
- **Owners leave:** owner is a team, and team changes trigger a review of their pages in the quarterly cycle.
- **Knowledge base grows unbounded:** archive with an index; set a review gate for new top-level sections.

## 12. Expected Deliverables

1. Information architecture with content types and canonical locations.
2. Page metadata schema (owner, status, review interval, classification).
3. Service catalogue / index pages per domain.
4. Staleness reporting and review cadence.
5. Search-miss backlog process.
6. Deprecation and archive policy.
7. Chat-to-KB escalation rule.

## 13. References

- Diátaxis (content types) — https://diataxis.fr/
- Write the Docs, "Documentation Guide" — https://www.writethedocs.org/guide/
- lychee link checker — https://github.com/lycheeverse/lychee
- markdownlint — https://github.com/DavidAnson/markdownlint
- Algolia DocSearch — https://docsearch.algolia.com/
- Typesense — https://typesense.org/docs/
- Google SRE Workbook, "Documentation as a Service" practices — https://sre.google/workbook/
