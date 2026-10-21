"""Caso de uso: avisar a Vector HR de los diagnósticos gratuitos nuevos (migración 0017).

Cada barrido:

1. Reclama los pendientes, del más viejo al más nuevo.
2. Verifica Turnstile en los que aún no lo pasaron. El que no pasa queda descartado
   y no se avisa nunca. Si Turnstile no responde, ese espera al siguiente barrido.
   Sin verificador (sin secreto, como en local) todos pasan.
3. Manda un solo correo de resumen con los verificados: con detalle hasta el tope
   del día, y los demás en una línea. Todos quedan avisados.
4. Si el correo no sale, cada uno suma un intento; con `MAX_INTENTOS_AVISO` se deja
   de intentar, y el diagnóstico sigue en la base.

Sin servicio de correo (sin `SMTP_PASS`) solo verifica: los verificados esperan
al correo, y su token, que dura 300 s, ya no hace falta.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.diagnostico import LOTE_DE_AVISOS, Diagnostico, resumen
from app.domain.puertos import (
    CorreoNoEnviadoError,
    RepositorioDeDiagnosticos,
    ServicioDeCorreo,
    VerificadorHumano,
    VerificadorNoDisponibleError,
)


@dataclass(slots=True)
class ResultadoDelAviso:
    avisados: int = 0
    #: De los avisados, los que fueron solo en la línea final.
    sin_detalle: int = 0
    descartados: int = 0
    #: Turnstile no respondió: se reintentan en el siguiente barrido.
    en_espera: int = 0
    #: Verificados que no se avisaron: el correo falló o no está configurado.
    sin_avisar: int = 0


class AvisarDiagnosticos:
    def __init__(
        self,
        repositorio: RepositorioDeDiagnosticos,
        verificador: VerificadorHumano | None,
        correo: ServicioDeCorreo | None,
        *,
        para: str,
        max_por_dia: int,
    ) -> None:
        self._repositorio = repositorio
        self._verificador = verificador
        self._correo = correo
        self._para = para
        self._max_por_dia = max_por_dia

    async def ejecutar(self, *, lote: int = LOTE_DE_AVISOS) -> ResultadoDelAviso:
        resultado = ResultadoDelAviso()
        try:
            listos = await self._verificados(await self._repositorio.reclamar(lote), resultado)
            if listos:
                await self._avisar(listos, resultado)
        finally:
            await self._repositorio.confirmar()
        return resultado

    async def _verificados(
        self, pendientes: list[Diagnostico], resultado: ResultadoDelAviso
    ) -> list[Diagnostico]:
        listos: list[Diagnostico] = []
        for diagnostico in pendientes:
            if not diagnostico.verificado:
                if self._verificador is not None:
                    try:
                        humano = await self._verificador.verificar(
                            diagnostico.turnstile_token, diagnostico.ip
                        )
                    except VerificadorNoDisponibleError:
                        resultado.en_espera += 1
                        continue
                    if not humano:
                        await self._repositorio.descartar(diagnostico)
                        resultado.descartados += 1
                        continue
                await self._repositorio.marcar_verificado(diagnostico)
            listos.append(diagnostico)
        return listos

    async def _avisar(self, listos: list[Diagnostico], resultado: ResultadoDelAviso) -> None:
        if self._correo is None:
            resultado.sin_avisar = len(listos)
            return
        cupo = max(0, self._max_por_dia - await self._repositorio.avisados_hoy())
        detallados = listos[:cupo]
        correo = resumen(self._para, detallados, len(listos) - len(detallados))
        if correo is None:
            return
        try:
            await self._correo.enviar(correo)
        except CorreoNoEnviadoError:
            await self._repositorio.sumar_intento(listos)
            resultado.sin_avisar = len(listos)
            return
        await self._repositorio.marcar_avisados(listos)
        resultado.avisados = len(listos)
        resultado.sin_detalle = len(listos) - len(detallados)
