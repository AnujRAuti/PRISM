---
name: realtime-and-websockets
description: Build realtime backends with WebSockets and SSE—connection lifecycle, auth handshake, heartbeats, backpressure, fan-out scaling, and reconnect semantics.
metadata:
  domain: backend
  version: 1.0.0
  risk: medium
---

# Realtime and WebSockets

## 1. Purpose

Push updates to clients without polling. Realtime adds state the request/response model never has: long-lived connections, per-connection authorization, fan-out across instances, backpressure when a client is slow, and reconnection storms after a deploy. This skill covers protocol choice, handshake authentication, heartbeats, message contracts, backpressure, horizontal scaling, and reconnect-with-resume.

**Scope:** your own realtime infrastructure. Every message pushed to a client is data disclosure if the channel authorization is wrong—subscribe authorization must be re-checked on connect and on permission change.

## 2. Activation Conditions

- Live dashboards, chat, notifications, collaborative editing, or progress updates.
- Polling at high frequency wastes bandwidth or hits rate limits.
- Connections drop, duplicate messages appear, or the server runs out of memory.
- Need to scale realtime beyond one instance.
- Keywords: WebSocket, SSE, long polling, pub/sub, Redis, STOMP, Socket.IO, heartbeat, backpressure, fan-out, reconnect, resumable, presence.

## 3. When Not to Use

- Updates needed less often than every ~30 s (polling or conditional requests suffice).
- One-way, low-frequency notifications (SSE or web push is simpler).
- Strict request/response semantics with no server-initiated events.

## 4. Required Context

1. Direction: server→client only, or bidirectional.
2. Expected concurrent connections and message rate per connection.
3. Delivery guarantees needed (at-most-once fine? ordering per room?).
4. Infrastructure: load balancer timeouts, sticky sessions, Redis/NATS availability.
5. Client platforms (browser, mobile with backgrounding).

## 5. Operating Procedure

1. **Pick the simplest protocol that works**: SSE for server→client only (auto-reconnect, works over HTTP/2); WebSockets for bidirectional or high-frequency; long polling as a fallback.
2. **Authenticate during the handshake** with a short-lived ticket or signed cookie; browsers cannot set headers on `WebSocket`, so avoid putting long-lived tokens in the query string (they leak into logs).
3. **Authorize each subscription** against the principal and the channel's resource; re-validate on permission change and on token expiry.
4. **Implement heartbeats**: server ping every 20–30 s, drop connections that miss two pongs, and configure the load balancer idle timeout above the ping interval.
5. **Define a message envelope**: `{type, id, channel, ts, data}` with versioned types; validate incoming messages against a schema.
6. **Bound every queue**: per-connection outbound buffer with a max size; on overflow, drop the connection (or close with a specific code) rather than growing memory without limit.
7. **Fan out via pub/sub** (Redis Pub/Sub, NATS, Redis Streams, Kafka) so any instance can serve any connection; never rely on in-process state for cross-instance delivery.
8. **Support resume**: keep a bounded per-channel sequence; client sends `last_seq` on reconnect and receives missed messages (or a "resync required" signal).
9. **Rate-limit inbound messages** per connection and cap frame size; reject oversized payloads before parsing.
10. **Handle deploys gracefully**: send a close frame with a "going away" code, and use reconnection jitter to avoid a thundering herd.
11. **Observe**: connections, messages/s, dropped due to backpressure, auth failures, and reconnect rates.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Python | FastAPI/Starlette WebSockets, `websockets`, `sse-starlette` |
| Node | `ws`, Socket.IO, `uWebSockets.js` |
| Fan-out | Redis Pub/Sub, NATS, Redis Streams, Kafka |
| Presence | Redis with TTL keys, NATS KV |
| Scaling | Sticky sessions by cookie, or stateless + pub/sub |
| Testing | `httpx`/`websockets` clients, k6 WebSocket scenarios, Autobahn suite |

## 7. Practical Implementation

**Handshake auth with a short-lived ticket:**

```python
import secrets, time
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

TICKETS: dict[str, tuple[str, float]] = {}      # ticket -> (user_id, expires_at); use Redis in production

@router.post("/realtime/ticket")
async def issue_ticket(principal: Principal = Depends(require_user)):
    ticket = secrets.token_urlsafe(24)
    TICKETS[ticket] = (principal.user_id, time.time() + 60)
    return {"ticket": ticket, "expires_in": 60}

@router.websocket("/realtime")
async def realtime(ws: WebSocket):
    ticket = ws.query_params.get("ticket", "")
    entry = TICKETS.pop(ticket, None)                     # single use
    if entry is None or entry[1] < time.time():
        await ws.close(code=4401)                          # custom: unauthorized
        return
    user_id = entry[0]
    await ws.accept()
    ...
```

