"""BE-020 structured JSON logging with correlation IDs.

structlog is optional at runtime: when unavailable (minimal dev
environments) :func:`setup_logging` degrades gracefully to the existing
stdlib logging instead of breaking application startup — telemetry is
secondary to domain execution.
"""
import json
import logging
import sys
from typing import Any, Dict
from uuid import uuid4

try:  # pragma: no cover - exercised only when structlog is installed
    import structlog
    from structlog.stdlib import LoggerFactory

    STRUCTLOG_AVAILABLE = True
except ImportError:  # pragma: no cover
    structlog = None
    LoggerFactory = None
    STRUCTLOG_AVAILABLE = False

from backend.core.config import settings

STRUCTLOG_CONFIGURED = False


def add_request_id(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add request_id to log entries if not present."""
    if "request_id" not in event_dict:
        rid = None
        try:
            from backend.core.logging import request_id_ctx

            rid = request_id_ctx.get(None)
        except Exception:
            rid = None
        event_dict["request_id"] = rid or str(uuid4())
    return event_dict


def add_trace_ids(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add trace_id and span_id from OpenTelemetry context if available."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is not None:
            span_context = span.get_span_context()
            if span_context is not None and span_context.is_valid:
                event_dict["trace_id"] = format(span_context.trace_id, "032x")
                event_dict["span_id"] = format(span_context.span_id, "016x")
    except ImportError:
        # OpenTelemetry not available, skip trace ID addition
        pass
    except Exception:
        # Telemetry must never break logging.
        pass
    return event_dict


def add_service_info(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add service and component information."""
    if "service" not in event_dict:
        event_dict["service"] = settings.otel_service_name
    if "component" not in event_dict:
        event_dict["component"] = "backend"
    return event_dict


def redact_sensitive_processor(logger, method_name, event_dict):
    """structlog processor applying central telemetry redaction (BE-020 §18)."""
    from backend.observability.redaction import redact_sensitive_data

    if settings.observability_redact_sensitive:
        return redact_sensitive_data(event_dict)
    return event_dict


def format_as_json(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> str:
    """Format event dict as JSON string (terminal renderer)."""
    return json.dumps(event_dict, sort_keys=True, default=str)


def setup_logging(log_level: str = "INFO", json_format: bool | None = None) -> None:
    """Setup structured logging for application and worker processes.

    JSON output by default (``OBSERVABILITY_LOG_FORMAT``); falls back to the
    existing stdlib configuration when structlog is not installed or
    configuration fails, so application startup can never break here.
    """
    global STRUCTLOG_CONFIGURED
    if json_format is None:
        json_format = settings.observability_log_format.lower() != "text"
    if not STRUCTLOG_AVAILABLE:
        logging.getLogger(__name__).debug(
            "structlog unavailable; keeping stdlib logging configuration"
        )
        return
    try:
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            add_request_id,
            add_trace_ids,
            add_service_info,
            redact_sensitive_processor,
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]
        # Exactly one terminal renderer (the previous double-renderer bug
        # chained JSONRenderer after format_as_json and crashed startup).
        if json_format:
            processors.append(format_as_json)
        else:
            processors.append(structlog.dev.ConsoleRenderer())

        structlog.configure(
            processors=processors,
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        root = logging.getLogger()
        root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        if not any(
            getattr(h, "_poa_structlog", False) for h in root.handlers
        ):
            from backend.core.logging import RedactingFormatter

            handler = logging.StreamHandler(sys.stdout)
            # The event_dict processor above only covers keys structlog saw;
            # this covers whatever ends up in the rendered line.
            handler.setFormatter(RedactingFormatter("%(message)s"))
            handler._poa_structlog = True  # type: ignore[attr-defined]
            root.addHandler(handler)
        STRUCTLOG_CONFIGURED = True
    except Exception:
        # Telemetry failure must never take down the application (BE-020 §27).
        logging.getLogger(__name__).exception("structlog setup failed; using stdlib logging")


def get_logger(name: str = None):
    """Get a structured logger instance (structlog or stdlib fallback)."""
    if STRUCTLOG_CONFIGURED:
        return structlog.get_logger(name)
    return logging.getLogger(name or "poa-backend")


# Convenience functions for common logging patterns
def log_request(logger, method: str, path: str,
                status_code: int = None, duration_ms: float = None, **kwargs) -> None:
    """Log HTTP request information."""
    event_data = {
        "event": "http_request",
        "method": method,
        "path": path,
        **kwargs
    }
    if status_code is not None:
        event_data["status_code"] = status_code
    if duration_ms is not None:
        event_data["duration_ms"] = duration_ms
    if status_code and status_code >= 400:
        logger.warning(**event_data)
    else:
        logger.info(**event_data)


def log_worker_job(logger, worker: str, job_type: str,
                   job_id: str = None, status: str = None, duration_ms: float = None,
                   **kwargs) -> None:
    """Log worker job information."""
    event_data = {
        "event": "worker_job",
        "worker": worker,
        "job_type": job_type,
        **kwargs
    }
    if job_id:
        event_data["job_id"] = job_id
    if status:
        event_data["status"] = status
    if duration_ms is not None:
        event_data["duration_ms"] = duration_ms
    if status in ("failed", "error"):
        logger.error(**event_data)
    else:
        logger.info(**event_data)


def log_storage_operation(logger, operation: str,
                          provider: str = None, status: str = None,
                          duration_ms: float = None, **kwargs) -> None:
    """Log storage operation information."""
    event_data = {
        "event": "storage_operation",
        "operation": operation,
        **kwargs
    }
    if provider:
        event_data["provider"] = provider
    if status:
        event_data["status"] = status
    if duration_ms is not None:
        event_data["duration_ms"] = duration_ms
    if status in ("failed", "error"):
        logger.error(**event_data)
    else:
        logger.info(**event_data)


def log_webhook_delivery(logger, event_id: str,
                         url: str, status_code: int = None,
                         duration_ms: float = None, **kwargs) -> None:
    """Log webhook delivery attempt."""
    event_data = {
        "event": "webhook_delivery",
        "event_id": event_id,
        "url": url,
        **kwargs
    }
    if status_code is not None:
        event_data["status_code"] = status_code
    if duration_ms is not None:
        event_data["duration_ms"] = duration_ms
    if status_code and status_code >= 400:
        logger.warning(**event_data)
    else:
        logger.info(**event_data)
