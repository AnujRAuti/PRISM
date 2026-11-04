---
name: webhook-engineering
description: Build webhook senders and receivers that are trustworthy—HMAC signing, timestamp windows, replay protection, retries with backoff, and SSRF-safe delivery.
metadata:
  domain: backend
  version: 1.0.0
  risk: high
---

# Webhook Engineering

## 1. Purpose

Deliver events to other systems, and accept events from them, without creating a forgery or replay hole. Webhooks are unauthenticated HTTP by default: anything that knows the URL can POST to it. Receivers must verify signatures over raw bodies within a time window and deduplicate by event ID; senders must retry with backoff, isolate failures per endpoint, and never let a user-supplied URL turn into an SSRF pivot.

**Scope:** your own senders and receivers. Outbound webhooks to customer URLs are a server-side request forgery surface by construction—allowlist schemes, block private ranges, and require verification before delivery. Testing SSRF defenses must stay within infrastructure you own or are authorized to test.

## 2. Activation Conditions

- Integrating a payment, CRM, or messaging provider via webhooks.
- Exposing events to customer endpoints.
- Webhook endpoints receive forged, duplicated, or out-of-order events.
- Deliveries fail silently or retry forever.
- Keywords: webhook, HMAC, signature, Svix, Stripe signature, replay attack, idempotency, retry, dead letter, SSRF, event delivery, endpoint verification.

## 3. When Not to Use

- Highly reliable, ordered, high-volume event delivery where a broker (Kafka/NATS) or a pull API with cursors is more appropriate.
- Same-process events (use an in-process event bus).

## 4. Required Context

1. Direction: receiving provider events, sending customer events, or both.
2. Provider signature scheme and documented algorithm.
3. Event volume, ordering needs, and delivery latency tolerance.
4. Retry policy expectations of consumers.
5. Egress controls available (proxy, allowlist) for outbound delivery.

## 5. Operating Procedure

**Receiving**

