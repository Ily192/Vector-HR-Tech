"""Shared pytest fixtures.

⚠️ El entorno se setea a nivel de MÓDULO, antes de cualquier `import app.*`.

La versión anterior usaba una fixture autouse con `monkeypatch.setenv`, que era
un no-op: `app.config` instancia `settings = get_settings()` en tiempo de
import (y `get_settings` está cacheada con `@lru_cache`), así que para cuando
la fixture corría el objeto `Settings` ya estaba construido con los defaults.
pytest importa los `conftest.py` antes que los módulos de test, así que setear
`os.environ` acá sí llega a tiempo.
"""

from __future__ import annotations

import os

# ── Env de test: se fuerza (no `setdefault`) porque son valores que no deben
#    depender de la máquina donde corre.
_FORCED_ENV = {
    "ENV": "development",
    "JWT_SECRET": "test-secret-not-for-production",
    "JWT_ALGORITHM": "HS256",
    "LOG_LEVEL": "warning",
}
for _key, _value in _FORCED_ENV.items():
    os.environ[_key] = _value

# ── Valores que CI puede querer sobreescribir (p. ej. DATABASE_URL para los
#    tests de RLS, que necesitan un Postgres real).
_DEFAULT_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://vortex:vortex@localhost:5432/vortex_test",
    "REDIS_URL": "redis://localhost:6379/1",
    "OPENAI_API_KEY": "test-openai-key",
    "GOOGLE_API_KEY": "test-google-key",
    # Límite bajo a propósito: los tests de rate limiting lo ejercitan.
    "RATE_LIMIT_TENANT_RUNS": "5/minute",
    "RATE_LIMIT_GLOBAL": "1000/minute",
}
for _key, _value in _DEFAULT_ENV.items():
    os.environ.setdefault(_key, _value)

import pytest  # noqa: E402

from app.config import settings  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _assert_test_env_applied() -> None:
    """Falla ruidosamente si el entorno de test NO llegó a `settings`.

    Es la red de seguridad del bug descrito en el docstring del módulo.
    """
    assert settings.env == "development"
    assert settings.jwt_secret == "test-secret-not-for-production"
    assert settings.log_level == "warning"
