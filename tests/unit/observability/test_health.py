"""
Unit tests for observability health checks.
"""
from contextlib import ExitStack
from unittest.mock import MagicMock, Mock, patch

import pytest

from backend.observability.health import (
    HealthStatus,
    HealthCheck,
    PostgresHealthCheck,
    RedisHealthCheck,
    StorageHealthCheck,
    ApplicationHealthCheck,
    HealthChecker,
    get_liveness,
    get_readiness,
    liveness_endpoint,
    readiness_endpoint,
    health_endpoint
)


def test_health_status_enum():
    """Test HealthStatus enum."""
    assert HealthStatus.HEALTHY.value == "healthy"
    assert HealthStatus.UNHEALTHY.value == "unhealthy"
    assert HealthStatus.UNKNOWN.value == "unknown"


def test_health_check_base():
    """Test base HealthCheck class."""
    check = HealthCheck("test_check", required=True)
    assert check.name == "test_check"
    assert check.required == True
    
    # Should raise NotImplementedError when check() is called
    with pytest.raises(NotImplementedError):
        check.check()


def test_application_health_check():
    """Test ApplicationHealthCheck."""
    check = ApplicationHealthCheck()
    assert check.name == "application"
    assert check.required == False
    
    status, details = check.check()
    assert status == HealthStatus.HEALTHY
    assert "message" in details
    assert "Application is running" in details["message"]


@patch('backend.observability.health.settings')
def test_postgres_health_check_success(mock_settings):
    """Test PostgreSQL health check when successful."""
    mock_settings.database_url = "postgresql://test:test@localhost:5432/test"

    # The check builds its own engine through the application's single guarded
    # engine factory (backend.db.session.build_guarded_engine), because that is
    # the one place the BE-029 database guard can run. Patch that seam rather
    # than a private create_engine.
    with patch('backend.db.session.build_guarded_engine') as mock_build:
        # MagicMock (not Mock) so ``engine.connect()`` supports the ``with``
        # statement. Production uses ``with engine.connect() as conn:`` — the
        # SQLAlchemy context-manager contract that both closes and rolls back
        # the connection on exit. A plain Mock has no ``__enter__``, so the
        # check raised AttributeError and reported UNHEALTHY.
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = [1]

        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.connect.return_value.__exit__.return_value = False
        mock_conn.execute.return_value = mock_result
        mock_build.return_value = mock_engine

        check = PostgresHealthCheck()
        status, details = check.check()
        
        assert status == HealthStatus.HEALTHY
        assert "PostgreSQL connection successful" in details["message"]


@patch('backend.observability.health.settings')
def test_postgres_health_check_failure(mock_settings):
    """Test PostgreSQL health check when it fails."""
    mock_settings.database_url = "postgresql://test:test@localhost:5432/test"
    
    with patch('backend.db.session.build_guarded_engine') as mock_build:
        mock_build.side_effect = Exception("Connection failed")
        
        check = PostgresHealthCheck()
        status, details = check.check()
        
        assert status == HealthStatus.UNHEALTHY
        assert "PostgreSQL connection failed" in details["message"]


@patch('backend.observability.health.settings')
def test_redis_health_check_success(mock_settings):
    """Test Redis health check when successful."""
    mock_settings.redis_url = "redis://localhost:6379/0"
    
    with patch('backend.observability.health.redis.from_url') as mock_from_url:
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_from_url.return_value = mock_redis
        
        check = RedisHealthCheck()
        status, details = check.check()
        
        assert status == HealthStatus.HEALTHY
        assert "Redis connection successful" in details["message"]


@patch('backend.observability.health.settings')
def test_redis_health_check_failure(mock_settings):
    """Test Redis health check when it fails."""
    mock_settings.redis_url = "redis://localhost:6379/0"
    
    with patch('backend.observability.health.redis.from_url') as mock_from_url:
        mock_from_url.side_effect = Exception("Connection failed")
        
        check = RedisHealthCheck()
        status, details = check.check()
        
        assert status == HealthStatus.UNHEALTHY
        assert "Redis connection failed" in details["message"]


def test_health_checker_initialization():
    """Test HealthChecker initialization."""
    checker = HealthChecker()
    assert len(checker.checks) >= 4  # application, postgresql, redis, storage
    assert "application" in checker._check_map
    assert "postgresql" in checker._check_map
    assert "redis" in checker._check_map
    assert "storage" in checker._check_map


