---
name: security-documentation
description: Produce security artifacts that survive audit—policies, control matrices, risk registers, runbooks, and architecture security docs—accurate, current, and mapped to standards.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: low
---

# Security Documentation

## 1. Purpose

Write the documents auditors, customers, and responders actually use: security policies, control implementations with evidence, risk registers, incident runbooks, data-flow/security architecture descriptions, and vendor assessments. Bad security documentation is worse than none—it certifies controls that do not exist. This skill enforces evidence-linked statements, version control, review cycles, and mapping to recognized frameworks (ISO 27001, SOC 2, NIST CSF 2.0).

## 2. Activation Conditions

- Preparing for SOC 2 / ISO 27001 / PCI evidence collection.
- Answering customer security questionnaires or vendor due diligence.
- Writing or updating policies, standards, and procedures.
- Documenting security architecture for a system.
- Creating an incident runbook or on-call security guide.
- Keywords: security policy, control matrix, SOC 2, ISO 27001, NIST CSF, risk register, runbook, security questionnaire, evidence.

## 3. When Not to Use

- Writing code-level security findings (use secure-code-review).
- Threat modeling a specific system (use threat-modeling), though its output is referenced here.
- Public marketing security pages (different audience and legal review).
- When you are asked to attest to controls you cannot verify—refuse to fabricate and flag the gap.

## 4. Required Context

1. Which framework or standard applies, and the audit scope.
2. Actual implemented controls with owners and evidence sources.
3. Existing document set, templates, and approval workflow.
4. Document management and retention requirements.
5. Audience: auditors (evidence-heavy), customers (assurance), engineers (operational).
6. Any claimed certifications and their validity dates.

## 5. Operating Procedure

1. **Define scope and audience first**; a document for auditors differs from one for engineers.
2. **Choose the structure**: policy (what and why) → standard (specific requirements) → procedure (how) → evidence (proof).
3. **Map to the framework**: build a control matrix (control ID, description, implementation, owner, evidence, test frequency, status).
4. **Verify every control claim** by locating evidence: config snippet, screenshot with date, tool output, ticket. Mark unverified items `gap`, never `implemented`.
5. **Write the risk register** with likelihood/impact, treatment (mitigate/transfer/accept/avoid), owner, and review date.
6. **Document security architecture** for each critical system: trust boundaries, data classification, authn/authz, logging, encryption.
7. **Write runbooks** as step-by-step procedures with commands, expected outputs, and escalation contacts.
8. **Review and approve** with named approvers and dates; record version history.
9. **Set a review cycle** (annual policy review; quarterly control testing; per-change architecture updates).
10. **Automate evidence collection** where possible (config exports, screenshots with timestamps) to keep the matrix truthful.
11. **Publish internally** with access control; keep a redacted customer-facing version.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Frameworks | ISO/IEC 27001:2022 Annex A, SOC 2 TSC, NIST CSF 2.0, PCI DSS 4.0 |
| Control mapping | Vanta, Drata, Secureframe, or a maintained spreadsheet |
| Evidence | Terraform state exports, SSO config screenshots, audit log samples |
| Docs | Git-backed Markdown, Confluence, Notion |
| Runbooks | Markdown + `make` targets or scripted steps |
| Review | Pull requests with required approvers |
| Standards references | CIS Controls v8.1, NIST SP 800-53 |

## 7. Practical Implementation

**Control matrix row (Markdown):**

```markdown
| ID | Control (ISO 27001:2022) | Implementation | Owner | Evidence | Test | Status |
|----|--------------------------|----------------|-------|----------|------|--------|
| A.5.15 | Access control | RBAC via Entra ID groups; JIT elevation via PIM; quarterly access review | @iam | `evidence/2026-q3/access-review.pdf`, PIM config export | Quarterly | Implemented |
| A.8.8 | Technical vulnerability management | Weekly authenticated scans (OpenVAS), KEV SLA 7d, monthly metrics | @secops | `reports/vuln/2026-10.pdf` | Monthly | Implemented |
| A.8.16 | Monitoring activities | Centralized logs (Loki) 90d hot / 1y cold; alerts for auth anomalies | @sre | Loki retention config, alert rules repo | Monthly | Partial — alert tuning in progress |
```

**Policy document skeleton:**

```markdown
# Access Control Policy

Owner: Head of Security        Version: 3.1        Effective: 2026-10-01
Review cycle: annual            Next review: 2027-10-01
Applies to: all employees, contractors, and systems

### 1. Purpose and scope
### 2. Roles and responsibilities
### 3. Requirements
  3.1 Unique identities; no shared accounts
  3.2 MFA mandatory for all workforce and admin access
  3.3 Least privilege; access reviews each quarter
  3.4 Offboarding within 24 hours
### 4. Exceptions
   Requests must name the risk owner, compensating control, and expiry (max 90 days).
### 5. Compliance and evidence
  Reviewed quarterly by @iam; evidence stored in evidence/access/.
### 6. Revision history
| Version | Date | Author | Change |
```

