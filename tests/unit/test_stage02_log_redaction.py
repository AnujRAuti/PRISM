"""Stage 02-2: the ordinary log stream must not carry credentials.

The audit measured that redaction existed but only reached OpenTelemetry span
attributes, while every ``logger.*`` call wrote its interpolated text to
stdout verbatim — and the four worker entrypoints configured ``logging.
basicConfig`` directly, bypassing even the application's log setup. These tests
pin the scrubber itself, the formatter that applies it to the *rendered* line
(so exception text is covered too), and the wiring of :func:`setup_logging`.
"""

import io
import logging

import pytest

from backend.core.logging import (
    LOG_FORMAT,
    RedactingFormatter,
    RequestIdFilter,
    scrub_secrets,
    setup_logging,
)


@pytest.mark.parametrize("raw, must_not_contain", [
    ("connect failed postgresql+psycopg2://poa_owner:S3cr3tPW@10.0.0.4:5432/pofa_prod",
     "S3cr3tPW"),
    ("redis unreachable at redis://:redispw123@poa_redis:6379/0", "redispw123"),
    ("outbound {'Authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc123'}",
     "eyJhbGciOiJIUzI1NiJ9"),
    ("retrying with token= abcdefghijklmnopqrstuvwx", "abcdefghijklmnopqrstuvwx"),
    ("presigned http://minio:9000/pofa-evidence/a.jpg?X-Amz-Credential=AKIA%2F2026"
     "&X-Amz-Signature=deadbeef9999", "deadbeef9999"),
    ("payload={\"password\": \"hunter2xyz\", \"user\": \"azure\"}", "hunter2xyz"),
    ("rotated client_id=7f6d5c4b client_secret=z9XqW2pLm4nR", "z9XqW2pLm4nR"),
])
def test_credential_shapes_are_scrubbed(raw, must_not_contain):
    assert must_not_contain not in scrub_secrets(raw)


@pytest.mark.parametrize("raw", [
    "retention sweep finished: {'evaluated': 12, 'archived': 3}",
    "uploaded evidence sha256=9f2c1b7a4d5e6f708192a3b4c5d6e7f80123456789abcdef project=42",
    "GET /api/v1/evidence/nearby?latitude=18.52&longitude=73.85&radius=1000 200 OK",
    "audit appended seq=9 type=ROLE_ASSIGNED resource=user_role_assignments:404097ce",
])
def test_operational_detail_is_not_collateral_damage(raw):
    """A scrubber that eats every log line tells nobody anything either.

    Digests, counters, coordinates and route names must survive: they are the
    reason the log stream is readable in the first place.
    """
    assert scrub_secrets(raw) == raw


def test_formatter_scrubs_args_and_exception_text():
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(RedactingFormatter(LOG_FORMAT))
    # LOG_FORMAT renders [rid=...], which RequestIdFilter supplies; a handler
    # without it cannot format a record (the pairing setup_logging installs).
    handler.addFilter(RequestIdFilter())
    logger = logging.getLogger("stage02.formatter")
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.info("worker retrying %s", "redis://:sup3rsecret@poa_redis:6379/0")
        try:
            raise ValueError("auth failed password=FrgttedPw99")
        except ValueError:
            logger.exception("analysis job failed")
    finally:
        logger.handlers[:] = []

    output = buffer.getvalue()
    assert "sup3rsecret" not in output
    assert "FrgttedPw99" not in output
    # Non-vacuity: the lines were written, only their secrets removed.
    assert "worker retrying" in output and "ValueError" in output


def test_setup_logging_installs_the_scrubber_on_the_shared_handler():
    """The wiring, not just the class: every process that calls setup_logging
    (the API and, since Stage 02, all four workers) gets the redacting format."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        root.handlers.clear()
        buffer = io.StringIO()
        setup_logging(stream=buffer)
        assert any(isinstance(h.formatter, RedactingFormatter) for h in root.handlers)
        logging.getLogger("backend.workers.analysis_worker").info(
            "storage configured with %s", "endpoint=minio client_secret=Wj0kS3yz")
        assert "Wj0kS3yz" not in buffer.getvalue()
        assert "storage configured with" in buffer.getvalue()
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
