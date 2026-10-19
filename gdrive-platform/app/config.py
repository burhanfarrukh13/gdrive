"""Application configuration loaded from .env / environment."""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_secret: str = "change-me"
    app_base_url: str = "http://localhost:8000"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"

    google_service_account_file: str = "secrets/service_account.json"
    google_workspace_domain: str | None = None

    # Bootstrap admin (created on first run if no users exist)
    bootstrap_admin_email: str = "admin@local"
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_name: str = "Owner"

    expiry_job_interval_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()