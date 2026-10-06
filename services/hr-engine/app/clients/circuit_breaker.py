"""Circuit breaker por proveedor de LLM, con el estado compartido en Redis.

Cuando un proveedor falla `umbral` veces dentro de `ventana_s`, el circuito se
abre durante `enfriamiento_s`: nadie lo llama y se va directo al respaldo, en vez
de que cada tarea espere sus timeouts y reintentos. Al expirar, se deja pasar
tráfico otra vez; si vuelve a fallar en ese periodo de prueba, se reabre al
primer fallo.

El estado vive en Redis porque los workers de Celery son varios procesos: un
breaker en memoria abriría el circuito en un proceso y no en los demás.

Si Redis no responde, el breaker se comporta como cerrado (deja pasar): perder
el breaker no puede tumbar la evaluación.
"""

from __future__ import annotations

from contextlib import suppress
from functools import cache

import redis
import sentry_sdk

from app.config import settings
from app.monitoring import logger


@cache
def _redis() -> redis.Redis:
    # Cliente síncrono a propósito: no está atado a ningún event loop, y estas
    # operaciones duran milisegundos.
    return redis.Redis.from_url(
        settings.redis_url,
        socket_timeout=0.25,
        socket_connect_timeout=0.25,
    )


class CircuitBreaker:
    def __init__(
        self,
        proveedor: str,
        *,
        umbral: int | None = None,
        ventana_s: int | None = None,
        enfriamiento_s: int | None = None,
    ) -> None:
        self.proveedor = proveedor
        self.umbral = umbral or settings.llm_breaker_umbral
        self.ventana_s = ventana_s or settings.llm_breaker_ventana_s
        self.enfriamiento_s = enfriamiento_s or settings.llm_breaker_enfriamiento_s
        base = f"llm:breaker:{proveedor}"
        self._k_abierto = f"{base}:abierto"
        self._k_fallos = f"{base}:fallos"
        self._k_prueba = f"{base}:en_prueba"

    def abierto(self) -> bool:
        try:
            return bool(_redis().exists(self._k_abierto))
        except redis.RedisError as exc:
            logger.warning(
                "llm.breaker.redis_down", proveedor=self.proveedor, error_type=type(exc).__name__
            )
            return False

    def registrar_exito(self) -> None:
        with suppress(redis.RedisError):
            _redis().delete(self._k_fallos, self._k_prueba)

    def registrar_fallo(self) -> None:
        try:
            r = _redis()
            if r.exists(self._k_prueba):
                self._abrir(r, motivo="falló durante el periodo de prueba")
                return
            fallos = r.incr(self._k_fallos)
            if fallos == 1:
                r.expire(self._k_fallos, self.ventana_s)
            if fallos >= self.umbral:
                self._abrir(r, motivo=f"{fallos} fallos en {self.ventana_s}s")
        except redis.RedisError as exc:
            logger.warning(
                "llm.breaker.redis_down", proveedor=self.proveedor, error_type=type(exc).__name__
            )

    def _abrir(self, r: redis.Redis, *, motivo: str) -> None:
        r.set(self._k_abierto, "1", ex=self.enfriamiento_s)
        # Al expirar `abierto`, `en_prueba` sigue vivo otro enfriamiento: un fallo ahí reabre.
        r.set(self._k_prueba, "1", ex=self.enfriamiento_s * 2)
        r.delete(self._k_fallos)
        logger.error(
            "llm.circuit_opened",
            proveedor=self.proveedor,
            motivo=motivo,
            enfriamiento_s=self.enfriamiento_s,
        )
        # Alerta: sin esto, una caída se descubre por un cliente. No-op si Sentry no está configurado.
        sentry_sdk.capture_message(
            f"Circuito abierto para el LLM '{self.proveedor}': {motivo}",
            level="error",
        )


def reset_redis_cache() -> None:
    _redis.cache_clear()
