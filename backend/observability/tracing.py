"""
OpenTelemetry tracing implementation.
"""
import functools
import logging
from typing import Any, Callable, Dict, Optional

from backend.core.config import settings
from backend.observability.redaction import redact_sensitive_data

logger = logging.getLogger(__name__)

# Global tracer instance
_tracer = None
_meter = None


def _safe_import_otel():
    """Safely import OpenTelemetry modules."""
    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        
        return {
            'trace': trace,
            'metrics': metrics,
            'TracerProvider': TracerProvider,
            'BatchSpanProcessor': BatchSpanProcessor,
            'MeterProvider': MeterProvider,
            'PeriodicExportingMetricReader': PeriodicExportingMetricReader,
            'OTLPSpanExporter': OTLPSpanExporter,
            'OTLPMetricExporter': OTLPMetricExporter,
            'Resource': Resource,
            'FastAPIInstrumentor': FastAPIInstrumentor,
            'SQLAlchemyInstrumentor': SQLAlchemyInstrumentor,
            'RedisInstrumentor': RedisInstrumentor,
            'RequestsInstrumentor': RequestsInstrumentor
        }
    except ImportError as e:
        logger.warning(f"OpenTelemetry not available: {e}")
        return None


def init_tracing():
    """Initialize OpenTelemetry tracing and metrics."""
    global _tracer, _meter
    
    if not settings.otel_enabled:
        logger.info("OpenTelemetry tracing is disabled")
        return False
    
    otel_modules = _safe_import_otel()
    if not otel_modules:
        logger.warning("OpenTelemetry modules not available, tracing disabled")
        return False
    
    try:
        # Set up resource attributes
        resource = otel_modules['Resource'].create({
            "service.name": settings.otel_service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.environment
        })
        
        # Set up tracing
        tracer_provider = otel_modules['TracerProvider'](resource=resource)
        
        # Configure OTLP exporter if endpoint is provided
        if settings.otel_exporter_otlp_endpoint:
            otlp_exporter = otel_modules['OTLPSpanExporter'](
                endpoint=settings.otel_exporter_otlp_endpoint,
            )
            span_processor = otel_modules['BatchSpanProcessor'](otlp_exporter)
            tracer_provider.add_span_processor(span_processor)
            logger.info(f"OpenTelemetry tracing enabled with OTLP endpoint: {settings.otel_exporter_otlp_endpoint}")
        else:
            # Use console exporter for development
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            console_exporter = ConsoleSpanExporter()
            span_processor = otel_modules['BatchSpanProcessor'](console_exporter)
            tracer_provider.add_span_processor(span_processor)
            logger.info("OpenTelemetry tracing enabled with console exporter")
        
        # Set global tracer provider
        otel_modules['trace'].set_tracer_provider(tracer_provider)
        _tracer = otel_modules['trace'].get_tracer(__name__)
        
        # Set up metrics if needed
        if settings.prometheus_enabled:
            # Prometheus is handled separately, but we can still set up OTLP metrics if needed
            if settings.otel_exporter_otlp_endpoint:
                try:
                    metric_reader = otel_modules['PeriodicExportingMetricReader'](
                        otel_modules['OTLPMetricExporter'](
                            endpoint=settings.otel_exporter_otlp_endpoint,
                        )
                    )
                    meter_provider = otel_modules['MeterProvider'](
                        resource=resource,
                        metric_readers=[metric_reader]
                    )
                    otel_modules['metrics'].set_meter_provider(meter_provider)
                    _meter = otel_modules['metrics'].get_meter(__name__)
                    logger.info("OpenTelemetry metrics enabled with OTLP exporter")
                except Exception as e:
                    logger.warning(f"Failed to set up OpenTelemetry metrics: {e}")
            else:
                logger.info("OpenTelemetry metrics disabled (no OTLP endpoint)")
        
        # Auto-instrument libraries
        _instrument_libraries(otel_modules)
        
        logger.info("OpenTelemetry tracing initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry tracing: {e}", exc_info=True)
        return False


def _instrument_libraries(otel_modules: Dict[str, Any]):
    """Auto-instrument supported libraries."""
    try:
        # Instrument FastAPI
        otel_modules['FastAPIInstrumentor']().instrument()
        logger.info("FastAPI instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument FastAPI: {e}")
    
    try:
        # Instrument SQLAlchemy
        otel_modules['SQLAlchemyInstrumentor']().instrument()
        logger.info("SQLAlchemy instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument SQLAlchemy: {e}")
    
    try:
        # Instrument Redis
        otel_modules['RedisInstrumentor']().instrument()
        logger.info("Redis instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument Redis: {e}")
    
    try:
        # Instrument Requests
        otel_modules['RequestsInstrumentor']().instrument()
        logger.info("Requests instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument Requests: {e}")


def get_tracer(name: str = None):
    """
    Get a tracer instance.
    
    Args:
        name: Tracer name
        
    Returns:
        OpenTelemetry tracer or None if not available
    """
    global _tracer
    if _tracer is None:
        # Try to initialize if not already done
        init_tracing()
    
    if _tracer is None:
        return None
        
    return otel_modules['trace'].get_tracer(name or __name__) if '_safe_import_otel' in globals() and _safe_import_otel() else None


