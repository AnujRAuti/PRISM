"""BE-020 health checks and readiness probes.

Liveness answers "is this process alive?" and never fails merely because
PostgreSQL/Redis/Storage are temporarily unavailable. Readiness answers
"can this instance safely receive work?" and fails when *required*
dependencies are unavailable. Optional checks never fail readiness on
their own; the semantics are intentionally not combined.
"""
import logging
import time
from enum import Enum
from typing import Any, Dict, Tuple

from backend.core.config import settings

try:  # pragma: no cover - availability probed once at import
    from sqlalchemy import create_engine, text

    SQLALCHEMY_AVAILABLE = True
except ImportError:  # pragma: no cover
    SQLALCHEMY_AVAILABLE = False

try:  # pragma: no cover
    import redis

    REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    redis = None
    REDIS_AVAILABLE = False

try:  # pragma: no cover
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:  # pragma: no cover
    boto3 = None
    BOTO3_AVAILABLE = False
    class NoCredentialsError(Exception):  # type: ignore[no-redef]
        pass

    class ClientError(Exception):  # type: ignore[no-redef]
        pass

    class BotoCoreError(Exception):  # type: ignore[no-redef]
        pass


logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class HealthCheck:
    """Base health check class."""

    def __init__(self, name: str, required: bool = True):
        self.name = name
        self.required = required

    def check(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Perform the health check; returns (status, details)."""
        raise NotImplementedError


class PostgresHealthCheck(HealthCheck):
    """PostgreSQL connectivity health check (required)."""

    def __init__(self):
        super().__init__("postgresql", required=True)

    def check(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        if not SQLALCHEMY_AVAILABLE:
            return HealthStatus.UNKNOWN, {
                "message": "SQLAlchemy not available for PostgreSQL check"
            }
        engine = None
        try:
            engine = create_engine(settings.database_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return HealthStatus.HEALTHY, {
                "message": "PostgreSQL connection successful"
            }
        except Exception as e:
            logger.warning("PostgreSQL health check failed: %s", e)
            return HealthStatus.UNHEALTHY, {
                "message": "PostgreSQL connection failed",
                "error": str(e) if settings.environment == "development" else "connection_failed",
            }
        finally:
            if engine is not None:
                try:
                    engine.dispose()
                except Exception:
                    pass


class RedisHealthCheck(HealthCheck):
    """Redis connectivity health check (required)."""

    def __init__(self):
        super().__init__("redis", required=True)

    def check(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        if not REDIS_AVAILABLE:
            return HealthStatus.UNKNOWN, {
                "message": "Redis library not available"
            }
        try:
            client = redis.from_url(settings.redis_url)
            client.ping()
            try:
                client.close()
            except Exception:
                pass
            return HealthStatus.HEALTHY, {
                "message": "Redis connection successful"
            }
        except Exception as e:
            logger.warning("Redis health check failed: %s", e)
            return HealthStatus.UNHEALTHY, {
                "message": "Redis connection failed",
                "error": str(e) if settings.environment == "development" else "connection_failed",
            }


class StorageHealthCheck(HealthCheck):
    """Object-storage connectivity health check (required)."""

    def __init__(self):
        super().__init__("storage", required=True)

    def check(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        if not BOTO3_AVAILABLE:
            return HealthStatus.UNKNOWN, {
                "message": "Boto3 not available for storage check"
            }
        try:
            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region,
                use_ssl=settings.s3_use_ssl,
            )
            client.list_buckets()
            return HealthStatus.HEALTHY, {
                "message": "Storage service connection successful"
            }
        except NoCredentialsError:
            logger.warning("Storage health check failed: missing credentials")
            return HealthStatus.UNHEALTHY, {
                "message": "Storage credentials not available",
                "error": "missing_credentials",
            }
        except (ClientError, BotoCoreError) as e:
            logger.warning("Storage health check failed: %s", e)
            return HealthStatus.UNHEALTHY, {
                "message": "Storage service connection failed",
                "error": str(e) if settings.environment == "development" else "connection_failed",
            }
        except Exception as e:
            logger.warning("Storage health check failed: %s", e)
            return HealthStatus.UNHEALTHY, {
                "message": "Storage service connection failed",
                "error": str(e) if settings.environment == "development" else "connection_failed",
            }


class ApplicationHealthCheck(HealthCheck):
    """Basic application-process health check (never fails on dependencies)."""

    def __init__(self):
        super().__init__("application", required=False)

    def check(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        return HealthStatus.HEALTHY, {
            "message": "Application is running",
            "timestamp": time.time(),
            "version": "0.1.0",
            "environment": settings.environment,
        }


class HealthChecker:
    """Manages health checks and determines overall health status."""

    def __init__(self):
        self.checks = [
            ApplicationHealthCheck(),
            PostgresHealthCheck(),
            RedisHealthCheck(),
            StorageHealthCheck(),
        ]
        self._check_map = {check.name: check for check in self.checks}

    def get_liveness_status(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Liveness: is the application process alive (dependency-agnostic)."""
        status, details = self._check_map["application"].check()
        return status, {
            "status": status.value,
            "timestamp": time.time(),
            "checks": {
                "application": {
                    "status": status.value,
                    "message": details.get("message", ""),
                }
            },
        }

    def get_readiness_status(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Readiness: can this instance safely receive work?

        Required dependency unavailable/unknown -> UNHEALTHY. Optional
        dependency unavailable -> reported but never fails readiness alone.
        """
        overall_status = HealthStatus.HEALTHY
        check_results = {}
        for check in self.checks:
            status, details = check.check()
            check_results[check.name] = {
                "status": status.value,
                "message": details.get("message", ""),
                "required": check.required,
            }
            if check.required and status != HealthStatus.HEALTHY:
                overall_status = HealthStatus.UNHEALTHY
        return overall_status, {
            "status": overall_status.value,
            "timestamp": time.time(),
            "checks": check_results,
        }


# Global health checker instance
health_checker = HealthChecker()


def get_liveness() -> Tuple[HealthStatus, Dict[str, Any]]:
    return health_checker.get_liveness_status()


def get_readiness() -> Tuple[HealthStatus, Dict[str, Any]]:
    return health_checker.get_readiness_status()


def liveness_endpoint():
    """(details, http_status) for the liveness probe."""
    status, details = get_liveness()
    return details, 200 if status == HealthStatus.HEALTHY else 503


def readiness_endpoint():
    """(details, http_status) for the readiness probe."""
    status, details = get_readiness()
    return details, 200 if status == HealthStatus.HEALTHY else 503


def health_endpoint():
    """(details, http_status) combining liveness and readiness snapshots."""
    liveness_status, liveness_details = get_liveness()
    readiness_status, readiness_details = get_readiness()
    overall_healthy = (
        liveness_status == HealthStatus.HEALTHY
        and readiness_status == HealthStatus.HEALTHY
    )
    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "timestamp": time.time(),
        "liveness": liveness_details,
        "readiness": readiness_details,
    }, 200 if overall_healthy else 503
