"""Tareas del alta desde la web (enmienda del 2026-11-12 a ADR-017).

`altas.limpiar` corre una vez al día con Celery beat: borra las empresas que se
registraron en vectorhrtech.com/publicar-vacantes y cuyo dueño nunca escribió el
código en 7 días, con su cuenta de Auth. No es un run de agente: no lleva
run-token ni llama a ningún LLM. La lógica está en `LimpiarAltasSinConfirmar`.

Antes de limpiar, `ConfirmarAltasDeLaWeb` (ADR-022) marca las confirmadas dándoles la
insignia: `moderacion.barrer` ya lo hace cada minuto, y aquí se repite para que la
limpieza nunca marque una confirmación sin haber pasado por la insignia.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict

import httpx

from app.application.alta_desde_la_web import LimpiarAltasSinConfirmar
from app.config import settings
from app.database import db_session
from app.infrastructure.altas_web import CodigosSupabase, SqlRepositorioDeAltasWeb
from app.monitoring import logger
from app.workers.celery_app import celery_app
from app.workers.moderacion import confirmar_altas

#: Lo que se espera a la API de administración de Auth por cada cuenta.
TIMEOUT_DE_AUTH_S = 30.0


async def _limpiar() -> dict[str, int]:
    async with db_session() as db, httpx.AsyncClient(timeout=TIMEOUT_DE_AUTH_S) as http:
        await confirmar_altas(db).ejecutar()
        caso = LimpiarAltasSinConfirmar(
            SqlRepositorioDeAltasWeb(db),
            CodigosSupabase(settings.supabase_url, settings.supabase_secret_key, http),
        )
        resultado = asdict(await caso.ejecutar())
    logger.info("altas.limpieza", **resultado)
    return resultado


@celery_app.task(name="altas.limpiar")
def limpiar() -> dict[str, int]:
    """Borra las altas de la web que nadie confirmó en 7 días."""
    if not (settings.supabase_url and settings.supabase_secret_key):
        logger.warning("altas.sin_auth", motivo="faltan SUPABASE_URL o la clave secreta")
        return {}
    return asyncio.run(_limpiar())
