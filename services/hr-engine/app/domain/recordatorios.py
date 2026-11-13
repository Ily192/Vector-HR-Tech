"""El recordatorio de postulados sin revisar (ADR-023, migración 0020).

Ilyra lo pidió así: "solo cuando ya tengan más de 5 postulados a sus ofertas y que
llegue un aviso cuando realmente se necesite avisarle a la persona si no ha
revisado el panel y recordarle los postulados". La regla:

- Cuenta como **sin revisar** lo que llegó a una vacante abierta después de la
  última vez que la empresa abrió sus postulaciones y después del último
  recordatorio. Se suman todas las vacantes de la empresa.
- Con **más de `UMBRAL_DE_POSTULADOS`**, el recordatorio sale `ESPERA` después de
  que llegó el que cruzó el umbral, si la empresa sigue sin entrar a verlos.
- **Uno solo:** después de un recordatorio no sale otro hasta que la empresa abra
  sus postulaciones y se junten otros más de 5.

Nunca un correo por postulación ni al candidato. El correo no lleva datos de
candidatos: cuántos hay, en qué vacantes y el enlace al panel.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

#: "Más de 5": el recordatorio pide al menos 6 sin revisar.
UMBRAL_DE_POSTULADOS = 5
#: Lo que se espera desde que llegó el sexto antes de recordarlo.
ESPERA = timedelta(hours=24)
#: Las vacantes que se nombran en el correo; las demás van como "y N más".
MAX_VACANTES_EN_EL_CORREO = 10


@dataclass(frozen=True, slots=True)
class VacanteConPostulados:
    titulo: str
    postulados: int


@dataclass(frozen=True, slots=True)
class PostuladosSinRevisar:
    """Lo que tiene sin revisar una empresa, como lo cuenta la base."""

    empresa_id: UUID
    empresa: str
    postulados: int
    #: Cuándo llegó el que cruzó el umbral (el sexto). `None` si no lo cruzó.
    cruzo_el_umbral_en: datetime | None
    #: El último recordatorio que se le mandó.
    recordado_en: datetime | None
    #: La última vez que abrió las postulaciones de alguna de sus vacantes.
    visto_en: datetime | None
    vacantes: tuple[VacanteConPostulados, ...]
    #: HR y Dirección de la empresa con el correo confirmado.
    destinatarios: tuple[str, ...]


def toca_recordar(
    e: PostuladosSinRevisar,
    ahora: datetime,
    *,
    umbral: int = UMBRAL_DE_POSTULADOS,
    espera: timedelta = ESPERA,
) -> bool:
    """Si a esta empresa le toca el recordatorio ahora."""
    if e.postulados <= umbral or e.cruzo_el_umbral_en is None:
        return False
    # Ya se le recordó y no ha vuelto a entrar: no se repite.
    if e.recordado_en is not None and (e.visto_en is None or e.visto_en <= e.recordado_en):
        return False
    return ahora - e.cruzo_el_umbral_en >= espera


def armar_recordatorio(
    e: PostuladosSinRevisar, panel_url: str, *, umbral: int = UMBRAL_DE_POSTULADOS
) -> tuple[str, str]:
    """El asunto y el texto del correo. Sin nombres ni datos de candidatos."""
    asunto = f"Tienes {e.postulados} postulados sin revisar"
    nombradas = e.vacantes[:MAX_VACANTES_EN_EL_CORREO]
    lineas = [
        f"- {v.titulo}: {v.postulados} {'postulado' if v.postulados == 1 else 'postulados'}"
        for v in nombradas
    ]
    resto = len(e.vacantes) - len(nombradas)
    if resto > 0:
        lineas.append(f"- Y {resto} {'vacante' if resto == 1 else 'vacantes'} más.")
    texto = "\n".join(
        [
            "Hola:",
            "",
            f"{e.empresa} tiene {e.postulados} postulados que todavía no revisas:",
            "",
            *lineas,
            "",
            f"Entra a tu panel para verlos: {panel_url.rstrip('/')}",
            "",
            "Este aviso llega una sola vez. El siguiente sale solo si, después de que "
            f"entres, se juntan más de {umbral} postulados nuevos.",
            "",
            "Vector HR Tech",
        ]
    )
    return asunto, texto


# ─────────────────────────────── puertos ───────────────────────────────


class RepositorioDeRecordatorios(Protocol):
    async def con_postulados_sin_revisar(
        self, umbral: int, limite: int
    ) -> Sequence[PostuladosSinRevisar]:
        """Las empresas con más de `umbral` sin revisar, la que cruzó antes primero."""
        ...

    async def enviados_en_24_horas(self) -> int:
        """Cuántos correos de recordatorio salieron en las últimas 24 horas."""
        ...

    async def registrar(self, empresa_id: UUID, *, postulados: int, destinatarios: int) -> None: ...
