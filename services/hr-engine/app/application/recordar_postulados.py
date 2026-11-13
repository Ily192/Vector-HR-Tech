"""Caso de uso: recordar a la empresa sus postulados sin revisar (ADR-023).

`RecordarPostuladosSinRevisar` corre cada hora. Toma las empresas con más de 5
postulados sin revisar, decide con `toca_recordar` a cuáles les toca y les manda un
solo correo. Antes de cada empresa mira el tope diario: Resend gratis da 100 correos
al día y los comparte con los códigos de acceso de Auth, que van primero. Si no
alcanza, la empresa espera a la hora siguiente.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.domain.moderacion import ServicioDeCorreo
from app.domain.recordatorios import (
    ESPERA,
    UMBRAL_DE_POSTULADOS,
    RepositorioDeRecordatorios,
    armar_recordatorio,
    toca_recordar,
)

#: Empresas por pasada: de sobra para el volumen del plan gratis.
LOTE = 200


@dataclass(slots=True)
class ResultadoDelRecordatorio:
    #: Empresas a las que les salió el recordatorio.
    empresas: int = 0
    #: Correos enviados (una empresa puede tener varias personas de HR).
    correos: int = 0
    #: Les tocaba y no tienen a quién escribirle: nadie de HR con el correo confirmado.
    sin_destinatarios: int = 0
    #: Les tocaba y el tope diario no alcanzó: esperan a la hora siguiente.
    sin_cupo: int = 0
    #: Correos que el SMTP no aceptó, con el tipo de error.
    fallidos: list[str] = field(default_factory=list)


class RecordarPostuladosSinRevisar:
    def __init__(
        self,
        repositorio: RepositorioDeRecordatorios,
        correo: ServicioDeCorreo,
        *,
        panel_url: str,
        max_en_24_horas: int,
        umbral: int = UMBRAL_DE_POSTULADOS,
        espera: timedelta = ESPERA,
        ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repositorio = repositorio
        self._correo = correo
        self._panel_url = panel_url
        self._max = max_en_24_horas
        self._umbral = umbral
        self._espera = espera
        self._ahora = ahora

    async def ejecutar(self, lote: int = LOTE) -> ResultadoDelRecordatorio:
        resultado = ResultadoDelRecordatorio()
        cupo = self._max - await self._repositorio.enviados_en_24_horas()
        ahora = self._ahora()
        for empresa in await self._repositorio.con_postulados_sin_revisar(self._umbral, lote):
            if not toca_recordar(empresa, ahora, umbral=self._umbral, espera=self._espera):
                continue
            if not empresa.destinatarios:
                resultado.sin_destinatarios += 1
                continue
            if len(empresa.destinatarios) > cupo:
                resultado.sin_cupo += 1
                continue

            asunto, texto = armar_recordatorio(empresa, self._panel_url, umbral=self._umbral)
            enviados = 0
            for para in empresa.destinatarios:
                try:
                    await self._correo.enviar(para=para, asunto=asunto, texto=texto)
                except Exception as error:  # el SMTP falla por persona: las demás siguen
                    resultado.fallidos.append(type(error).__name__)
                    continue
                enviados += 1
            if enviados == 0:
                # Nadie lo recibió: se intenta otra vez en la siguiente pasada.
                continue
            # Con que una persona lo reciba, la empresa ya quedó avisada: no se repite.
            await self._repositorio.registrar(
                empresa.empresa_id, postulados=empresa.postulados, destinatarios=enviados
            )
            cupo -= enviados
            resultado.empresas += 1
            resultado.correos += enviados
        return resultado
