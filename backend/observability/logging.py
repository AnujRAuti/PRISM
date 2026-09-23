"""
Structured JSON logging with correlation IDs.
"""
import json
import logging
import sys
from typing import Any, Dict
from uuid import uuid4

import structlog
from structlog.stdlib import LoggerFactory

from backend.observability.redaction import redact_sensitive_data


def add_request_id(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add request_id to log entries if not present."""
    if "request_id" not in event_dict:
        event_dict["request_id"] = str(uuid4())
    return event_dict


def add_trace_ids(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add trace_id and span_id from OpenTelemetry context if available."""
    try:
        from opentelemetry import trace
        
        span = trace.get_current_span()
        if span:
            span_context = span.get_span_context()
            if span_context.is_valid:
                event_dict["trace_id"] = format(span_context.trace_id, "032x")
                event_dict["span_id"] = format(span_context.span_id, "016x")
    except ImportError:
        # OpenTelemetry not available, skip trace ID addition
        pass
    except Exception:
        # Silently ignore trace context errors to avoid breaking logging
        pass
    
    return event_dict


def add_service_info(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add service and component information."""
    if "service" not in event_dict:
        event_dict["service"] = "poa-backend"
    if "component" not in event_dict:
        # Try to get component from the logger name
        event_dict["component"] = event_dict.get("logger", "unknown")
    return event_dict


def format_as_json(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> str:
    """Format event dict as JSON string."""
    # Redact sensitive data before serialization
    if event_dict.get("redact_sensitive", True):
        event_dict = redact_sensitive_data(event_dict)
    return json.dumps(event_dict, sort_keys=True)


def setup_logging(log_level: str = "INFO", json_format: bool = True) -> None:
    """
    Setup structured logging for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to output logs as JSON
    """
    # Configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
        stream=sys.stdout,
    )
    
    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        add_request_id,
        add_trace_ids,
        add_service_info,
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if json_format:
        processors.append(format_as_json)
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    processors.append(structlog.stdlib.processor.JSONRenderer() if json_format else structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


# Convenience functions for common logging patterns
def log_request(logger: structlog.stdlib.BoundLogger, method: str, path: str, 
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


def log_worker_job(logger: structlog.stdlib.BoundLogger, worker: str, job_type: str,
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
        
    if status == "failed" or status == "error":
        logger.error(**event_data)
    elif status == "completed" or status == "success":
        logger.info(**event_data)
    else:
        logger.info(**event_data)


def log_storage_operation(logger: structlog.stdlib.BoundLogger, operation: str,
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
        
    if status == "failed" or status == "error":
        logger.error(**event_data)
    else:
        logger.info(**event_data)


def log_webhook_delivery(logger: structlog.stdlib.BoundLogger, event_id: str,
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
