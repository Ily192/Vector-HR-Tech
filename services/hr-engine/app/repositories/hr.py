"""Repository del dominio HR. Queries raw para evitar duplicar el schema.

El estado de `runs` vive en `app.repositories.runs` (necesita una sesión sin
tenant context por RLS; ver el docstring de ese módulo).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class VacanteRow:
    id: UUID
    empresa_id: UUID
    title: str
    jd: str
    icp_text: str | None
    icp_embedding: list[float] | None
    status: str


@dataclass(slots=True)
class CandidatoMatch:
    id: UUID
    full_name: str
    headline: str | None
    summary: str | None
    distance: float


def _vec_literal(embedding: list[float]) -> str:
    """pgvector acepta un literal '[0.1,0.2,...]' — bind param + cast."""
    return "[" + ",".join(f"{v:.7f}" for v in embedding) + "]"


async def get_vacante(db: AsyncSession, vacante_id: UUID | str) -> VacanteRow | None:
    row = (
        (
            await db.execute(
                text(
                    """
                select id, empresa_id, title, jd, icp_text,
                       icp_embedding::text as icp_embedding_text, status
                  from vacantes
                 where id = :id
                """,
                ),
                {"id": str(vacante_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    embedding_text = row["icp_embedding_text"]
    embedding: list[float] | None = None
    if embedding_text:
        # pgvector serializa como "[0.1,0.2,...]"
        embedding = [float(x) for x in embedding_text.strip("[]").split(",") if x]
    return VacanteRow(
        id=row["id"],
        empresa_id=row["empresa_id"],
        title=row["title"],
        jd=row["jd"],
        icp_text=row["icp_text"],
        icp_embedding=embedding,
        status=row["status"],
    )


async def update_vacante_embedding(
    db: AsyncSession,
    vacante_id: UUID | str,
    embedding: list[float],
) -> None:
    await db.execute(
        text(
            """
            update vacantes
               set icp_embedding = cast(:emb as vector),
                   updated_at = now()
             where id = :id
            """,
        ),
        {"id": str(vacante_id), "emb": _vec_literal(embedding)},
    )


async def match_candidates(
    db: AsyncSession,
    icp_embedding: list[float],
    *,
    limit: int = 50,
) -> list[CandidatoMatch]:
    """Vector search ordenado por cosine distance (HNSW index)."""
    rows = (
        (
            await db.execute(
                text(
                    """
                select id, full_name, headline, summary,
                       (cv_embedding <=> cast(:emb as vector)) as distance
                  from candidatos
                 where cv_embedding is not null
                 order by cv_embedding <=> cast(:emb as vector)
                 limit :limit
                """,
                ),
                {"emb": _vec_literal(icp_embedding), "limit": limit},
            )
        )
        .mappings()
        .all()
    )
    return [
        CandidatoMatch(
            id=r["id"],
            full_name=r["full_name"],
            headline=r["headline"],
            summary=r["summary"],
            distance=float(r["distance"]),
        )
        for r in rows
    ]


async def upsert_application(
    db: AsyncSession,
    *,
    empresa_id: UUID | str,
    vacante_id: UUID | str,
    candidato_id: UUID | str,
    fit_score: float,
    fit_rationale: str,
    fit_gaps: list[str],
) -> UUID:
    """Crea o actualiza la application (vacante, candidato) → status='evaluated'."""
    row = (
        (
            await db.execute(
                text(
                    """
                insert into applications
                    (empresa_id, vacante_id, candidato_id, status,
                     fit_score, fit_rationale, fit_gaps)
                values
                    (:empresa_id, :vacante_id, :candidato_id, 'evaluated',
                     :fit_score, :fit_rationale, :fit_gaps)
                on conflict (vacante_id, candidato_id) do update
                set fit_score = excluded.fit_score,
                    fit_rationale = excluded.fit_rationale,
                    fit_gaps = excluded.fit_gaps,
                    status = case
                        when applications.status = 'applied' then 'evaluated'
                        else applications.status
                    end
                returning id
                """,
                ),
                {
                    "empresa_id": str(empresa_id),
                    "vacante_id": str(vacante_id),
                    "candidato_id": str(candidato_id),
                    "fit_score": fit_score,
                    "fit_rationale": fit_rationale,
                    "fit_gaps": fit_gaps,
                },
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise RuntimeError("upsert_application no devolvió id")
    application_id: UUID = row["id"]
    return application_id
