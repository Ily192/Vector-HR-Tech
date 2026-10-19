"""Planes de Vortex y sus límites (ADR-017).

El career site es el único módulo gratuito. A cambio de registrarse, la empresa
publica vacantes sin costo, con tres límites:

- Vacantes activas: 3 hasta 50 personas y 4 desde 51 (3 si no se sabe el tamaño).
  Vector HR puede fijar otro número para una empresa concreta.
- Publicaciones: en 30 días, tantas vacantes nuevas como vacantes activas.
  Reabrir una vacante no cuenta.
- Aplicaciones: 50 recibidas por vacante. Borrar o descartar no libera cupo.
- Pipeline: solo la etapa "Aplicados". Las demás son de los servicios de IA.

El plan con IA no tiene estos topes. Y la IA es lo que se paga (ADR-019): para
una empresa gratuita no corre ningún agente ni se llama a ningún LLM. Su gancho
es una coincidencia de skills sin IA (`domain/coincidencia.py`).

La base aplica la misma regla (migraciones 0008 y 0010), porque el panel y el
career site escriben en Supabase sin pasar por el hr-engine. El contrato
`packages/types/contracts/limites-plan.json` mantiene alineadas las tres copias.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast, get_args

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
#: Las publicaciones nuevas se cuentan en una ventana móvil de estos días.
VENTANA_DE_PUBLICACIONES_DIAS = 30


class LimiteDeVacantesError(RuntimeError):
    """La empresa ya tiene todas las vacantes activas que permite su plan."""


class LimiteDePublicacionesError(RuntimeError):
    """La empresa ya publicó en la ventana todas las vacantes nuevas que permite su plan."""


class CupoDeAplicacionesLlenoError(RuntimeError):
    """La vacante llegó al máximo de aplicaciones de su plan."""


class PlanSinIAError(RuntimeError):
    """La empresa no tiene el plan con IA: para ella no corre ningún agente."""


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
    #: Agentes y LLM: evaluación, búsqueda de perfiles. Lo que se paga.
    incluye_ia: bool
    modulos: tuple[Modulo, ...]
    etapas_visibles: tuple[Etapa, ...]
    vacantes_activas: int | None
    #: Vacantes nuevas en `VENTANA_DE_PUBLICACIONES_DIAS`. En el gratis, las mismas que activas.
    publicaciones_por_ventana: int | None
    aplicaciones_por_vacante: int | None

    def verificar_publicacion(self, activas: int) -> None:
        """Lanza `LimiteDeVacantesError` si publicar una vacante más se pasa del tope."""
        if self.vacantes_activas is not None and activas >= self.vacantes_activas:
            raise LimiteDeVacantesError(
                f"{activas} de {self.vacantes_activas} vacantes activas: elimina una para publicar otra"
            )

    def verificar_publicacion_nueva(self, recientes: int) -> None:
        """Lanza `LimiteDePublicacionesError` si ya publicó todas las de la ventana.

        `recientes` son las vacantes publicadas por primera vez en los últimos
        `VENTANA_DE_PUBLICACIONES_DIAS` días. Reabrir una vacante no llama a esto.
        """
        if (
            self.publicaciones_por_ventana is not None
            and recientes >= self.publicaciones_por_ventana
        ):
            raise LimiteDePublicacionesError(
                f"{recientes} de {self.publicaciones_por_ventana} vacantes publicadas en los "
                f"últimos {VENTANA_DE_PUBLICACIONES_DIAS} días"
            )

    def verificar_aplicacion(self, aplicaciones: int) -> None:
        """Lanza `CupoDeAplicacionesLlenoError` si la vacante ya no recibe aplicaciones.

        `aplicaciones` son las recibidas desde que se publicó, no las que quedan.
        """
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
            incluye_ia=True,
            modulos=("career-site", "cockpit"),
            etapas_visibles=ETAPAS_DEL_PIPELINE,
            vacantes_activas=None,
            publicaciones_por_ventana=None,
            aplicaciones_por_vacante=None,
        )
    return LimitesDelPlan(
        plan="gratis",
        incluye_ia=False,
        modulos=("career-site",),
        etapas_visibles=("applied",),
        vacantes_activas=limite_de_vacantes(tamano, ajuste),
        publicaciones_por_ventana=limite_de_vacantes(tamano, ajuste),
        aplicaciones_por_vacante=MAX_APLICACIONES_GRATIS,
    )


def verificar_ia(plan: str | None) -> None:
    """Lanza `PlanSinIAError` si el plan de la empresa no incluye los servicios de IA.

    `plan` llega de la base tal cual; `None` es una empresa que no existe.
    """
    if plan not in get_args(Plan) or not limites_del_plan(cast(Plan, plan)).incluye_ia:
        raise PlanSinIAError(
            f"el plan {plan} no incluye los servicios de IA"
            if plan
            else "la empresa no existe o no tiene plan"
        )
