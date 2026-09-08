"""Verificación de run-tokens emitidos por Paperclip (ADR-005).

Contrato de claims — espejo de `packages/types/src/tenant.ts::RunTokenClaimsSchema`:

```json
{
  "empresa_id": "uuid",
  "agent_skill": "sourcer",
  "run_id": "uuid",
  "cost_cap_usd": 0.05,
  "exp": 1746710000
}
```

Reglas que aplica este módulo:

1. `Authorization: Bearer <jwt>` obligatorio → sin header ⇒ 401.
2. Firma + `exp` verificados con `settings.jwt_secret` / `jwt_algorithm`
   (leeway configurable para clock skew) → firma inválida o expirado ⇒ 401.
3. Los claims se validan contra el schema; claim faltante o malformado ⇒ 401.
4. `agent_skill` del token debe corresponder al endpoint invocado; un token de
   `sourcer` NO puede llamar a `cv-evaluator` ⇒ 403.
5. `empresa_id` y `cost_cap_usd` SIEMPRE salen del token, nunca del body.
6. El `cost_cap_usd` se recorta a `settings.max_run_cost_cap_usd` (techo duro
   del engine, defensa ante un control plane comprometido).
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.monitoring import logger

#: Esquema de seguridad expuesto en OpenAPI (`security` en cada endpoint).
run_token_scheme = HTTPBearer(
    scheme_name="PaperclipRunToken",
    description=(
        "Run-token JWT emitido por Paperclip (ADR-005, TTL 5 min). "
        "Claims: empresa_id, agent_skill, run_id, cost_cap_usd, exp."
    ),
    auto_error=False,  # queremos 401 propio, no el 403 por defecto de FastAPI.
)


def normalize_skill(skill: str) -> str:
    """`cv_evaluator`, `CV-Evaluator` y `cv-evaluator` son el mismo skill."""
    return skill.strip().lower().replace("_", "-")


class RunTokenClaims(BaseModel):
    """Claims validados del run-token."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    empresa_id: UUID
    agent_skill: str = Field(min_length=1)
    run_id: UUID
    cost_cap_usd: float = Field(gt=0)
    exp: int

    @property
    def skill(self) -> str:
        return normalize_skill(self.agent_skill)

    @property
    def effective_cost_cap_usd(self) -> float:
        """Cap del token recortado por el techo duro del engine."""
        return min(self.cost_cap_usd, settings.max_run_cost_cap_usd)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_run_token(token: str) -> RunTokenClaims:
    """Decodifica + verifica firma/exp y valida los claims.

    Raises:
        HTTPException 401: token malformado, firma inválida, expirado o con
            claims que no cumplen `RunTokenClaimsSchema`.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={
                "require_exp": True,
                "verify_exp": True,
                "verify_aud": False,
                "leeway": settings.jwt_leeway_seconds,
            },
        )
    except ExpiredSignatureError as exc:
        raise _unauthorized("Run-token expirado") from exc
    except JWTError as exc:
        raise _unauthorized("Run-token inválido") from exc

    try:
        return RunTokenClaims.model_validate(payload)
    except ValidationError as exc:
        # No logueamos el payload: puede traer datos del tenant.
        logger.warning("run_token.invalid_claims", errors=exc.error_count())
        raise _unauthorized("Run-token con claims inválidos") from exc


class RunTokenAuth:
    """Dependencia FastAPI: verifica el run-token y fija el skill esperado.

    Uso:
        ```python
        @router.post("/run", dependencies=[])
        async def endpoint(claims: Annotated[RunTokenClaims, Depends(require_sourcer_token)]):
            ...
        ```
    """

    def __init__(self, agent_skill: str) -> None:
        self.agent_skill = normalize_skill(agent_skill)

    async def __call__(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Security(run_token_scheme),
    ) -> RunTokenClaims:
        if credentials is None or not credentials.credentials:
            raise _unauthorized("Falta el header Authorization: Bearer <run-token>")
        if credentials.scheme.lower() != "bearer":
            raise _unauthorized("El esquema de autenticación debe ser Bearer")

        claims = decode_run_token(credentials.credentials)

        if claims.skill != self.agent_skill:
            logger.warning(
                "run_token.skill_mismatch",
                expected=self.agent_skill,
                received=claims.skill,
                empresa_id=str(claims.empresa_id),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"El run-token es para el skill '{claims.skill}', no para '{self.agent_skill}'"
                ),
            )

        # `tenant_guard` (app.database) lee esto como defensa en profundidad.
        request.state.empresa_id = claims.empresa_id
        request.state.run_claims = claims
        return claims


require_sourcer_token = RunTokenAuth("sourcer")
require_cv_evaluator_token = RunTokenAuth("cv-evaluator")


def issue_run_token(
    *,
    empresa_id: UUID | str,
    agent_skill: str,
    run_id: UUID | str,
    cost_cap_usd: float,
    ttl_seconds: int | None = None,
    secret: str | None = None,
    algorithm: str | None = None,
) -> str:
    """Emite un run-token. Producción = Paperclip; acá para dev/tests/CLI."""
    ttl = settings.run_token_ttl_seconds if ttl_seconds is None else ttl_seconds
    payload = {
        "empresa_id": str(empresa_id),
        "agent_skill": agent_skill,
        "run_id": str(run_id),
        "cost_cap_usd": cost_cap_usd,
        "exp": int(time.time()) + ttl,
    }
    token: str = jwt.encode(
        payload,
        secret or settings.jwt_secret,
        algorithm=algorithm or settings.jwt_algorithm,
    )
    return token


__all__ = [
    "RunTokenAuth",
    "RunTokenClaims",
    "decode_run_token",
    "issue_run_token",
    "normalize_skill",
    "require_cv_evaluator_token",
    "require_sourcer_token",
    "run_token_scheme",
]
