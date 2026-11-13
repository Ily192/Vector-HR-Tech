"""Adaptador del recordatorio de postulados (ADR-023, migración 0020).

`SqlRepositorioDeRecordatorios`: el puerto sobre el SQL de
`app/repositories/recordatorios.py`, con la sesión del hr-engine (rol dueño). El
correo sale por `CorreoSmtp` (`app/infrastructure/moderacion.py`), el mismo SMTP de
Resend que usan Auth y la moderación.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.recordatorios import PostuladosSinRevisar, VacanteConPostulados
from app.repositories import recordatorios as recordatorios_repo


def _vacantes(crudo: Any) -> tuple[VacanteConPostulados, ...]:
    lista = json.loads(crudo) if isinstance(crudo, str) else (crudo or [])
    return tuple(
        VacanteConPostulados(titulo=str(v["titulo"]), postulados=int(v["postulados"]))
        for v in lista
        if isinstance(v, dict)
    )


class SqlRepositorioDeRecordatorios:
    """`RepositorioDeRecordatorios` sobre la sesión del hr-engine (rol dueño)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def con_postulados_sin_revisar(
        self, umbral: int, limite: int
    ) -> Sequence[PostuladosSinRevisar]:
        filas = await recordatorios_repo.con_postulados_sin_revisar(
            self._db, umbral=umbral, limite=limite
        )
        return [
            PostuladosSinRevisar(
                empresa_id=f.empresa_id,
                empresa=f.empresa,
                postulados=int(f.postulados),
                cruzo_el_umbral_en=f.cruzo_el_umbral_en,
                recordado_en=f.recordado_en,
                visto_en=f.visto_en,
                vacantes=_vacantes(f.vacantes),
                destinatarios=tuple(f.destinatarios or ()),
            )
            for f in filas
        ]

    async def enviados_en_24_horas(self) -> int:
        return await recordatorios_repo.enviados_en_24_horas(self._db)

    async def registrar(self, empresa_id: UUID, *, postulados: int, destinatarios: int) -> None:
        await recordatorios_repo.registrar(
            self._db, empresa_id=empresa_id, postulados=postulados, destinatarios=destinatarios
        )
        await self._db.commit()
