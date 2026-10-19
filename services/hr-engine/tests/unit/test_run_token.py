"""Tests del run-token (ADR-005) a nivel unidad: decode + claims."""

from __future__ import annotations

import time
import warnings
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from jwt.warnings import InsecureKeyLengthWarning

from app.config import settings
from app.security.run_token import (
    RunTokenClaims,
    decode_run_token,
    issue_run_token,
    normalize_skill,
)

EMPRESA_ID = uuid4()
RUN_ID = uuid4()


def _token(**overrides: object) -> str:
    payload: dict[str, object] = {
        "empresa_id": str(EMPRESA_ID),
        "agent_skill": "sourcer",
        "run_id": str(RUN_ID),
        "cost_cap_usd": 0.05,
        "exp": int(time.time()) + 300,
    }
    payload.update(overrides)
    return str(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))


def test_decode_valid_token_returns_claims() -> None:
    claims = decode_run_token(_token())
    assert claims == RunTokenClaims(
        empresa_id=EMPRESA_ID,
        agent_skill="sourcer",
        run_id=RUN_ID,
        cost_cap_usd=0.05,
        exp=claims.exp,
    )
    assert claims.skill == "sourcer"


def test_decode_rejects_bad_signature() -> None:
    forged = jwt.encode(
        {"empresa_id": str(EMPRESA_ID)}, "otra-clave-de-al-menos-32-bytes!", algorithm="HS256"
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_run_token(forged)
    assert exc_info.value.status_code == 401


@pytest.mark.parametrize("algoritmo", ["HS384", "HS512"])
def test_el_algoritmo_lo_fija_el_engine_no_el_token(algoritmo: str) -> None:
    # Misma clave, otro algoritmo en el header: se rechaza (algorithm confusion).
    # HS384/HS512 piden claves más largas que la de los tests; aquí se firma así
    # a propósito, por eso se silencia el aviso solo en este encode.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureKeyLengthWarning)
        token = jwt.encode(
            {
                "empresa_id": str(EMPRESA_ID),
                "agent_skill": "sourcer",
                "run_id": str(RUN_ID),
                "cost_cap_usd": 0.05,
                "exp": int(time.time()) + 300,
            },
            settings.jwt_secret,
            algorithm=algoritmo,
        )
    with pytest.raises(HTTPException) as exc_info:
        decode_run_token(token)
    assert exc_info.value.status_code == 401


def test_decode_rejects_unsigned_token() -> None:
    # `alg: none`: un token sin firma no pasa aunque traiga claims válidos.
    token = jwt.encode(
        {
            "empresa_id": str(EMPRESA_ID),
            "agent_skill": "sourcer",
            "run_id": str(RUN_ID),
            "cost_cap_usd": 0.05,
            "exp": int(time.time()) + 300,
        },
        None,
        algorithm="none",
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_run_token(token)
    assert exc_info.value.status_code == 401


def test_decode_rejects_expired_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        decode_run_token(_token(exp=int(time.time()) - 600))
    assert exc_info.value.status_code == 401
    assert "expirado" in str(exc_info.value.detail).lower()


def test_decode_rejects_token_without_exp() -> None:
    payload = {
        "empresa_id": str(EMPRESA_ID),
        "agent_skill": "sourcer",
        "run_id": str(RUN_ID),
        "cost_cap_usd": 0.05,
    }
    token = str(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))
    with pytest.raises(HTTPException) as exc_info:
        decode_run_token(token)
    assert exc_info.value.status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"empresa_id": "no-es-uuid"},
        {"run_id": "no-es-uuid"},
        {"cost_cap_usd": -1},
        {"cost_cap_usd": "gratis"},
        {"agent_skill": ""},
    ],
)
def test_decode_rejects_invalid_claims(overrides: dict[str, object]) -> None:
    with pytest.raises(HTTPException) as exc_info:
        decode_run_token(_token(**overrides))
    assert exc_info.value.status_code == 401


def test_decode_rejects_garbage() -> None:
    with pytest.raises(HTTPException) as exc_info:
        decode_run_token("no.es.un.jwt")
    assert exc_info.value.status_code == 401


def test_effective_cost_cap_is_clamped_by_engine_ceiling() -> None:
    claims = decode_run_token(_token(cost_cap_usd=999.0))
    assert claims.cost_cap_usd == 999.0
    assert claims.effective_cost_cap_usd == settings.max_run_cost_cap_usd


def test_issue_run_token_roundtrip() -> None:
    token = issue_run_token(
        empresa_id=EMPRESA_ID,
        agent_skill="cv-evaluator",
        run_id=RUN_ID,
        cost_cap_usd=0.02,
    )
    claims = decode_run_token(token)
    assert claims.empresa_id == EMPRESA_ID
    assert claims.skill == "cv-evaluator"
    assert claims.cost_cap_usd == 0.02


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("cv_evaluator", "cv-evaluator"), ("CV-Evaluator", "cv-evaluator"), (" sourcer ", "sourcer")],
)
def test_normalize_skill(raw: str, expected: str) -> None:
    assert normalize_skill(raw) == expected
