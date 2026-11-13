"""Tareas de la moderación de vacantes (ADR-022).

`moderacion.barrer` corre cada minuto con Celery beat. Primero da la insignia a las
empresas cuyo dueño acaba de confirmar el código del alta desde la web
(`ConfirmarAltasDeLaWeb`), y después modera con las reglas fijas y, si hay
GOOGLE_API_KEY, con el revisor de Gemini: una vacante de una empresa verificada sin
señales de riesgo sale al career site en el siguiente barrido. Si el revisor falla,
la vacante espera y, después de `MODERACION_MAX_INTENTOS_IA` barridos, va a revisión.
`moderacion.avisar` corre cada 5 minutos y decide si toca mandar el resumen de la
cola a hola@. No son runs de agente: sin run-token. El revisor cuesta ~US$0,0004
por vacante y cada llamada deja sus tokens en el log (`moderacion.ia`).
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from functools import cache
from typing import TYPE_CHECKING
from uuid import UUID

import redis

from app.application.moderar_vacantes import AvisarColaDeRevision, ModerarVacantesPendientes
from app.application.verificar_empresa import ConfirmarAltasDeLaWeb, VerificarEmpresa
from app.config import settings
from app.database import db_session
from app.infrastructure.altas_web import SqlRepositorioDeAltasWeb
from app.infrastructure.moderacion import (
    CorreoSmtp,
    RegistroDeIntentosRedis,
    SqlRepositorioDeModeracion,
)
from app.infrastructure.verificador_gemini import revisor_configurado
from app.monitoring import logger
from app.security import enlaces_de_revision
from app.workers.celery_app import celery_app

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def confirmar_altas(db: AsyncSession) -> ConfirmarAltasDeLaWeb:
    """La insignia de las altas recién confirmadas, y su marca `confirmado_en`."""
    return ConfirmarAltasDeLaWeb(
        SqlRepositorioDeAltasWeb(db), VerificarEmpresa(SqlRepositorioDeModeracion(db))
    )


@cache
def _redis() -> redis.Redis:
    # Síncrono, como el circuit breaker: no se ata a ningún event loop.
    return redis.Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)


_avisado_sin_ia = False


def _avisar_si_no_hay_revisor(hay_revisor: bool) -> None:
    """Una vez por proceso: la moderación sigue, pero solo con las reglas fijas."""
    global _avisado_sin_ia
    if hay_revisor or _avisado_sin_ia:
        return
    _avisado_sin_ia = True
    motivo = (
        "MODERACION_IA_ACTIVA=false"
        if not settings.moderacion_ia_activa
        else "falta GOOGLE_API_KEY"
    )
    logger.warning("moderacion.sin_ia", motivo=motivo, efecto="solo reglas fijas")


async def _barrer() -> dict[str, int]:
    revisor = revisor_configurado()
    _avisar_si_no_hay_revisor(revisor is not None)
    async with db_session() as db:
        confirmadas = await confirmar_altas(db).ejecutar()
        caso = ModerarVacantesPendientes(
            SqlRepositorioDeModeracion(db),
            revisor,
            intentos=RegistroDeIntentosRedis(_redis()),
            max_intentos=settings.moderacion_max_intentos_ia,
        )
        resultado = {
            "altas_confirmadas": confirmadas,
            **asdict(await caso.ejecutar(lote=settings.moderacion_lote)),
        }
    if any(resultado.values()):
        logger.info("moderacion.barrido", **resultado)
    return resultado


@celery_app.task(name="moderacion.barrer")
def barrer() -> dict[str, int]:
    """Modera las vacantes 'pendiente': las publica, las manda a revisión o las rechaza."""
    return asyncio.run(_barrer())


def enlace_de_revision(vacante_id: UUID) -> str:
    token = enlaces_de_revision.firmar(settings.moderacion_secreto, vacante_id)
    return f"{settings.api_publica_url.rstrip('/')}/moderacion/revisar?t={token}"


def correo() -> CorreoSmtp:
    return CorreoSmtp(
        host=settings.smtp_host,
        puerto=settings.smtp_port,
        usuario=settings.smtp_user,
        clave=settings.smtp_pass,
        remitente=settings.smtp_remitente,
        nombre=settings.smtp_nombre,
        starttls=settings.smtp_starttls,
    )


async def _avisar() -> int:
    async with db_session() as db:
        caso = AvisarColaDeRevision(
            SqlRepositorioDeModeracion(db),
            correo(),
            destino=settings.moderacion_correo,
            enlace=enlace_de_revision,
            horas_entre_resumenes=settings.moderacion_horas_entre_resumenes,
            max_en_24_horas=settings.moderacion_max_resumenes_24h,
        )
        return await caso.ejecutar()


@celery_app.task(name="moderacion.avisar")
def avisar() -> int:
    """Manda a hola@ el resumen de la cola de revisión, si toca."""
    if not (settings.moderacion_secreto and settings.smtp_host and settings.smtp_remitente):
        logger.warning(
            "moderacion.sin_aviso",
            motivo="faltan MODERACION_SECRETO, SMTP_HOST o el remitente",
        )
        return 0
    return asyncio.run(_avisar())
