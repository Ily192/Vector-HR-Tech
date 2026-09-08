"""Regresión del bug bloqueante de arranque.

`structlog.configure()` traía processors `structlog.stdlib.*` pero NO
`logger_factory`, así que structlog usaba `PrintLoggerFactory` y
`add_logger_name` reventaba con
`AttributeError: 'PrintLogger' object has no attribute 'name'`
en la PRIMERA línea de log: se caía el lifespan de FastAPI y el worker Celery.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
import structlog

from app.config import settings
from app.monitoring import hash_pii, init_monitoring, logger


def test_structlog_uses_stdlib_logger_factory() -> None:
    init_monitoring(force=True)
    config = structlog.get_config()
    assert isinstance(config["logger_factory"], structlog.stdlib.LoggerFactory)
    assert config["wrapper_class"] is structlog.stdlib.BoundLogger


def test_first_log_line_does_not_explode() -> None:
    init_monitoring(force=True)
    # Antes: AttributeError en esta misma línea.
    logger.info("monitoring.smoke", empresa_id="x", run_id="y")
    logger.bind(run_id="z").warning("monitoring.smoke.bound")


def test_log_level_is_driven_by_settings() -> None:
    init_monitoring(force=True)
    assert settings.log_level == "warning"
    assert logging.getLogger().level == logging.WARNING


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    yield
    init_monitoring(force=True)


def test_log_level_change_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    """`logging.basicConfig` corre con `force=True`, así que el nivel se aplica.

    Sin `force=True` es un no-op cuando uvicorn/celery ya tocaron el root logger
    y `LOG_LEVEL` se ignoraría en silencio.
    """
    monkeypatch.setattr(settings, "log_level", "debug")
    init_monitoring(force=True)
    assert logging.getLogger().level == logging.DEBUG

    monkeypatch.setattr(settings, "log_level", "error")
    init_monitoring(force=True)
    assert logging.getLogger().level == logging.ERROR


def test_init_monitoring_is_idempotent() -> None:
    init_monitoring(force=True)
    init_monitoring()
    init_monitoring()
    logger.info("monitoring.smoke.idempotent")


def test_hash_pii_is_stable_and_not_the_plaintext() -> None:
    digest = hash_pii("Ana Dev")
    assert digest is not None
    assert digest == hash_pii("Ana Dev")
    assert digest != hash_pii("Otro Nombre")
    assert "Ana" not in digest
    assert hash_pii(None) is None
    assert hash_pii("") is None
