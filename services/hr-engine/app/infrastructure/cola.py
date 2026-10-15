"""Encolado de tareas por nombre: la API no importa los workers.

Importar el módulo de un worker desde la API arrastraba al proceso web todo lo
que ese worker usa (SDK de LLM, adaptadores, la tarea de Celery). Por nombre,
la API solo necesita la app de Celery y el broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from celery.result import AsyncResult

from app.workers.celery_app import celery_app


@dataclass(frozen=True, slots=True)
class TareaPorNombre:
    nombre: str

    def delay(self, **kwargs: Any) -> AsyncResult[Any]:
        return celery_app.send_task(self.nombre, kwargs=kwargs)


#: Los nombres tienen que coincidir con los `@celery_app.task(name=...)`; lo comprueba un test.
cv_evaluator_task = TareaPorNombre("cv_evaluator.run")
sourcer_task = TareaPorNombre("sourcer.run")
