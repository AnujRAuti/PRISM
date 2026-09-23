"""
Health checks and readiness probes for Proof-of-Action backend.
"""
import logging
import time
from typing import Dict, Any, Tuple
from enum import Enum

from backend.core.config import settings
from backend.observability.redaction import redact_sensitive_data
from backend.observability.logging import get_logger

logger = get_logger(__name__)


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
        """
        Perform the health check.
        
        Returns:
            Tuple of (status, details_dict)
        """
        raise NotImplementedError


class PostgresHealthCheck(HealthCheck):
    """PostgreSQL connectivity health check."""
    
    def __init__(self):
        super().__init__("postgresql", required=True)
    
    def check(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        try:
            # Import here to avoid hard dependency if not used
            from sqlalchemy import create_engine, text
            from sqlalchemy.exc import SQLAlchemyError
            
            engine = create_engine(settings.database_url)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            
            engine.dispose()
            return HealthStatus.HEALTHY, {
                "message": "PostgreSQL connection successful",
                "response_time_ms": 0  # Would measure actual time in production
            }
        except ImportError:
            return HealthStatus.UNKNOWN, {
                "message": "SQLAlchemy not available for PostgreSQL check"
            }
        except Exception as e:
            logger.warning(f"PostgreSQL health check failed: {e}")
            return HealthStatus.UNHEALTHY, {
                "message": "PostgreSQL connection failed",
                "error": str(e) if settings.environment == "development" else "connection_failed"
            }


class RedisHealthCheck(HealthCheck):
    """Redis connectivity health check."""
    
    def __init__(self):
        super().__init__("redis", required=True)
    
    def check(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        try:
            # Import here to avoid hard dependency if not used
            import redis
            
            r = redis.from_url(settings.redis_url)
            r.ping()
            
            return HealthStatus.HEALTHY, {
                "message": "Redis connection successful",
                "response_time_ms": 0  # Would measure actual time in production
            }
        except ImportError:
            return HealthStatus.UNKNOWN, {
                "message": "Redis library not available"
            }
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            return HealthStatus.UNHEALTHY, {
                "message": "Redis connection failed",
                "error": str(e) if settings.environment == "development" else "connection_failed"
            }


class StorageHealthCheck(HealthCheck):
    """Storage service health check."""
    
    def __init__(self):
        super().__init__("storage", required=True)
    
    def check(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        try:
            # Import here to avoid hard dependency if not used
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError
            
            # Configure S3 client for MinIO
            s3_client = boto3.client(
                's3',
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                use_ssl=settings.s3_use_ssl
            )
            
            # Try to list buckets as a simple connectivity test
            s3_client.list_buckets()
            
            return HealthStatus.HEALTHY, {
                "message": "Storage service connection successful",
                "response_time_ms": 0  # Would measure actual time in production
            }
        except ImportError:
            return HealthStatus.UNKNOWN, {
                "message": "Boto3 not available for storage check"
            }
        except NoCredentialsError:
            return HealthStatus.UNHEALTHY, {
                "message": "Storage credentials not available",
                "error": "missing_credentials" if settings.environment == "development" else "auth_failed"
            }
        except ClientError as e:
            logger.warning(f"Storage health check failed: {e}")
            return HealthStatus.UNHEALTHY, {
                "message": "Storage service connection failed",
                "error": str(e) if settings.environment == "development" else "connection_failed"
            }
        except Exception as e:
            logger.warning(f"Storage health check failed: {e}")
            return HealthStatus.UNHEALTHY, {
                "message": "Storage service connection failed",
                "error": str(e) if settings.environment == "development" else "connection_failed"
            }


class ApplicationHealthCheck(HealthCheck):
    """Basic application health check."""
    
    def __init__(self):
        super().__init__("application", required=False)
    
    def check(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        return HealthStatus.HEALTHY, {
            "message": "Application is running",
            "timestamp": time.time(),
            "version": "0.1.0",
            "environment": settings.environment
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
        """
        Get liveness status - checks if application process is alive.
        Should not fail due to external dependencies being unavailable.
        """
        # Liveness only checks the application itself, not dependencies
        app_check = self._check_map["application"]
        status, details = app_check.check()
        
        return status, {
            "status": status.value,
            "timestamp": time.time(),
            "checks": {
                "application": {
                    "status": status.value,
                    "message": details.get("message", "")
                }
            }
        }
    
    def get_readiness_status(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """
        Get readiness status - checks if instance can safely receive work.
        Should fail when required dependencies are unavailable.
        """
        overall_status = HealthStatus.HEALTHY
        check_results = {}
        
        for check in self.checks:
            status, details = check.check()
            check_results[check.name] = {
                "status": status.value,
                "message": details.get("message", ""),
                "required": check.required
            }
            
            # If any required check is unhealthy, overall status is unhealthy
            if check.required and status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            # If any required check is unknown, we might want to treat as unhealthy
            elif check.required and status == HealthStatus.UNKNOWN:
                overall_status = HealthStatus.UNHEALTHY
        
        return overall_status, {
            "status": overall_status.value,
            "timestamp": time.time(),
            "checks": check_results
        }


# Global health checker instance
health_checker = HealthChecker()


def get_liveness() -> Tuple[HealthStatus, Dict[str, Any]]:
    """Get liveness status."""
    return health_checker.get_liveness_status()


def get_readiness() -> Tuple[HealthStatus, Dict[str, Any]]:
    """Get readiness status."""
    return health_checker.get_readiness_status()


# FastAPI endpoint handlers (to be imported by API routers)
def liveness_endpoint():
    """FastAPI endpoint handler for liveness check."""
    status, details = get_liveness()
    status_code = 200 if status == HealthStatus.HEALTHY else 503
    return details, status_code


def readiness_endpoint():
    """FastAPI endpoint handler for readiness check."""
    status, details = get_readiness()
    status_code = 200 if status == HealthStatus.HEALTHY else 503
    return details, status_code


def health_endpoint():
    """Combined health endpoint (returns both liveness and readiness)."""
    liveness_status, liveness_details = get_liveness()
    readiness_status, readiness_details = get_readiness()
    
    # Overall status is healthy only if both liveness and readiness are healthy
    overall_healthy = (liveness_status == HealthStatus.HEALTHY and 
                      readiness_status == HealthStatus.HEALTHY)
    
    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "timestamp": time.time(),
        "liveness": liveness_details,
        "readiness": readiness_details
    }, 200 if overall_healthy else 503
