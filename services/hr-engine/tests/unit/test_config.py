"""Tests de `app.config`: hardening de producción + alineación de env vars."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, settings

PROD_OK: dict[str, object] = {
    "env": "production",
    "jwt_secret": "u" * 48,
    "database_url": "postgresql+asyncpg://vortex:pw@db.internal.vortex:5432/vortex",
    "redis_url": "redis://cache.internal.vortex:6379/0",
    "cors_allow_origins": "https://app.vortex.io",
    "rate_limit_storage_uri": "redis://cache.internal.vortex:6379/2",
}


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**PROD_OK, **overrides})  # type: ignore[arg-type]


def test_production_config_is_valid_when_hardened() -> None:
    cfg = _settings()
    assert cfg.is_production
    assert cfg.cors_origins == ["https://app.vortex.io"]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"jwt_secret": "change-me"}, "JWT_SECRET"),
        ({"jwt_secret": "change-me-in-production"}, "JWT_SECRET"),
        ({"jwt_secret": "corto123"}, "JWT_SECRET"),
        (
            {"database_url": "postgresql+asyncpg://vortex:vortex@localhost:5432/vortex_dev"},
            "DATABASE_URL",
        ),
        ({"redis_url": "redis://127.0.0.1:6379/0"}, "REDIS_URL"),
        ({"cors_allow_origins": "http://localhost:3000"}, "CORS_ALLOW_ORIGINS"),
        ({"cors_allow_origins": ""}, "CORS_ALLOW_ORIGINS"),
        ({"cors_allow_origins": "*"}, "CORS_ALLOW_ORIGINS"),
        ({"rate_limit_storage_uri": ""}, "RATE_LIMIT_STORAGE_URI"),
        ({"celery_visibility_timeout": 60}, "CELERY_VISIBILITY_TIMEOUT"),
    ],
)
def test_production_rejects_dev_defaults(overrides: dict[str, object], expected: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _settings(**overrides)
    assert expected in str(exc_info.value)


def test_development_allows_dev_defaults() -> None:
    cfg = Settings(_env_file=None, env="development", jwt_secret="change-me")
    assert cfg.jwt_secret == "change-me"
    assert cfg.is_production is False


def test_cors_origins_parses_csv() -> None:
    cfg = Settings(
        _env_file=None,
        cors_allow_origins=" https://a.io , https://b.io ,",
    )
    assert cfg.cors_origins == ["https://a.io", "https://b.io"]


def test_sentry_dsn_reads_backend_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """La raíz define SENTRY_DSN_BACKEND; antes se leía SENTRY_DSN y se perdía."""
    monkeypatch.setenv("SENTRY_DSN_BACKEND", "https://token@sentry.io/42")
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert Settings(_env_file=None).sentry_dsn == "https://token@sentry.io/42"


def test_sentry_dsn_legacy_alias_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_DSN_BACKEND", raising=False)
    monkeypatch.setenv("SENTRY_DSN", "https://legacy@sentry.io/1")
    assert Settings(_env_file=None).sentry_dsn == "https://legacy@sentry.io/1"


def test_otel_endpoint_reads_standard_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://otlp.vortex.io/v1/traces")
    monkeypatch.delenv("OTEL_ENDPOINT", raising=False)
    cfg = Settings(_env_file=None)
    assert cfg.otel_exporter_otlp_endpoint == "https://otlp.vortex.io/v1/traces"


def test_conftest_env_reached_the_module_level_settings() -> None:
    """El fix de `tests/conftest.py`: el env de test llega al singleton."""
    assert settings.jwt_secret == "test-secret-not-for-production"
    assert settings.env == "development"
