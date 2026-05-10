"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://depo:localdev@localhost:5432/deposition_prep"

    @property
    def async_database_url(self) -> str:
        """Convert database URL to async format for SQLAlchemy."""
        from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg doesn't accept sslmode — strip it; ssl is passed via connect_args
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params.pop("sslmode", None)
        params.pop("sslcert", None)
        params.pop("sslkey", None)
        params.pop("sslrootcert", None)
        clean_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=clean_query))

    @property
    def requires_ssl(self) -> bool:
        """True when the database URL includes sslmode=require (cloud DBs)."""
        return "sslmode" in self.database_url

    # Anthropic (LLM calls)
    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-6"

    # OpenAI (embeddings only — Claude has no embedding API)
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    # Document Storage
    documents_path: str = "./transcripts"

    # Optional: OCR
    tesseract_path: str | None = None

    # Authentication — Clerk
    clerk_secret_key: str = ""  # sk_live_... or sk_test_...  (required in prod)
    auth_disabled: bool = False  # Set True for local dev without auth

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
