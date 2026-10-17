"""Application settings, loaded from `backend/.env` (see `.env.example`)."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/  — resolved from this file so the app behaves the same whatever the CWD is.
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- application ------------------------------------------------------
    APP_NAME: str = "enterprise-admin"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    DOCS_ENABLED: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # -- security ---------------------------------------------------------
    # No default on purpose: a shipped placeholder secret is worse than a loud
    # startup failure. `init.ps1` generates a random value into .env.
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -- database ---------------------------------------------------------
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DB: str = "enterprise_admin"

    # -- infrastructure ---------------------------------------------------
    # Comma-separated on purpose: pydantic-settings would require JSON syntax for
    # a list field, which is easy to get wrong when hand-editing .env.
    CORS_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"

    UPLOAD_DIR: Path = BACKEND_DIR / "uploads"
    LOG_DIR: Path = BACKEND_DIR / "logs"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        """SQLAlchemy async URL.

        The password is percent-encoded because it may legally contain
        characters that would otherwise terminate the userinfo section.
        SQLAlchemy decodes it again when parsing the URL.
        """
        return (
            f"mysql+asyncmy://{self.MYSQL_USER}:{quote_plus(self.MYSQL_PASSWORD)}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
