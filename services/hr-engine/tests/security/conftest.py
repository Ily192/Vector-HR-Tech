"""Fixtures para los RLS tests.

Aplica las migraciones Supabase (`infra/supabase/migrations/*.sql`) sobre la
DB de prueba y expone helpers para abrir conexiones con JWT-claim simulado
vía la función `public.set_tenant_context`.

El stack se basa en asyncpg directo (no SQLAlchemy) porque queremos ejecutar
SQL crudo y observar el comportamiento de RLS sin la capa ORM en medio.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest_asyncio

# Buscar repo root subiendo desde tests/security/ hasta encontrar pnpm-workspace.yaml.
_HERE = Path(__file__).resolve()
_REPO_ROOT = next(
    p for p in _HERE.parents if (p / "pnpm-workspace.yaml").exists()
)
MIGRATIONS_DIR = _REPO_ROOT / "infra" / "supabase" / "migrations"
SEED_FILE = _REPO_ROOT / "infra" / "supabase" / "seed.sql"

# asyncpg usa el DSN sin el dialecto SQLAlchemy.
def _asyncpg_dsn() -> str:
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://vortex:vortex@localhost:5432/vortex_test",
    )
    return raw.replace("postgresql+asyncpg://", "postgresql://")


EMPRESA_VECTOR = "11111111-1111-1111-1111-111111111111"
EMPRESA_SIETE = "22222222-2222-2222-2222-222222222222"


async def _ensure_auth_schema(conn: asyncpg.Connection) -> None:
    """Supabase corre sobre Postgres con un schema `auth` y varios roles
    preinstalados. En el contenedor `pgvector/pgvector:pg15` de CI nada de eso
    existe, así que stubeamos lo mínimo que las migraciones referencian:
    schema `auth`, `auth.users`, `auth.uid()` y los roles `authenticated`,
    `anon`, `supabase_auth_admin`.
    """
    await conn.execute(
        """
        create schema if not exists auth;
        create table if not exists auth.users (
            id uuid primary key,
            email text,
            raw_user_meta_data jsonb default '{}'::jsonb
        );
        create or replace function auth.uid() returns uuid as $$
            select nullif(
                current_setting('request.jwt.claims', true)::jsonb ->> 'sub',
                ''
            )::uuid;
        $$ language sql stable;
        do $$ begin
            create role anon nologin;
        exception when duplicate_object then null; end $$;
        do $$ begin
            create role authenticated nologin;
        exception when duplicate_object then null; end $$;
        do $$ begin
            create role supabase_auth_admin nologin;
        exception when duplicate_object then null; end $$;
        """
    )


async def _apply_migrations(conn: asyncpg.Connection) -> None:
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        raise RuntimeError(f"no migrations found in {MIGRATIONS_DIR}")
    for path in sql_files:
        await conn.execute(path.read_text(encoding="utf-8"))


async def _apply_seed(conn: asyncpg.Connection) -> None:
    if SEED_FILE.exists():
        await conn.execute(SEED_FILE.read_text(encoding="utf-8"))


@pytest_asyncio.fixture(scope="session")
async def _migrated_db() -> AsyncIterator[None]:
    """Una sola vez por sesión: drop+create del schema y aplicar migraciones."""
    conn = await asyncpg.connect(_asyncpg_dsn())
    try:
        # Limpiar todo lo de runs anteriores. Drop cascade del schema público.
        await conn.execute(
            """
            drop schema if exists public cascade;
            drop schema if exists auth cascade;
            create schema public;
            grant all on schema public to public;
            """
        )
        await _ensure_auth_schema(conn)
        await _apply_migrations(conn)
        await _apply_seed(conn)
    finally:
        await conn.close()
    yield


@pytest_asyncio.fixture
async def db(_migrated_db: None) -> AsyncIterator[asyncpg.Connection]:
    """Conexión nueva por test. Importante: cada conexión empieza con role
    `authenticated` y SIN claims (deny-by-default para RLS)."""
    conn = await asyncpg.connect(_asyncpg_dsn())
    try:
        # Replicar el role que Supabase asigna al cliente con anon key.
        # Necesita SELECT/INSERT grants — las dan las migraciones de Supabase
        # vía `grant ... to authenticated`, pero acá las concedemos amplias
        # porque RLS es lo único que separa tenants en este test bench.
        await conn.execute(
            "grant select, insert, update, delete "
            "on all tables in schema public to authenticated;"
        )
        await conn.execute(
            "grant usage on all sequences in schema public to authenticated;"
        )
        await conn.execute("set role authenticated;")
        yield conn
    finally:
        await conn.execute("reset role;")
        await conn.close()


async def assume_tenant(
    conn: asyncpg.Connection, empresa_id: str, role: str = "HR"
) -> None:
    """Simula el JWT que Supabase Auth inyecta para un usuario del tenant.

    Setea el GUC `request.jwt.claims` a nivel de sesión (no transacción) —
    asyncpg corre cada statement en su propio bloque implícito, así que
    `is_local=true` se perdería antes del siguiente query.
    """
    claims = json.dumps({"empresa_id": empresa_id, "role": role})
    # set_config requiere ser corrido como superuser/owner para setear GUCs
    # custom. Salimos del role authenticated, seteamos, y volvemos.
    await conn.execute("reset role;")
    await conn.execute(
        "select set_config('request.jwt.claims', $1, false)", claims
    )
    await conn.execute("set role authenticated;")
