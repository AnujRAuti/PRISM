
"""Configuration using Pydantic BaseSettings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "proof-of-action-backend"
    environment: str = "development"

    # Data stores
    # Use PostgreSQL in development by default (do not use SQLite).
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"
    redis_url: str = "redis://localhost:6379/0"

    # S3 / MinIO
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    s3_quarantine_bucket: str = "pofa-quarantine"
    s3_evidence_bucket: str = "pofa-evidence"

    jwt_secret: str = "changeme"

    class Config:
        env_file = ".env"


settings = Settings()
