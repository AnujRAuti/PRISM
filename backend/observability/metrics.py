"""
Prometheus metrics collection for Proof-of-Action backend.
"""
try:
    from prometheus_client import Counter, Histogram, Gauge, Info
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Create dummy classes for when prometheus_client is not available
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def inc(self, amount=1): pass
        def __iadd__(self, other): return self
    
    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def observe(self, amount): pass
        def time(self): return self
        def __enter__(self): return self
        def __exit__(self, *args): pass
    
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def set(self, value): pass
        def inc(self): pass
        def dec(self): pass
    
    class Info:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def info(self, data): pass

from backend.core.config import settings


class Metrics:
    """Centralized metrics collection."""
    
    def __init__(self):
        if not PROMETHEUS_AVAILABLE or not settings.prometheus_enabled:
            self.enabled = False
            return
            
        self.enabled = True
        
        # Application info
        self.app_info = Info(
            'poa_app_info',
            'Application information'
        )
        self.app_info.info({
            'version': '0.1.0',
            'service': 'poa-backend',
            'environment': settings.environment
        })
        
        # HTTP Metrics
        self.http_requests_total = Counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'route', 'status_code']
        )
        
        self.http_request_duration_seconds = Histogram(
            'http_request_duration_seconds',
            'HTTP request duration in seconds',
            ['method', 'route'],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
        )
        
        self.http_errors_total = Counter(
            'http_errors_total',
            'Total HTTP errors',
            ['method', 'route', 'error_type']
        )
        
        # Database Metrics
        self.db_connections_total = Gauge(
            'db_connections_total',
            'Total database connections',
            ['state']  # active, idle, etc.
        )
        
        self.db_connection_acquisition_failures_total = Counter(
            'db_connection_acquisition_failures_total',
            'Failed database connection acquisitions'
        )
        
        self.db_query_duration_seconds = Histogram(
            'db_query_duration_seconds',
            'Database query duration in seconds',
            ['operation'],  # select, insert, update, delete
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
        )
        
        self.db_transaction_failures_total = Counter(
            'db_transaction_failures_total',
            'Database transaction failures',
            ['reason']
        )
        
        self.db_connectivity_status = Gauge(
            'db_connectivity_status',
            'Database connectivity status (1=connected, 0=disconnected)'
        )
        
        # Redis Metrics
        self.redis_connections_total = Gauge(
            'redis_connections_total',
            'Total Redis connections',
            ['state']
        )
        
        self.redis_connection_failures_total = Counter(
            'redis_connection_failures_total',
            'Failed Redis connection attempts'
        )
        
        self.redis_command_duration_seconds = Histogram(
            'redis_command_duration_seconds',
            'Redis command duration in seconds',
            ['command'],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5)
        )
        
        self.redis_queue_backlog = Gauge(
            'redis_queue_backlog',
            'Redis queue/stream backlog',
            ['queue_name']
        )
        
        self.redis_retry_total = Counter(
            'redis_retry_total',
            'Redis operation retries',
            ['reason']
        )
        
        # Background Worker Metrics
        self.worker_jobs_started_total = Counter(
            'worker_jobs_started_total',
            'Total worker jobs started',
            ['worker', 'job_type']
        )
        
        self.worker_jobs_completed_total = Counter(
            'worker_jobs_completed_total',
            'Total worker jobs completed',
            ['worker', 'job_type', 'status']
        )
        
        self.worker_jobs_failed_total = Counter(
            'worker_jobs_failed_total',
            'Total worker jobs failed',
            ['worker', 'job_type', 'error_type']
        )
        
        self.worker_job_duration_seconds = Histogram(
            'worker_job_duration_seconds',
            'Worker job duration in seconds',
            ['worker', 'job_type'],
            buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600)
        )
        
        self.worker_retry_total = Counter(
            'worker_retry_total',
            'Total worker job retries',
            ['worker', 'job_type', 'reason']
        )
        
        self.worker_backlog = Gauge(
            'worker_backlog',
            'Worker queue backlog',
            ['worker', 'queue_name']
        )
        
        # Analysis Pipeline Observability
        self.analysis_jobs_total = Counter(
            'analysis_jobs_total',
            'Total analysis jobs',
            ['job_type', 'status']  # status: created, completed, failed
        )
        
        self.analysis_job_duration_seconds = Histogram(
            'analysis_job_duration_seconds',
            'Analysis job duration in seconds',
            ['job_type'],
            buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)
        )
        
        self.analysis_job_failures_total = Counter(
            'analysis_job_failures_total',
            'Failed analysis jobs',
            ['job_type', 'error_type']
        )
        
        self.analysis_job_retries_total = Counter(
            'analysis_job_retries_total',
            'Analysis job retries',
            ['job_type', 'reason']
        )
        
        self.analysis_abandoned_jobs_recovered_total = Counter(
            'analysis_abandoned_jobs_recovered_total',
            'Recovered abandoned analysis jobs',
            ['job_type']
        )
        
        # Webhook / Integration Observability
        self.webhook_events_total = Counter(
            'webhook_events_total',
            'Total webhook events',
            ['event_type', 'subscription_id']
        )
        
        self.webhook_delivery_attempts_total = Counter(
            'webhook_delivery_attempts_total',
            'Webhook delivery attempts',
            ['subscription_id', 'event_type', 'status_code']
        )
        
        self.webhook_delivery_success_total = Counter(
            'webhook_delivery_success_total',
            'Successful webhook deliveries',
            ['subscription_id', 'event_type']
        )
        
        self.webhook_delivery_failures_total = Counter(
            'webhook_delivery_failures_total',
            'Failed webhook deliveries',
            ['subscription_id', 'event_type', 'error_type']
        )
        
        self.webhook_delivery_duration_seconds = Histogram(
            'webhook_delivery_duration_seconds',
            'Webhook delivery duration in seconds',
            ['subscription_id', 'event_type'],
            buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60)
        )
        
        self.webhook_retries_total = Counter(
            'webhook_retries_total',
            'Webhook delivery retries',
            ['subscription_id', 'event_type', 'reason']
        )
        
        self.webhook_subscriptions_suspended_total = Counter(
            'webhook_subscriptions_suspended_total',
            'Suspended webhook subscriptions',
            ['subscription_id', 'reason']
        )
        
        # Storage Observability
        self.storage_operations_total = Counter(
            'storage_operations_total',
            'Total storage operations',
            ['operation', 'provider', 'status']
        )
        
        self.storage_operation_duration_seconds = Histogram(
            'storage_operation_duration_seconds',
            'Storage operation duration in seconds',
            ['operation', 'provider'],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
        )
        
        self.storage_operation_errors_total = Counter(
            'storage_operation_errors_total',
            'Storage operation errors',
            ['operation', 'provider', 'error_type']
        )
        
        self.storage_latency_seconds = Histogram(
            'storage_latency_seconds',
            'Storage latency in seconds',
            ['operation', 'provider'],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
        )

    def record_http_request(self, method: str, route: str, status_code: int, duration_seconds: float):
        """Record HTTP request metrics."""
        if not self.enabled:
            return
        self.http_requests_total.labels(
            method=method,
            route=route,
            status_code=status_code
        ).inc()
        self.http_request_duration_seconds.labels(
            method=method,
            route=route
        ).observe(duration_seconds)
        
        if status_code >= 400:
            self.http_errors_total.labels(
                method=method,
                route=route,
                error_type=f"http_{status_code}"
            ).inc()

    def record_db_query(self, operation: str, duration_seconds: float):
        """Record database query metrics."""
        if not self.enabled:
            return
        self.db_query_duration_seconds.labels(
            operation=operation
        ).observe(duration_seconds)

    def record_db_connection_failure(self):
        """Record database connection acquisition failure."""
        if not self.enabled:
            return
        self.db_connection_acquisition_failures_total.inc()

    def record_db_transaction_failure(self, reason: str):
        """Record database transaction failure."""
        if not self.enabled:
            return
        self.db_transaction_failures_total.labels(reason=reason).inc()

    def set_db_connectivity(self, connected: bool):
        """Set database connectivity status."""
        if not self.enabled:
            return
        self.db_connectivity_status.set(1 if connected else 0)

    def record_worker_job_started(self, worker: str, job_type: str):
        """Record worker job started."""
        if not self.enabled:
            return
        self.worker_jobs_started_total.labels(
            worker=worker,
            job_type=job_type
        ).inc()

    def record_worker_job_completed(self, worker: str, job_type: str, status: str, duration_seconds: float = None):
        """Record worker job completed."""
        if not self.enabled:
            return
        self.worker_jobs_completed_total.labels(
            worker=worker,
            job_type=job_type,
            status=status
        ).inc()
        if duration_seconds is not None:
            self.worker_job_duration_seconds.labels(
                worker=worker,
                job_type=job_type
            ).observe(duration_seconds)

    def record_worker_job_failed(self, worker: str, job_type: str, error_type: str):
        """Record worker job failed."""
        if not self.enabled:
            return
        self.worker_jobs_failed_total.labels(
            worker=worker,
            job_type=job_type,
            error_type=error_type
        ).inc()

    def record_worker_retry(self, worker: str, job_type: str, reason: str):
        """Record worker job retry."""
        if not self.enabled:
            return
        self.worker_retry_total.labels(
            worker=worker,
            job_type=job_type,
            reason=reason
        ).inc()

    def set_worker_backlog(self, worker: str, queue_name: str, backlog_size: int):
        """Set worker queue backlog."""
        if not self.enabled:
            return
        self.worker_backlog.labels(
            worker=worker,
            queue_name=queue_name
        ).set(backlog_size)

    def record_analysis_job(self, job_type: str, status: str):
        """Record analysis job."""
        if not self.enabled:
            return
        self.analysis_jobs_total.labels(
            job_type=job_type,
            status=status
        ).inc()

    def record_analysis_job_duration(self, job_type: str, duration_seconds: float):
        """Record analysis job duration."""
        if not self.enabled:
            return
        self.analysis_job_duration_seconds.labels(
            job_type=job_type
        ).observe(duration_seconds)

    def record_analysis_job_failure(self, job_type: str, error_type: str):
        """Record analysis job failure."""
        if not self.enabled:
            return
        self.analysis_job_failures_total.labels(
            job_type=job_type,
            error_type=error_type
        ).inc()

    def record_analysis_job_retry(self, job_type: str, reason: str):
        """Record analysis job retry."""
        if not self.enabled:
            return
        self.analysis_job_retries_total.labels(
            job_type=job_type,
            reason=reason
        ).inc()

    def record_analysis_job_recovered(self, job_type: str):
        """Record recovered abandoned analysis job."""
        if not self.enabled:
            return
        self.analysis_abandoned_jobs_recovered_total.labels(
            job_type=job_type
        ).inc()

    def record_webhook_event(self, event_type: str, subscription_id: str):
        """Record webhook event created."""
        if not self.enabled:
            return
        self.webhook_events_total.labels(
            event_type=event_type,
            subscription_id=subscription_id
        ).inc()

    def record_webhook_delivery_attempt(self, subscription_id: str, event_type: str, 
                                      status_code: int, duration_seconds: float = None):
        """Record webhook delivery attempt."""
        if not self.enabled:
            return
        self.webhook_delivery_attempts_total.labels(
            subscription_id=subscription_id,
            event_type=event_type,
            status_code=status_code
        ).inc()
        if duration_seconds is not None:
            self.webhook_delivery_duration_seconds.labels(
                subscription_id=subscription_id,
                event_type=event_type
            ).observe(duration_seconds)
            
        if 200 <= status_code < 300:
            self.webhook_delivery_success_total.labels(
                subscription_id=subscription_id,
                event_type=event_type
            ).inc()
        else:
            self.webhook_delivery_failures_total.labels(
                subscription_id=subscription_id,
                event_type=event_type,
                error_type=f"http_{status_code}"
            ).inc()

    def record_webhook_retry(self, subscription_id: str, event_type: str, reason: str):
        """Record webhook delivery retry."""
        if not self.enabled:
            return
        self.webhook_retries_total.labels(
            subscription_id=subscription_id,
            event_type=event_type,
            reason=reason
        ).inc()

    def record_webhook_subscription_suspended(self, subscription_id: str, reason: str):
        """Record webhook subscription suspension."""
        if not self.enabled:
            return
        self.webhook_subscriptions_suspended_total.labels(
            subscription_id=subscription_id,
            reason=reason
        ).inc()

    def record_storage_operation(self, operation: str, provider: str, 
                               status: str, duration_seconds: float = None):
        """Record storage operation."""
        if not self.enabled:
            return
        self.storage_operations_total.labels(
            operation=operation,
            provider=provider,
            status=status
        ).inc()
        if duration_seconds is not None:
            self.storage_operation_duration_seconds.labels(
                operation=operation,
                provider=provider
            ).observe(duration_seconds)

    def record_storage_error(self, operation: str, provider: str, error_type: str):
        """Record storage operation error."""
        if not self.enabled:
            return
        self.storage_operation_errors_total.labels(
            operation=operation,
            provider=provider,
            error_type=error_type
        ).inc()

    def set_redis_connectivity(self, connected: bool):
        """Set Redis connectivity status."""
        if not self.enabled:
            return
        # We could add a Redis connectivity gauge similar to DB if needed
        pass

    def set_redis_queue_backlog(self, queue_name: str, backlog_size: int):
        """Set Redis queue backlog."""
        if not self.enabled:
            return
        self.redis_queue_backlog.labels(
            queue_name=queue_name
        ).set(backlog_size)

    def record_redis_command(self, command: str, duration_seconds: float):
        """Record Redis command execution."""
        if not self.enabled:
            return
        self.redis_command_duration_seconds.labels(
            command=command
        ).observe(duration_seconds)

    def record_redis_connection_failure(self):
        """Record Redis connection failure."""
        if not self.enabled:
            return
        self.redis_connection_failures_total.inc()

    def record_redis_retry(self, reason: str):
        """Record Redis operation retry."""
        if not self.enabled:
            return
        self.redis_retry_total.labels(reason=reason).inc()


# Global metrics instance
metrics = Metrics()


def get_metrics() -> Metrics:
    """Get the global metrics instance."""
    return metrics
