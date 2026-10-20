"""Adaptadores de la evaluación con IA del plan de pago (ADR-021): el SQL del barrido.

Storage y el texto del CV son los mismos del plan gratis (`infrastructure/coincidencias.py`),
y el modelo, `LlmScoring` (`infrastructure/evaluacion.py`).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entidades import AplicacionPorEvaluar, ResultadoScoring, VacanteParaEvaluar
from app.domain.evaluacion_ia import MAX_INTENTOS, MINUTOS_DE_RECLAMO
from app.repositories import evaluaciones as evaluaciones_repo


class SqlRepositorioDeEvaluaciones:
    """`RepositorioDeEvaluaciones` sobre la sesión del worker (rol dueño).

    Confirma cada escritura: el reclamo y su intento tienen que sobrevivir aunque el
    proceso muera leyendo un PDF.
    """

    def __init__(self, db: AsyncSession, *, tope_por_evaluacion_usd: float) -> None:
        self._db = db
        self._tope = tope_por_evaluacion_usd

    async def gastado_este_mes(self) -> float:
        return await evaluaciones_repo.gastado_este_mes(self._db)

    async def reclamar(self, limite: int) -> list[AplicacionPorEvaluar]:
        filas = await evaluaciones_repo.reclamar(
            self._db,
            limite=limite,
            max_intentos=MAX_INTENTOS,
            minutos_de_reclamo=MINUTOS_DE_RECLAMO,
        )
        await self._db.commit()
        return [
            AplicacionPorEvaluar(
                application_id=f.application_id,
                empresa_id=f.empresa_id,
                plan=f.plan,
                ruta=f.ruta,
                nombre=f.nombre,
                correo=f.correo,
                vacante=VacanteParaEvaluar(
                    titulo=f.titulo,
                    descripcion=f.descripcion,
                    skills=tuple(f.skills),
                    nivel=f.nivel,
                    modalidad=f.modalidad,
                    ubicacion=f.ubicacion,
                    icp_text=f.icp_text,
                ),
            )
            for f in filas
        ]

    async def guardar(self, aplicacion: AplicacionPorEvaluar, resultado: ResultadoScoring) -> bool:
        guardada = await evaluaciones_repo.guardar(
            self._db,
            application_id=aplicacion.application_id,
            empresa_id=aplicacion.empresa_id,
            score=resultado.fit.score,
            rationale=resultado.fit.rationale,
            gaps=list(resultado.fit.gaps),
            strengths=list(resultado.fit.strengths),
            costo_usd=resultado.cost_usd,
            tope_usd=self._tope,
            modelo=resultado.model,
        )
        await self._db.commit()
        return guardada

    async def aplazar(self, aplicacion: AplicacionPorEvaluar, *, motivo: str) -> None:
        await evaluaciones_repo.aplazar(
            self._db, application_id=aplicacion.application_id, motivo=motivo, tope_usd=self._tope
        )
        await self._db.commit()

    async def soltar(self, aplicacion: AplicacionPorEvaluar) -> None:
        await evaluaciones_repo.soltar(self._db, application_id=aplicacion.application_id)
        await self._db.commit()

    async def marcar_ilegible(self, aplicacion: AplicacionPorEvaluar) -> None:
        await evaluaciones_repo.marcar_ilegible(
            self._db, application_id=aplicacion.application_id, empresa_id=aplicacion.empresa_id
        )
        await self._db.commit()
