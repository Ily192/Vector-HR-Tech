"""Adaptadores falsos de los puertos del dominio, para probar casos de uso sin base ni red.

Guardan lo que reciben, para que los tests comprueben qué salió hacia cada puerto.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.domain.anonimizacion import CvAnonimo
from app.domain.entidades import (
    AplicacionPorEvaluar,
    Candidato,
    CvPendiente,
    Embedding,
    FitScore,
    PerfilAnonimo,
    ResultadoScoring,
    Vacante,
)
from app.domain.puertos import (
    AlmacenNoDisponibleError,
    CvInaccesibleError,
    ProveedorNoDisponibleError,
)


@dataclass(frozen=True, slots=True)
class ApplicationGuardada:
    id: UUID
    empresa_id: UUID
    fit: FitScore


@dataclass
class RepositorioEnMemoria:
    """`CandidateRepository` sobre diccionarios: lo que no está se comporta como de otro tenant."""

    vacantes: dict[UUID, Vacante] = field(default_factory=dict)
    candidatos: dict[UUID, Candidato] = field(default_factory=dict)
    embeddings_vacante: dict[UUID, tuple[float, ...]] = field(default_factory=dict)
    embeddings_candidato: dict[UUID, tuple[float, ...]] = field(default_factory=dict)
    #: Por (vacante, candidato), como la clave única de `applications`.
    applications: dict[tuple[UUID, UUID], ApplicationGuardada] = field(default_factory=dict)

    async def get_vacante(self, vacante_id: UUID) -> Vacante | None:
        return self.vacantes.get(vacante_id)

    async def get_candidato(self, candidato_id: UUID) -> Candidato | None:
        return self.candidatos.get(candidato_id)

    async def update_vacante_embedding(self, vacante_id: UUID, vector: tuple[float, ...]) -> None:
        self.embeddings_vacante[vacante_id] = vector

    async def update_candidato_embedding(
        self, candidato_id: UUID, vector: tuple[float, ...]
    ) -> None:
        self.embeddings_candidato[candidato_id] = vector

    async def upsert_application(
        self, *, empresa_id: UUID, vacante_id: UUID, candidato_id: UUID, fit: FitScore
    ) -> UUID:
        previa = self.applications.get((vacante_id, candidato_id))
        guardada = ApplicationGuardada(
            id=previa.id if previa else uuid4(), empresa_id=empresa_id, fit=fit
        )
        self.applications[(vacante_id, candidato_id)] = guardada
        return guardada.id


@dataclass
class EmbeddingsFalsos:
    """`EmbeddingProvider` con un coste fijo por llamada. Con `disponible=False`, caído."""

    costo_usd: float = 0.00001
    disponible: bool = True
    textos: list[str] = field(default_factory=list)

    async def embed(self, texto: str) -> Embedding:
        self.textos.append(texto)
        if not self.disponible:
            raise ProveedorNoDisponibleError("proveedor de embeddings caído")
        return Embedding(
            vector=(0.0, 0.0, 0.0), cost_usd=self.costo_usd, model="text-embedding-3-small"
        )


@dataclass
class ScoringFalso:
    """`ScoringProvider` con una respuesta fija, o con `error` si se le pone uno."""

    fit: FitScore
    costo_usd: float = 0.0002
    model: str = "gemini-2.5-flash"
    error: Exception | None = None
    recibido: list[tuple[PerfilAnonimo, str]] = field(default_factory=list)

    async def score(self, perfil: PerfilAnonimo, icp: str) -> ResultadoScoring:
        self.recibido.append((perfil, icp))
        if self.error is not None:
            raise self.error
        return ResultadoScoring(fit=self.fit, cost_usd=self.costo_usd, model=self.model)


# ─── Coincidencia de skills del plan gratis (ADR-019) ────────────────────────


@dataclass
class RepositorioDeCoincidenciasEnMemoria:
    """`RepositorioDeCoincidencias` en memoria.

    `skills_de_hoy` simula que la empresa cambió las skills de la vacante mientras
    se leía el CV. `eventos` guarda el orden de las escrituras.
    """

    pendientes_: list[CvPendiente] = field(default_factory=list)
    skills_de_hoy: dict[UUID, tuple[str, ...]] = field(default_factory=dict)
    guardadas: dict[UUID, tuple[str, ...]] = field(default_factory=dict)
    ilegibles: set[UUID] = field(default_factory=set)
    eventos: list[tuple[str, UUID]] = field(default_factory=list)

    async def pendientes(self, limite: int) -> list[CvPendiente]:
        return self.pendientes_[:limite]

    async def guardar(self, cv: CvPendiente, encontradas: tuple[str, ...]) -> bool:
        if self.skills_de_hoy.get(cv.application_id, cv.skills) != cv.skills:
            return False
        self.guardadas[cv.application_id] = encontradas
        self.ilegibles.discard(cv.application_id)
        self.eventos.append(("guardar", cv.application_id))
        return True

    async def marcar_ilegible(self, cv: CvPendiente) -> None:
        self.ilegibles.add(cv.application_id)
        self.eventos.append(("marcar", cv.application_id))

    async def desmarcar_ilegible(self, cv: CvPendiente) -> None:
        self.ilegibles.discard(cv.application_id)
        self.eventos.append(("desmarcar", cv.application_id))


@dataclass
class AlmacenEnMemoria:
    """`AlmacenDeCvs` sobre un diccionario. `caido` simula Storage sin responder."""

    cvs: dict[str, bytes] = field(default_factory=dict)
    caido: bool = False
    descargas: list[str] = field(default_factory=list)

    async def descargar(self, ruta: str) -> bytes:
        self.descargas.append(ruta)
        if self.caido:
            raise AlmacenNoDisponibleError("Storage no responde")
        if ruta not in self.cvs:
            raise CvInaccesibleError(ruta)
        return self.cvs[ruta]


class ExtractorDeTextoPlano:
    """`ExtractorDeTexto` que lee el contenido como UTF-8. Lo que empieza con un byte
    nulo es un formato que no se lee, como un .doc."""

    def extraer(self, contenido: bytes) -> str | None:
        return None if contenido.startswith(b"\x00") else contenido.decode("utf-8")


# ─── Evaluación con IA del plan de pago (ADR-021) ────────────────────────────


@dataclass
class RepositorioDeEvaluacionesEnMemoria:
    """`RepositorioDeEvaluaciones` en memoria.

    `opuestas` simula candidatos que se opusieron mientras se evaluaba su CV.
    `eventos` guarda el orden de las escrituras.
    """

    pendientes_: list[AplicacionPorEvaluar] = field(default_factory=list)
    gastado: float = 0.0
    opuestas: set[UUID] = field(default_factory=set)
    guardadas: dict[UUID, ResultadoScoring] = field(default_factory=dict)
    aplazadas: dict[UUID, str] = field(default_factory=dict)
    sueltas: set[UUID] = field(default_factory=set)
    ilegibles: set[UUID] = field(default_factory=set)
    eventos: list[tuple[str, UUID]] = field(default_factory=list)
    reclamos: int = 0

    async def gastado_este_mes(self) -> float:
        return self.gastado

    async def reclamar(self, limite: int) -> list[AplicacionPorEvaluar]:
        self.reclamos += 1
        return self.pendientes_[:limite]

    async def guardar(self, aplicacion: AplicacionPorEvaluar, resultado: ResultadoScoring) -> bool:
        self.gastado += resultado.cost_usd
        self.eventos.append(("guardar", aplicacion.application_id))
        if aplicacion.application_id in self.opuestas:
            return False
        self.guardadas[aplicacion.application_id] = resultado
        return True

    async def aplazar(self, aplicacion: AplicacionPorEvaluar, *, motivo: str) -> None:
        self.aplazadas[aplicacion.application_id] = motivo
        self.eventos.append(("aplazar", aplicacion.application_id))

    async def soltar(self, aplicacion: AplicacionPorEvaluar) -> None:
        self.sueltas.add(aplicacion.application_id)
        self.eventos.append(("soltar", aplicacion.application_id))

    async def marcar_ilegible(self, aplicacion: AplicacionPorEvaluar) -> None:
        self.ilegibles.add(aplicacion.application_id)
        self.eventos.append(("ilegible", aplicacion.application_id))


@dataclass
class EvaluadorFalso:
    """`EvaluadorDeCvs` con una respuesta fija. `errores` hace fallar los CVs que
    contengan cierta frase, y `en_curso_max` registra cuántos puntuó a la vez."""

    fit: FitScore
    costo_usd: float = 0.0025
    model: str = "gemini-2.5-flash"
    errores: dict[str, Exception] = field(default_factory=dict)
    recibido: list[tuple[CvAnonimo, str]] = field(default_factory=list)
    en_curso: int = 0
    en_curso_max: int = 0

    async def evaluar(self, cv: CvAnonimo, vacante: str) -> ResultadoScoring:
        self.recibido.append((cv, vacante))
        self.en_curso += 1
        self.en_curso_max = max(self.en_curso_max, self.en_curso)
        try:
            # Cede el turno para que se note si el lote corre en paralelo.
            await asyncio.sleep(0)
            for frase, error in self.errores.items():
                if frase in cv.texto:
                    raise error
            return ResultadoScoring(fit=self.fit, cost_usd=self.costo_usd, model=self.model)
        finally:
            self.en_curso -= 1
