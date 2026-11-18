"""SQL del tablero de admin del panel (ADR-022, enmienda del 2026-11-17).

Solo conteos, con la sesión del hr-engine (rol dueño, sin contexto de tenant), como el
resto de la moderación: así lee `privado.altas_web`, que ningún rol de la API ve, sin
sumar permisos a nadie. Ninguna consulta devuelve una empresa, una persona ni un
candidato.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Altas: las que crearon una empresa (`resultado = 'empresa_creada'`, 0018). La limpieza
# de 7 días borra la empresa que nadie confirmó y su alta con ella (on delete cascade),
# así que las de la semana pueden bajar al día siguiente. Vacantes: "eliminar" en el panel
# las cierra (`status = 'closed'`).
_CONTEOS = text(
    """
    select
        (select count(*) from public.empresas) as empresas,
        (select count(*) from public.empresas where verificada) as empresas_verificadas,
        (select count(*) from privado.altas_web
          where resultado = 'empresa_creada'
            and confirmado_en is not null) as altas_web_confirmadas,
        (select count(*) from privado.altas_web
          where resultado = 'empresa_creada'
            and creado_en > now() - interval '7 days') as altas_ultimos_7_dias,
        (select count(*) from public.vacantes where status = 'open') as vacantes_abiertas,
        (select count(*) from public.vacantes
          where status in ('closed', 'filled')) as vacantes_cerradas,
        (select count(*) from public.applications) as aplicaciones,
        (select count(*) from public.applications
          where applied_at > now() - interval '7 days') as aplicaciones_ultimos_7_dias
    """
)

# Las abiertas: lo que está (o no) en el career site ahora. Una rechazada sigue abierta
# hasta que la empresa la elimina.
_POR_MODERACION = text(
    """
    select v.moderacion::text as estado, count(*) as n
      from public.vacantes v
     where v.status = 'open'
     group by v.moderacion
    """
)


async def conteos(db: AsyncSession) -> Any:
    return (await db.execute(_CONTEOS)).one()


async def por_moderacion(db: AsyncSession) -> Sequence[Any]:
    return (await db.execute(_POR_MODERACION)).all()
