---
name: incident-response
description: Run a security incident end-to-end—detect, triage, contain, eradicate, recover, and write the postmortem—while preserving evidence and avoiding destructive containment.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: high
---

# Incident Response

## 1. Purpose

Provide a disciplined response process when a security incident is suspected or confirmed. The priorities, in order: stop the harm, preserve evidence, understand scope, remove the adversary's access, restore safely, and prevent recurrence. This skill follows NIST SP 800-61 phases and adapts them to small teams without a dedicated SOC.

**Scope:** incidents on systems you own or administer. Containment actions affect production—require explicit approval from the incident owner for anything destructive or externally visible.

## 2. Activation Conditions

- Alert of compromise: unusual logins, malware detection, crypto-mining, data exfiltration, ransomware.
- Leaked credentials confirmed in use.
- Customer report of unauthorized access.
- Anomalous billing or resource usage.
- Keywords: incident, breach, compromise, malware, ransomware, exfiltration, containment, forensics, postmortem, SEV, IoC.

## 3. When Not to Use

- Routine vulnerability findings with no evidence of exploitation (use vulnerability-assessment).
- Planned security testing (use api-security-testing with scope).
- Availability incidents with no security dimension (use your SRE incident process).

## 4. Required Context

1. Incident severity and blast radius estimate (start conservative).
2. Who has decision authority for containment (kill instance, revoke keys, block IPs).
3. Legal/privacy obligations: breach notification timelines, counsel involvement.
4. Logging availability: which sources, retention, and whether they may be tampered.
5. Asset inventory and ownership for affected systems.
6. Communication channels that are out-of-band (assume corporate email/chat may be compromised).

## 5. Operating Procedure

**Phase 1 — Preparation (before incidents, but verify during)**

1. Confirm contacts, escalation tree, and out-of-band comms (phone bridge, separate chat workspace).
2. Confirm logging and retention; snapshot capability; backup integrity.
3. Pre-stage forensic tooling (read-only) and credentials with least privilege.

**Phase 2 — Detection and Analysis**

4. **Open an incident record** with ID, timestamp (UTC), reporter, and initial description.
5. **Establish a timeline** from logs: first suspicious event, detection, actions taken.
6. **Preserve evidence before changing anything**: snapshot disks/volumes, export logs to a separate account/host, capture memory if warranted.
7. **Scope**: which accounts, hosts, cloud resources, data stores are involved. Use IoCs to search broadly.
8. **Classify severity** (SEV1–SEV4) based on data sensitivity, blast radius, and business impact.

**Phase 3 — Containment**

9. **Short-term containment** with least destructive action first: revoke sessions/tokens, disable compromised accounts, rotate keys, block egress to C2 IPs/domains, isolate host via security group (keep it running for forensics).
10. **Do not delete** the instance or wipe disks until evidence is preserved and the incident owner approves.
11. **Long-term containment**: rebuild affected hosts from known-good images, patch entry vector, keep monitoring heightened.

**Phase 4 — Eradication**

12. Identify and remove persistence: cron jobs, systemd units, SSH keys, cloud IAM keys/roles, OAuth app consents, web shells, container images.
13. Patch the root-cause vulnerability; verify no remaining IoCs.

**Phase 5 — Recovery**

14. Restore from verified-clean backups (check backup integrity and that it predates the compromise).
15. Monitor closely for 72+ hours with heightened alerting; validate business functionality.
16. Confirm with stakeholders before declaring resolution.

**Phase 6 — Post-incident**

17. Write the postmortem within 5 business days: timeline, root cause, impact, what went well/poorly, action items with owners and dates.
18. Update detections and runbooks; share lessons with the team.
19. Close the record only when actions have owners and dates.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Evidence capture | Cloud volume snapshots, `dd`/`dc3dd` with hashing, `LiME`/AVML for memory |
| Log export | Cloud trail logs, `journalctl --since`, Loki/ELK export, `aws s3 cp --recursive` |
| Analysis | `grep`/`jq` over exported logs, `zeek`, `tshark`, timeline tools (`plaso`) |
| IoC scanning | `yara`, `osquery`, `falco` |
| Containment | Cloud security groups, IAM deny policies, IdP session revocation |
| Communication | Incident doc, out-of-band chat, status updates |
| Case management | TheHive, Jira Service Management (security project) |

## 7. Practical Implementation

**Evidence preservation with hashing:**

```bash
sudo dd if=/dev/nvme0n1 of=/mnt/evidence/host-01.dd bs=4M status=progress conv=noerror,sync
sha256sum /mnt/evidence/host-01.dd | tee /mnt/evidence/host-01.dd.sha256
# Record: who, when, from which host, tool version, hash
```

**Export logs before rotating or terminating:**

