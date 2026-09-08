"""Tipo-seguro settings driven by env. Una sola fuente de verdad.

Reglas:
- Nada de `os.getenv` suelto fuera de este módulo.
- Los nombres de env var están alineados con la raíz `.env.example` del monorepo.
  Donde el nombre histórico difiere se acepta el alias legacy vía `AliasChoices`
  (p. ej. `SENTRY_DSN_BACKEND` con fallback a `SENTRY_DSN`), para que un deploy
  no crea que tiene observabilidad cuando en realidad Pydantic descartó la var.
- `env=production` no arranca con secretos/infra de desarrollo (ver
  `_validate_production_hardening`).
"""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores placeholder que jamás pueden llegar a producción.
INSECURE_SECRETS: frozenset[str] = frozenset(
    {
        "change-me",
        "change-me-in-production",
        "changeme",
        "secret",
        "test-secret",
        "test-secret-not-for-production",
    },
)

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "host.docker.internal")


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
    # Hard kill: el worker muere si una task pasa de acá (segundos).
    celery_task_time_limit: int = 600
    # Soft kill: se lanza SoftTimeLimitExceeded dentro de la task para cleanup.
    celery_task_soft_time_limit: int = 540
    # TTL de los resultados en el backend Redis (segundos).
    celery_result_expires: int = 3600
    # Debe ser > task_time_limit o Redis re-entrega la task mientras corre.
    celery_visibility_timeout: int = 900
    # Rate limit por worker para todas las tasks (protege el gasto LLM).
    celery_task_default_rate_limit: str = "30/m"

    # ─── Auth (run-tokens, ADR-005) ──────────────────────
    jwt_secret: str = Field(default="change-me", min_length=8)
    jwt_algorithm: Literal["HS256", "RS256"] = "HS256"
    run_token_ttl_seconds: int = 300
    # Tolerancia de clock skew al validar `exp` (segundos).
    jwt_leeway_seconds: int = 10

    # ─── HTTP / CORS ─────────────────────────────────────
    # CSV de orígenes permitidos. Ej: "https://app.vortex.io,https://admin.vortex.io".
    cors_allow_origins: str = "http://localhost:3000,http://localhost:3001"
    cors_allow_credentials: bool = True

    # ─── Rate limiting (slowapi) ─────────────────────────
    rate_limit_enabled: bool = True
    # Límite global por IP aplicado como middleware a toda la app.
    rate_limit_global: str = "120/minute"
    # Límite por tenant (empresa_id del run-token) en los endpoints /run.
    rate_limit_tenant_runs: str = "20/minute"
    # Vacío = storage en memoria (solo válido con 1 proceso). En prod: redis://…
    rate_limit_storage_uri: str = ""

    # ─── LLMs ────────────────────────────────────────────
    openai_api_key: str = ""
    google_api_key: str = ""
    default_scoring_model: str = "gemini-2.5-flash"
    reasoning_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    # Timeouts por request al proveedor (segundos). El default del SDK de
    # OpenAI son 600 s: inaceptable dentro de una task con time limit.
    openai_timeout_seconds: float = 30.0
    gemini_timeout_seconds: float = 60.0
    llm_max_attempts: int = 3

    # ─── Control plane ───────────────────────────────────
    paperclip_url: str = "http://localhost:4000"
    paperclip_api_key: str = ""

    # ─── Observability ───────────────────────────────────
    # La raíz del monorepo define SENTRY_DSN_BACKEND / OTEL_EXPORTER_OTLP_ENDPOINT.
    sentry_dsn: str = Field(
        default="",
        validation_alias=AliasChoices("SENTRY_DSN_BACKEND", "SENTRY_DSN"),
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_ENDPOINT"),
    )
    otel_exporter_otlp_headers: str = ""

    # ─── Cost caps (defaults; override per-tenant) ───────
    default_run_cost_cap_usd: float = 0.05
    # Techo duro: aunque Paperclip firme un cap mayor, el engine lo recorta.
    max_run_cost_cap_usd: float = 5.0

    # ─── Derivados ───────────────────────────────────────
    @property
    def cors_origins(self) -> list[str]:
        """CSV → lista, ignorando espacios y entradas vacías."""
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @model_validator(mode="after")
    def _validate_production_hardening(self) -> "Settings":
        """Falla al arrancar si producción quedó con defaults de desarrollo.

        Preferimos un crash ruidoso en el boot antes que un servicio en prod
        firmando run-tokens con `change-me`.
        """
        if self.env != "production":
            return self

        problems: list[str] = []

        if self.jwt_secret.strip().lower() in INSECURE_SECRETS:
            problems.append("JWT_SECRET usa un valor placeholder inseguro")
        elif len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET debe tener >= 32 chars en producción")

        if any(host in self.database_url for host in _LOCAL_HOSTS):
            problems.append("DATABASE_URL apunta a localhost en producción")

        if any(host in self.redis_url for host in _LOCAL_HOSTS):
            problems.append("REDIS_URL apunta a localhost en producción")

        origins = self.cors_origins
        if not origins:
            problems.append("CORS_ALLOW_ORIGINS vacío en producción")
        if "*" in origins and self.cors_allow_credentials:
            problems.append("CORS_ALLOW_ORIGINS='*' con credenciales es inválido")
        if any(any(host in o for host in _LOCAL_HOSTS) for o in origins):
            problems.append("CORS_ALLOW_ORIGINS incluye localhost en producción")

        if self.rate_limit_enabled and not self.rate_limit_storage_uri:
            problems.append(
                "RATE_LIMIT_STORAGE_URI es obligatorio en producción "
                "(el storage en memoria no se comparte entre workers)",
            )

        if self.celery_visibility_timeout <= self.celery_task_time_limit:
            problems.append(
                "CELERY_VISIBILITY_TIMEOUT debe ser > CELERY_TASK_TIME_LIMIT",
            )

        if problems:
            raise ValueError(
                "Config de producción inválida:\n  - " + "\n  - ".join(problems),
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Invalida el singleton — solo para tests que manipulan el entorno."""
    get_settings.cache_clear()


settings = get_settings()
