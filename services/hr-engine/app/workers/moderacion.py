"""Tareas de la moderación de vacantes (ADR-022). Sin IA.

`moderacion.barrer` corre cada minuto con Celery beat: una vacante de una empresa
verificada sin señales de riesgo sale al career site en el siguiente barrido.
`moderacion.avisar` corre cada 5 minutos y decide si toca mandar el resumen de la
cola a hola@. Como coincidencias, no son runs de agente: sin run-token ni tope de
gasto, porque no llaman a ningún LLM.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from uuid import UUID

from app.application.moderar_vacantes import AvisarColaDeRevision, ModerarVacantesPendientes
from app.config import settings
from app.database import db_session
from app.infrastructure.moderacion import CorreoSmtp, SqlRepositorioDeModeracion
from app.monitoring import logger
from app.security import enlaces_de_revision
from app.workers.celery_app import celery_app


async def _barrer() -> dict[str, int]:
    async with db_session() as db:
        caso = ModerarVacantesPendientes(SqlRepositorioDeModeracion(db))
        resultado = asdict(await caso.ejecutar(lote=settings.moderacion_lote))
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
