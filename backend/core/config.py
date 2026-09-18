
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

    class Config:
        env_file = ".env"


settings = Settings()
