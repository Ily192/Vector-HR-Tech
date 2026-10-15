"""Caso de uso: evaluar el encaje de un candidato con una vacante.

Es la orquestación que hoy vive dentro del worker `cv_evaluator`, escrita contra
los puertos del dominio:

1. Lee la vacante y el candidato. Si falta alguno, falla antes de gastar nada.
2. Genera los embeddings que falten. Sirven a la búsqueda del sourcer y no a esta
   puntuación: si su proveedor no está disponible, se puntúa igual y el embedding
   queda para otra ejecución.
3. Puntúa el perfil anónimo contra el ICP de la vacante. El siguiente paso lo
   decide la política del dominio (`FitScore.siguiente_paso`), no el modelo.
4. Guarda la application.

El gasto se apunta en el `CostBudget` que recibe, y el tope se comprueba antes de
cada llamada de pago. El presupuesto lo crea quien llama porque lo necesita
también cuando la evaluación falla: lo gastado hasta ahí se registra en el run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.domain.entidades import Embedding, FitScore
from app.domain.presupuesto import CostBudget
from app.domain.puertos import (
    CandidateRepository,
    EmbeddingProvider,
    ProveedorNoDisponibleError,
    ScoringProvider,
)

EmbeddingAplazado = Literal["icp", "candidato"]


class NoEncontradoError(ValueError):
    """La vacante o el candidato no existen, o son de otro tenant y el repositorio no los ve.

    Es `ValueError`, como lo que lanzaba el worker, así que la tarea no lo reintenta.
    """


@dataclass(frozen=True, slots=True)
class ResultadoEvaluacion:
    application_id: UUID
    fit: FitScore
    #: El modelo que puntuó: el de respaldo si el principal no estaba disponible.
    model: str
    #: Los embeddings que no se pudieron generar y quedan para otra ejecución.
    embeddings_aplazados: tuple[EmbeddingAplazado, ...] = ()


@dataclass(frozen=True, slots=True)
class EvaluateCandidate:
    repo: CandidateRepository
    embeddings: EmbeddingProvider
    scoring: ScoringProvider

    async def ejecutar(
        self, *, vacante_id: UUID, candidato_id: UUID, presupuesto: CostBudget
    ) -> ResultadoEvaluacion:
        vacante = await self.repo.get_vacante(vacante_id)
        if vacante is None:
            raise NoEncontradoError(f"vacante {vacante_id} no existe (o RLS la oculta)")
        candidato = await self.repo.get_candidato(candidato_id)
        if candidato is None:
            raise NoEncontradoError(f"candidato {candidato_id} no existe (o RLS lo oculta)")

        aplazados: list[EmbeddingAplazado] = []
        if not vacante.tiene_embedding:
            embedding = await self._embedding(vacante.icp, "embedding_icp", presupuesto)
            if embedding is None:
                aplazados.append("icp")
            else:
                await self.repo.update_vacante_embedding(vacante.id, embedding.vector)
        if not candidato.tiene_embedding:
            embedding = await self._embedding(
                candidato.texto_para_embedding(), "embedding_candidato", presupuesto
            )
            if embedding is None:
                aplazados.append("candidato")
            else:
                await self.repo.update_candidato_embedding(candidato.id, embedding.vector)

        presupuesto.assert_under_cap()
        scoring = await self.scoring.score(candidato.perfil_anonimo(), vacante.icp)
        presupuesto.add(scoring.cost_usd, "scoring")

        # La application es de la empresa de la vacante.
        application_id = await self.repo.upsert_application(
            empresa_id=vacante.empresa_id,
            vacante_id=vacante.id,
            candidato_id=candidato.id,
            fit=scoring.fit,
        )
        return ResultadoEvaluacion(
            application_id=application_id,
            fit=scoring.fit,
            model=scoring.model,
            embeddings_aplazados=tuple(aplazados),
        )

    async def _embedding(self, texto: str, paso: str, presupuesto: CostBudget) -> Embedding | None:
        """El embedding, o `None` si su proveedor no está disponible.

        El tope se comprueba fuera del `try`: superarlo corta la evaluación y no se
        confunde con una caída del proveedor.
        """
        presupuesto.assert_under_cap()
        try:
            embedding = await self.embeddings.embed(texto)
        except ProveedorNoDisponibleError:
            return None
        presupuesto.add(embedding.cost_usd, paso)
        return embedding
