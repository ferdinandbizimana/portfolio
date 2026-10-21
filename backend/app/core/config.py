"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg://portfolio:portfolio@localhost:5432/portfolio",
        description="SQLAlchemy URL of the PostgreSQL database.",
    )
    redis_url: str = "redis://localhost:6379/0"

    # Comma-separated list of origins allowed to call the API from a browser.
    # State-changing requests from any other Origin are refused.
    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    # Where uploaded files, converted data and reports are stored.
    storage_dir: str = "/data/storage"

    # Login sessions
    session_cookie_name: str = "session"
    cookie_secure: bool = Field(
        default=True, description="Send the session cookie over HTTPS only. False for local HTTP."
    )
    session_idle_minutes: int = 12 * 60
    session_absolute_hours: int = 7 * 24

    # Login rate limiting: after this many failures in the window, refuse further attempts.
    login_max_failures: int = 5
    login_window_minutes: int = 15

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
