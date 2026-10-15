"""Adaptadores de los puertos de la evaluación: SQL bajo RLS, OpenAI y Gemini.

Traducen entre el dominio y la infraestructura y nada más: las reglas (qué
embedding falta, el tope de gasto, el siguiente paso) son del caso de uso y del
dominio.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embeddings import embed_text
from app.clients.errors import is_retryable_llm_error
from app.clients.scoring import score_candidate_fit
from app.domain.entidades import (
    Candidato,
    Embedding,
    FitScore,
    PerfilAnonimo,
    ResultadoScoring,
    Vacante,
)
from app.domain.puertos import ProveedorNoDisponibleError
from app.monitoring import logger
from app.repositories import hr as hr_repo


class SqlCandidateRepository:
    """`CandidateRepository` sobre una sesión con el contexto de tenant ya puesto."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_vacante(self, vacante_id: UUID) -> Vacante | None:
        row = await hr_repo.get_vacante(self._db, vacante_id)
        if row is None:
            return None
        return Vacante(
            id=row.id,
            empresa_id=row.empresa_id,
            title=row.title,
            jd=row.jd,
            icp_text=row.icp_text,
            tiene_embedding=bool(row.icp_embedding),
        )

    async def get_candidato(self, candidato_id: UUID) -> Candidato | None:
        row = await hr_repo.get_candidato(self._db, candidato_id)
        if row is None:
            return None
        return Candidato(
            id=row.id,
            full_name=row.full_name,
            headline=row.headline,
            summary=row.summary,
            tiene_embedding=row.tiene_embedding,
        )

    async def update_vacante_embedding(self, vacante_id: UUID, vector: tuple[float, ...]) -> None:
        await hr_repo.update_vacante_embedding(self._db, vacante_id, list(vector))

    async def update_candidato_embedding(
        self, candidato_id: UUID, vector: tuple[float, ...]
    ) -> None:
        await hr_repo.update_candidato_embedding(self._db, candidato_id, list(vector))

    async def upsert_application(
        self, *, empresa_id: UUID, vacante_id: UUID, candidato_id: UUID, fit: FitScore
    ) -> UUID:
        return await hr_repo.upsert_application(
            self._db,
            empresa_id=empresa_id,
            vacante_id=vacante_id,
            candidato_id=candidato_id,
            fit_score=fit.score,
            fit_rationale=fit.rationale,
            fit_gaps=list(fit.gaps),
        )


class OpenAIEmbeddings:
    """`EmbeddingProvider` sobre la API de embeddings de OpenAI."""

    async def embed(self, texto: str) -> Embedding:
        try:
            resultado = await embed_text(texto)
        except Exception as exc:
            # Caída tras los reintentos, o sin key (RuntimeError): no hay proveedor
            # ahora. Lo demás (p. ej. texto vacío) es un error de verdad.
            if is_retryable_llm_error(exc) or isinstance(exc, RuntimeError):
                logger.warning("embeddings.no_disponible", error_type=type(exc).__name__)
                raise ProveedorNoDisponibleError("embeddings no disponibles") from exc
            raise
        return Embedding(
            vector=tuple(resultado.vector), cost_usd=resultado.cost_usd, model=resultado.model
        )


class LlmScoring:
    """`ScoringProvider` sobre Gemini con OpenAI de respaldo (`app.clients.scoring`).

    Sin ningún modelo disponible, `score_candidate_fit` lanza `LLMUnavailableError`,
    que es un `ProveedorNoDisponibleError`: sale tal cual y la tarea aplaza.
    """

    async def score(self, perfil: PerfilAnonimo, icp: str) -> ResultadoScoring:
        resultado = await score_candidate_fit(
            {"headline": perfil.headline, "summary": perfil.summary}, icp
        )
        r = resultado.response
        return ResultadoScoring(
            fit=FitScore(
                score=r.score,
                rationale=r.rationale,
                gaps=tuple(r.gaps),
                strengths=tuple(r.strengths),
            ),
            cost_usd=resultado.cost_usd,
            model=resultado.model,
        )
