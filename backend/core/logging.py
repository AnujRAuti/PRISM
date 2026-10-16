import logging
import re
import sys
import contextvars

from backend.observability.redaction import EXACT_MATCH_REDACT

request_id_ctx = contextvars.ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        rid = request_id_ctx.get(None)
        record.request_id = rid or "-"
        return True


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [rid=%(request_id)s] %(message)s"

# Credentials can only reach the log stream as text, so the scrubbers match
# text shapes rather than structures. The key names come from the telemetry
# redaction catalogue so the two paths cannot drift apart.
_KEY_NAMES = "|".join(sorted(EXACT_MATCH_REDACT))

_SCRUBBERS = (
    # ``"password": "…"``, ``token=…``, ``Authorization: Bearer …`` — the whole
    # value is replaced; the optional bearer word stays visible so an operator
    # can still tell which scheme was used.
    (re.compile(
        r'(["\']?(?:' + _KEY_NAMES + r')\b["\']?\s*[:=]\s*["\']?(?:bearer\s+)?["\']?)'
        r'([^\s"\',;}&\]]+)',
        re.IGNORECASE), r'\1[REDACTED]'),
    # ``scheme://[user]:password@host`` — connection strings, including the
    # password-only form Redis uses (``redis://:secret@host:6379/0``).
    (re.compile(r'([a-z][a-z0-9+.-]*://[^\s/@:]*:)([^\s/@]+)@', re.IGNORECASE),
     r'\1[REDACTED]@'),
    # Credential-bearing query parameters of presigned/S3-style URLs.
    (re.compile(r'([?&](?:x-amz-credential|x-amz-signature|x-amz-security-token'
                r'|awsaccesskeyid|signature|token|secret)=)([^&\s]+)', re.IGNORECASE),
     r'\1[REDACTED]'),
    # Any bearer token that appears without a recognised key in front of it.
    (re.compile(r'(\bbearer\s+)([A-Za-z0-9._~+/=-]{8,})', re.IGNORECASE),
     r'\1[REDACTED]'),
    # Bare JWTs (three base64url segments) interpolated into a message.
    (re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*)?'),
     '[REDACTED]'),
)


def scrub_secrets(text: str) -> str:
    """Replace credential-shaped substrings with ``[REDACTED]``."""
    for pattern, replacement in _SCRUBBERS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    """Format a record, then scrub its rendered line.

    Applied to the final output on purpose: that covers the message, the
    interpolated args *and* exception text, which no record-level filter can
    reach. Without it anything a ``logger.*`` call interpolates reaches stdout
    verbatim.
    """

    def format(self, record):
        return scrub_secrets(super().format(record))


def setup_logging(stream=None):
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(RedactingFormatter(LOG_FORMAT))
    # The filter belongs on the handler, not the root logger: ancestor logger
    # filters are not consulted for records propagating up from third-party
    # loggers, and those records then fail to format the [rid=...] field.
    handler.addFilter(RequestIdFilter())
    root.setLevel(logging.INFO)
    root.addHandler(handler)
