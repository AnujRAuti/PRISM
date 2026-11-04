---
name: human-in-the-loop-workflows
description: Design approval gates, review queues, and escalation paths for agents—interruptible execution, resumable state, clear review UX, and auditable decisions.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: high
---

# Human-in-the-Loop Workflows

## 1. Purpose

Add human judgment at the points where mistakes are expensive. HITL is not "a person watches the agent"; it is an engineered workflow: deterministic pause points, durable state, a review interface that shows what will happen, and a resume/abort path with an audit trail. This skill covers where to put gates, how to implement interrupts and resumption, how to design the approval payload, and how to measure whether reviewers are actually effective.

**Scope:** workflows you operate. Approval gates are a security control—bypassing them must be impossible by design, not discouraged by policy.

## 2. Activation Conditions

- Agent actions are irreversible or externally visible (payments, emails, deployments, deletions).
- Regulated processes require named approvers.
- Confidence is below threshold for a subset of cases.
- Reviewers need to correct agent output before it is used.
- Keywords: human in the loop, approval gate, review queue, interrupt, resume, checkpoint, escalation, four-eyes, audit trail, autonomy levels.

## 3. When Not to Use

- Fully reversible internal actions with strong verification (log-and-monitor is enough).
- When review volume would exceed human capacity and create rubber-stamping—reduce agent scope instead.
- Real-time interactions where a pause breaks the product (use pre-approved action policies).

## 4. Required Context

1. Action inventory: reversibility, external visibility, and financial/legal impact.
2. Reviewer roles and their authority limits.
3. SLA for approvals and what happens on timeout.
4. State model: what must be persisted to resume after a pause.
5. Audit requirements and retention.

## 5. Operating Procedure

1. **Classify actions by risk**: auto-approve (reversible, low impact), notify (act then inform), approve (pause for human), and forbid (never allowed).
2. **Place gates before the irreversible step**, not after; the approval payload must describe exactly what will happen.
3. **Define autonomy levels per task type** and store them in configuration, not in prompts.
4. **Persist state before pausing**: full agent state, the proposed action, the diff/preview, and the trace ID.
5. **Implement the interrupt** as a durable workflow signal (not an in-memory `input()`): queue a review task, park the run, and resume by ID when a decision arrives.
6. **Design the review payload**: summary, exact diff/action, evidence/citations, risk notes, and one-click approve/reject/edit.
7. **Support partial approval**: approve with edits, approve a subset of items, or request regeneration with instructions.
8. **Handle timeouts explicitly**: auto-reject (default), escalate to a second reviewer, or hold—never auto-approve because nobody looked.
9. **Record decisions immutably**: approver identity, timestamp, before/after content, and rationale.
10. **Measure reviewer effectiveness**: approval rate, time-to-decision, downstream error rate on approved items, and rubber-stamping signals (median decision time under N seconds).
11. **Tune the gate thresholds** based on measured precision—gates that always approve add cost without control.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Durable workflows | Temporal, Airflow sensors, AWS Step Functions with task tokens, Celery + DB state |
| Review UI | Internal admin app, Slack/Teams approval cards, Jira/ServiceNow tickets |
| State store | Postgres (runs, steps, approvals tables) |
| Identity | SSO with role-based approver groups |
| Audit | Append-only approval log, SIEM forwarding |

## 7. Practical Implementation

**Risk policy as configuration:**

```yaml
# policy/autonomy.yaml
actions:
  create_internal_note:
    autonomy: auto
  send_customer_email:
    autonomy: approve
    approvers: ["support-lead", "support-senior"]
    timeout_minutes: 120
    on_timeout: reject
  issue_refund:
    autonomy: approve
    approvers: ["finance"]
    max_auto_amount_cents: 5000      # below this, notify-only
    timeout_minutes: 240
    on_timeout: escalate
  delete_customer_record:
    autonomy: forbid
```

**Interrupt + resume with persisted state (Python, DB-backed):**

```python
from dataclasses import dataclass, asdict
import json, uuid, datetime as dt

@dataclass
class PendingApproval:
    run_id: str
    action: dict
    preview: str
    risk_notes: list[str]
    requested_by: str
    created_at: str
    expires_at: str

def request_approval(conn, run_id: str, action: dict, preview: str,
                     risk_notes: list[str], policy: dict, requester: str) -> PendingApproval:
    now = dt.datetime.now(dt.UTC)
    pa = PendingApproval(
        run_id=run_id, action=action, preview=preview, risk_notes=risk_notes,
        requested_by=requester, created_at=now.isoformat(),
        expires_at=(now + dt.timedelta(minutes=policy["timeout_minutes"])).isoformat(),
    )
    conn.execute(
        """INSERT INTO approvals (id, run_id, action, preview, risk_notes, requested_by,
                                  created_at, expires_at, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending')""",
        (uuid.uuid4().hex, pa.run_id, json.dumps(pa.action), pa.preview,
         json.dumps(pa.risk_notes), pa.requested_by, pa.created_at, pa.expires_at))
    conn.execute("UPDATE runs SET status='awaiting_approval' WHERE id=%s", (run_id,))
    return pa

def resume_run(conn, approval_id: str, decision: str, approver: str,
               edits: dict | None = None, note: str | None = None) -> None:
    if decision not in {"approve", "reject"}:
        raise ValueError("invalid decision")
    row = conn.execute(
        "SELECT run_id, action, status FROM approvals WHERE id=%s FOR UPDATE",
        (approval_id,)).fetchone()
    if row is None or row["status"] != "pending":
        raise ValueError("approval not pending")
    final_action = {**json.loads(row["action"]), **(edits or {})}
    conn.execute(
        """UPDATE approvals SET status=%s, decided_by=%s, decided_at=now(),
                  final_action=%s, note=%s WHERE id=%s""",
        (decision, approver, json.dumps(final_action), note, approval_id))
    conn.execute(
        "UPDATE runs SET status=%s, resume_payload=%s WHERE id=%s",
        ("approved" if decision == "approve" else "rejected",
         json.dumps(final_action), row["run_id"]))
```

