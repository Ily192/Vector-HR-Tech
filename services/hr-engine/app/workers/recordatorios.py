"""Tarea del recordatorio de postulados sin revisar (ADR-023).

`postulados.recordar` corre cada hora con Celery beat. A la empresa con más de 5
postulados sin revisar le llega un solo correo 24 horas después de que llegó el
sexto, si no entró a verlos, y no otro hasta que entre y se junten más. Sale por el
SMTP de Resend que usan Auth y la moderación, con un tope diario
(`RECORDATORIO_MAX_24H`) para que los códigos de acceso no se queden sin cuota.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from app.application.recordar_postulados import RecordarPostuladosSinRevisar
from app.config import settings
from app.database import db_session
from app.infrastructure.recordatorios import SqlRepositorioDeRecordatorios
from app.monitoring import logger
from app.workers.celery_app import celery_app
from app.workers.moderacion import correo


async def _recordar() -> dict[str, Any]:
    async with db_session() as db:
        caso = RecordarPostuladosSinRevisar(
            SqlRepositorioDeRecordatorios(db),
            correo(),
            panel_url=settings.panel_url,
            max_en_24_horas=settings.recordatorio_max_24h,
            umbral=settings.recordatorio_umbral,
            espera=timedelta(hours=settings.recordatorio_horas_de_espera),
        )
        resultado = asdict(await caso.ejecutar())
    if resultado["fallidos"]:
        logger.warning("postulados.recordatorio_fallido", **resultado)
    elif resultado["empresas"] or resultado["sin_cupo"] or resultado["sin_destinatarios"]:
        logger.info("postulados.recordatorio", **resultado)
    return resultado


@celery_app.task(name="postulados.recordar")
def recordar() -> dict[str, Any]:
    """Recuerda a cada empresa sus postulados sin revisar, si le toca."""
    if settings.recordatorio_max_24h == 0:
        return {"apagado": True}
    if not (settings.smtp_host and settings.smtp_remitente):
        logger.warning("postulados.sin_recordatorio", motivo="faltan SMTP_HOST o el remitente")
        return {"sin_smtp": True}
    return asyncio.run(_recordar())
