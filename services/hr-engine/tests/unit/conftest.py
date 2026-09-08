"""Fixtures compartidas de los tests unitarios de la API.

La API se testea con `TestClient` real (routing + dependencias + middlewares),
reemplazando solo lo que toca infra: la sesión de DB, el repo de `runs` y el
`.delay()` de Celery.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import cv_evaluator as cv_evaluator_api
from app.api import sourcer as sourcer_api
from app.database import get_db
from app.main import app
from app.repositories import runs as runs_repo


class FakeSession:
    """Sustituto mínimo de AsyncSession para los endpoints."""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:  # pragma: no cover - defensivo
        return None

    async def execute(self, *_a: object, **_kw: object) -> Any:  # pragma: no cover
        raise AssertionError("los tests no deberían tocar SQL real")


@dataclass
class FakeTask:
    """Sustituto de la task Celery: registra los kwargs de `.delay()`."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def delay(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(id=f"task-{len(self.calls)}")


@dataclass
class ApiWorld:
    """Handle para inspeccionar lo que hicieron los endpoints."""

    sourcer_task: FakeTask
    cv_evaluator_task: FakeTask
    runs: dict[str, runs_repo.RunRow]


@pytest.fixture
def api_world(monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiWorld]:
    stored: dict[str, runs_repo.RunRow] = {}

    async def fake_create_run(
        _db: object,
        *,
        run_id: UUID | str,
        empresa_id: UUID | str,
        agent_skill: str,
        cost_cap_usd: float,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        key = str(run_id)
        existing = stored.get(key)
        if existing is not None:
            if str(existing.empresa_id) != str(empresa_id):
                raise runs_repo.TenantMismatchError(f"run {run_id} pertenece a otro tenant")
            return False
        stored[key] = runs_repo.RunRow(
            id=UUID(str(run_id)),
            empresa_id=UUID(str(empresa_id)),
            agent_skill=agent_skill,
            status=runs_repo.STATUS_PENDING,
            cost_usd=0.0,
            cost_cap_usd=cost_cap_usd,
            error_message=None,
            payload=payload,
        )
        return True

    async def fake_get_run(_db: object, run_id: UUID | str) -> runs_repo.RunRow | None:
        return stored.get(str(run_id))

    monkeypatch.setattr(runs_repo, "create_run", fake_create_run)
    monkeypatch.setattr(runs_repo, "get_run", fake_get_run)

    sourcer_task = FakeTask()
    cv_task = FakeTask()
    monkeypatch.setattr(sourcer_api, "sourcer_task", sourcer_task)
    monkeypatch.setattr(cv_evaluator_api, "cv_evaluator_task", cv_task)

    async def fake_get_db() -> AsyncIterator[FakeSession]:
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_get_db
    try:
        yield ApiWorld(sourcer_task=sourcer_task, cv_evaluator_task=cv_task, runs=stored)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def empresa_id() -> UUID:
    """UUID único por test — aísla la key del rate limiter por tenant."""
    return uuid4()