```bash
sudo journalctl --since "2026-10-01" -u sshd -u nginx --no-pager > /evidence/journal-2026-10.txt
aws cloudtrail lookup-events --start-time 2026-10-01 --end-time 2026-10-05 \
  --query 'Events[]' > /evidence/cloudtrail.json
```

**IoCs sweep across a fleet:**

```bash
grep -RIn --binary-files=without-match -e '45.148.10.77' -e 'cdn-update.example-malware.net' \
  /var/log /etc /home 2>/dev/null | tee /evidence/ioc-hits.txt
```

**osquery for persistence:**

```sql
SELECT name, path, schedule FROM crontab;
SELECT name, path, cmdline FROM processes WHERE path LIKE '/tmp/%' OR path LIKE '/dev/shm/%';
SELECT * FROM authorized_keys;
SELECT name, path, status FROM systemd_units WHERE status = 'enabled';
```

**Revoke sessions and keys (AWS example):**

```bash
# Attach an explicit deny-all policy to the compromised principal
aws iam attach-user-policy --user-name compromised --policy-arn arn:aws:iam::aws:policy/AWSDenyAll
# Invalidate temporary credentials via revocation list; rotate long-lived keys
aws iam create-access-key --user-name service-bot   # then deploy, then delete old
aws iam delete-access-key --user-name service-bot --access-key-id AKIA...
```

**Containment decision table:**

| Option | Destructive? | Evidence preserved? | Use when |
|---|---|---|---|
| Revoke sessions/tokens | No | Yes | Always first |
| Rotate keys | No | Yes | Credential exposure |
| Block egress to C2 | No | Yes | Active C2 traffic |
| Isolate host (SG change) | Low | Yes | Lateral movement risk |
| Snapshot + terminate | Yes | Yes (snapshot) | Ransomware, no forensic value in runtime |
| Wipe and rebuild | Yes | Only if imaged | Approved eradication step |

## 8. Quality Standards

- All timestamps recorded in UTC with source system noted.
- Every containment action is logged with who approved it and at what time.
- Evidence is hashed and stored in a separate trust domain from the compromised environment.
- Scope is stated with confidence levels: confirmed, likely, ruled out.
- Postmortem is blameless and action-item-driven.
- Notification obligations are evaluated with legal, not assumed.

## 9. Verification and Testing

- After eradication, run IoC sweeps again and require zero hits.
- Verify no active sessions for compromised accounts (`aws sts get-caller-identity`, IdP session list).
- Confirm restored systems run patched versions and pass a vulnerability scan.
- Validate detections: replay a benign test of the original attack pattern and confirm the alert fires.
- Evidence: hash manifests, export timestamps, scan results, alert-firing proof.

## 10. Security Considerations

- Assume the attacker retains access until proven otherwise; rotate credentials from a trusted device, not the suspect host.
- Communication may be monitored: use out-of-band channels and avoid discussing details in compromised systems.
- Chain of custody: document every evidence transfer; use write-once storage where possible.
- Do not run untrusted binaries from the compromised host on your analysis machine; use an isolated environment.
- Privacy: minimize collection of unrelated personal data; follow legal guidance on employee monitoring.
- Attackers may watch for containment—coordinate timing of blocking actions to avoid tipping off before evidence is secured.

## 11. Failure Handling

- **Evidence lost by premature deletion:** document it; proceed with log-based reconstruction; add a checklist item to prevent recurrence.
- **Scope keeps expanding:** step back, model the initial access vector, and search backwards from it (credential source, exposed service, phishing).
- **Cannot contain with current tooling:** escalate to the cloud provider's security team or use network-level blocks at the edge.
- **Backups also compromised:** restore from immutable/offline backups; if none, rebuild and accept data loss with business sign-off.
- **Regulatory uncertainty:** engage legal immediately; do not delay containment pending legal, but do preserve evidence.

## 12. Expected Deliverables

1. Incident record with timeline and severity.
2. Evidence manifest with hashes and storage location.
3. Scope assessment and IoC list.
4. Containment/eradication/recovery action log with approvals.
5. Postmortem with root cause and action items.
6. Updated detections, runbooks, and notification record.

## 13. References

- NIST SP 800-61r3 Incident Response Recommendations — https://csrc.nist.gov/pubs/sp/800/61/r3/final
- NIST SP 800-86 Forensic Techniques — https://csrc.nist.gov/pubs/sp/800/86/final
- MITRE ATT&CK (technique mapping) — https://attack.mitre.org/
- CISA Incident and Vulnerability Response Playbooks — https://www.cisa.gov/resources-tools/resources/federal-government-cybersecurity-incident-and-vulnerability-response-playbooks
- SANS Incident Handler's Handbook — https://www.sans.org/white-papers/33901/
- osquery documentation — https://osquery.readthedocs.io/
