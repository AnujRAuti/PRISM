import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.logging import setup_logging, request_id_ctx
from backend.core.middleware import RequestIDMiddleware
from backend.api.v1.router import router as api_router
from backend.observability.logging import setup_logging as setup_obs_logging, get_logger
from backend.observability.tracing import init_tracing, shutdown_tracing
from backend.observability.health import liveness_endpoint, readiness_endpoint, health_endpoint
from backend.observability.metrics import get_metrics
from backend.observability.redaction import redact_sensitive_data

logger = get_logger(__name__)

setup_logging()
setup_obs_logging()  # Setup structured JSON logging

# Initialize observability
if settings.otel_enabled:
    init_tracing()

app = FastAPI(title=settings.app_name)

# Basic CORS (allow dev origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID middleware
app.add_middleware(RequestIDMiddleware)


# Metrics middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Collect HTTP request metrics."""
    method = request.method
    url = str(request.url)
    # Extract route pattern (simplified - in production you'd want to get the actual route)
    route = request.url.path
    
    start_time = time.time()
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        status_code = 500
        raise exc
    finally:
        # Record metrics
        duration = time.time() - start_time
        metrics = get_metrics()
        metrics.record_http_request(
            method=method,
            route=route,
            status_code=status_code,
            duration_seconds=duration
        )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


# Health endpoints using our new implementation
@app.get("/health")
async def liveness():
    """Liveness endpoint - checks if application process is alive."""
    details, status_code = liveness_endpoint()
    return JSONResponse(content=details, status_code=status_code)


@app.get("/ready")
async def readiness():
    """Readiness endpoint - checks if instance can safely receive work."""
    details, status_code = readiness_endpoint()
    return JSONResponse(content=details, status_code=status_code)


@app.get("/healthz")
async def health():
    """Combined health endpoint."""
    details, status_code = health_endpoint()
    return JSONResponse(content=details, status_code=status_code)


# Prometheus metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    if not settings.prometheus_enabled:
        return JSONResponse(
            content={"error": "Prometheus metrics disabled"},
            status_code=404
        )
    
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        metrics_data = generate_latest()
        return JSONResponse(
            content=metrics_data.decode("utf-8"),
            media_type=CONTENT_TYPE_LATEST
        )
    except ImportError:
        return JSONResponse(
            content={"error": "Prometheus client not available"},
            status_code=500
        )


app.include_router(api_router, prefix="/api/v1")


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("application.starting", 
                version="0.1.0",
                environment=settings.environment,
                otel_enabled=settings.otel_enabled,
                prometheus_enabled=settings.prometheus_enabled)


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("application.shutting_down")
    if settings.otel_enabled:
        shutdown_tracing()
