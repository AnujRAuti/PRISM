---
name: notifications-and-email
description: Deliver transactional email, SMS, and push reliably—template architecture, provider integration, deliverability (SPF/DKIM/DMARC), bounce and complaint handling, and user preferences.
metadata:
  domain: backend
  version: 1.0.0
  risk: medium
---

# Notifications and Email

## 1. Purpose

Send messages users actually receive and expect. Notification systems fail in predictable ways: email lands in spam because authentication records are wrong, duplicates go out after a retry, bounces and complaints are ignored until the domain is blacklisted, and every new notification requires a code change in three services. This skill covers template and dispatch architecture, provider integration with idempotency, deliverability configuration, feedback loops, preferences and unsubscribe, and multi-channel routing.

**Scope:** your own sending infrastructure and recipient data. Email and SMS are regulated channels (consent, unsubscribe, retention); sending without consent is a legal and reputational risk. Never use production recipient lists for testing.

## 2. Activation Conditions

- Adding transactional email (receipts, password resets, alerts) or SMS/push.
- Deliverability drops, or messages land in spam.
- Duplicate or missing notifications reported.
- Need user-level notification preferences or unsubscribe.
- Keywords: transactional email, SMTP, SES, Postmark, SendGrid, Resend, DKIM, SPF, DMARC, bounce, complaint, suppression list, template, push notification, SMS, unsubscribe, webhook feedback.

## 3. When Not to Use

- Marketing campaigns at scale (separate tooling, separate reputation strategy, marketing consent rules).
- In-app notifications that never leave the system (store and render in the app).
- Urgent on-call paging (use a paging provider with its own escalation path).

## 4. Required Context

1. Channels required: email, SMS, push, in-app.
2. Provider(s) and their API limits, sandbox mode, and feedback webhooks.
3. Domain(s) used for sending and DNS control availability.
4. Consent model and regional requirements (GDPR/CAN-SPAM/TRAI DLT for India SMS).
5. Volume: per-minute peaks and monthly totals.

## 5. Operating Procedure

1. **Separate channels behind one notifier interface**: business code calls `notify(user, event, data)`; channel adapters handle the rest.
2. **Keep templates versioned as data**, not as string concatenation in code; render server-side with escaping and localizable strings.
3. **Authenticate the sending domain**: SPF, DKIM (2048-bit), DMARC (`p=none` → `quarantine` → `reject`), and a separate subdomain for transactional vs. marketing mail.
4. **Use a dedicated IP or a reputable shared pool**; warm up gradually if using a dedicated IP.
5. **Deduplicate and make sends idempotent**: a `notification_log` unique key prevents a retried job from sending twice.
6. **Handle provider feedback**: process bounce and complaint webhooks, maintain a suppression list, and never retry hard bounces.
7. **Honor preferences and unsubscribe**: per-category preferences, `List-Unsubscribe` headers, and instant suppression on unsubscribe.
8. **Rate-limit and queue**: notifications go through the job queue with retries for transient provider errors only.
9. **Protect reset/verification links**: single-use tokens, short TTL, not logged, and never in the subject line.
10. **Track delivery**: accepted → delivered → opened (if tracked) → bounced, keyed by a message ID, exposed in support tooling.
11. **Test with a sandbox provider** and assert rendered HTML/text, headers, and links.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Provider | Amazon SES, Postmark, SendGrid, Resend, Mailgun |
| SMTP fallback | `aiosmtplib`, Postfix relay |
| Templates | Jinja2, MJML (responsive email), React Email, Handlebars |
| SMS | Twilio, Vonage, SNS; TRAI DLT registration for India |
| Push | FCM, APNs, Web Push (`pywebpush`) |
| Feedback loops | Provider webhooks, SES SNS notifications |
| Testing | Mailpit, MailHog, `pytest` with HTML assertions, Litmus (rendering) |

## 7. Practical Implementation

**Channel-agnostic notifier with idempotent logging:**

```sql
CREATE TABLE notification_log (
  id           bigserial PRIMARY KEY,
  user_id      text        NOT NULL,
  channel      text        NOT NULL CHECK (channel IN ('email','sms','push')),
  template     text        NOT NULL,
  dedupe_key   text        NOT NULL,
  status       text        NOT NULL CHECK (status IN ('queued','sent','failed','suppressed')),
  provider_id  text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (channel, template, dedupe_key)
);

CREATE TABLE email_suppression (
  email      citext PRIMARY KEY,
  reason     text NOT NULL CHECK (reason IN ('hard_bounce','complaint','unsubscribe','manual')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE notification_pref (
  user_id  text NOT NULL,
  category text NOT NULL,
  channel  text NOT NULL,
  enabled  boolean NOT NULL DEFAULT true,
  PRIMARY KEY (user_id, category, channel)
);
```

