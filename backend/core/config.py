"""Configuration using Pydantic BaseSettings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "proof-of-action-backend"
    environment: str = "development"

    # Data stores
    # Use PostgreSQL in development by default (do not use SQLite).
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"
    redis_url: str = "redis://localhost:6379/0"
    analysis_queue_name: str = "pofa:analysis:jobs"
    analysis_max_attempts: int = 3
    analysis_abandoned_timeout_seconds: int = 300
    phash_max_hamming_distance: int = 8
    embedding_model_name: str = "openai/clip-vit-base-patch32"
    embedding_dimension: int = 512
    embedding_top_k: int = 10

    # BE-009 Vision Intelligence (Ultralytics YOLO; weights auto-downloaded
    # at runtime, never committed to Git).
    vision_enabled: bool = True
    vision_model_name: str = "yolo11n.pt"
    vision_conf_threshold: float = 0.25
    vision_iou_threshold: float = 0.45
    vision_max_detections: int = 100
    vision_device: str = "auto"
    vision_imgsz: int = 640

    # S3 / MinIO
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    s3_quarantine_bucket: str = "pofa-quarantine"
    s3_evidence_bucket: str = "pofa-evidence"
    max_upload_size: int = 10 * 1024 * 1024

    jwt_secret: str = "changeme"

    # CORS. Comma-separated list of the origins allowed to call this API with
    # credentials. The default keeps the historical development behaviour
    # (every origin), which must be replaced for any shared deployment: with
    # allow_credentials on, a wildcard makes the middleware echo back whatever
    # Origin the caller sent, so any website can read authenticated responses.
    cors_allow_origins: str = "*"

    # BE-016 Authentication & Authorization foundation.
    # development: anonymous requests are permitted (existing behavior) while
    # presented credentials are fully enforced. enforcing: anonymous requests
    # are rejected (401); use in any shared/production deployment.
    auth_mode: str = "development"
    # Development bearer tokens (dev-user-<uuid>, dev-client-<id>) are
    # non-secret identifiers accepted only when this is explicitly enabled.
    # Production OIDC/OAuth2 integration must disable this.
    auth_dev_tokens_enabled: bool = True

    # BE-020 Observability Configuration
    otel_enabled: bool = False
    otel_service_name: str = "poa-backend"
    otel_exporter_otlp_endpoint: str = ""
    otel_trace_sample_rate: float = 0.1
    prometheus_enabled: bool = True
    observability_log_format: str = "json"
    observability_redact_sensitive: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        """The allowlist as a list; an empty or blank value keeps every origin."""
        origins = [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]
        return origins or ["*"]

    class Config:
        env_file = ".env"


settings = Settings()
