"""
Unit tests for observability logging.
"""
import json
from unittest.mock import Mock


from backend.observability.logging import (
    setup_logging,
    get_logger,
    log_request,
    log_worker_job,
    log_storage_operation,
    log_webhook_delivery,
    add_request_id,
    add_trace_ids,
    add_service_info,
    format_as_json,
    STRUCTLOG_AVAILABLE,
)
import backend.observability.logging as logging_module
from backend.observability.redaction import redact_sensitive_data


def test_setup_logging():
    """Test logging setup.

    structlog optional at runtime: when available, setup_logging must
    configure it; when missing, the call degrades to a stdlib no-op
    instead of raising (telemetry must never break startup).
    """
    logging_module.STRUCTLOG_CONFIGURED = False
    setup_logging()
    if STRUCTLOG_AVAILABLE:
        assert logging_module.STRUCTLOG_CONFIGURED is True
    else:
        # Graceful fallback: no exception, no structlog configuration.
        assert logging_module.STRUCTLOG_CONFIGURED is False


def test_get_logger():
    """Test getting a logger instance."""
    logger = get_logger("test_logger")
    assert logger is not None


def test_add_request_id():
    """Test adding request ID to log entries."""
    event_dict = {}
    result = add_request_id(None, None, event_dict)
    assert "request_id" in result
    assert isinstance(result["request_id"], str)
    assert len(result["request_id"]) > 0


def test_add_trace_ids_no_otel():
    """Test trace ID addition when OpenTelemetry is not available."""
    event_dict = {}
    result = add_trace_ids(None, None, event_dict)
    # Should not add trace IDs when OTel is not available
    assert "trace_id" not in result or result.get("trace_id") is None
    assert "span_id" not in result or result.get("span_id") is None


def test_add_service_info():
    """Test adding service information."""
    event_dict = {}
    result = add_service_info(None, None, event_dict)
    assert result["service"] == "poa-backend"
    assert "component" in result


def test_format_as_json():
    """Test JSON formatting."""
    event_dict = {
        "message": "test message",
        "level": "info",
        "service": "test-service"
    }
    result = format_as_json(None, None, event_dict)
    parsed = json.loads(result)
    assert parsed["message"] == "test message"
    assert parsed["level"] == "info"
    assert parsed["service"] == "test-service"


def test_redact_sensitive_data():
    """Test sensitive data redaction."""
    data = {
        "username": "testuser",
        "password": "secret123",
        "api_key": "key123",
        "nested": {
            "token": "token123",
            "safe_field": "safe_value"
        },
        "list_data": [
            {"password": "list_secret"},
            "plain_value"
        ]
    }

    redacted = redact_sensitive_data(data)

    # Check that sensitive fields are redacted
    assert redacted["password"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["list_data"][0]["password"] == "[REDACTED]"

    # Check that safe fields are preserved
    assert redacted["username"] == "testuser"
    assert redacted["nested"]["safe_field"] == "safe_value"
    assert redacted["list_data"][1] == "plain_value"


def test_log_request():
    """Test logging HTTP requests."""
    logger = Mock()

    # Test successful request
    log_request(logger, "GET", "/api/test", status_code=200, duration_ms=150)
    logger.info.assert_called_once()

    # Test error request
    log_request(logger, "POST", "/api/test", status_code=500, duration_ms=200)
    logger.warning.assert_called_once()


def test_log_worker_job():
    """Test logging worker jobs."""
    logger = Mock()

    # Test started job
    log_worker_job(logger, "analysis_worker", "image_processing", job_id="job123")
    logger.info.assert_called()

    # Test completed job
    log_worker_job(logger, "analysis_worker", "image_processing",
                   job_id="job123", status="completed", duration_ms=1500)
    logger.info.assert_called()

    # Test failed job
    log_worker_job(logger, "analysis_worker", "image_processing",
                   job_id="job123", status="failed", duration_ms=100)
    logger.error.assert_called()


def test_log_storage_operation():
    """Test logging storage operations."""
    logger = Mock()

    # Test successful operation
    log_storage_operation(logger, "upload", provider="s3", status="success", duration_ms=500)
    logger.info.assert_called()

    # Test failed operation
    log_storage_operation(logger, "download", provider="minio", status="failed", duration_ms=100)
    logger.error.assert_called()


def test_log_webhook_delivery():
    """Test logging webhook deliveries."""
    logger = Mock()

    # Test successful delivery
    log_webhook_delivery(logger, "event123", "https://example.com/webhook",
                        status_code=200, duration_ms=300)
    logger.info.assert_called()

    # Test failed delivery
    log_webhook_delivery(logger, "event124", "https://example.com/webhook2",
                        status_code=500, duration_ms=500)
    logger.warning.assert_called()
