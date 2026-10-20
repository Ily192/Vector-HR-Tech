"""Entidades y valores de la evaluación candidato↔vacante.

Son las reglas que hoy están repartidas entre el worker, el cliente de scoring y
el prompt, escritas una sola vez y sin dependencias de infraestructura:

- El modelo nunca ve el nombre del candidato (evaluación a ciegas, #38): lo
  único que sale hacia él es un `PerfilAnonimo`, que no tiene campo para el nombre.
- El texto del embedding tampoco lleva el nombre: el vector decide a quién
  encuentra el sourcer, y el nombre no dice nada del perfil.
- Sin ICP escrito, la vacante se evalúa contra su descripción del puesto.
- Un `FitScore` fuera de rango no existe, y su siguiente paso lo decide la
  política de `siguiente_paso`, no el modelo.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.siguiente_paso import SiguientePaso, siguiente_paso

#: Escala del score, la del SKILL.md de cv-evaluator.
SCORE_MIN = 0.0
SCORE_MAX = 10.0
#: Mínimo del razonamiento, el mismo que el contrato
#: (`packages/types/contracts/cv-evaluation.json`).
MIN_RATIONALE = 10


@dataclass(frozen=True, slots=True)
class PerfilAnonimo:
    """Lo que el modelo sabe del candidato. No tiene campo para el nombre, a propósito."""

    headline: str | None
    summary: str | None


@dataclass(frozen=True, slots=True)
class Candidato:
    id: UUID
    full_name: str
    headline: str | None
    summary: str | None
    tiene_embedding: bool

    def perfil_anonimo(self) -> PerfilAnonimo:
        return PerfilAnonimo(headline=self.headline, summary=self.summary)

    def texto_para_embedding(self) -> str:
        """Titular y resumen, sin el nombre. Vacío si el candidato no tiene ninguno."""
        return "\n".join(p for p in (self.headline, self.summary) if p)


@dataclass(frozen=True, slots=True)
class Vacante:
    id: UUID
    empresa_id: UUID
    title: str
    jd: str
    icp_text: str | None
    tiene_embedding: bool

    @property
    def icp(self) -> str:
        """El perfil ideal contra el que se evalúa: el ICP escrito o, si no hay, la descripción."""
        return self.icp_text or self.jd


@dataclass(frozen=True, slots=True)
class FitScore:
    score: float
    rationale: str
    gaps: tuple[str, ...] = ()
    strengths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Escrito así para que un NaN también quede fuera.
        if not SCORE_MIN <= self.score <= SCORE_MAX:
            raise ValueError(f"score fuera de [{SCORE_MIN}, {SCORE_MAX}]: {self.score}")
        if len(self.rationale) < MIN_RATIONALE:
            raise ValueError(f"el razonamiento necesita al menos {MIN_RATIONALE} caracteres")

    @property
    def siguiente_paso(self) -> SiguientePaso:
        return siguiente_paso(self.score)


@dataclass(frozen=True, slots=True)
class Embedding:
    vector: tuple[float, ...]
    cost_usd: float
    model: str


@dataclass(frozen=True, slots=True)
class ResultadoScoring:
    fit: FitScore
    cost_usd: float
    model: str


@dataclass(frozen=True, slots=True)
class CvPendiente:
    """Un CV del plan gratis sin coincidencia con las skills que su vacante pide hoy (ADR-019)."""

    application_id: UUID
    empresa_id: UUID
    #: Dónde está en el bucket `cvs`: `{empresa_id}/...` (migración 0005).
    ruta: str
    skills: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VacanteParaEvaluar:
    """Lo que el modelo sabe de la vacante. Sin el nombre de la empresa (ADR-021 §3)."""

    titulo: str
    descripcion: str
    skills: tuple[str, ...]
    nivel: str | None
    modalidad: str | None
    ubicacion: str | None
    icp_text: str | None

    def perfil(self) -> str:
        """El perfil contra el que se evalúa el CV, en texto."""
        lineas = [f"Puesto: {self.titulo}"]
        for etiqueta, valor in (
            ("Nivel", self.nivel),
            ("Modalidad", self.modalidad),
            ("Ubicación", self.ubicacion),
        ):
            if valor:
                lineas.append(f"{etiqueta}: {valor}")
        if self.skills:
            lineas.append(f"Skills que pide: {', '.join(self.skills)}")
        lineas += ["", "Descripción:", self.descripcion]
        if self.icp_text:
            lineas += ["", "Perfil ideal (ICP):", self.icp_text]
        return "\n".join(lineas)


@dataclass(frozen=True, slots=True)
class AplicacionPorEvaluar:
    """Una aplicación de una empresa con IA, reclamada por el barrido (ADR-021)."""

    application_id: UUID
    empresa_id: UUID
    #: El plan al reclamarla: se vuelve a comprobar antes de gastar.
    plan: str
    #: Dónde está el CV en el bucket `cvs`.
    ruta: str
    #: Solo para quitarlos del texto del CV: nunca llegan al modelo.
    nombre: str
    correo: str | None
    vacante: VacanteParaEvaluar
