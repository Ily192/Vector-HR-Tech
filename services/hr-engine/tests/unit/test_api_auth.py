"""Tests de autenticación/autorización de los endpoints `/run` (ADR-005).

Cubre el agujero original: `empresa_id` y `cost_cap_usd` llegaban del BODY sin
verificar nada, así que cualquiera lanzaba runs contra cualquier tenant.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.security.run_token import issue_run_token

from .conftest import ApiWorld

SOURCER_URL = "/api/sourcer/run"
CV_URL = "/api/cv-evaluator/run"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sourcer_body(**extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"icp_text": "Senior Python LATAM remoto", "target": 10}
    body.update(extra)
    return body


def _cv_body(**extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "vacante_id": str(uuid4()),
        "candidato_id": str(uuid4()),
    }
    body.update(extra)
    return body


# ── 401: sin credenciales / credenciales inválidas ──────────────────────────


def test_missing_authorization_header_is_401(client: TestClient, api_world: ApiWorld) -> None:
    response = client.post(SOURCER_URL, json=_sourcer_body())
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"] == "http_error"
    assert response.headers["X-Request-ID"]
    assert api_world.sourcer_task.calls == []


def test_non_bearer_scheme_is_401(client: TestClient, api_world: ApiWorld) -> None:
    response = client.post(
        SOURCER_URL,
        json=_sourcer_body(),
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 401
    assert api_world.sourcer_task.calls == []


def test_invalid_signature_is_401(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    forged = str(
        jwt.encode(
            {
                "empresa_id": str(empresa_id),
                "agent_skill": "sourcer",
                "run_id": str(uuid4()),
                "cost_cap_usd": 0.05,
                "exp": int(time.time()) + 300,
            },
            "clave-del-atacante",
            algorithm="HS256",
        ),
    )
    response = client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(forged))
    assert response.status_code == 401
    assert api_world.sourcer_task.calls == []


def test_expired_token_is_401(client: TestClient, api_world: ApiWorld, empresa_id: UUID) -> None:
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="sourcer",
        run_id=uuid4(),
        cost_cap_usd=0.05,
        ttl_seconds=-600,
    )
    response = client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token))
    assert response.status_code == 401
    assert "expirado" in response.json()["detail"].lower()
    assert api_world.sourcer_task.calls == []


# ── 403: skill que no corresponde al endpoint ───────────────────────────────


def test_sourcer_token_cannot_call_cv_evaluator(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="sourcer",
        run_id=uuid4(),
        cost_cap_usd=0.05,
    )
    response = client.post(CV_URL, json=_cv_body(), headers=_auth(token))
    assert response.status_code == 403
    assert api_world.cv_evaluator_task.calls == []


def test_cv_evaluator_token_cannot_call_sourcer(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="cv-evaluator",
        run_id=uuid4(),
        cost_cap_usd=0.05,
    )
    response = client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token))
    assert response.status_code == 403
    assert api_world.sourcer_task.calls == []


# ── 202: token válido ───────────────────────────────────────────────────────


def test_valid_token_enqueues_with_token_claims(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    run_id = uuid4()
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="sourcer",
        run_id=run_id,
        cost_cap_usd=0.03,
    )
    response = client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token))

    assert response.status_code == 202
    body = response.json()
    assert body["run_id"] == str(run_id)
    assert body["empresa_id"] == str(empresa_id)
    assert body["cost_cap_usd"] == 0.03
    assert body["deduplicated"] is False

    # La fila `runs` se crea ANTES de encolar (antes no existía ninguna).
    assert str(run_id) in api_world.runs
    assert api_world.runs[str(run_id)].agent_skill == "sourcer"

    call = api_world.sourcer_task.calls[0]
    assert call["empresa_id"] == str(empresa_id)
    assert call["run_id"] == str(run_id)
    assert call["cost_cap_usd"] == 0.03


def test_cv_evaluator_valid_token_enqueues(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    run_id = uuid4()
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="cv_evaluator",  # variante con guión bajo: mismo skill
        run_id=run_id,
        cost_cap_usd=0.05,
    )
    response = client.post(CV_URL, json=_cv_body(), headers=_auth(token))
    assert response.status_code == 202
    assert api_world.cv_evaluator_task.calls[0]["empresa_id"] == str(empresa_id)


# ── El body NO puede pisar el token ─────────────────────────────────────────


def test_body_empresa_id_and_cost_cap_are_ignored(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    """El tenant y el cap salen del token; el body se descarta en silencio."""
    victima = uuid4()
    run_id = uuid4()
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="sourcer",
        run_id=run_id,
        cost_cap_usd=0.01,
    )
    response = client.post(
        SOURCER_URL,
        json=_sourcer_body(empresa_id=str(victima), cost_cap_usd=4.99, run_id=str(uuid4())),
        headers=_auth(token),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["empresa_id"] == str(empresa_id) != str(victima)
    assert body["cost_cap_usd"] == 0.01
    call = api_world.sourcer_task.calls[0]
    assert call["empresa_id"] == str(empresa_id)
    assert call["cost_cap_usd"] == 0.01
    assert call["run_id"] == str(run_id)


def test_cost_cap_from_token_is_clamped_to_engine_ceiling(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="sourcer",
        run_id=uuid4(),
        cost_cap_usd=1_000.0,
    )
    response = client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token))
    assert response.status_code == 202
    assert response.json()["cost_cap_usd"] == settings.max_run_cost_cap_usd
    assert api_world.sourcer_task.calls[0]["cost_cap_usd"] == settings.max_run_cost_cap_usd


# ── Idempotencia + validación de negocio ────────────────────────────────────


def test_replayed_run_token_does_not_enqueue_twice(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="sourcer",
        run_id=uuid4(),
        cost_cap_usd=0.05,
    )
    first = client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token))
    second = client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token))

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["deduplicated"] is True
    assert second.json()["task_id"] is None
    assert len(api_world.sourcer_task.calls) == 1


def test_run_id_reused_by_another_tenant_is_409(
    client: TestClient,
    api_world: ApiWorld,
) -> None:
    run_id = uuid4()
    token_a = issue_run_token(
        empresa_id=uuid4(),
        agent_skill="sourcer",
        run_id=run_id,
        cost_cap_usd=0.05,
    )
    token_b = issue_run_token(
        empresa_id=uuid4(),
        agent_skill="sourcer",
        run_id=run_id,
        cost_cap_usd=0.05,
    )
    assert client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token_a)).status_code == 202
    conflict = client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token_b))
    assert conflict.status_code == 409
    assert len(api_world.sourcer_task.calls) == 1


def test_sourcer_requires_vacante_or_icp_text(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="sourcer",
        run_id=uuid4(),
        cost_cap_usd=0.05,
    )
    response = client.post(SOURCER_URL, json={"target": 5}, headers=_auth(token))
    assert response.status_code == 400
    assert api_world.sourcer_task.calls == []


def test_validation_error_has_request_id(
    client: TestClient,
    api_world: ApiWorld,
    empresa_id: UUID,
) -> None:
    token = issue_run_token(
        empresa_id=empresa_id,
        agent_skill="cv-evaluator",
        run_id=uuid4(),
        cost_cap_usd=0.05,
    )
    response = client.post(CV_URL, json={"vacante_id": "no-uuid"}, headers=_auth(token))
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert response.json()["request_id"]
    assert api_world.cv_evaluator_task.calls == []


# ── Rate limiting ───────────────────────────────────────────────────────────


@pytest.mark.usefixtures("api_world")
def test_rate_limit_per_tenant(client: TestClient, empresa_id: UUID) -> None:
    """El límite es por tenant del token (`RATE_LIMIT_TENANT_RUNS=5/minute`)."""
    statuses = []
    for _ in range(7):
        token = issue_run_token(
            empresa_id=empresa_id,
            agent_skill="sourcer",
            run_id=uuid4(),
            cost_cap_usd=0.01,
        )
        statuses.append(
            client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token)).status_code,
        )
    assert statuses.count(202) == 5
    assert statuses[-1] == 429


@pytest.mark.usefixtures("api_world")
def test_rate_limit_is_scoped_per_tenant(client: TestClient) -> None:
    """Un tenant quemado no afecta a otro."""
    hot = uuid4()
    for _ in range(6):
        token = issue_run_token(
            empresa_id=hot,
            agent_skill="sourcer",
            run_id=uuid4(),
            cost_cap_usd=0.01,
        )
        client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(token))

    other = issue_run_token(
        empresa_id=uuid4(),
        agent_skill="sourcer",
        run_id=uuid4(),
        cost_cap_usd=0.01,
    )
    assert client.post(SOURCER_URL, json=_sourcer_body(), headers=_auth(other)).status_code == 202


# ── OpenAPI declara la seguridad ────────────────────────────────────────────


def test_openapi_declares_security_on_run_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "PaperclipRunToken" in schema["components"]["securitySchemes"]
    for path in (SOURCER_URL, CV_URL):
        security = schema["paths"][path]["post"]["security"]
        assert any("PaperclipRunToken" in scheme for scheme in security)
