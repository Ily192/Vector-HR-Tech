"""Caso de uso: comparar los CVs del plan gratis con las skills de su vacante (ADR-019).

Sin IA. Baja el CV, saca el texto y guarda qué skills menciona; la empresa solo
verá el resumen (`resumen_del_gancho()`).

- Lo que no se puede leer queda como ilegible y no se reintenta.
- Si Storage no responde, el resto del lote espera al siguiente barrido.
- Si la empresa cambió las skills mientras tanto, no se guarda: el siguiente
  barrido lo recalcula con las nuevas.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.coincidencia import coincidir, es_legible
from app.domain.puertos import (
    AlmacenDeCvs,
    AlmacenNoDisponibleError,
    CvInaccesibleError,
    ExtractorDeTexto,
    RepositorioDeCoincidencias,
)


@dataclass(slots=True)
class ResultadoDelBarrido:
    revisados: int = 0
    ilegibles: int = 0
    #: La vacante cambió sus skills mientras se leía el CV.
    descartados: int = 0
    #: Storage no respondió: se reintentan en el siguiente barrido.
    en_espera: int = 0


class CoincidirCvsPendientes:
    def __init__(
        self,
        repositorio: RepositorioDeCoincidencias,
        almacen: AlmacenDeCvs,
        extractor: ExtractorDeTexto,
    ) -> None:
        self._repositorio = repositorio
        self._almacen = almacen
        self._extractor = extractor

    async def ejecutar(self, *, lote: int) -> ResultadoDelBarrido:
        resultado = ResultadoDelBarrido()
        pendientes = await self._repositorio.pendientes(lote)
        for i, cv in enumerate(pendientes):
            # Se marca antes de leerlo. Si un PDF malicioso tumba el proceso, ese CV
            # queda ilegible y no vuelve a bloquear los barridos siguientes.
            await self._repositorio.marcar_ilegible(cv)
            try:
                contenido = await self._almacen.descargar(cv.ruta)
            except CvInaccesibleError:
                resultado.ilegibles += 1
                continue
            except AlmacenNoDisponibleError:
                await self._repositorio.desmarcar_ilegible(cv)
                resultado.en_espera += len(pendientes) - i
                break

            texto = self._extractor.extraer(contenido)
            if texto is None or not es_legible(texto):
                resultado.ilegibles += 1
                continue

            if await self._repositorio.guardar(cv, coincidir(texto, cv.skills).encontradas):
                resultado.revisados += 1
            else:
                await self._repositorio.desmarcar_ilegible(cv)
                resultado.descartados += 1
        return resultado
