"""Puertos de la evaluación: lo que el dominio necesita del mundo exterior.

Los implementan los adaptadores de infraestructura (SQL, OpenAI, Gemini) y, en
los tests, adaptadores falsos. El dominio solo conoce estas firmas.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.entidades import (
    Candidato,
    Embedding,
    FitScore,
    PerfilAnonimo,
    ResultadoScoring,
    Vacante,
)


class ProveedorNoDisponibleError(RuntimeError):
    """El proveedor no puede atender ahora: caído, sin configurar, con timeouts,
    con 429/5xx o con el circuito abierto.

    Los adaptadores traducen a esta excepción los errores de disponibilidad de su
    SDK. Los demás fallos (una respuesta inválida, un 400) no se traducen: son
    errores de verdad y tienen que verse.
    """


class CandidateRepository(Protocol):
    """Lectura y escritura de candidatos, vacantes y applications de un tenant.

    Ve solo lo que deja ver el tenant de la sesión: un id de otra empresa se
    comporta como inexistente (`None`).
    """

    async def get_vacante(self, vacante_id: UUID) -> Vacante | None: ...

    async def get_candidato(self, candidato_id: UUID) -> Candidato | None: ...

    async def update_vacante_embedding(
        self, vacante_id: UUID, vector: tuple[float, ...]
    ) -> None: ...

    async def update_candidato_embedding(
        self, candidato_id: UUID, vector: tuple[float, ...]
    ) -> None: ...

    async def upsert_application(
        self,
        *,
        empresa_id: UUID,
        vacante_id: UUID,
        candidato_id: UUID,
        fit: FitScore,
    ) -> UUID:
        """Crea o actualiza la application (vacante, candidato) y devuelve su id."""
        ...


class EmbeddingProvider(Protocol):
    """Genera el embedding de un texto.

    Si el proveedor no está disponible lanza `ProveedorNoDisponibleError`. Los
    embeddings sirven a la búsqueda del sourcer, así que la evaluación sigue sin él.
    """

    async def embed(self, texto: str) -> Embedding: ...


class ScoringProvider(Protocol):
    """Puntúa el encaje de un perfil con un ICP.

    Recibe un `PerfilAnonimo` y no un `Candidato`: así el tipo impide que el
    nombre llegue al modelo. Si ningún modelo está disponible lanza
    `ProveedorNoDisponibleError`, y quien llama aplaza la evaluación.
    """

    async def score(self, perfil: PerfilAnonimo, icp: str) -> ResultadoScoring: ...
