"""Caso de uso: medir al evaluador de CVs con un set de casos (ADR-021 §9).

Cada CV recorre el camino de producción: se anonimiza con el nombre y el correo del
candidato y se evalúa contra el perfil de su vacante. Cada evaluación se repite,
porque el modelo no es determinista, y en paralelo, porque es solo espera de red.

- `acierto` compara la media con el score que puso una persona.
- `sesgo` evalúa cada CV con los dos valores de cada eje (género, edad, origen).

Una respuesta inválida cuenta como error de esa repetición y no entra en la media.
Si el modelo no está disponible no hay nada que medir: se corta todo.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Sequence

from app.domain.anonimizacion import CvAnonimo, anonimizar
from app.domain.entidades import ResultadoScoring
from app.domain.evals import (
    EJES,
    Acierto,
    CasoDeEval,
    Medicion,
    ParContrafactual,
    ResumenDeAcierto,
    con_marcador,
)
from app.domain.puertos import EvaluadorDeCvs, ProveedorNoDisponibleError


class MedirElEvaluador:
    def __init__(
        self, evaluador: EvaluadorDeCvs, *, repeticiones: int = 3, en_paralelo: int = 8
    ) -> None:
        if repeticiones < 1:
            raise ValueError("hace falta al menos una repetición")
        self._evaluador = evaluador
        self._repeticiones = repeticiones
        self._semaforo = asyncio.Semaphore(en_paralelo)
        self._sin_modelo: ProveedorNoDisponibleError | None = None
        #: Lo que costaron las evaluaciones hasta ahora.
        self.costo_usd = 0.0
        #: Cuántas veces se llamó al modelo.
        self.evaluaciones = 0
        #: Los modelos que respondieron: con el respaldo puede haber dos.
        self.modelos: set[str] = set()

    async def acierto(self, casos: Sequence[CasoDeEval]) -> ResumenDeAcierto:
        """Solo los casos con score esperado."""
        con_esperado = [(c, c.esperado) for c in casos if c.esperado is not None]
        mediciones = await _todas([self._medir(c, c.texto) for c, _ in con_esperado])
        return ResumenDeAcierto(
            tuple(
                Acierto(caso=c.id, esperado=esperado, medicion=m)
                for (c, esperado), m in zip(con_esperado, mediciones, strict=True)
            )
        )

    async def sesgo(
        self, casos: Sequence[CasoDeEval], ejes: Sequence[str] = tuple(EJES)
    ) -> tuple[ParContrafactual, ...]:
        async def par(caso: CasoDeEval, eje: str) -> ParContrafactual:
            uno, otro = EJES[eje]
            a, b = await _todas(
                [
                    self._medir(caso, con_marcador(caso.texto, uno)),
                    self._medir(caso, con_marcador(caso.texto, otro)),
                ]
            )
            return ParContrafactual(
                caso=caso.id, eje=eje, valores=(uno.valor, otro.valor), a=a, b=b
            )

        return tuple(await _todas([par(c, e) for c in casos for e in ejes]))

    async def _medir(self, caso: CasoDeEval, texto: str) -> Medicion:
        cv = anonimizar(texto, nombre=caso.nombre, correo=caso.correo)
        perfil = caso.vacante.perfil()
        resultados = await _todas([self._una(cv, perfil) for _ in range(self._repeticiones)])
        scores = tuple(r.fit.score for r in resultados if r is not None)
        return Medicion(scores=scores, errores=len(resultados) - len(scores))

    async def _una(self, cv: CvAnonimo, perfil: str) -> ResultadoScoring | None:
        async with self._semaforo:
            # Si el modelo ya no estaba disponible, no se gasta otra llamada en saberlo.
            if self._sin_modelo is not None:
                raise self._sin_modelo
            try:
                resultado = await self._evaluador.evaluar(cv, perfil)
            except ProveedorNoDisponibleError as exc:
                self._sin_modelo = exc
                raise
            except Exception:
                self.evaluaciones += 1
                return None
            self.evaluaciones += 1
            self.costo_usd += resultado.cost_usd
            self.modelos.add(resultado.model)
            return resultado


async def _todas[T](tareas: list[Awaitable[T]]) -> list[T]:
    """Como `gather`, pero espera a todas antes de relanzar el primer error: así ninguna
    queda corriendo ni con su excepción sin leer."""
    resultados = await asyncio.gather(*tareas, return_exceptions=True)
    errores = [r for r in resultados if isinstance(r, BaseException)]
    if errores:
        raise errores[0]
    return [r for r in resultados if not isinstance(r, BaseException)]
