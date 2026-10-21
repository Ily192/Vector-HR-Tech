"""SQL del aviso de los diagnósticos gratuitos (migración 0017).

Corre con la sesión del worker (rol dueño): `privado.diagnosticos` no la toca
ningún rol de la API, y solo se escribe por `public.registrar_diagnostico()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class DiagnosticoRow:
    id: UUID
    creado_en: datetime
    nombre: str
    empresa: str
    correo: str
    origen: str | None
    utm_medium: str | None
    utm_campaign: str | None
    horas_recuperables_mes: Decimal
    resultado: dict[str, Any]
    ip: str | None
    turnstile_token: str | None
    verificado: bool


# `skip locked`: un barrido que corre a la vez no toma los mismos. El bloqueo dura
# hasta que el barrido confirma.
_RECLAMAR = text(
    """
    select id, creado_en, nombre, empresa, correo, origen, utm_medium, utm_campaign,
           horas_recuperables_mes, resultado, ip, turnstile_token,
           verificado_en is not null as verificado
      from privado.diagnosticos
     where avisado_en is null
       and descartado_en is null
       and intentos_aviso < :max_intentos
     order by creado_en, id
     limit :limite
       for update skip locked
    """
)

_AVISADOS_HOY = text(
    """
    select count(*) from privado.diagnosticos
     where avisado_en >= date_trunc('day', now() at time zone 'UTC') at time zone 'UTC'
    """
)

_MARCAR_VERIFICADO = text("update privado.diagnosticos set verificado_en = now() where id = :id")

_DESCARTAR = text("update privado.diagnosticos set descartado_en = now() where id = :id")

_MARCAR_AVISADOS = text(
    "update privado.diagnosticos set avisado_en = now() where id = any(:ids)"
).bindparams(bindparam("ids", type_=postgresql.ARRAY(postgresql.UUID(as_uuid=True))))

_SUMAR_INTENTO = text(
    """
    update privado.diagnosticos
       set intentos_aviso = intentos_aviso + 1
     where id = any(:ids)
    """
).bindparams(bindparam("ids", type_=postgresql.ARRAY(postgresql.UUID(as_uuid=True))))


async def reclamar(db: AsyncSession, *, limite: int, max_intentos: int) -> list[DiagnosticoRow]:
    filas = (
        (await db.execute(_RECLAMAR, {"limite": limite, "max_intentos": max_intentos}))
        .mappings()
        .all()
    )
    return [DiagnosticoRow(**dict(f)) for f in filas]


async def avisados_hoy(db: AsyncSession) -> int:
    return int((await db.execute(_AVISADOS_HOY)).scalar_one())


async def marcar_verificado(db: AsyncSession, *, diagnostico_id: UUID) -> None:
    await db.execute(_MARCAR_VERIFICADO, {"id": diagnostico_id})


async def descartar(db: AsyncSession, *, diagnostico_id: UUID) -> None:
    await db.execute(_DESCARTAR, {"id": diagnostico_id})


async def marcar_avisados(db: AsyncSession, *, ids: list[UUID]) -> None:
    await db.execute(_MARCAR_AVISADOS, {"ids": ids})


async def sumar_intento(db: AsyncSession, *, ids: list[UUID]) -> None:
    await db.execute(_SUMAR_INTENTO, {"ids": ids})
