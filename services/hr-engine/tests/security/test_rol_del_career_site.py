"""El rol `career_site` (migración 0017): lo que el career site en Vercel puede y no puede.

El career site sale de la service_role. Con su clave solo lee el `id` y el
`empresa_id` de las vacantes abiertas y sube CVs al bucket `cvs`. El banco no tiene
Storage: las policies del bucket se prueban sobre una `storage.objects` mínima, dentro
de una transacción que se deshace, con el GUC `request.headers` como lo pone la Storage
API. Contra el stack real (Envoy y la Storage API de verdad) lo prueba
`infra/vps/pruebas/humo.py career-site`.
"""

from __future__ import annotations

import json
import uuid

import asyncpg
import pytest

from .conftest import EMPRESA_VECTOR, MIGRATIONS_DIR

pytestmark = pytest.mark.asyncio

SinPermiso = asyncpg.exceptions.InsufficientPrivilegeError


async def _como_career_site(db: asyncpg.Connection) -> None:
    await db.execute("reset role")
    await db.execute("select set_config('request.jwt.claims', '', false)")
    await db.execute("set role career_site")


async def _abierta(db: asyncpg.Connection) -> asyncpg.Record:
    """Una vacante abierta del seed, leída como dueño de la base."""
    await db.execute("reset role")
    fila = await db.fetchrow(
        "select id::text as id, empresa_id::text as empresa_id, slug from vacantes"
        " where status = 'open' order by created_at limit 1"
    )
    assert fila is not None, "el seed trae vacantes abiertas"
    return fila


async def _borrador(db: asyncpg.Connection) -> str:
    """Una vacante en borrador (no cuenta para el tope del plan), como dueño de la base."""
    await db.execute("reset role")
    return await db.fetchval(
        """
        insert into vacantes (empresa_id, slug, title, jd, status)
        values ($1::uuid, 'career-site-' || gen_random_uuid(), 'Prueba', 'Prueba', 'draft')
        returning id::text
        """,
        EMPRESA_VECTOR,
    )


async def test_lee_id_y_empresa_de_la_vacante_abierta(db: asyncpg.Connection) -> None:
    abierta = await _abierta(db)
    await _como_career_site(db)
    fila = await db.fetchrow(
        "select id::text, empresa_id::text from vacantes where slug = $1 and status = 'open'",
        abierta["slug"],
    )
    assert fila is not None
    assert (fila["id"], fila["empresa_id"]) == (abierta["id"], abierta["empresa_id"])


async def test_no_ve_las_vacantes_que_no_estan_abiertas(db: asyncpg.Connection) -> None:
    borrador = await _borrador(db)
    await _como_career_site(db)
    assert await db.fetchval("select count(*) from vacantes where id = $1::uuid", borrador) == 0


async def test_no_lee_las_columnas_internas_de_la_vacante(db: asyncpg.Connection) -> None:
    await _como_career_site(db)
    for columna in ("icp_text", "salary_min", "title"):
        with pytest.raises(SinPermiso):
            await db.fetch(f"select {columna} from vacantes limit 1")


async def test_no_escribe_vacantes(db: asyncpg.Connection) -> None:
    abierta = (await _abierta(db))["id"]
    await _como_career_site(db)
    with pytest.raises(SinPermiso):
        await db.execute("update vacantes set status = 'closed' where id = $1::uuid", abierta)
    with pytest.raises(SinPermiso):
        await db.execute("delete from vacantes where id = $1::uuid", abierta)
    with pytest.raises(SinPermiso):
        await db.execute(
            "insert into vacantes (empresa_id, slug, title, jd) values ($1::uuid, 'x', 'x', 'x')",
            EMPRESA_VECTOR,
        )


@pytest.mark.parametrize("tabla", ["empresas", "candidatos", "applications", "profiles"])
async def test_no_toca_las_demas_tablas(db: asyncpg.Connection, tabla: str) -> None:
    await _como_career_site(db)
    with pytest.raises(SinPermiso):
        await db.fetch(f"select 1 from {tabla} limit 1")


