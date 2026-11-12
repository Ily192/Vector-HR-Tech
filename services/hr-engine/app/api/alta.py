"""`POST /alta/plan-gratis`: el registro de vectorhrtech.com/publicar-vacantes da de alta
la empresa al instante (enmienda del 2026-11-12 a ADR-017).

Lo llama la ruta del servidor de la web, nunca el navegador, con el secreto que
comparten las dos (`Authorization: Bearer <ALTA_SECRETO>`). Turnstile lo valida la
web antes de llamar: un token de Turnstile solo se puede validar una vez.

Respuestas:
- 200 `{estado: "codigo_enviado", verificar_url}`, tenga o no cuenta el correo.
- 401 sin el secreto o con otro; 503 si el alta no está configurada.
- 422 si los datos no sirven; 429 con `Retry-After` si se pasó un tope.
- 503 si Auth o la base no responden: la web muestra su agradecimiento de respaldo.
"""

from __future__ import annotations

import hmac
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.application.alta_desde_la_web import DarDeAltaDesdeLaWeb
from app.config import settings
from app.database import api_session
from app.domain.alta import SolicitudInvalidaError
from app.domain.alta_web import SolicitudDeAltaWeb, hash_de_ip
from app.domain.puertos import CodigoNoEnviadoError, LimiteDeAltasError
from app.infrastructure.altas import SqlRepositorioDeAltas
from app.infrastructure.altas_web import (
    CodigosSupabase,
    LimitadorConLimits,
    SqlRepositorioDeAltasWeb,
)
from app.monitoring import logger

router = APIRouter()

#: Lo que se espera a Auth antes de responder 503. La web corta a los 10 s.
TIMEOUT_DE_AUTH_S = 8.0

_limitador: LimitadorConLimits | None = None


def _el_limitador() -> LimitadorConLimits:
    global _limitador
    if _limitador is None:
        _limitador = LimitadorConLimits(
            settings.rate_limit_storage_uri or "memory://",
            settings.alta_limite_por_ip,
            settings.alta_limite_por_correo,
        )
    return _limitador


Texto = Annotated[str, Field(max_length=320)]


class CuerpoDelAlta(BaseModel):
    """El body exacto que manda la web. Un campo de más o mal escrito es un 422."""

    model_config = ConfigDict(extra="forbid")

    lead_id: int | Annotated[str, Field(max_length=64)]
    nombre: Texto
    correo: Texto
    publica_para: Literal["propia", "clientes"]
    empresa: Texto
    cargo: Texto | None = None
    web_empresa: Texto | None = None
    linkedin: Texto | None = None
    verificacion: Literal["dominio", "revision"]
    pais: Literal["mx", "ve", "otro"]
    tamano: Literal["1-15", "16-50", "51-200", "200+"] | None = None
    sector: Texto
    contrataciones_mes: Texto
    puestos: Annotated[list[Texto], Field(max_length=16)] = []
    origen: Texto | None = None
    utm_medium: Texto | None = None
    utm_campaign: Texto | None = None
    ip: Texto | None = None


class RespuestaDelAltaWeb(BaseModel):
    estado: Literal["codigo_enviado"]
    verificar_url: str


def _verificar_secreto(authorization: Annotated[str | None, Header()] = None) -> None:
    """Antes que el body: sin el secreto no se dice nada de qué campos faltan."""
    secreto = settings.alta_secreto
    if not secreto:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "el alta desde la web está apagada"
        )
    esquema, _, valor = (authorization or "").partition(" ")
    if esquema.lower() != "bearer" or not hmac.compare_digest(valor.encode(), secreto.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "falta el secreto del alta",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post(
    "/alta/plan-gratis",
    response_model=RespuestaDelAltaWeb,
    dependencies=[Depends(_verificar_secreto)],
)
async def alta_plan_gratis(cuerpo: CuerpoDelAlta, response: Response) -> RespuestaDelAltaWeb:
    try:
        solicitud = SolicitudDeAltaWeb.nueva(
            **{**cuerpo.model_dump(), "lead_id": str(cuerpo.lead_id)}
        )
    except SolicitudInvalidaError as exc:
        # 422 a secas: el nombre de la constante cambió entre versiones de Starlette.
        raise HTTPException(422, str(exc)) from exc

    ip_hash = hash_de_ip(solicitud.ip, settings.alta_secreto)
    try:
        async with api_session() as db, httpx.AsyncClient(timeout=TIMEOUT_DE_AUTH_S) as http:
            caso = DarDeAltaDesdeLaWeb(
                SqlRepositorioDeAltas(db),
                SqlRepositorioDeAltasWeb(db),
                CodigosSupabase(settings.supabase_url, settings.supabase_secret_key, http),
                _el_limitador(),
                settings.panel_url,
            )
            respuesta = await caso.ejecutar(solicitud, ip_hash)
    except LimiteDeAltasError as exc:
        logger.info("alta_web.limite", lead_id=solicitud.lead_id)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "demasiados registros, intenta más tarde",
            headers={"Retry-After": str(exc.reintentar_en_s)},
        ) from exc
    except (CodigoNoEnviadoError, SQLAlchemyError, OSError) as exc:
        logger.warning(
            "alta_web.no_disponible", lead_id=solicitud.lead_id, error=type(exc).__name__
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "el alta no está disponible ahora"
        ) from exc

    logger.info("alta_web.ok", lead_id=solicitud.lead_id)
    response.headers["Cache-Control"] = "no-store"
    return RespuestaDelAltaWeb(estado="codigo_enviado", verificar_url=respuesta.verificar_url)
