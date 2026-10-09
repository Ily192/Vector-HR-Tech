"""Un cliente async por event loop.

Los workers de Celery hacen un `asyncio.run()` por tarea. Un cliente async
cacheado con `lru_cache` (AsyncOpenAI, el de google-genai) guarda conexiones
httpx atadas al loop en el que nacieron, y la tarea siguiente las recibe con
ese loop ya cerrado. Medido el 2026-10-06 contra un servidor local: con un
AsyncOpenAI cacheado, 1 de cada 2 tareas falla con APIConnectionError. Es el
mismo defecto que tenía el motor de SQLAlchemy (ver app/database.py), y
disfrazado de "proveedor caído" abriría el circuit breaker sin motivo.

`por_event_loop(fabrica)` devuelve una función que crea un cliente por loop y lo
reutiliza dentro de ese loop; cuando el loop muere, su entrada desaparece.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from weakref import WeakKeyDictionary


class por_event_loop[T]:  # noqa: N801 - se usa como decorador
    def __init__(self, fabrica: Callable[[], T]) -> None:
        self._fabrica = fabrica
        self._clientes: WeakKeyDictionary[asyncio.AbstractEventLoop, T] = WeakKeyDictionary()

    def __call__(self) -> T:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Sin loop (código síncrono, tests): no hay nada a lo que atarlo.
            return self._fabrica()
        cliente = self._clientes.get(loop)
        if cliente is None:
            cliente = self._fabrica()
            self._clientes[loop] = cliente
        return cliente

    def cache_clear(self) -> None:
        self._clientes.clear()
