"""Tipo-seguro settings driven by env. Una sola fuente de verdad."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Vortex hr-engine settings. Env > .env > defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Core ─────────────────────────────────────────────
    env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    service_name: str = "hr-engine"
    service_version: str = "0.1.0"

    # ─── DB ───────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://vortex:vortex@localhost:5432/vortex_dev",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 5

    # ─── Redis / Celery ──────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_concurrency: int = 4

    # ─── Auth ────────────────────────────────────────────
    jwt_secret: str = Field(default="change-me", min_length=8)
    jwt_algorithm: Literal["HS256", "RS256"] = "HS256"
    run_token_ttl_seconds: int = 300

    # ─── LLMs ────────────────────────────────────────────
    openai_api_key: str = ""
    google_api_key: str = ""
    default_scoring_model: str = "gemini-1.5-flash"
    reasoning_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"

    # ─── Control plane ───────────────────────────────────
    paperclip_url: str = "http://localhost:4000"
    paperclip_api_key: str = ""

    # ─── Observability ───────────────────────────────────
    sentry_dsn: str = ""
    otel_endpoint: str = ""

    # ─── Cost caps (defaults; override per-tenant) ───────
    default_run_cost_cap_usd: float = 0.05


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