**Approval payload (what a reviewer must see):**

```json
{
  "summary": "Send refund confirmation to customer 4412 for order ord_0123...",
  "action": {"type": "send_email", "to": "customer-4412", "template": "refund_confirmed",
             "variables": {"amount": "₹4,200", "order_id": "ord_0123456789abcdef"}},
  "preview": "Hi Asha, we've processed your refund of ₹4,200 for order ord_0123... It will appear in 5-7 business days.",
  "evidence": [{"source": "policy/refunds.md#window", "quote": "within 30 days of delivery"}],
  "risk_notes": ["Amount above auto-approval threshold", "Customer had 2 prior refunds"],
  "expires_at": "2026-11-04T14:30:00Z"
}
```

**Timeout handling job:**

```python
def expire_pending(conn) -> None:
    rows = conn.execute(
        """SELECT id, policy_key FROM approvals
           WHERE status='pending' AND expires_at < now()""").fetchall()
    for r in rows:
        policy = load_policy(r["policy_key"])
        if policy["on_timeout"] == "escalate":
            conn.execute("UPDATE approvals SET status='escalated' WHERE id=%s", (r["id"],))
        else:
            conn.execute(
                """UPDATE approvals SET status='expired', decided_by='system',
                          decided_at=now() WHERE id=%s""", (r["id"],))
```

**Reviewer effectiveness metrics:**

```text
approval_rate            = approved / total decisions
median_time_to_decision  = p50(decided_at - created_at)
rubber_stamp_rate        = decisions < 10 s and approved
post_approval_error_rate = downstream incidents on approved items / approved items
```

## 8. Quality Standards

- Every irreversible action routes through a gate defined in configuration, not prompt text.
- State is persisted before the pause; the run resumes exactly where it stopped.
- The reviewer sees the exact action and its effects, not a vague summary.
- Approvers are authenticated and authorized for that risk class.
- Timeouts default to reject or escalate; never auto-approve.
- Decisions are immutably logged with actor, time, content, and note.
- Gate metrics are reviewed; gates that never reject are re-examined.

## 9. Verification and Testing

- Test that an unapproved action cannot execute (attempt to bypass via direct tool call and confirm denial).
- Kill the process during the pause and confirm the run resumes on approval.
- Test timeout paths for both reject and escalate.
- Test partial approval (edit reduces the amount) and confirm the edited payload is what executes.
- Audit-log test: every decision has actor, timestamp, and final content.

## 10. Security Considerations

- Approval is a security control: enforce it in the execution path, not only in the UI.
- Prevent approver spoofing—identity from SSO, never from a request body.
- Prohibit self-approval for high-risk actions (four-eyes principle).
- Bind approvals to the exact payload hash so an action cannot change after approval.
- Protect the approval queue from tampering (write-once logs, restricted DB roles).
- Watch for social engineering: reviewers may approve content that was crafted by an attacker, so show provenance and risk signals.
- Never expose the full queue to low-privilege users; approval items can contain sensitive data.

## 11. Failure Handling

- **Approvals pile up and SLA breaches:** add a queue-health alert, staff to volume, or reduce gate scope for low-risk actions.
- **Rubber-stamping detected:** add friction for high-risk items (required rationale, sampled post-review).
- **State loss on resume:** persist before pausing; test crash-during-pause explicitly.
- **Approver edits cause invalid state:** validate the edited payload against the same schema as the original action.
- **Gate bypass discovered:** treat as a security incident; add a test that asserts the execution path requires an approval token.

## 12. Expected Deliverables

1. Action risk classification and autonomy policy.
2. Interrupt/resume implementation with persisted state.
3. Review payload schema and UI requirement.
4. Timeout and escalation logic.
5. Immutable decision log design.
6. Effectiveness metrics and dashboards.
7. Tests for bypass prevention and resume integrity.

## 13. References

- NIST AI RMF (human-AI configuration) — https://www.nist.gov/itl/ai-risk-management-framework
- Temporal durable execution — https://docs.temporal.io/
- AWS Step Functions callback patterns — https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html
- Google PAIR, "People + AI Guidebook" — https://pair.withgoogle.com/guidebook/
- Microsoft HAX Toolkit — https://www.microsoft.com/en-us/haxtoolkit/
- OWASP LLM06 Excessive Agency — https://owasp.org/www-project-top-10-for-large-language-model-applications/