**Connection loop with heartbeat, bounded queue, and clean close:**

```python
import asyncio, contextlib, json, logging

log = logging.getLogger(__name__)
MAX_FRAME = 64 * 1024
MAX_OUTBOUND = 256

async def run_connection(ws: WebSocket, user_id: str, hub: "Hub") -> None:
    outbox: asyncio.Queue[str] = asyncio.Queue(maxsize=MAX_OUTBOUND)
    tasks = [
        asyncio.create_task(reader(ws, hub, user_id)),
        asyncio.create_task(writer(ws, outbox)),
        asyncio.create_task(pinger(ws)),
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    finally:
        for t in tasks:
            t.cancel()
        with contextlib.suppress(Exception):
            await asyncio.gather(*tasks, return_exceptions=True)
        await hub.disconnect(user_id, outbox)

async def reader(ws: WebSocket, hub: "Hub", user_id: str) -> None:
    while True:
        raw = await ws.receive_text()
        if len(raw) > MAX_FRAME:
            await ws.close(code=4409)                      # frame too large
            return
        msg = json.loads(raw)
        if msg.get("type") == "subscribe":
            await hub.subscribe(user_id, msg["channel"])    # authorization inside
        elif msg.get("type") == "ping":
            pass

async def writer(ws: WebSocket, outbox: asyncio.Queue[str]) -> None:
    while True:
        payload = await outbox.get()
        await ws.send_text(payload)                         # blocked sends apply backpressure

async def pinger(ws: WebSocket) -> None:
    missed = 0
    while missed < 2:
        await asyncio.sleep(25)
        try:
            await ws.send_json({"type": "ping"})
            missed += 1                                     # reset on pong in reader
        except Exception:
            return
```

**Backpressure decision (drop the slow client, not the server):**

```python
def publish(self, user_id: str, payload: str) -> None:
    q = self._outboxes.get(user_id)
    if q is None:
        return
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        DROPPED.labels(channel="direct").inc()
        # Close asynchronously with a "slow consumer" code so the client can reconnect and resync
        asyncio.create_task(self._close(user_id, code=4408))
```

**Redis pub/sub fan-out across instances:**

```python
import redis.asyncio as redis

class Hub:
    def __init__(self, r: redis.Redis) -> None:
        self._r = r
        self._outboxes: dict[str, asyncio.Queue[str]] = {}
        self._subs: dict[str, set[str]] = {}

    async def subscribe(self, user_id: str, channel: str, *, principal) -> None:
        if not await can_subscribe(principal, channel):
            self._outboxes[user_id].put_nowait(json.dumps({"type": "error", "code": "FORBIDDEN"}))
            return
        self._subs.setdefault(channel, set()).add(user_id)
        await self._r.sadd(f"subs:{channel}", user_id)          # for other instances
        await self._r.publish("events", json.dumps({"channel": channel, "user": user_id,
                                                    "kind": "join"}))

    async def listen(self) -> None:
        pubsub = self._r.pubsub()
        await pubsub.subscribe("events")
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            evt = json.loads(message["data"])
            for uid in self._subs.get(evt["channel"], set()):
                self.publish(uid, json.dumps({"type": "event", "channel": evt["channel"],
                                              "data": evt["payload"]}))
```

In production, run one Redis subscription per instance and fan out locally to that instance's connections.

**SSE alternative (server→client only):**

```python
from sse_starlette.sse import EventSourceResponse

@router.get("/events")
async def events(request: Request, principal: Principal = Depends(require_user)):
    async def stream():
        last_id = request.headers.get("last-event-id")
        async for evt in event_bus.subscribe(principal.user_id, after=last_id):
            if await request.is_disconnected():
                break
            yield {"id": evt.seq, "event": evt.type, "data": evt.json()}
    return EventSourceResponse(stream(), ping=20, headers={"X-Accel-Buffering": "no"})
```

SSE resumes automatically via `Last-Event-ID`; design the event store to serve from a sequence number.

**Resume with a bounded replay buffer:**

```python
async def on_reconnect(user_id: str, last_seq: int, channel: str) -> list[dict]:
    buf = await store.range(channel, start=last_seq + 1, limit=500)
    if len(buf) == 500 or (buf and buf[0]["seq"] != last_seq + 1):
        return [{"type": "resync_required", "channel": channel}]   # too far behind
    return buf
```