**Risk register entry:**

```markdown
| ID | Risk | Likelihood | Impact | Score | Treatment | Control | Owner | Review |
|----|------|-----------|--------|-------|-----------|---------|-------|--------|
| R-014 | Stale admin accounts retain prod access | 3 | 5 | 15 | Mitigate | Quarterly access review + SCIM deprovisioning | @iam | 2027-01-15 |
| R-015 | Single-region deployment risks data loss | 2 | 5 | 10 | Accept (documented) | Daily backups with restore tests | @sre | 2027-04-01 |
```

**Incident runbook excerpt:**

```markdown
### Runbook: Leaked Cloud Access Key

Trigger: secret scanning alert or verified exposure of an AWS access key.

1. Confirm the key is live and identify its principal:
   aws sts get-caller-identity   # from a controlled environment with the key ONLY if safe; prefer CloudTrail lookup
2. Identify usage: aws cloudtrail lookup-events --lookup-attributes AttributeKey=AccessKeyId,AttributeValue=<redacted>
3. Contain: attach explicit deny policy; disable the key.
4. Rotate: create replacement, deploy, verify using new key, then delete the old key.
5. Scope abuse: review IAM changes, resource creation, data access in the window.
6. Notify: security lead immediately; DPO if customer data was accessed.
7. Postmortem within 5 business days.
Expected time: containment < 30 min. Escalation: #sec-incident, +1-555-0100.
```

**Questionnaire answer discipline:**

```markdown
Q: Do you encrypt data at rest?
A: Yes — AES-256 on all production volumes (EBS default encryption) and PostgreSQL storage;
   app-level field encryption for tax IDs. Evidence: control A.8.24, evidence/2026-q3/encryption.pdf.
   Scope note: analytics warehouse uses the same KMS key policy; verified 2026-09-12.
```

## 8. Quality Standards

- Every "implemented" claim links to dated evidence.
- Unverified controls are marked `gap` with a remediation ticket.
- Documents have an owner, version, effective date, and review date.
- Runbooks are executable: exact commands, expected output, escalation path.
- Language is precise; avoid "should", "best effort", and unsupported absolutes.
- Customer-facing documents are reviewed for information disclosure.
- The same control is described identically across documents.

## 9. Verification and Testing

- **Tabletop test** the runbook: can a responder follow it without the author present?
- **Evidence audit**: sample 3 controls and confirm the linked evidence exists, is dated, and shows what the claim says.
- **Consistency check** across documents (policy vs. control matrix vs. questionnaire answers).
- **Freshness check**: flag documents past their review date in CI or calendar.
- Evidence: signed approval records, audit sample results, drift tickets.

## 10. Security Considerations

- Security documentation is a target list: restrict access; never publish internal control gaps externally.
- Do not include credentials, internal IPs, or exploitable details in customer-facing docs.
- Preserve integrity: version control with signed commits or protected branches for policy files.
- Keep the document stock consistent with the actual environment; stale claims create legal and audit exposure.
- Records with personal data (access reviews) fall under privacy rules—limit retention as required.
- Be explicit about subprocessors and shared responsibility boundaries in cloud deployments.

## 11. Failure Handling

- **Control not implemented but promised:** immediately mark as gap, notify the accountable owner, and set a remediation date; do not keep the claim.
- **Auditor requests evidence you do not have:** acknowledge the gap, describe the compensating control, and produce a plan.
- **Documents scattered/conflicting:** establish a single canonical source (repo) and mark others read-only.
- **Runbook fails during an incident:** update immediately after the incident with what actually worked; add a dry-run cadence.
- **Questionnaire deadline too tight:** answer only what is verified; request an extension rather than guessing.

## 12. Expected Deliverables

1. Policy/standard/procedure documents with owners and review dates.
2. Control matrix mapped to the chosen framework with evidence links.
3. Risk register with treatments and review dates.
4. Security architecture descriptions per critical system.
5. Executable runbooks for defined scenarios.
6. Version history and approval records.
7. Gap list with remediation tickets.

## 13. References

- ISO/IEC 27001:2022 — https://www.iso.org/standard/27001
- NIST Cybersecurity Framework 2.0 — https://www.nist.gov/cyberframework
- NIST SP 800-53 Rev. 5 — https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- AICPA SOC 2 Trust Services Criteria — https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2
- PCI DSS v4.0 — https://www.pcisecuritystandards.org/document_library/
- CIS Critical Security Controls v8.1 — https://www.cisecurity.org/controls