1. **Read the raw body** before any parsing middleware; signature verification must run on exact bytes.
2. **Verify the signature** with HMAC-SHA256 (or the provider's documented scheme), comparing in constant time, over `timestamp + "." + raw_body`.
3. **Enforce a timestamp window** (±5 minutes) to block replays of captured payloads.
4. **Deduplicate by event ID** with a unique constraint; return `200` for duplicates so the sender stops retrying.
5. **Acknowledge fast, process asynchronously**: verify, persist the event, return `2xx`, then handle it in a worker.
6. **Validate the payload schema** and version before acting; unknown types are acknowledged and ignored, not errored.
7. **Never trust payload state over your own records**: fetch the authoritative object from the provider API when the event changes money or entitlements.

**Sending**

8. **Sign every delivery** with a per-endpoint secret, include `X-Webhook-Timestamp` and `X-Webhook-Id`, and document the verification recipe for consumers.
9. **Deliver from a queue with per-endpoint isolation**: exponential backoff with jitter for up to 24–72 h, then a dead-letter state visible in the dashboard.
10. **Set timeouts and cap response sizes** (e.g. 10 s connect/read, read at most 8 kB); treat a slow endpoint as failing.
11. **Prevent SSRF**: require HTTPS, resolve DNS and reject private/loopback/link-local/metadata IPs, re-resolve on redirects, disable redirects by default.
12. **Rotate secrets** with an overlap window and support multiple active secrets during rotation.
13. **Give consumers control**: endpoint enable/disable, delivery logs, manual replay, and a test event.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Provider SDKs | Stripe, GitHub, Razorpay, Shopify (signature helpers) |
| Signing | `hmac` + `hashlib` (Python), Node `crypto.timingSafeEqual` |
| Delivery infra | Your job queue (Celery/BullMQ), Svix, Hookdeck |
| SSRF defense | Egress proxy, allowlist, DNS pinning, `ipaddress` checks |
| Local testing | `stripe listen`, `ngrok`, `smee.io`, Mailpit-like relays |
| Contract tests | Provider sandbox fixtures, recorded payloads |

## 7. Practical Implementation

**Receiver: verify, dedupe, persist, acknowledge fast**

```python
import hashlib, hmac, json, time
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
TOLERANCE_SECONDS = 300

def verify_signature(raw: bytes, timestamp: str, signature: str, secret: bytes) -> bool:
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > TOLERANCE_SECONDS:
        return False
    signed = timestamp.encode() + b"." + raw
    expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)     # constant time

@router.post("/webhooks/payments")
async def payments_webhook(request: Request, session=Depends(get_session)):
    raw = await request.body()
    ts = request.headers.get("X-Webhook-Timestamp", "")
    sig = request.headers.get("X-Webhook-Signature", "")

    if not verify_signature(raw, ts, sig, WEBHOOK_SECRET):
        raise HTTPException(401, "invalid signature")     # log with source IP, never the secret

    event = json.loads(raw)                               # parse only after verification
    if event.get("schema_version") != "1":
        return {"ok": True, "ignored": "unsupported_version"}

    inserted = (await session.execute(
        """INSERT INTO webhook_event (provider, event_id, type, payload, received_at)
           VALUES ('payments', :id, :type, :payload, now())
           ON CONFLICT (provider, event_id) DO NOTHING
           RETURNING id""",
        {"id": event["id"], "type": event["type"], "payload": json.dumps(event)},
    )).first()

    if inserted is None:
        return {"ok": True, "duplicate": True}             # 200 so the sender stops retrying

    await webhook_queue.enqueue({"event_row_id": inserted[0]})
    return {"ok": True}                                    # ack in milliseconds
```

**Worker: re-fetch authoritative state before changing money or access**

```python
async def process_payment_event(session, payload: dict) -> None:
    if payload["type"] != "payment.succeeded":
        return
    reference = payload["data"]["reference"]
    # Trust the provider API, not the webhook body, for amounts and status
    payment = await payments_api.retrieve(reference)
    if payment.status != "succeeded" or payment.amount_cents != int(payload["data"]["amount_cents"]):
        await audit.warn("webhook_state_mismatch", reference=reference)
        return
    async with session.begin():
        await mark_order_paid(session, reference, idempotency_key=f"payment:{reference}")
```

**Sender: per-endpoint delivery with backoff and dead-letter**

```python
import asyncio, hashlib, hmac, json, secrets, time
import httpx

async def deliver(endpoint: dict, event: dict, attempt: int) -> None:
    body = json.dumps(event, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    msg_id = event["id"]

    signature = hmac.new(endpoint["secret"].encode(), ts.encode() + b"." + body,
                         hashlib.sha256).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=False) as client:
            resp = await client.post(
                endpoint["url"], content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Id": msg_id,
                    "X-Webhook-Timestamp": ts,
                    "X-Webhook-Signature": signature,
                    "User-Agent": "Example-Webhooks/1.0",
                },
            )
    except (httpx.ConnectError, httpx.ReadTimeout) as exc:
        await schedule_retry(endpoint, event, attempt, reason=type(exc).__name__)
        return

    if 200 <= resp.status_code < 300:
        await record_delivery(endpoint["id"], msg_id, "delivered", resp.status_code)
    elif resp.status_code in (410, 404) or 400 <= resp.status_code < 500:
        await record_delivery(endpoint["id"], msg_id, "failed", resp.status_code)
        if resp.status_code in (401, 403):
            await disable_endpoint(endpoint["id"], reason="auth_rejected")   # stop hammering
    else:
        await schedule_retry(endpoint, event, attempt, reason=f"http_{resp.status_code}")

async def schedule_retry(endpoint, event, attempt, *, reason: str) -> None:
    if attempt >= 12:
        await record_delivery(endpoint["id"], event["id"], "dead", None, reason=reason)
        await notify_endpoint_owner(endpoint["id"], event["id"])
        return
    delay = min(6 * 3600, 15 * 2 ** attempt) * (0.5 + secrets.randbelow(1000) / 1000)
    await delivery_queue.enqueue_in(delay, deliver, endpoint, event, attempt + 1)
```

**SSRF-safe URL validation for customer endpoints**

```python
import ipaddress, socket
from urllib.parse import urlparse

BLOCKED = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "::1/128", "fc00::/7", "fe80::/10", "::ffff:0:0/96",
)]

def validate_endpoint_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("endpoint must use https")
    if not parsed.hostname or parsed.port not in (None, 443):
        raise ValueError("endpoint must use the default HTTPS port")
    infos = socket.getaddrinfo(parsed.hostname, 443, proto=socket.IPPROTO_TCP)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved \
                or any(ip in net for net in BLOCKED):
            raise ValueError("endpoint resolves to a disallowed address")
```

Resolve-and-pin at delivery time, not only at registration (DNS rebinding), and re-validate after any redirect. Where available, route all outbound deliveries through an egress proxy with an allowlist.

**Endpoint verification handshake (prove ownership before sending events)**

```python
@router.post("/webhook-endpoints")
async def create_endpoint(payload: EndpointIn, principal: Principal = Depends(require_user),
                          session=Depends(get_session)):
    validate_endpoint_url(payload.url)
    endpoint = WebhookEndpoint(
        id=str(uuid.uuid4()), tenant_id=principal.tenant_id, url=payload.url,
        secret=secrets.token_urlsafe(32), status="pending_verification",
        event_types=payload.event_types,
    )
    session.add(endpoint)
    await session.commit()
    await deliver_test_event(endpoint)          # consumer must echo the challenge back
    return {"id": endpoint.id, "secret": endpoint.secret, "status": endpoint.status}
```

**Consumer verification snippet (documented for your users):**

```python
# Reference implementation published in your docs
def verify(raw_body: bytes, headers: dict, secret: str) -> bool:
    ts, sig = headers["X-Webhook-Timestamp"], headers["X-Webhook-Signature"]
    if abs(time.time() - int(ts)) > 300:
        return False
    expected = hmac.new(secret.encode(), ts.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
```

**Tables backing delivery state:**

```sql
CREATE TABLE webhook_endpoint (
  id           uuid PRIMARY KEY,
  tenant_id    text NOT NULL,
  url          text NOT NULL,
  secret       text NOT NULL,                 -- encrypt at rest
  status       text NOT NULL CHECK (status IN ('pending_verification','active','disabled')),
  event_types  text[] NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE webhook_delivery (
  id           bigserial PRIMARY KEY,
  endpoint_id  uuid NOT NULL REFERENCES webhook_endpoint(id) ON DELETE CASCADE,
  event_id     text NOT NULL,
  attempt      int  NOT NULL DEFAULT 1,
  status       text NOT NULL CHECK (status IN ('delivered','failed','dead')),
  http_status  int,
  reason       text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (endpoint_id, event_id, attempt)
);
CREATE INDEX webhook_delivery_dead ON webhook_delivery (endpoint_id, created_at DESC) WHERE status = 'dead';
```

## 8. Quality Standards

- Signatures are computed over the raw body plus timestamp and verified in constant time.
- A timestamp window rejects replays; event IDs are deduplicated by a unique constraint.
- Receivers acknowledge in under a second and process asynchronously.
- Receivers never trust webhook amounts/entitlements without re-fetching authoritative state.
- Deliveries retry with exponential backoff and jitter, then dead-letter with an owner notification.
- Endpoint URLs are HTTPS-only, resolve to public IPs, and are re-validated at delivery (no SSRF).
- Secrets are per-endpoint, encrypted at rest, rotatable with overlap, and never logged.
- Delivery logs, manual replay, and endpoint disable are available to users/support.

## 9. Verification and Testing

- Tampered-body test: flip one byte → `401`.
- Replay test: resend a valid signed payload with the same timestamp → rejected after the window; within the window → deduplicated, side effect once.
- Missing/garbage signature headers → `401`, no parsing errors leaked.
- Slow endpoint test: consumer sleeps 15 s → sender times out, retries, and does not block other endpoints.
- 500-loop test: endpoint always fails → backoff schedule observed, dead-letter after the cap.
- SSRF test (in your own environment): endpoint pointing at `169.254.169.254` and `127.0.0.1` is rejected at registration and delivery.
- Queue isolation: one broken endpoint does not delay deliveries to healthy endpoints.

## 10. Security Considerations

- Signature verification must use the raw bytes; re-serializing JSON changes bytes and breaks or bypasses verification.
- Use `hmac.compare_digest`/`timingSafeEqual`; `==` on secrets is a timing oracle.
- Store endpoint secrets encrypted (KMS/envelope); never return them in list APIs after creation.
- Do not reflect request bodies or verification errors back to the caller—they leak internals.
- Require endpoint ownership verification and cap endpoints per tenant to prevent using your platform as an SSRF/DoS amplifier.
- Block redirects on delivery; a 302 to an internal address defeats validation.
- Rate-limit and monitor inbound webhooks; providers can be spoofed cheaply if signatures are optional.
- Webhook payloads often contain PII; encrypt at rest, set retention, and expose them only to the owning tenant.

## 11. Failure Handling

- **Endpoint reports missing events:** check dead-letter state and per-event delivery logs; offer replay rather than manual resend.
- **Duplicate processing downstream:** the receiver's dedupe key included a timestamp or delivery attempt; key on the provider's event ID only.
- **Signature mismatches in production only:** a proxy or framework is re-encoding the body, or the consumer is verifying the parsed JSON. Verify raw bytes.
- **Retry storm after an outage:** backoff resets when the queue restarts—persist the attempt count with the delivery record.
- **Provider sends events out of order:** order by the provider's sequence/timestamp and make the handler tolerant of late events (re-fetch state).
- **Endpoint disabled by mistake:** expose an enable action with an audit trail and an automatic re-verification.

## 12. Expected Deliverables

1. Signature scheme and verification recipe (published for consumers).
2. Receiver pipeline (verify → dedupe → persist → ack → process).
3. Sender delivery state machine with backoff schedule.
4. SSRF controls and endpoint verification flow.
5. Secret rotation procedure.
6. Delivery-log and replay tooling.
7. Test suite covering tampering, replay, duplication, and SSRF.

## 13. References

- Standard Webhooks specification — https://www.standardwebhooks.com/
- Stripe webhooks: signature verification — https://docs.stripe.com/webhooks/signatures
- GitHub webhook signature validation — https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- OWASP SSRF Prevention Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- RFC 2104 HMAC — https://www.rfc-editor.org/rfc/rfc2104
- Svix documentation — https://docs.svix.com/
- AWS IMDS security (blocking SSRF to metadata) — https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html