```python
import hashlib
from dataclasses import dataclass

@dataclass(frozen=True)
class Notification:
    user_id: str
    channel: str
    template: str
    data: dict
    dedupe_key: str

async def send_notification(session, n: Notification) -> bool:
    async with session.begin():
        row = (await session.execute(
            """INSERT INTO notification_log (user_id, channel, template, dedupe_key, status)
               VALUES (:u, :c, :t, :k, 'queued')
               ON CONFLICT (channel, template, dedupe_key) DO NOTHING
               RETURNING id""",
            {"u": n.user_id, "c": n.channel, "t": n.template, "k": n.dedupe_key},
        )).first()
    if row is None:
        return False                                   # already queued or sent
    await dispatch_queue.enqueue({"log_id": row[0], **n.__dict__})
    return True
```

**Provider send with suppression check and error classification:**

```python
from email.utils import formataddr

async def deliver_email(session, log_id: int, to: str, template: str, data: dict) -> None:
    if await is_suppressed(session, to):
        await mark(session, log_id, "suppressed")
        return

    html, text, subject = render(template, data)       # Jinja2: autoescape on
    try:
        resp = await ses_client.send_email(
            FromEmailAddress=formataddr(("Example", "no-reply@notify.example.com")),
            Destination={"ToAddresses": [to]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Html": {"Data": html, "Charset": "UTF-8"},
                             "Text": {"Data": text, "Charset": "UTF-8"}},
                }
            },
            EmailTags=[{"Name": "template", "Value": template}],
        )
    except ProviderThrottled:
        raise TransientJobError("throttled")            # retry with backoff
    except ProviderRejected as exc:
        await mark(session, log_id, "failed", error=str(exc)[:500])
        return                                          # permanent — do not retry

    await mark(session, log_id, "sent", provider_id=resp["MessageId"])
```

**Templates: HTML + text, escaped, localized:**

```jinja
{# templates/email/password_reset.html.j2 #}
<!doctype html>
<html lang="{{ locale }}"><body style="font-family:system-ui,sans-serif;background:#f8fafc;padding:24px">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;padding:32px">
    <h1 style="font-size:20px;margin:0 0 16px">Reset your password</h1>
    <p style="line-height:1.6">Hi {{ user_name }},</p>
    <p style="line-height:1.6">Use the button below within {{ ttl_minutes }} minutes.
       If you didn't request this, you can ignore this email.</p>
    <p style="margin:24px 0">
      <a href="{{ reset_url }}" style="background:#2563eb;color:#fff;padding:12px 20px;
         border-radius:8px;text-decoration:none">Reset password</a>
    </p>
    <p style="color:#64748b;font-size:12px">This link can be used once. It expires at {{ expires_at }} {{ tz }}.</p>
  </div>
</body></html>
```

```jinja
{# templates/email/password_reset.txt.j2 #}
Hi {{ user_name }},

Reset your password within {{ ttl_minutes }} minutes:
{{ reset_url }}

If you didn't request this, ignore this email. The link can be used once.
```

Always send a multipart alternative; plain text improves deliverability and accessibility. Escape user-provided values (Jinja2 `autoescape=True`) — a name containing HTML becomes an injection vector.

**Deliverability DNS records:**

```dns
; SPF (one record, includes the provider, ends with ~all)
notify.example.com.      TXT "v=spf1 include:amazonses.com ~all"

; DKIM (2048-bit, provider CNAMEs or TXT selectors)
s1._domainkey.notify.example.com. CNAME s1.dkim.amazonses.com.

; DMARC, start permissive, then enforce
_dmarc.example.com.      TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com; adkim=s; aspf=s; pct=100"

; Return-Path/bounce subdomain alignment
; Track opens/clicks on a separate link domain (clicks.example.com)
```

**Feedback webhook handler (bounces and complaints):**

```python
@router.post("/webhooks/email/provider")
async def provider_events(request: Request, session=Depends(get_session)):
    raw = await request.body()
    if not verify_provider_signature(raw, request.headers):
        raise HTTPException(401)                        # never process unsigned events

    for event in parse_events(raw):
        if event["type"] == "PermanentBounce":
            await suppress(session, event["email"], "hard_bounce")
        elif event["type"] == "Complaint":
            await suppress(session, event["email"], "complaint")
        elif event["type"] == "TransientBounce":
            pass                                        # provider retries; do not suppress
        await update_status(session, event["message_id"], event["type"])
    return {"ok": True}
```

**Unsubscribe with one-click headers and a signed link:**

```python
def unsubscribe_headers(user_id: str, category: str) -> dict[str, str]:
    token = sign_token({"u": user_id, "c": category}, ttl_days=365)
    url = f"https://app.example.com/unsubscribe?token={token}"
    return {
        "List-Unsubscribe": f"<{url}>, <mailto:unsubscribe@notify.example.com?subject={token}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
```

```python
@router.post("/unsubscribe")
async def unsubscribe(token: str, session=Depends(get_session)):
    claims = verify_token(token)                       # signature + expiry + purpose
    await session.execute(
        """INSERT INTO notification_pref (user_id, category, channel, enabled)
           VALUES (:u, :c, 'email', false)
           ON CONFLICT (user_id, category, channel) DO UPDATE SET enabled = false""",
        {"u": claims["u"], "c": claims["c"]},
    )
    return {"ok": True}                                # idempotent, no login required
```

