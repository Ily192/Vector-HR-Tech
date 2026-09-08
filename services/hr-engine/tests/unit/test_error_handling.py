"""Handler global de excepciones + request-id.

Antes no había `exception_handler` global: cualquier excepción salía como un
traceback 500 sin request-id, imposible de correlacionar con los logs.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import REQUEST_ID_HEADER, app
from app.repositories import runs as runs_repo
from app.security.run_token import issue_run_token

from .conftest import ApiWorld

SOURCER_URL = "/api/sourcer/run"


def _body() -> dict[str, Any]:
    return {"icp_text": "Senior Python", "target": 5}


def test_health_response_carries_request_id(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers[REQUEST_ID_HEADER]


def test_incoming_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/health", headers={REQUEST_ID_HEADER: "trace-abc-123"})
    assert response.headers[REQUEST_ID_HEADER] == "trace-abc-123"


@pytest.mark.usefixtures("api_world")
def test_unhandled_exception_becomes_500_with_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*_a: object, **_kw: object) -> bool:
        raise RuntimeError("la DB explotó en el peor momento")

    monkeypatch.setattr(runs_repo, "create_run", boom)
    token = issue_run_token(
        empresa_id=uuid4(),
        agent_skill="sourcer",
        run_id=uuid4(),
        cost_cap_usd=0.05,
    )

    with TestClient(app, raise_server_exceptions=False) as raw_client:
        response = raw_client.post(
            SOURCER_URL,
            json=_body(),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "internal_error"
    # No filtramos el mensaje interno al cliente…
    assert body["detail"] == "Internal server error"
    # …pero sí damos el hilo para encontrarlo en los logs.
    assert body["request_id"]
    assert response.headers[REQUEST_ID_HEADER] == body["request_id"]


@pytest.mark.usefixtures("api_world")
def test_http_exception_keeps_www_authenticate_header(client: TestClient) -> None:
    response = client.post(SOURCER_URL, json=_body())
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["request_id"]


def test_api_world_fixture_used(api_world: ApiWorld) -> None:
    """Guard: el fixture aísla la DB real en todos los tests de este módulo."""
    assert api_world.runs == {}
