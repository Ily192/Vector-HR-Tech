"""Un worker de Celery abre un event loop por tarea. El motor tiene que aguantarlo.

Cada tarea de Celery corre `asyncio.run(_run(...))`: abre un event loop, trabaja
y lo cierra. Un `AsyncEngine` con pool se guarda las conexiones entre tareas,
pero una conexión asyncpg está atada al loop en el que nació; cuando la tarea
siguiente la saca del pool, el loop original ya está cerrado y la conexión no
sirve.

La documentación oficial de SQLAlchemy lo dice en «Using multiple asyncio event
loops»: si el mismo motor se comparte entre loops, hay que configurarlo con
`NullPool` para que no reutilice ninguna conexión.
https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-multiple-asyncio-event-loops

Esto es un test de integración de verdad: necesita Postgres. No se salta si no
hay base — si no arranca, falla, porque un guard que se salta solo no guarda
nada.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app import database

pytestmark = pytest.mark.integration

#: Cuatro tareas seguidas: con pool, las que reciben una conexión reciclada de
#: un loop ya cerrado revientan. Con NullPool, las cuatro pasan.
_TAREAS = 4


def _tarea_de_worker() -> int:
    """Imita lo que hace una tarea de Celery: su propio `asyncio.run`."""

    async def _trabajo() -> int:
        async with database.db_session() as db:
            return int((await db.execute(text("select 1"))).scalar_one())

    return asyncio.run(_trabajo())


def test_varias_tareas_seguidas_no_se_pisan_el_event_loop() -> None:
    resultados = [_tarea_de_worker() for _ in range(_TAREAS)]
    assert resultados == [1] * _TAREAS


def test_el_motor_de_los_workers_no_guarda_conexiones() -> None:
    assert isinstance(database._worker_engine.pool, NullPool)


def test_la_api_si_mantiene_su_pool() -> None:
    """El arreglo no debe quitarle el pool a la API, que vive en un solo loop."""
    assert not isinstance(database._api_engine.pool, NullPool)
