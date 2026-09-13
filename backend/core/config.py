"""Configuration placeholders for the backend."""

from pydantic import BaseSettings


class Settings(BaseSettings):
    app_name: str = "proof-of-action-backend"


settings = Settings()
