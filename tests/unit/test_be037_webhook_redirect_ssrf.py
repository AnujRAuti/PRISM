"""BE-037 Phase 2: close BE-036-D1 — a webhook redirect must not reach a
prohibited destination.

BE-036-D1: ``urllib``'s *default* opener transparently follows HTTP 3xx
redirects. A subscription endpoint that passes ``validate_webhook_url`` could
answer with a redirect toward loopback, a private/link-local/cloud-metadata
address, or an HTTPS→HTTP downgrade, and the worker would connect to a
destination that was never validated. ``validate_webhook_url`` running on the
*original* URL does not help, because the bypass happens after validation, in
the transport layer.

These tests pin the fix at the layer that actually matters — the request path,
not the validator's return value — and follow the milestone's instruction to
verify that the *actual* request path cannot follow the prohibited destination:

* ``_opener_for`` builds a real ``OpenerDirector`` containing the production
  ``_NoRedirectHandler`` and a fake *transport* handler. The fake stands in only
  for the socket layer; the redirect-dispatch machinery is urllib's own, so a
  refusal here is a refusal of the real code path.
* Every redirect case asserts ``connects`` never contains the redirect target —
  the socket to the prohibited destination is never opened.
* A control case drives the *default* opener over the same fake transport to
  show it DOES connect to the redirect target — proving the vulnerability was
  real and that ``_NoRedirectHandler`` is what closes it.

No DNS and no network are touched: the fake transport never opens a socket, and
``deliver_webhook`` tests stub ``socket.getaddrinfo`` so the real SSRF validator
runs against a deterministic public answer.
"""

from __future__ import annotations

import ipaddress
import urllib.error
import urllib.request
from email.message import Message

import pytest

from backend.services import webhook as ws


VALID_ENDPOINT = "https://hooks.invalid.example/poa-be037"


# ---------------------------------------------------------------------------
# Fake transport (socket layer only)
# ---------------------------------------------------------------------------


class _FakeResponse:
    """A minimal urllib response: enough for the real dispatch machinery."""

    def __init__(self, url: str, code: int, headers: Message):
        self.url = url
        self.code = code
        self.status = code
        self.msg = ""
        self._headers = headers

    def info(self):
        return self._headers

    def geturl(self):
        return self.url

    def read(self, *args):
        return b""

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeTransport(urllib.request.BaseHandler):
    """Return a canned response for the first URL requested and record connects.

    ``handler_order`` (10) is below urllib's real HTTP(S)Handler so this is the
    handler consulted first, and it never opens a socket. Because it returns a
    non-``None`` response, the real network handlers are not reached.
    """

    handler_order = 10

    def __init__(self, plan: dict[str, tuple[int, str | None]]):
        self.connects: list[str] = []
        self.plan = plan

    def http_open(self, req):
        return self._open(req)

    def https_open(self, req):
        return self._open(req)

    def _open(self, req):
        self.connects.append(req.full_url)
        code, location = self.plan.get(req.full_url, (200, None))
        headers = Message()
        if location is not None:
            headers["Location"] = location
        return _FakeResponse(req.full_url, code, headers)


def _opener_for(transport: _FakeTransport, *, reject_redirects: bool):
    handlers: list[urllib.request.BaseHandler] = [transport]
    if reject_redirects:
        handlers.insert(0, ws._NoRedirectHandler())
    return urllib.request.build_opener(*handlers)


def _drive(opener, url: str):
    req = urllib.request.Request(url, data=b"x", method="POST")
    req.timeout = 10
    try:
        with opener.open(req) as resp:
            return ("ok", resp.status)
    except Exception as exc:  # noqa: BLE001 - tests assert the exception type
        return ("raised", exc)


