import logging
import time

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.logging import setup_logging
from backend.core.middleware import RequestIDMiddleware
from backend.api.v1.router import router as api_router
from backend.api.v1.endpoints.health import router as health_router
from backend.observability.logging import setup_logging as setup_obs_logging
from backend.observability.tracing import init_tracing, shutdown_tracing
from backend.observability.health import liveness_endpoint, readiness_endpoint, health_endpoint
from backend.observability.metrics import get_metrics
from backend.security.authorization import require
from backend.services.authorization import Principal

stdlib_logger = logging.getLogger(__name__)

setup_logging()
# Structured logging is best-effort: it degrades to the stdlib config above
# when structlog is unavailable and must never block application startup.
setup_obs_logging()

app = FastAPI(title=settings.app_name)

# CORS origins come from the environment (CORS_ALLOW_ORIGINS). The default is
# still every origin, so a shared deployment must set the real frontend
# origins: with allow_credentials on, the wildcard makes the middleware echo
# back the caller's Origin header.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID middleware (BE-001 behavior preserved)
app.add_middleware(RequestIDMiddleware)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """BE-020: collect HTTP metrics with bounded labels only.

    The route label uses the matched route template (e.g.
    ``/api/v1/evidence/{evidence_id}``), never the raw path — UUID-bearing
    raw paths would explode metric-label cardinality.
    """
    method = request.method
    start_time = time.time()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", None) or "unmatched"
        try:
            get_metrics().record_http_request(
                method=method,
                route=route,
                status_code=status_code,
                duration_seconds=time.time() - start_time,
            )
        except Exception:
            # Telemetry failure must never take down the application.
            stdlib_logger.debug("failed to record http metrics", exc_info=True)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


# ---------------------------------------------------------------------------
# BE-001 health/readiness contract (preserved; original endpoints).
# ---------------------------------------------------------------------------
app.include_router(health_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# BE-020 operational endpoints (liveness/readiness/metrics).
# ---------------------------------------------------------------------------
@app.get("/health", summary="Liveness probe (process alive, dependency-agnostic)")
async def liveness():
    details, status_code = liveness_endpoint()
    return JSONResponse(content=details, status_code=status_code)


@app.get("/ready", summary="Readiness probe (required dependencies available)")
async def readiness():
    details, status_code = readiness_endpoint()
    return JSONResponse(content=details, status_code=status_code)


@app.get("/healthz", summary="Combined liveness + readiness snapshot")
async def combined_health():
    details, status_code = health_endpoint()
    return JSONResponse(content=details, status_code=status_code)


@app.get("/metrics", summary="Prometheus-compatible metrics exposition")
async def prometheus_metrics(
    principal: Principal = Depends(require("metrics.read")),
):
    if not settings.prometheus_enabled:
        return JSONResponse(content={"detail": "metrics disabled"}, status_code=404)
    try:
        from prometheus_client import (
            CONTENT_TYPE_LATEST,
            generate_latest,
        )
    except ImportError:
        return JSONResponse(
            content={"detail": "prometheus client not installed"}, status_code=503
        )
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.on_event("startup")
async def startup_event():
    if settings.otel_enabled:
        try:
            init_tracing()
        except Exception:
            stdlib_logger.exception("OpenTelemetry initialization failed; continuing without tracing")
    stdlib_logger.info(
        "application.starting",
        extra={"otel_enabled": settings.otel_enabled,
               "prometheus_enabled": settings.prometheus_enabled},
    )


@app.on_event("shutdown")
async def shutdown_event():
    stdlib_logger.info("application.shutting_down")
    if settings.otel_enabled:
        try:
            shutdown_tracing()
        except Exception:
            stdlib_logger.warning("OpenTelemetry shutdown failed", exc_info=True)