**Preference gate before dispatch:**

```python
async def should_send(session, user_id: str, category: str, channel: str) -> bool:
    pref = await session.scalar(
        select(NotificationPref.enabled).where(
            NotificationPref.user_id == user_id,
            NotificationPref.category == category,
            NotificationPref.channel == channel,
        )
    )
    return True if pref is None else pref              # default-on for transactional
```

Transactional categories (password reset, receipts, security alerts) must be non-optional and excluded from marketing preferences; say so in the UI.

**Test with a capturing transport:**

```python
def test_password_reset_email(notifier, mailbox):
    notifier.send_password_reset(user_id="u1", email="a@example.com", reset_token="tok")
    msg = mailbox[-1]
    assert msg["Subject"] == "Reset your password"
    assert "https://app.example.com/reset?token=tok" in msg.text_body
    assert msg.text_body.strip()                        # multipart alternative exists
    assert "List-Unsubscribe" not in msg.headers        # transactional mail opts out of marketing headers
```

## 8. Quality Standards

- Every message is idempotent; retries never duplicate sends.
- Both HTML and plain-text bodies are rendered, localized, and escaped.
- SPF, DKIM, and DMARC are configured and monitored; DMARC policy is enforced after a baseline period.
- Hard bounces and complaints immediately suppress the address; suppression is checked before every send.
- Unsubscribe works with one click, without login, and is honored within seconds.
- Transactional and marketing mail use different subdomains/streams.
- Every send is logged with status and provider message ID for support.
- Reset/verification tokens are single-use, short-lived, and never logged.

## 9. Verification and Testing

- Render tests for every template (HTML + text), including RTL and long names.
- Idempotency test: dispatch the same notification twice; exactly one provider call.
- Sandbox delivery to a real inbox on Gmail/Outlook; check SPF/DKIM pass in headers (`Authentication-Results`).
- Bounce simulation: provider sandbox hard bounce → address suppressed, subsequent sends skipped.
- Unsubscribe test: one-click POST marks the preference and blocks the next marketing send.
- Link validity: reset token expires and is single-use.
- Accessibility: email renders with images blocked and at 200% zoom.

## 10. Security Considerations

- Never put tokens, passwords, or full PII in subject lines or URLs that appear in logs/referrers; use single-use tokens.
- Verify provider webhook signatures; an unsigned endpoint lets anyone suppress addresses or forge delivery events.
- HTML injection in templates: escape all interpolated user data and never render raw user HTML.
- Prevent open redirects in click-tracking links; validate the destination against an allowlist.
- Send from a dedicated subdomain so a compromise cannot damage the primary domain's reputation or cookie scope.
- Rate-limit notification triggers per user to prevent using your system to spam a third party (mail-bombing).
- Comply with consent and retention: store minimal recipient data, honor deletion requests, and document lawful basis.
- SMS costs money per message — enforce per-user quotas and alert on spikes (SMS pumping fraud).

## 11. Failure Handling

- **Mail lands in spam:** check SPF/DKIM/DMARC alignment, link reputation, spammy content, and volume spikes; use a seed-list test.
- **Duplicate emails after a job retry:** the dedupe key was not unique per event (e.g., included a timestamp); derive it from the business event.
- **Deliverability collapse:** a spike of complaints or a purchased list; stop sending, review consent, and warm up again.
- **Provider outage:** fail over to a secondary provider for critical transactional mail, with a shared suppression list.
- **Notifications silently missing:** check preference defaults and suppression before assuming a provider issue; log the reason at decision time.
- **SMS not delivered in India:** DLT template registration missing or mismatched; register templates and headers with the operator.

## 12. Expected Deliverables

1. Channel and provider architecture.
2. Template inventory with HTML/text/localized variants.
3. DNS authentication records and DMARC rollout plan.
4. Idempotency/dedupe scheme.
5. Bounce, complaint, and suppression handling.
6. Preference and unsubscribe design.
7. Delivery observability and support lookup.

## 13. References

- RFC 8617 (DMARC-related) and RFC 7489 DMARC — https://www.rfc-editor.org/rfc/rfc7489
- RFC 7208 SPF — https://www.rfc-editor.org/rfc/rfc7208
- RFC 6376 DKIM — https://www.rfc-editor.org/rfc/rfc6376
- RFC 8058 One-Click Unsubscribe — https://www.rfc-editor.org/rfc/rfc8058
- Amazon SES developer guide — https://docs.aws.amazon.com/ses/latest/dg/Welcome.html
- Gmail sender guidelines — https://support.google.com/mail/answer/81126
- Postmark transactional email best practices — https://postmarkapp.com/guides/transactional-email-best-practices
- MJML (responsive email framework) — https://documentation.mjml.io/
- Google Postmaster Tools — https://postmaster.google.com/
