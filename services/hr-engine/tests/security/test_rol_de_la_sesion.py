"""`public.app_role()` y `public.empresa_id()` con lo que pone cada cliente (migración 0011).

- PostgREST pone `request.jwt.claims` con el JWT entero.
- La Storage API de Supabase, además, `request.jwt.claim.role` con el rol de
  Postgres del JWT (`authenticated`).
- El hr-engine no tiene JWT: pone `request.jwt.claim.empresa_id` y
  `request.jwt.claim.role` con el rol de la aplicación (`set_tenant_context`).

Hasta 0011, en Storage `app_role()` valía 'authenticated' y la empresa no podía
bajar sus propios CVs. El banco no tiene Storage: estos tests reproducen sus GUCs.
"""

from __future__ import annotations

import json

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio

EMPRESA = "22222222-2222-2222-2222-222222222222"
CLAIMS_DE_SUPABASE = json.dumps(
    {
        "sub": "8a7c5d1e-0000-4000-8000-000000000001",
        "role": "authenticated",
        "app_metadata": {"empresa_id": EMPRESA, "app_role": "HR"},
    }
)


async def _sesion(db: asyncpg.Connection, gucs: dict[str, str]) -> tuple[str | None, str | None]:
    await db.execute("reset role")
    for nombre, valor in gucs.items():
        await db.execute("select set_config($1, $2, false)", nombre, valor)
    await db.execute("set role authenticated")
    fila = await db.fetchrow(
        "select public.app_role() as rol, public.empresa_id()::text as empresa"
    )
    return fila["rol"], fila["empresa"]


async def test_en_storage_gana_el_rol_de_app_metadata(db: asyncpg.Connection) -> None:
    gucs = {"request.jwt.claims": CLAIMS_DE_SUPABASE, "request.jwt.claim.role": "authenticated"}
    assert await _sesion(db, gucs) == ("HR", EMPRESA)


async def test_postgrest_solo_trae_los_claims(db: asyncpg.Connection) -> None:
    gucs = {"request.jwt.claims": CLAIMS_DE_SUPABASE, "request.jwt.claim.role": ""}
    assert await _sesion(db, gucs) == ("HR", EMPRESA)


async def test_el_hr_engine_sigue_usando_sus_gucs(db: asyncpg.Connection) -> None:
    gucs = {
        "request.jwt.claims": "",
        "request.jwt.claim.role": "HR",
        "request.jwt.claim.empresa_id": EMPRESA,
    }
    assert await _sesion(db, gucs) == ("HR", EMPRESA)


@pytest.mark.parametrize("rol_de_postgres", ["authenticated", "anon", "service_role"])
async def test_un_rol_de_postgres_no_es_un_rol_de_la_aplicacion(
    db: asyncpg.Connection, rol_de_postgres: str
) -> None:
    gucs = {"request.jwt.claims": "", "request.jwt.claim.role": rol_de_postgres}
    assert await _sesion(db, gucs) == (None, None)