def trace_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Decorator to create a span for a function.
    
    Args:
        name: Span name
        attributes: Optional attributes to add to the span
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args,): 
            # Get tracer
            otel_modules = _safe_import_otel()
            if not otel_modules or not settings.otel_enabled:
                return func(*args)
            
            tracer = otel_modules['trace'].get_tracer(__name__)
            with tracer.start_as_current_span(name) as span:
                # Add attributes if provided
                if attributes:
                    # Redact sensitive data from attributes
                    safe_attributes = redact_sensitive_data(attributes) if settings.observability_redact_sensitive else attributes
                    for key, value in safe_attributes.items():
                        span.set_attribute(key, value)
                
                try:
                    result = func(*args)
                    span.set_status(otel_modules['trace'].StatusCode.OK)
                    return result
                except Exception as e:
                    span.set_status(
                        otel_modules['trace'].StatusCode.ERROR,
                        str(e)
                    )
                    # Record exception
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator


def start_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Start a new span and return it for manual management.
    
    Args:
        name: Span name
        attributes: Optional attributes to add to the span
        
    Returns:
        Span context manager or None if tracing not available
    """
    otel_modules = _safe_import_otel()
    if not otel_modules or not settings.otel_enabled:
        return None
    
    tracer = otel_modules['trace'].get_tracer(__name__)
    span = tracer.start_span(name)
    
    # Add attributes if provided
    if attributes:
        # Redact sensitive data from attributes
        safe_attributes = redact_sensitive_data(attributes) if settings.observability_redact_sensitive else attributes
        for key, value in safe_attributes.items():
            span.set_attribute(key, value)
    
    return span


def add_span_event(span, name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Add an event to a span.
    
    Args:
        span: Span to add event to
        name: Event name
        attributes: Optional event attributes
    """
    if span is None:
        return
        
    otel_modules = _safe_import_otel()
    if not otel_modules:
        return
    
    # Redact sensitive data from attributes
    if attributes and settings.observability_redact_sensitive:
        attributes = redact_sensitive_data(attributes)
    
    span.add_event(name, attributes or {})


def set_span_attribute(span, key: str, value: Any):
    """
    Set an attribute on a span.
    
    Args:
        span: Span to set attribute on
        key: Attribute key
        value: Attribute value
    """
    if span is None:
        return
        
    otel_modules = _safe_import_otel()
    if not otel_modules:
        return
    
    # Redact sensitive data from value if it's a dict
    if isinstance(value, dict) and settings.observability_redact_sensitive:
        value = redact_sensitive_data(value)
    
    span.set_attribute(key, value)


# Convenience functions for common operations
def trace_db_query(operation: str, **kwargs):
    """Trace a database query operation."""
    return trace_span(f"db.query.{operation}", attributes={
        "db.operation": operation,
        **kwargs
    })


def trace_redis_command(command: str, **kwargs):
    """Trace a Redis command."""
    return trace_span(f"redis.command.{command}", attributes={
        "redis.command": command,
        **kwargs
    })


def trace_storage_operation(operation: str, provider: str = None, **kwargs):
    """Trace a storage operation."""
    attributes = {"storage.operation": operation}
    if provider:
        attributes["storage.provider"] = provider
    attributes.update(kwargs)
    return trace_span(f"storage.operation.{operation}", attributes=attributes)


def trace_worker_job(worker: str, job_type: str, **kwargs):
    """Trace a worker job execution."""
    return trace_span(f"worker.job.{job_type}", attributes={
        "worker.name": worker,
        "worker.job_type": job_type,
        **kwargs
    })


def trace_webhook_delivery(event_id: str, subscription_id: str, event_type: str, **kwargs):
    """Trace a webhook delivery attempt."""
    return trace_span("webhook.delivery", attributes={
        "webhook.event_id": event_id,
        "webhook.subscription_id": subscription_id,
        "webhook.event_type": event_type,
        **kwargs
    })


def trace_http_request(method: str, url: str, **kwargs):
    """Trace an HTTP request."""
    return trace_span("http.client.request", attributes={
        "http.method": method,
        "http.url": url,
        **kwargs
    })


# Health check for tracing
def is_tracing_enabled() -> bool:
    """Check if tracing is enabled and initialized."""
    return settings.otel_enabled and _safe_import_otel() is not None


# Shutdown function
def shutdown_tracing():
    """Shutdown OpenTelemetry tracing and metrics."""
    otel_modules = _safe_import_otel()
    if not otel_modules:
        return
    
    try:
        # Shutdown tracer provider
        tracer_provider = otel_modules['trace'].get_tracer_provider()
        if hasattr(tracer_provider, 'shutdown'):
            tracer_provider.shutdown()
        
        # Shutdown meter provider
        meter_provider = otel_modules['metrics'].get_meter_provider()
        if hasattr(meter_provider, 'shutdown'):
            meter_provider.shutdown()
            
        logger.info("OpenTelemetry tracing and metrics shutdown")
    except Exception as e:
        logger.warning(f"Error during OpenTelemetry shutdown: {e}")


# Initialize tracing when module is imported
# But only if explicitly enabled to avoid startup delays in development
if settings.otel_enabled:
    init_tracing()
