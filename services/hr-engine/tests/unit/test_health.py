"""Tests de liveness/readiness.

`/ready` solo chequeaba Postgres. Redis es el broker: sin él fallan el 100% de
los POST /run, así que un readiness que lo ignoraba dejaba entrar tráfico a un
servicio inútil (y el HEALTHCHECK del Dockerfile ni siquiera miraba /ready).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import health


def test_health_is_a_liveness_probe(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_ok_when_both_dependencies_are_up(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ok() -> bool:
        return True

    monkeypatch.setattr(health, "_check_postgres", ok)
    monkeypatch.setattr(health, "_check_redis", ok)

    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "postgres": "ok", "redis": "ok"}


def test_ready_is_503_when_redis_is_down(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ok() -> bool:
        return True

    async def down() -> bool:
        return False

    monkeypatch.setattr(health, "_check_postgres", ok)
    monkeypatch.setattr(health, "_check_redis", down)

    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["redis"] == "error"
    assert body["postgres"] == "ok"


def test_ready_is_503_when_postgres_is_down(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ok() -> bool:
        return True

    async def down() -> bool:
        return False

    monkeypatch.setattr(health, "_check_postgres", down)
    monkeypatch.setattr(health, "_check_redis", ok)

    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["postgres"] == "error"


def test_dependency_check_swallows_errors_and_reports_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo de conexión se traduce a `False`, no a un 500."""

    class _BrokenSession:
        async def __aenter__(self) -> None:
            raise ConnectionError("postgres inalcanzable")

        async def __aexit__(self, *_a: object) -> None:
            return None

    monkeypatch.setattr(health, "db_session", lambda: _BrokenSession())

    import asyncio

    assert asyncio.run(health._check_postgres()) is False
