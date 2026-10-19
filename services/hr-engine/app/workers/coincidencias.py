"""Tareas de la coincidencia de skills del plan gratis (ADR-019). Sin IA.

`coincidencias.barrer` corre cada minuto con Celery beat y `coincidencias.purgar`
una vez al día. No son runs de agente: no llevan run-token, no dejan fila en
`runs` y no tienen tope de gasto, porque no llaman a ningún LLM (ADR-005,
actualización ADR-019). La lógica está en `CoincidirCvsPendientes`.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict

import httpx

from app.application.coincidir_cvs import CoincidirCvsPendientes
from app.config import settings
from app.database import db_session
from app.domain.gancho import DIAS_HASTA_LA_PURGA
from app.infrastructure.coincidencias import (
    AlmacenSupabase,
    ExtractorDeTextoDeCv,
    SqlRepositorioDeCoincidencias,
)
from app.monitoring import logger
from app.repositories import coincidencias as coincidencias_repo
from app.workers.celery_app import celery_app

#: Lo que espera la descarga de un CV antes de dejarlo para el siguiente barrido.
TIMEOUT_DE_STORAGE_S = 30.0


async def _barrer() -> dict[str, int]:
    async with (
        db_session() as db,
        httpx.AsyncClient(timeout=TIMEOUT_DE_STORAGE_S) as http,
    ):
        caso = CoincidirCvsPendientes(
            SqlRepositorioDeCoincidencias(db),
            AlmacenSupabase(settings.supabase_url, settings.supabase_secret_key, http),
            ExtractorDeTextoDeCv(),
        )
        resultado = asdict(await caso.ejecutar(lote=settings.coincidencias_lote))
    logger.info("coincidencias.barrido", **resultado)
    return resultado


@celery_app.task(name="coincidencias.barrer")
def barrer() -> dict[str, int]:
    """Compara con las skills de su vacante los CVs pendientes del plan gratis."""
    if not (settings.supabase_url and settings.supabase_secret_key):
        logger.warning("coincidencias.sin_storage", motivo="faltan SUPABASE_URL o la clave secreta")
        return {}
    return asyncio.run(_barrer())


async def _purgar() -> int:
    async with db_session() as db:
        borradas = await coincidencias_repo.purgar(db, dias=DIAS_HASTA_LA_PURGA)
        await db.commit()
    logger.info("coincidencias.purga", borradas=borradas)
    return borradas


@celery_app.task(name="coincidencias.purgar")
def purgar() -> int:
    """Borra las coincidencias de las vacantes cerradas hace más de 30 días."""
    return asyncio.run(_purgar())