# ---------------------------------------------------------------------------
# 2.  Redirect toward every prohibited destination is refused without a send
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,redirect_target",
    [
        ("loopback-v4", "http://127.0.0.1/latest/admin"),
        ("loopback-v6", "https://[::1]/internal"),
        ("private-v4-10", "http://10.0.0.5/internal"),
        ("private-v4-192", "http://192.168.1.1/gateway"),
        ("private-v4-172", "http://172.16.9.9/secret"),
        ("link-local-metadata-v4", "http://169.254.169.254/latest/meta-data/"),
        ("link-local", "http://169.254.1.1/nd"),
        ("carrier-nat", "http://100.64.0.1/x"),
        ("ula-v6", "https://[fd00::5]/x"),
        ("link-local-v6-metadata", "https://[fd00:ec2::254]/meta"),
        ("disallowed-hostname", "http://localhost:8080/anything"),
    ],
)
def test_redirect_to_prohibited_destination_is_refused(label, redirect_target):
    transport = _FakeTransport({VALID_ENDPOINT: (302, redirect_target)})
    opener = _opener_for(transport, reject_redirects=True)

    kind, payload = _drive(opener, VALID_ENDPOINT)

    assert kind == "raised", f"{label}: a redirect must not deliver"
    assert isinstance(payload, ws.WebhookRedirectError)
    # The security-critical assertion: the socket to the redirect target was
    # never opened — only the originally validated URL was connected to.
    assert transport.connects == [VALID_ENDPOINT], (
        f"{label}: opener connected to {transport.connects}; redirect target "
        f"{redirect_target!r} must never be reached"
    )


def test_https_to_http_downgrade_redirect_is_refused():
    """A redirect from https to a plaintext endpoint is rejected outright."""
    downgrade = "http://hooks.invalid.example/poa-plain"
    transport = _FakeTransport({VALID_ENDPOINT: (301, downgrade)})
    opener = _opener_for(transport, reject_redirects=True)

    kind, payload = _drive(opener, VALID_ENDPOINT)

    assert kind == "raised" and isinstance(payload, ws.WebhookRedirectError)
    assert transport.connects == [VALID_ENDPOINT]
    assert downgrade not in transport.connects


def test_every_redirect_is_rejected_including_public_destinations():
    """Chosen contract: reject ALL redirects, not just ones to blocked ranges.

    A public→public redirect is also refused, so redirect-based SSRF pivoting
    (a public hop that is itself the attacker's rebind step) cannot be used as
    a chain to reach an internal target on a later hop.
    """
    public = "https://elsewhere.invalid.example/hook"
    transport = _FakeTransport({VALID_ENDPOINT: (302, public)})
    opener = _opener_for(transport, reject_redirects=True)

    kind, payload = _drive(opener, VALID_ENDPOINT)

    assert kind == "raised" and isinstance(payload, ws.WebhookRedirectError)
    assert transport.connects == [VALID_ENDPOINT], "no second hop may be followed"


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_all_redirect_status_codes_are_refused(code):
    """Any 3xx-with-Location is refused, not only the codes urllib special-cases."""
    target = "http://127.0.0.1/secret"
    transport = _FakeTransport({VALID_ENDPOINT: (code, target)})
    opener = _opener_for(transport, reject_redirects=True)

    kind, payload = _drive(opener, VALID_ENDPOINT)

    assert kind == "raised" and isinstance(payload, ws.WebhookRedirectError)
    assert transport.connects == [VALID_ENDPOINT]


def test_redirect_chain_cannot_bypass_via_a_second_hop():
    """Even a redirect to another public host is refused, so chains are bounded at 0."""
    hop2 = "https://p2.invalid.example/r"
    transport = _FakeTransport({VALID_ENDPOINT: (302, hop2)})
    opener = _opener_for(transport, reject_redirects=True)

    kind, payload = _drive(opener, VALID_ENDPOINT)

    assert kind == "raised" and isinstance(payload, ws.WebhookRedirectError)
    assert transport.connects == [VALID_ENDPOINT]
    assert hop2 not in transport.connects


# ---------------------------------------------------------------------------
# 1.  An ordinary valid destination still delivers through the opener
# ---------------------------------------------------------------------------


def test_ordinary_valid_destination_delivers_unchanged():
    """A 2xx response (no Location) is delivered exactly as before — no over-block."""
    transport = _FakeTransport({VALID_ENDPOINT: (200, None)})
    opener = _opener_for(transport, reject_redirects=True)

    kind, payload = _drive(opener, VALID_ENDPOINT)

    assert kind == "ok" and payload == 200
    assert transport.connects == [VALID_ENDPOINT]


