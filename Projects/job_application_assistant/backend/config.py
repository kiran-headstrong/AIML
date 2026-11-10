"""
Application configuration.

Settings are loaded from environment variables (and an optional .env file)
using pydantic-settings. Access the singleton via `get_settings()` or the
module-level `settings` instance.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (job_application_assistant/)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Environment-based application settings."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "Job Application Assistant API"
    app_version: str = "1.0.0"
    debug: bool = False

    # --- Server ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # --- Database ---
    # Async driver (asyncpg) is used by the SQLAlchemy async engine.
    database_url: str = Field(
        default="postgresql+asyncpg://jaa_user:jaa_pass@localhost:5432/job_application_assistant",
        description="Async SQLAlchemy database URL (asyncpg driver).",
    )

    # --- Authentication / JWT ---
    jwt_secret: str = Field(
        default="change-me-in-production-super-secret-key",
        description="Secret key used to sign JWT tokens.",
    )
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours

    # --- CORS ---
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed CORS origins for the frontend SPA.",
    )

    # --- File storage ---
    upload_dir: Path = BASE_DIR / "uploads"
    generated_dir: Path = BASE_DIR / "generated"

    # --- LLM configuration ---
    llm_provider: str = Field(
        default="openai",
        description="LLM provider identifier used by the LangChain abstraction.",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Model name to use for LLM calls.",
    )
    llm_api_key: str = Field(
        default="",
        description="API key for the configured LLM provider.",
    )
    llm_api_base: str | None = Field(
        default=None,
        description="Optional custom base URL for the LLM provider (e.g. local/proxy).",
    )
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2048

    def ensure_directories(self) -> None:
        """Create file-storage directories if they do not exist."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


# Module-level singleton for convenient imports.
settings = get_settings()
