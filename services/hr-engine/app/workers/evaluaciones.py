"""Tarea de la evaluación con IA del plan de pago (ADR-021).

`evaluaciones.barrer` corre cada minuto con Celery beat. No lleva run-token: es un
trabajo interno del hr-engine, y cada evaluación deja su fila en `runs` con su
costo (ADR-005). La lógica está en `EvaluarAplicacionesPendientes`.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

import httpx

from app.application.evaluar_aplicaciones import EvaluarAplicacionesPendientes
from app.config import settings
from app.database import db_session
from app.infrastructure.coincidencias import AlmacenSupabase, ExtractorDeTextoDeCv
from app.infrastructure.evaluacion import LlmScoring
from app.infrastructure.evaluaciones import SqlRepositorioDeEvaluaciones
from app.monitoring import logger
from app.workers.celery_app import celery_app

#: Lo que espera la descarga de un CV antes de dejarlo para el siguiente barrido.
TIMEOUT_DE_STORAGE_S = 30.0


async def _barrer() -> dict[str, Any]:
    async with (
        db_session() as db,
        httpx.AsyncClient(timeout=TIMEOUT_DE_STORAGE_S) as http,
    ):
        caso = EvaluarAplicacionesPendientes(
            SqlRepositorioDeEvaluaciones(
                db, tope_por_evaluacion_usd=settings.default_run_cost_cap_usd
            ),
            AlmacenSupabase(settings.supabase_url, settings.supabase_secret_key, http),
            ExtractorDeTextoDeCv(),
            LlmScoring(),
            presupuesto_mensual_usd=settings.ia_presupuesto_mensual_usd,
            en_paralelo=settings.evaluaciones_en_paralelo,
        )
        resultado = asdict(await caso.ejecutar(lote=settings.evaluaciones_lote))
    if resultado["en_pausa"]:
        logger.warning(
            "evaluaciones.presupuesto_agotado",
            presupuesto_usd=settings.ia_presupuesto_mensual_usd,
        )
    logger.info("evaluaciones.barrido", **resultado)
    return resultado


@celery_app.task(name="evaluaciones.barrer")
def barrer() -> dict[str, Any]:
    """Evalúa con IA las aplicaciones pendientes de las empresas del plan de pago."""
    if not (settings.supabase_url and settings.supabase_secret_key):
        logger.warning("evaluaciones.sin_storage", motivo="faltan SUPABASE_URL o la clave secreta")
        return {}
    return asyncio.run(_barrer())