# ---------------------------------------------------------------------------
# Control: prove BE-036-D1 was real — the DEFAULT opener follows the redirect.
# ---------------------------------------------------------------------------


def test_default_opener_would_have_followed_the_redirect_control():
    """Without ``_NoRedirectHandler`` the same transport is driven to the target.

    This is the vulnerability BE-036-D1 described: the plain opener re-issues
    the request against the Location, so the prohibited destination IS connected
    to. It is asserted here so the fix is demonstrably the thing that closes the
    gap, rather than a test that merely checks a return value.
    """
    target = "http://127.0.0.1/latest-meta-stub"
    transport = _FakeTransport({VALID_ENDPOINT: (302, target), target: (200, None)})
    opener = _opener_for(transport, reject_redirects=False)  # default redirect handler

    _drive(opener, VALID_ENDPOINT)

    # Control only: the *unfixed* path reaches the target. (A real server would
    # re-issue as GET for 302, but the fake transport accepts either method.)
    assert target in transport.connects, (
        "control broken: default opener should follow the redirect; if urllib "
        "stops doing so this regression test no longer demonstrates BE-036-D1"
    )


# ---------------------------------------------------------------------------
# deliver_webhook: validation and transport wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def public_resolver(monkeypatch):
    """Deterministic DNS for the SSRF validator: named hosts → a public IP."""

    def _fake(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
            resolved = host
        except ValueError:
            resolved = "93.184.216.34"
        return [(2, 1, 6, "", (resolved, 0))]

    monkeypatch.setattr(ws.socket, "getaddrinfo", _fake)


def test_deliver_webhook_returns_status_and_sets_timeout(public_resolver, monkeypatch):
    captured: dict[str, object] = {}

    class _Resp:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _fake_open(req, *args, **kwargs):
        captured["req"] = req
        return _Resp()

    monkeypatch.setattr(ws.NO_REDIRECT_OPENER, "open", _fake_open)

    status = ws.deliver_webhook(VALID_ENDPOINT, b"{}1", {"A": "b"}, timeout=10)

    assert status == 201
    req = captured["req"]
    assert isinstance(req, urllib.request.Request)
    assert req.full_url == VALID_ENDPOINT
    assert req.get_method() == "POST"
    assert req.data == b"{}1"
    assert req.headers.get("A") == "b"
    assert getattr(req, "timeout", None) == 10, "explicit outbound timeout preserved"


def test_deliver_webhook_blocks_ssrf_before_any_connect(public_resolver, monkeypatch):
    """A prohibited endpoint fails validation and the opener is never invoked."""
    calls: list[object] = []

    def _fake_open(req, *args, **kwargs):
        calls.append(req)
        raise AssertionError("must not connect for a blocked URL")

    monkeypatch.setattr(ws.NO_REDIRECT_OPENER, "open", _fake_open)

    with pytest.raises(ValueError):
        ws.deliver_webhook("http://169.254.169.254/latest/meta-data/", b"{}", {})

    assert calls == [], "SSRF-blocked delivery must not reach the transport"


def test_deliver_webhook_propagates_redirect_error(public_resolver, monkeypatch):
    """A refused redirect surfaces from deliver_webhook as a ValueError subclass."""

    class _Boom:
        def __enter__(self):
            raise ws.WebhookRedirectError("302 to http://127.0.0.1/x")

        def __exit__(self, *exc):
            return False

    def _fake_open(req, *args, **kwargs):
        # Real opener raises before entering the with-block; emulate that.
        raise ws.WebhookRedirectError("302 to http://127.0.0.1/x")

    monkeypatch.setattr(ws.NO_REDIRECT_OPENER, "open", _fake_open)

    with pytest.raises(ws.WebhookRedirectError):
        ws.deliver_webhook(VALID_ENDPOINT, b"{}", {})

    # It is a ValueError, so the worker's permanent-failure branch can catch it.
    assert issubclass(ws.WebhookRedirectError, ValueError)
