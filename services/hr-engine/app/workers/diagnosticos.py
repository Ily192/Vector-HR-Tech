"""Tarea del aviso de los diagnósticos gratuitos de vectorhrtech.com (migración 0017).

`diagnosticos.avisar` corre cada minuto con Celery beat: el token de Turnstile dura
300 s y se verifica aquí. No es un run de agente: no lleva run-token, no deja fila
en `runs` y no llama a ningún LLM. La lógica está en `AvisarDiagnosticos`.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict

import httpx

from app.application.avisar_diagnosticos import AvisarDiagnosticos
from app.config import settings
from app.database import db_session
from app.infrastructure.diagnosticos import (
    CorreoSmtp,
    SqlRepositorioDeDiagnosticos,
    TurnstileCloudflare,
)
from app.monitoring import logger
from app.workers.celery_app import celery_app

#: Lo que espera la respuesta de Turnstile antes de dejar el diagnóstico para el
#: siguiente barrido.
TIMEOUT_DE_TURNSTILE_S = 10.0
#: Lo que espera cada paso del SMTP. Con 20 diagnósticos por barrido cabe holgado en
#: el `task_soft_time_limit`.
TIMEOUT_DE_SMTP_S = 30.0


def _correo() -> CorreoSmtp | None:
    if not settings.smtp_pass:
        logger.warning("diagnosticos.sin_smtp", motivo="falta SMTP_PASS; no se avisa")
        return None
    if not settings.smtp_remitente:
        logger.warning("diagnosticos.sin_smtp", motivo="falta SMTP_ADMIN_EMAIL; no se avisa")
        return None
    return CorreoSmtp(
        host=settings.smtp_host,
        puerto=settings.smtp_port,
        usuario=settings.smtp_user,
        clave=settings.smtp_pass,
        remitente=settings.smtp_remitente,
        starttls=settings.smtp_starttls,
        timeout_s=TIMEOUT_DE_SMTP_S,
    )


async def _avisar() -> dict[str, int]:
    async with (
        db_session() as db,
        httpx.AsyncClient(timeout=TIMEOUT_DE_TURNSTILE_S) as http,
    ):
        verificador = None
        if settings.turnstile_secret_key:
            verificador = TurnstileCloudflare(settings.turnstile_secret_key, http)
        else:
            logger.warning(
                "diagnosticos.sin_turnstile", motivo="falta TURNSTILE_SECRET_KEY; no se verifica"
            )
        caso = AvisarDiagnosticos(
            SqlRepositorioDeDiagnosticos(db),
            verificador,
            _correo(),
            para=settings.aviso_diagnosticos_para,
            max_por_dia=settings.aviso_diagnosticos_max_dia,
        )
        resultado = asdict(await caso.ejecutar())
    logger.info("diagnosticos.barrido", **resultado)
    return resultado


@celery_app.task(name="diagnosticos.avisar")
def avisar() -> dict[str, int]:
    """Verifica Turnstile y manda a Vector HR el resumen de los diagnósticos nuevos."""
    return asyncio.run(_avisar())
