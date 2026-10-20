"""Caso de uso: evaluar con IA las aplicaciones de las empresas del plan de pago (ADR-021).

Lo corre un barrido de Celery beat cada minuto, sin run-token:

1. Si el presupuesto del mes de la plataforma se acabó, no hace nada.
2. Reclama un lote de aplicaciones pendientes. Ya vienen solo de empresas con IA y
   bajo su tope del mes.
3. Baja cada CV, saca su texto y lo anonimiza. Lo ilegible se marca y no se manda.
4. Puntúa en paralelo: es solo espera de red.
5. Guarda cada resultado.

Lo que no se pudo puntuar espera al siguiente barrido:
- Si el modelo no estaba disponible (caído, sin key, con el circuito abierto), se
  suelta sin gastar su intento: no es culpa del CV.
- Si falló por otra causa, como una respuesta inválida, se aplaza y gasta un
  intento. Con `MAX_INTENTOS` queda "sin evaluar" para revisarla a mano.

El siguiente paso que se muestra lo decide la política del dominio, no el modelo,
y es una sugerencia: descartar sigue siendo de una persona (ADR-021 §4).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.domain.anonimizacion import CvAnonimo, anonimizar
from app.domain.coincidencia import es_legible
from app.domain.entidades import AplicacionPorEvaluar, ResultadoScoring
from app.domain.evaluacion_ia import presupuesto_agotado
from app.domain.plan import PlanSinIAError, verificar_ia
from app.domain.puertos import (
    AlmacenDeCvs,
    AlmacenNoDisponibleError,
    CvInaccesibleError,
    EvaluadorDeCvs,
    ExtractorDeTexto,
    ProveedorNoDisponibleError,
    RepositorioDeEvaluaciones,
)


@dataclass(slots=True)
class ResultadoDeLasEvaluaciones:
    evaluadas: int = 0
    ilegibles: int = 0
    #: Sin puntuar en este barrido (modelo caído, respuesta inválida, Storage sin
    #: responder): se reintentan en el siguiente.
    aplazadas: int = 0
    #: De las aplazadas, las que esperan porque el modelo no estaba disponible.
    sin_modelo: int = 0
    #: El presupuesto del mes de la plataforma se acabó y no se evaluó nada.
    en_pausa: bool = False
    costo_usd: float = 0.0


class EvaluarAplicacionesPendientes:
    def __init__(
        self,
        repositorio: RepositorioDeEvaluaciones,
        almacen: AlmacenDeCvs,
        extractor: ExtractorDeTexto,
        evaluador: EvaluadorDeCvs,
        *,
        presupuesto_mensual_usd: float,
        en_paralelo: int,
    ) -> None:
        self._repositorio = repositorio
        self._almacen = almacen
        self._extractor = extractor
        self._evaluador = evaluador
        self._presupuesto = presupuesto_mensual_usd
        self._en_paralelo = en_paralelo

    async def ejecutar(self, *, lote: int) -> ResultadoDeLasEvaluaciones:
        resultado = ResultadoDeLasEvaluaciones()
        if presupuesto_agotado(await self._repositorio.gastado_este_mes(), self._presupuesto):
            resultado.en_pausa = True
            return resultado

        listas = await self._leer(await self._repositorio.reclamar(lote), resultado)
        semaforo = asyncio.Semaphore(self._en_paralelo)

        async def puntuar(
            aplicacion: AplicacionPorEvaluar, cv: CvAnonimo
        ) -> ResultadoScoring | Exception:
            async with semaforo:
                try:
                    return await self._evaluador.evaluar(cv, aplicacion.vacante.perfil())
                except Exception as exc:
                    # Una respuesta inválida o un proveedor caído no tumban el lote: esa
                    # aplicación se aplaza y las demás siguen.
                    return exc

        puntuadas = await asyncio.gather(*(puntuar(a, cv) for a, cv in listas))
        for (aplicacion, _), puntuada in zip(listas, puntuadas, strict=True):
            if isinstance(puntuada, ProveedorNoDisponibleError):
                await self._repositorio.soltar(aplicacion)
                resultado.aplazadas += 1
                resultado.sin_modelo += 1
                continue
            if isinstance(puntuada, Exception):
                await self._repositorio.aplazar(aplicacion, motivo=type(puntuada).__name__)
                resultado.aplazadas += 1
                continue
            resultado.costo_usd += puntuada.cost_usd
            if await self._repositorio.guardar(aplicacion, puntuada):
                resultado.evaluadas += 1
        return resultado

    async def _leer(
        self, reclamadas: list[AplicacionPorEvaluar], resultado: ResultadoDeLasEvaluaciones
    ) -> list[tuple[AplicacionPorEvaluar, CvAnonimo]]:
        """El CV de cada una, anonimizado. Lo ilegible o de otro plan se queda fuera."""
        listas: list[tuple[AplicacionPorEvaluar, CvAnonimo]] = []
        for i, aplicacion in enumerate(reclamadas):
            try:
                verificar_ia(aplicacion.plan)
            except PlanSinIAError:
                await self._repositorio.soltar(aplicacion)
                continue
            try:
                contenido = await self._almacen.descargar(aplicacion.ruta)
            except CvInaccesibleError:
                await self._repositorio.marcar_ilegible(aplicacion)
                resultado.ilegibles += 1
                continue
            except AlmacenNoDisponibleError:
                for resto in reclamadas[i:]:
                    await self._repositorio.soltar(resto)
                resultado.aplazadas += len(reclamadas) - i
                break
            texto = self._extractor.extraer(contenido)
            if texto is None or not es_legible(texto):
                await self._repositorio.marcar_ilegible(aplicacion)
                resultado.ilegibles += 1
                continue
            listas.append(
                (aplicacion, anonimizar(texto, nombre=aplicacion.nombre, correo=aplicacion.correo))
            )
        return listas
