"""Casos de uso de la moderación de vacantes (ADR-022).

- `ModerarVacantesPendientes`: el barrido de cada minuto. Pasa cada vacante
  'pendiente' por las reglas (y por un revisor externo, si hay) y guarda la
  decisión. Una empresa verificada sin señales de riesgo queda publicada en el
  siguiente barrido.
- `AvisarColaDeRevision`: el resumen de la cola a hola@. Como mucho uno cada
  `horas_entre_resumenes`, salvo que haya una vacante oculta por reportes, y con
  un tope diario: Resend gratis da 100 correos al día y los comparte con los
  códigos de acceso de Auth.
- `ResolverRevision`: lo que hace una persona de Vector HR desde la página de
  revisión o la CLI: aprobar o rechazar con motivo.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.domain.moderacion import (
    EstadoDeModeracion,
    Gravedad,
    Marca,
    RepositorioDeModeracion,
    RevisorDeVacantes,
    ServicioDeCorreo,
    VacanteEnCola,
    decidir,
    evaluar,
)

# ─────────────────────────────── el barrido ───────────────────────────────


@dataclass
class ResultadoDeLaModeracion:
    publicadas: int = 0
    en_revision: int = 0
    rechazadas: int = 0
    #: La vacante cambió (la editaron o la cerraron) entre leerla y guardarla.
    descartadas: int = 0
    #: El revisor externo falló: la vacante espera al siguiente barrido.
    en_espera: int = 0


class ModerarVacantesPendientes:
    def __init__(
        self,
        repositorio: RepositorioDeModeracion,
        revisor: RevisorDeVacantes | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._revisor = revisor

    async def ejecutar(self, *, lote: int) -> ResultadoDeLaModeracion:
        resultado = ResultadoDeLaModeracion()
        for vacante in await self._repositorio.pendientes(lote):
            extra: Sequence[Marca] = ()
            if self._revisor is not None:
                try:
                    extra = tuple(await self._revisor.revisar(vacante))
                except Exception:  # el revisor es opcional: no tumba el barrido
                    resultado.en_espera += 1
                    continue
            decision = decidir(vacante, evaluar(vacante, extra))
            if not await self._repositorio.guardar(vacante.id, decision):
                resultado.descartadas += 1
                continue
            match decision.estado:
                case EstadoDeModeracion.PUBLICADA:
                    resultado.publicadas += 1
                case EstadoDeModeracion.RECHAZADA:
                    resultado.rechazadas += 1
                case _:
                    resultado.en_revision += 1
        return resultado


# ─────────────────────────────── el resumen ───────────────────────────────

#: Con una vacante oculta por reportes se avisa antes, pero no más de una vez por este lapso.
ESPERA_URGENTE = timedelta(minutes=15)
#: Vacantes por resumen. Las demás van en el siguiente.
MAX_POR_RESUMEN = 30

_ESTADO = {
    EstadoDeModeracion.EN_REVISION: "En revisión",
    EstadoDeModeracion.OCULTA: "OCULTA POR REPORTES",
}


def armar_resumen(cola: Sequence[VacanteEnCola], enlace: Callable[[UUID], str]) -> str:
    """El texto del correo: cada vacante con sus motivos y su enlace firmado."""
    lineas = [
        f"Hay {len(cola)} {'vacante' if len(cola) == 1 else 'vacantes'} esperando revisión "
        "en el career site de Vector HR Tech.",
        "",
        "Cada enlace abre la vacante con sus motivos y los botones Aprobar y Rechazar. "
        "Vence en 7 días; quien lo tenga puede decidir, así que no lo reenvíes.",
    ]
    for v in cola:
        quien = (
            "reclutador(a) independiente"
            if v.publica_para == "clientes"
            else ("empresa verificada" if v.empresa_verificada else "empresa sin verificar")
        )
        lineas += ["", f"■ {v.titulo} · {v.empresa} ({quien}) · {_ESTADO.get(v.estado, '')}"]
        for m in v.motivos:
            cita = f" — «{m.cita}»" if m.cita else ""
            lineas.append(f"  - {m.senal}{cita}")
        lineas.append(f"  Revisar: {enlace(v.id)}")
    lineas += ["", "— El hr-engine de Vector HR Tech (moderación de vacantes, ADR-022)"]
    return "\n".join(lineas)


class AvisarColaDeRevision:
    def __init__(
        self,
        repositorio: RepositorioDeModeracion,
        correo: ServicioDeCorreo,
        *,
        destino: str,
        enlace: Callable[[UUID], str],
        horas_entre_resumenes: float,
        max_en_24_horas: int,
        ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repositorio = repositorio
        self._correo = correo
        self._destino = destino
        self._enlace = enlace
        self._entre_resumenes = timedelta(hours=horas_entre_resumenes)
        self._max = max_en_24_horas
        self._ahora = ahora

    async def ejecutar(self) -> int:
        """Manda el resumen si toca. Devuelve cuántas vacantes avisó."""
        cola = await self._repositorio.cola_sin_avisar(MAX_POR_RESUMEN)
        if not cola:
            return 0
        urgente = any(v.estado is EstadoDeModeracion.OCULTA for v in cola)
        avisos = await self._repositorio.avisos_recientes()
        if avisos.ultimas_24_horas >= self._max:
            return 0
        if avisos.ultimo is not None:
            espera = ESPERA_URGENTE if urgente else self._entre_resumenes
            if self._ahora() - avisos.ultimo < espera:
                return 0

        n = len(cola)
        asunto = (
            f"[Urgente] Vacante oculta por reportes · {n} en revisión"
            if urgente
            else f"{n} {'vacante espera' if n == 1 else 'vacantes esperan'} revisión"
        )
        await self._correo.enviar(
            para=self._destino, asunto=asunto, texto=armar_resumen(cola, self._enlace)
        )
        await self._repositorio.marcar_avisadas([v.id for v in cola])
        await self._repositorio.registrar_aviso(urgente=urgente, vacantes=n)
        return n


# ─────────────────────────────── la revisión ───────────────────────────────

#: Desde dónde se aprueba: lo que espera a una persona, y lo rechazado (corregir un falso positivo).
_APROBABLES = (
    EstadoDeModeracion.EN_REVISION,
    EstadoDeModeracion.OCULTA,
    EstadoDeModeracion.RECHAZADA,
    EstadoDeModeracion.PENDIENTE,
)
#: Desde dónde se rechaza: también una publicada que alguien reportó por otra vía.
_RECHAZABLES = (
    EstadoDeModeracion.EN_REVISION,
    EstadoDeModeracion.OCULTA,
    EstadoDeModeracion.PENDIENTE,
    EstadoDeModeracion.PUBLICADA,
)
MAX_MOTIVO = 300


class MotivoVacioError(ValueError):
    """Rechazar exige decirle a la empresa por qué."""


class ResolverRevision:
    def __init__(self, repositorio: RepositorioDeModeracion) -> None:
        self._repositorio = repositorio

    async def aprobar(self, vacante_id: UUID) -> bool:
        return await self._repositorio.resolver(
            vacante_id, EstadoDeModeracion.PUBLICADA, None, _APROBABLES
        )

    async def rechazar(self, vacante_id: UUID, motivo: str) -> bool:
        texto = " ".join(motivo.split())[:MAX_MOTIVO]
        if not texto:
            raise MotivoVacioError("el rechazo necesita un motivo")
        marca = Marca(
            regla="revision",
            senal=f"Vector HR la revisó y no la publicó: {texto}",
            gravedad=Gravedad.ALTA,
            corregir=texto,
        )
        return await self._repositorio.resolver(
            vacante_id, EstadoDeModeracion.RECHAZADA, marca, _RECHAZABLES
        )


__all__ = [
    "AvisarColaDeRevision",
    "ModerarVacantesPendientes",
    "MotivoVacioError",
    "ResolverRevision",
    "ResultadoDeLaModeracion",
    "armar_resumen",
]
