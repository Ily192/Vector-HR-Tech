"""Planes de Vortex y sus límites (ADR-017).

El career site es el único módulo gratuito. A cambio de registrarse, la empresa
publica vacantes sin costo, con tres límites:

- Vacantes activas: 3 hasta 50 personas y 4 desde 51 (3 si no se sabe el tamaño).
  Vector HR puede fijar otro número para una empresa concreta.
- Aplicaciones: 50 por vacante.
- Pipeline: solo la etapa "Aplicados". Las demás son de los servicios de IA.

El plan con IA no tiene estos topes.

La base aplica la misma regla (migración 0008), porque el panel y el career site
escriben en Supabase sin pasar por el hr-engine. El contrato
`packages/types/contracts/limites-plan.json` mantiene alineadas las tres copias.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Plan = Literal["gratis", "ia"]
Modulo = Literal["career-site", "cockpit"]
Etapa = Literal["applied", "evaluated", "shortlisted", "interviewed", "offered"]

#: Las etapas del embudo, en orden. Las de salida (contratado, descartado) van aparte.
ETAPAS_DEL_PIPELINE: tuple[Etapa, ...] = (
    "applied",
    "evaluated",
    "shortlisted",
    "interviewed",
    "offered",
)

MAX_APLICACIONES_GRATIS = 50
#: Desde este tamaño la empresa tiene una vacante activa más.
EMPLEADOS_EMPRESA_GRANDE = 51
LIMITE_VACANTES_EMPRESA_CHICA = 3
LIMITE_VACANTES_EMPRESA_GRANDE = 4


class LimiteDeVacantesError(RuntimeError):
    """La empresa ya tiene todas las vacantes activas que permite su plan."""


class CupoDeAplicacionesLlenoError(RuntimeError):
    """La vacante llegó al máximo de aplicaciones de su plan."""


def limite_de_vacantes(tamano: int | None, ajuste: int | None = None) -> int:
    """Vacantes activas del plan gratuito. `ajuste` es el número que fijó Vector HR."""
    if ajuste is not None:
        return ajuste
    if tamano is not None and tamano >= EMPLEADOS_EMPRESA_GRANDE:
        return LIMITE_VACANTES_EMPRESA_GRANDE
    return LIMITE_VACANTES_EMPRESA_CHICA


@dataclass(frozen=True, slots=True)
class LimitesDelPlan:
    """Lo que el plan permite. `None` en un tope = sin tope."""

    plan: Plan
    modulos: tuple[Modulo, ...]
    etapas_visibles: tuple[Etapa, ...]
    vacantes_activas: int | None
    aplicaciones_por_vacante: int | None

    def verificar_publicacion(self, activas: int) -> None:
        """Lanza `LimiteDeVacantesError` si publicar una vacante más se pasa del tope."""
        if self.vacantes_activas is not None and activas >= self.vacantes_activas:
            raise LimiteDeVacantesError(
                f"{activas} de {self.vacantes_activas} vacantes activas: elimina una para publicar otra"
            )

    def verificar_aplicacion(self, aplicaciones: int) -> None:
        """Lanza `CupoDeAplicacionesLlenoError` si la vacante ya no recibe aplicaciones."""
        if (
            self.aplicaciones_por_vacante is not None
            and aplicaciones >= self.aplicaciones_por_vacante
        ):
            raise CupoDeAplicacionesLlenoError(
                f"la vacante tiene {aplicaciones} de {self.aplicaciones_por_vacante} aplicaciones"
            )


def limites_del_plan(
    plan: Plan, *, tamano: int | None = None, ajuste: int | None = None
) -> LimitesDelPlan:
    if plan == "ia":
        return LimitesDelPlan(
            plan="ia",
            modulos=("career-site", "cockpit"),
            etapas_visibles=ETAPAS_DEL_PIPELINE,
            vacantes_activas=None,
            aplicaciones_por_vacante=None,
        )
    return LimitesDelPlan(
        plan="gratis",
        modulos=("career-site",),
        etapas_visibles=("applied",),
        vacantes_activas=limite_de_vacantes(tamano, ajuste),
        aplicaciones_por_vacante=MAX_APLICACIONES_GRATIS,
    )