async def test_no_hereda_privilegios(db: asyncpg.Connection) -> None:
    await db.execute("reset role")
    fila = await db.fetchrow(
        "select rolcanlogin, rolinherit, rolbypassrls, rolsuper from pg_roles"
        " where rolname = 'career_site'"
    )
    assert fila is not None
    assert not any(fila.values())


async def _cabecera(db: asyncpg.Connection, ruta: str | None) -> None:
    """Lo que pone la Storage API en `request.headers`, y vuelve a `career_site`."""
    await db.execute("reset role")
    cabeceras = {"content-type": "application/json"}
    if ruta is not None:
        cabeceras["x-cv-ruta"] = ruta
    await db.execute("select set_config('request.headers', $1, false)", json.dumps(cabeceras))
    await db.execute("set role career_site")


async def test_policies_del_bucket_cvs(db: asyncpg.Connection) -> None:
    abierta = await _abierta(db)
    empresa = abierta["empresa_id"]
    ruta = f"{empresa}/{uuid.uuid4()}.pdf"
    vieja = f"{empresa}/{uuid.uuid4()}.pdf"
    migracion = (MIGRATIONS_DIR / "0017_rol_del_career_site.sql").read_text(encoding="utf-8")
    transaccion = db.transaction()
    await transaccion.start()
    try:
        await db.execute(
            """
            create schema storage;
            create table storage.objects (
                id uuid primary key default gen_random_uuid(),
                bucket_id text not null,
                name text not null,
                created_at timestamptz not null default now()
            );
            alter table storage.objects enable row level security;
            """
        )
        # La migración otra vez, ahora con `storage.objects`: crea las policies.
        await db.execute(migracion.replace("begin;", "", 1).replace("commit;", "", 1))
        await db.execute(
            "insert into storage.objects (bucket_id, name, created_at)"
            " values ('cvs', $1, now() - interval '20 minutes')",
            vieja,
        )

        # Sube a la carpeta de una empresa con vacantes abiertas, con la forma de la ruta.
        await _cabecera(db, None)
        await db.execute("insert into storage.objects (bucket_id, name) values ('cvs', $1)", ruta)
        for bucket, nombre in (
            ("otro", f"{empresa}/{uuid.uuid4()}.pdf"),
            ("cvs", f"{uuid.uuid4()}/{uuid.uuid4()}.pdf"),
            ("cvs", f"{empresa}/{uuid.uuid4()}.exe"),
            ("cvs", f"{empresa}/a/{uuid.uuid4()}.pdf"),
        ):
            # Cada rechazo en su savepoint: un error aborta la transacción entera.
            with pytest.raises(SinPermiso):
                async with db.transaction():
                    await db.execute(
                        "insert into storage.objects (bucket_id, name) values ($1, $2)",
                        bucket,
                        nombre,
                    )

        # Sin la cabecera, o con la de otra ruta, no ve nada ni borra nada.
        assert await db.fetchval("select count(*) from storage.objects") == 0
        assert await db.execute("delete from storage.objects where name = $1", ruta) == "DELETE 0"
        await _cabecera(db, f"{empresa}/{uuid.uuid4()}.pdf")
        assert await db.fetchval("select count(*) from storage.objects") == 0
        assert await db.execute("delete from storage.objects where name = $1", ruta) == "DELETE 0"

        # Con su ruta, la ve y la borra; la de hace 20 minutos ya no.
        await _cabecera(db, vieja)
        assert await db.execute("delete from storage.objects where name = $1", vieja) == "DELETE 0"
        await _cabecera(db, ruta)
        borradas = await db.fetch(
            "delete from storage.objects where name = $1 returning name", ruta
        )
        assert [f["name"] for f in borradas] == [ruta]

        # Y no cambia nada: sin UPDATE sobre la tabla.
        await _cabecera(db, vieja)
        with pytest.raises(SinPermiso):
            async with db.transaction():
                await db.execute("update storage.objects set name = name where name = $1", vieja)
    finally:
        await transaccion.rollback()