def test_health_checker_liveness():
    """Test HealthChecker liveness status."""
    checker = HealthChecker()
    
    # Mock the application check to return healthy
    with patch.object(checker._check_map["application"], 'check') as mock_app_check:
        mock_app_check.return_value = (HealthStatus.HEALTHY, {"message": "Application running"})
        
        status, details = checker.get_liveness_status()
        
        assert status == HealthStatus.HEALTHY
        assert details["status"] == "healthy"
        assert "checks" in details
        assert "application" in details["checks"]


def test_health_checker_readiness():
    """Test HealthChecker readiness status."""
    checker = HealthChecker()

    # Mock all checks to return healthy. Every patch must stay open for the
    # duration of the readiness call: readiness is an aggregate over all
    # registered checks, so closing each patch at the end of its loop
    # iteration would run the real postgres/redis/storage probes and assert on
    # live dependencies instead of on the aggregation logic under test.
    with ExitStack() as stack:
        for name, check in checker._check_map.items():
            mock_check = stack.enter_context(patch.object(check, 'check'))
            mock_check.return_value = (HealthStatus.HEALTHY, {"message": f"{name} healthy"})

        status, details = checker.get_readiness_status()

    assert status == HealthStatus.HEALTHY
    assert details["status"] == "healthy"
    assert "checks" in details

    # Check that all expected checks are present
    expected_checks = ["application", "postgresql", "redis", "storage"]
    for check_name in expected_checks:
        assert check_name in details["checks"]


def test_get_liveness():
    """Test get_liveness function."""
    with patch('backend.observability.health.health_checker') as mock_checker:
        mock_checker.get_liveness_status.return_value = (HealthStatus.HEALTHY, {"status": "healthy"})
        
        status, details = get_liveness()
        
        assert status == HealthStatus.HEALTHY
        assert details["status"] == "healthy"


def test_get_readiness():
    """Test get_readiness function."""
    with patch('backend.observability.health.health_checker') as mock_checker:
        mock_checker.get_readiness_status.return_value = (HealthStatus.HEALTHY, {"status": "healthy"})
        
        status, details = get_readiness()
        
        assert status == HealthStatus.HEALTHY
        assert details["status"] == "healthy"


def test_liveness_endpoint():
    """Test liveness endpoint function."""
    with patch('backend.observability.health.get_liveness') as mock_get_liveness:
        mock_get_liveness.return_value = (
            HealthStatus.HEALTHY, 
            {"status": "healthy", "timestamp": 12345}
        )
        
        details, status_code = liveness_endpoint()
        
        assert status_code == 200
        assert details["status"] == "healthy"
        assert details["timestamp"] == 12345


def test_readiness_endpoint():
    """Test readiness endpoint function."""
    with patch('backend.observability.health.get_readiness') as mock_get_readiness:
        mock_get_readiness.return_value = (
            HealthStatus.HEALTHY, 
            {"status": "healthy", "timestamp": 12345}
        )
        
        details, status_code = readiness_endpoint()
        
        assert status_code == 200
        assert details["status"] == "healthy"
        assert details["timestamp"] == 12345


def test_health_endpoint():
    """Test health endpoint function."""
    with patch('backend.observability.health.get_liveness') as mock_get_liveness, \
         patch('backend.observability.health.get_readiness') as mock_get_readiness:
        
        mock_get_liveness.return_value = (
            HealthStatus.HEALTHY, 
            {"status": "healthy", "timestamp": 12345}
        )
        mock_get_readiness.return_value = (
            HealthStatus.HEALTHY, 
            {"status": "healthy", "timestamp": 12345}
        )
        
        details, status_code = health_endpoint()
        
        assert status_code == 200
        assert details["status"] == "healthy"
        assert "liveness" in details
        assert "readiness" in details
        assert details["liveness"]["status"] == "healthy"
        assert details["readiness"]["status"] == "healthy"


def test_health_endpoint_unhealthy():
    """Test health endpoint when dependencies are unhealthy."""
    with patch('backend.observability.health.get_liveness') as mock_get_liveness, \
         patch('backend.observability.health.get_readiness') as mock_get_readiness:
        
        # Liveness healthy but readiness unhealthy
        mock_get_liveness.return_value = (
            HealthStatus.HEALTHY, 
            {"status": "healthy", "timestamp": 12345}
        )
        mock_get_readiness.return_value = (
            HealthStatus.UNHEALTHY, 
            {"status": "unhealthy", "timestamp": 12345}
        )
        
        details, status_code = health_endpoint()
        
        assert status_code == 503  # Service unavailable
        assert details["status"] == "unhealthy"
        assert "liveness" in details
        assert "readiness" in details
        assert details["liveness"]["status"] == "healthy"
        assert details["readiness"]["status"] == "unhealthy"