**Load balancer and proxy settings:**

```nginx
location /realtime {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;      # must exceed heartbeat interval
    proxy_send_timeout 3600s;
    proxy_buffering off;
}
```

**Client reconnect with jitter (documented contract):**

```ts
export function connect(url: string, onMessage: (m: unknown) => void) {
  let attempt = 0;
  const open = () => {
    const ws = new WebSocket(url);
    ws.onmessage = (e) => onMessage(JSON.parse(e.data));
    ws.onclose = (e) => {
      if (e.code === 1000) return;                     // normal closure
      attempt++;
      const delay = Math.min(30_000, 500 * 2 ** attempt) * (0.5 + Math.random());
      setTimeout(open, delay);                         // jitter prevents synchronized reconnects
    };
  };
  open();
}
```

## 8. Quality Standards

- No long-lived credential in a URL; handshake uses a single-use, short-lived ticket.
- Every subscription is authorized server-side and re-checked when permissions change.
- Heartbeats and timeouts are configured end-to-end (client, proxy, server).
- Outbound buffers are bounded; slow consumers are disconnected with a specific close code.
- Fan-out works across instances via pub/sub, not in-memory maps.
- Messages are versioned, validated, and size-limited.
- Reconnect behavior is documented, including resume and resync semantics.
- Connection count, message rate, drops, and auth failures are monitored.

## 9. Verification and Testing

- Connect with an invalid/expired ticket → close code 4401.
- Subscribe to another tenant's channel → error frame, no data.
- Simulate a slow consumer (don't read from the socket) → server drops it after the buffer limit, memory stays flat.
- Kill one instance during traffic → clients reconnect to another instance and receive messages (no lost subscriptions).
- Reconnect with `last_seq` within and beyond the replay window → messages or `resync_required`.
- Load test with k6 WebSocket scenario at expected concurrency; measure connections/instance and memory.
- Verify proxy timeouts by idling a connection for the heartbeat interval.

## 10. Security Considerations

- Cross-site WebSocket hijacking: browsers send cookies on the handshake. Validate `Origin` against an allowlist and use ticket-based auth, not ambient cookies alone.
- Authorize every channel at subscribe time and on every publish if the permission may have changed; cache with short TTL and invalidate on role change.
- Do not broadcast sensitive tenant data to a shared channel; scope channels by resource and principal.
- Rate-limit inbound frames per connection and cap total connections per user/IP to prevent resource exhaustion.
- Mask the server's internal errors: close frames should carry codes, not stack traces.
- Compression (permessage-deflate) plus secrets enables compression side-channel leaks; disable compression for sensitive channels.
- Presence and typing indicators leak activity metadata — make them opt-in and avoid exposing exact timestamps to others.

## 11. Failure Handling

- **Connections drop every 60 s:** a proxy idle timeout shorter than the heartbeat; raise the timeout or shorten the ping.
- **Memory grows with connections:** unbounded outbound queues or per-message history retained per socket. Bound and evict.
- **Duplicate deliveries after reconnect:** the client replays without dedupe; use message IDs and resume from `last_seq`.
- **Thundering herd on deploy:** all clients reconnect simultaneously; use jittered backoff and drain connections with a "going away" close.
- **Messages lost while a node is down:** fan-out used in-process state; move to a durable log (Streams/Kafka) if delivery matters.
- **Auth expires mid-connection:** close with 4401 at token expiry and require a fresh ticket; the client reconnects transparently.

## 12. Expected Deliverables

1. Protocol choice and rationale.
2. Auth handshake and ticket design.
3. Message envelope and channel authorization model.
4. Heartbeat and timeout configuration for client, proxy, and server.
5. Backpressure and drop policy.
6. Scale-out and pub/sub topology.
7. Reconnect/resume contract and test results.

## 13. References

- MDN WebSocket API — https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API
- RFC 6455 The WebSocket Protocol — https://www.rfc-editor.org/rfc/rfc6455
- MDN Server-sent events — https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
- HTML Living Standard: Server-sent events — https://html.spec.whatwg.org/multipage/server-sent-events.html
- OWASP WebSocket security — https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
- FastAPI WebSockets — https://fastapi.tiangolo.com/advanced/websockets/
- Redis Pub/Sub — https://redis.io/docs/latest/develop/interact/pubsub/
- k6 WebSocket testing — https://grafana.com/docs/k6/latest/using-k6/protocols/websockets/
