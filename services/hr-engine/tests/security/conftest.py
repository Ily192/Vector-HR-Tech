"""Fixtures para los RLS tests.

Aplica las migraciones Supabase (`infra/supabase/migrations/*.sql`) sobre la
DB de prueba y expone helpers para abrir conexiones con JWT-claim simulado.

El stack se basa en asyncpg directo (no SQLAlchemy) porque queremos ejecutar
SQL crudo y observar el comportamiento de RLS sin la capa ORM en medio.

Modelo de privilegios
---------------------
En Supabase, `anon` y `authenticated` reciben GRANT sobre las tablas por
default privileges, y RLS es lo unico que separa tenants. Este bench replica
eso concediendo los mismos default privileges ANTES de que las migraciones
creen las tablas — asi los `revoke` que las migraciones hacen (por ejemplo,
quitarle `psicometricos` a `anon` en 0004) se ejercitan de verdad en vez de
quedar pisados por un grant de la fixture.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest_asyncio

# Buscar repo root subiendo desde tests/security/ hasta encontrar pnpm-workspace.yaml.
_HERE = Path(__file__).resolve()
_REPO_ROOT = next(p for p in _HERE.parents if (p / "pnpm-workspace.yaml").exists())
MIGRATIONS_DIR = _REPO_ROOT / "infra" / "supabase" / "migrations"
SEED_FILE = _REPO_ROOT / "infra" / "supabase" / "seed.sql"


# asyncpg usa el DSN sin el dialecto SQLAlchemy.
def _asyncpg_dsn() -> str:
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://vortex:vortex@localhost:5432/vortex_test",
    )
    return raw.replace("postgresql+asyncpg://", "postgresql://")


def _assert_disposable(dsn: str) -> None:
    """La fixture hace `drop schema public cascade`. Si DATABASE_URL apunta a
    algo que no es una DB de prueba desechable, aborta antes de destruirla.
    """
    dbname = dsn.rsplit("/", 1)[-1].split("?")[0]
    if not ("test" in dbname or "dev" in dbname):
        raise RuntimeError(
            f"Los RLS tests dropean el schema public. DATABASE_URL apunta a "
            f"la base '{dbname}', que no parece desechable. Aborto."
        )


EMPRESA_VECTOR = "11111111-1111-1111-1111-111111111111"
EMPRESA_SIETE = "22222222-2222-2222-2222-222222222222"


async def _ensure_auth_schema(conn: asyncpg.Connection) -> None:
    """Supabase corre sobre Postgres con un schema `auth` y varios roles
    preinstalados. En el contenedor `pgvector/pgvector:pg15` de CI nada de eso
    existe, asi que stubeamos lo minimo que las migraciones referencian:
    schema `auth`, `auth.users`, `auth.uid()` y los roles `authenticated`,
    `anon`, `service_role` y `supabase_auth_admin`.

    Los default privileges se conceden AQUI, antes de que existan las tablas,
    para que las migraciones puedan revocarlos despues (ver docstring del
    modulo).
    """
    await conn.execute(
        """
        create schema if not exists auth;
        create table if not exists auth.users (
            id uuid primary key,
            email text,
            raw_user_meta_data jsonb default '{}'::jsonb,
            raw_app_meta_data jsonb default '{}'::jsonb,
            created_at timestamptz not null default now()
        );
        -- Replica literal de la `auth.uid()` de Supabase. El orden importa: el
        -- `nullif` va ANTES del cast a jsonb. Con el GUC seteado a cadena vacia
        -- —que es como esta fixture representa "sin sesion"— un `''::jsonb`
        -- lanza 22P02 y tumba la query entera en vez de comportarse como
        -- "sin claims". El stub anterior tenia el nullif despues del cast, asi
        -- que `empresas`, `constancias` y `platform_admins` abortaban para un
        -- `authenticated` sin claims. Es el mismo error que 0001 documenta para
        -- `public.empresa_id()`, cometido en el arnes en vez de en el esquema:
        -- los tests ejercitaban una funcion que no es la de produccion.
        create or replace function auth.uid() returns uuid as $$
            select coalesce(
                nullif(current_setting('request.jwt.claim.sub', true), ''),
                nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
            )::uuid;
        $$ language sql stable;
        do $$ begin
            create role anon nologin;
        exception when duplicate_object then null; end $$;
        do $$ begin
            create role authenticated nologin;
        exception when duplicate_object then null; end $$;
        do $$ begin
            create role service_role nologin bypassrls;
        exception when duplicate_object then null; end $$;
        do $$ begin
            create role supabase_auth_admin nologin;
        exception when duplicate_object then null; end $$;

        grant usage on schema public to anon, authenticated, service_role;
        alter default privileges in schema public
            grant select, insert, update, delete on tables
            to anon, authenticated, service_role;
        alter default privileges in schema public
            grant usage, select on sequences
            to anon, authenticated, service_role;
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
    """Una sola vez por sesion: drop+create del schema y aplicar migraciones."""
    dsn = _asyncpg_dsn()
    _assert_disposable(dsn)
    conn = await asyncpg.connect(dsn)
    try:
        # Limpiar todo lo de runs anteriores. Drop cascade del schema publico.
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
    """Conexion nueva por test. Importante: cada conexion empieza con role
    `authenticated` y SIN claims (deny-by-default para RLS)."""
    conn = await asyncpg.connect(_asyncpg_dsn())
    try:
        await conn.execute("set role authenticated;")
        yield conn
    finally:
        await conn.execute("reset role;")
        await conn.close()


async def assume_tenant(
    conn: asyncpg.Connection,
    empresa_id: str,
    role: str = "HR",
    user_id: str | None = None,
) -> None:
    """Simula el JWT que Supabase Auth inyecta para un usuario del tenant.

    Los claims van bajo `app_metadata`, igual que los emite
    `custom_access_token_hook` desde 0003. `role` en la raiz del JWT es un
    claim RESERVADO que PostgREST usa para hacer `SET LOCAL ROLE`, asi que el
    rol de aplicacion viaja como `app_metadata.app_role`.

    Setea el GUC `request.jwt.claims` a nivel de sesion (no transaccion) —
    asyncpg corre cada statement en su propio bloque implicito, asi que
    `is_local=true` se perderia antes del siguiente query.
    """
    claims = json.dumps(
        {
            "sub": user_id or str(uuid.uuid4()),
            "app_metadata": {"empresa_id": empresa_id, "app_role": role},
        }
    )
    # set_config requiere ser corrido como superuser/owner para setear GUCs
    # custom. Salimos del role authenticated, seteamos, y volvemos.
    await conn.execute("reset role;")
    await conn.execute("select set_config('request.jwt.claims', $1, false)", claims)
    await conn.execute("set role authenticated;")


async def assume_anon(conn: asyncpg.Connection) -> None:
    """Simula un cliente con la anon key: sin claims y con el rol `anon`.

    Antes los tests usaban `authenticated` sin claims para representar esto,
    lo cual ocultaba los `revoke ... from anon` de las migraciones.
    """
    await conn.execute("reset role;")
    await conn.execute("select set_config('request.jwt.claims', '', false)")
    await conn.execute("set role anon;")
