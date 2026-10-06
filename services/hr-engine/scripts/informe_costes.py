"""Informe de coste real por ejecución, a partir de la tabla `runs`.

Para la fase de medición (2026-10): el tope de gasto está apagado y cada run
guarda su coste total y, en `payload.cost_breakdown`, cuánto gastó cada paso.

Uso (desde services/hr-engine):
    python -m uv run python scripts/informe_costes.py [--dias 30]

Lee DATABASE_URL del entorno (o del .env vía app.config). Solo hace SELECT.
"""

from __future__ import annotations

import argparse
import asyncio

import asyncpg

from app.config import settings

_POR_SKILL = """
select agent_skill,
       count(*)                                                   as runs,
       sum(cost_usd)                                              as total,
       avg(cost_usd)                                              as media,
       percentile_cont(0.5)  within group (order by cost_usd)     as p50,
       percentile_cont(0.95) within group (order by cost_usd)     as p95,
       max(cost_usd)                                              as maximo
  from runs
 where status = 'completed'
   and finished_at >= now() - make_interval(days => $1)
 group by agent_skill
 order by total desc
"""

_POR_PASO = """
select r.agent_skill, paso.key as paso, count(*) as runs, avg(paso.value::numeric) as media
  from runs r, jsonb_each_text(coalesce(r.payload -> 'cost_breakdown', '{}'::jsonb)) as paso
 where r.status = 'completed'
   and r.finished_at >= now() - make_interval(days => $1)
 group by 1, 2
 order by 1, 4 desc
"""

_POR_MODELO = """
select coalesce(payload ->> 'model', '(sin registrar)') as modelo, count(*) as runs,
       avg(cost_usd) as media
  from runs
 where status = 'completed'
   and finished_at >= now() - make_interval(days => $1)
 group by 1
 order by 2 desc
"""


def _usd(v: object) -> str:
    return f"${float(v or 0):.5f}"


async def main(dias: int) -> None:
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        filas = await conn.fetch(_POR_SKILL, dias)
        print(f"Coste real de las ejecuciones completadas, últimos {dias} días\n")
        if not filas:
            print("Sin ejecuciones completadas en ese periodo.")
            return
        print(f"{'skill':16} {'runs':>5} {'total':>10} {'media':>10} {'p50':>10} {'p95':>10} {'máx':>10}")
        for f in filas:
            print(
                f"{f['agent_skill']:16} {f['runs']:>5} {_usd(f['total']):>10} {_usd(f['media']):>10} "
                f"{_usd(f['p50']):>10} {_usd(f['p95']):>10} {_usd(f['maximo']):>10}",
            )
        print("\nPor paso (media por run):")
        for f in await conn.fetch(_POR_PASO, dias):
            print(f"  {f['agent_skill']:16} {f['paso']:22} {_usd(f['media']):>10}  ({f['runs']} runs)")
        print("\nPor modelo:")
        for f in await conn.fetch(_POR_MODELO, dias):
            print(f"  {f['modelo']:22} {f['runs']:>5} runs   media {_usd(f['media'])}")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dias", type=int, default=30)
    asyncio.run(main(parser.parse_args().dias))
