"""El recordatorio de postulados sin revisar en la base (migración 0020, ADR-023).

El panel marca por PostgREST, con la sesión del tenant, que abrió las postulaciones
de una vacante: la base es la que impide marcar las de otra empresa. Y el SQL del
hr-engine (rol dueño) que cuenta lo que quedó sin revisar se prueba aquí contra
Postgres real.

La base es compartida entre pruebas: cada una mira solo su empresa y los cambios
relativos del tope diario.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.domain.recordatorios import PostuladosSinRevisar
from app.infrastructure.recordatorios import SqlRepositorioDeRecordatorios

from .conftest import _asyncpg_dsn, assume_anon, assume_tenant
from .test_plan_gratis import _como_soporte, _empresa, _llenar, _vacante
from .test_rls import _drop, _elevate, _make_user

pytestmark = pytest.mark.asyncio

SinPermiso = asyncpg.exceptions.InsufficientPrivilegeError


@pytest_asyncio.fixture
async def repo(_migrated_db: None) -> AsyncIterator[SqlRepositorioDeRecordatorios]:
    """El repositorio con la sesión del hr-engine: rol dueño, sin contexto de tenant."""
    motor = create_async_engine(
        _asyncpg_dsn().replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool
    )
    async with AsyncSession(motor) as s:
        yield SqlRepositorioDeRecordatorios(s)
    await motor.dispose()


async def _confirmado(db: asyncpg.Connection, empresa_id: str, role: str) -> str:
    """Un usuario de la empresa con el correo confirmado. Devuelve su correo."""
    usuario = await _make_user(db, empresa_id, role)
    await _como_soporte(
        db, "update auth.users set email_confirmed_at = now() where id = $1::uuid", usuario
    )
    return f"{usuario}@test.local"


async def _postulaciones(
    db: asyncpg.Connection, vacante_id: str, total: int, *, hace: timedelta
) -> None:
    """`total` postulaciones por la vía pública, llegadas hace `hace` (una por minuto)."""
    await _llenar(db, vacante_id, total)
    await _como_soporte(
        db,
        """
        with orden as (
            select id, row_number() over (order by applied_at, id) as n
              from applications where vacante_id = $1::uuid
        )
        update applications a
           set applied_at = now() - $2::interval + make_interval(mins => o.n::int)
          from orden o
         where a.id = o.id
        """,
        vacante_id,
        hace,
    )


async def _de(repo: SqlRepositorioDeRecordatorios, empresa_id: str) -> PostuladosSinRevisar | None:
    filas = await repo.con_postulados_sin_revisar(5, 10_000)
    return next((f for f in filas if str(f.empresa_id) == empresa_id), None)


async def _marcar(db: asyncpg.Connection, empresa_id: str, vacante_id: str) -> bool:
    await assume_tenant(db, empresa_id)
    return bool(await db.fetchval("select marcar_postulaciones_vistas($1::uuid)", vacante_id))


# ─────────────────────── lo que el panel puede marcar ───────────────────────


async def test_la_empresa_marca_como_vistas_solo_sus_vacantes(db: asyncpg.Connection) -> None:
    una, otra = await _empresa(db), await _empresa(db)
    suya, ajena = await _vacante(db, una), await _vacante(db, otra)

    assert await _marcar(db, una, suya) is True
    assert await _marcar(db, una, suya) is True  # otra vez: solo mueve la fecha
    assert await _marcar(db, una, ajena) is False

    await _elevate(db)
    try:
        filas = await db.fetch(
            "select vacante_id::text, empresa_id::text from privado.postulaciones_vistas"
            " where vacante_id = any($1::uuid[])",
            [suya, ajena],
        )
    finally:
        await _drop(db)
    assert [tuple(f) for f in filas] == [(suya, una)]


@pytest.mark.parametrize("rol", ["Colaborador", "SuperAdmin"])
async def test_solo_hr_y_direccion_marcan(db: asyncpg.Connection, rol: str) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await assume_tenant(db, empresa_id, role="Director")
    assert await db.fetchval("select marcar_postulaciones_vistas($1::uuid)", vacante_id)

    await assume_tenant(db, empresa_id, role=rol)
    with pytest.raises(SinPermiso):
        await db.execute("select marcar_postulaciones_vistas($1::uuid)", vacante_id)
    await assume_anon(db)
    with pytest.raises(SinPermiso):
        await db.execute("select marcar_postulaciones_vistas($1::uuid)", vacante_id)


@pytest.mark.parametrize("tabla", ["postulaciones_vistas", "recordatorios_de_postulados"])
async def test_el_panel_no_lee_ni_escribe_las_tablas(db: asyncpg.Connection, tabla: str) -> None:
    await assume_tenant(db, await _empresa(db))
    with pytest.raises(SinPermiso):
        await db.fetch(f"select * from privado.{tabla}")


# ─────────────────────── lo que cuenta el hr-engine ───────────────────────


async def test_suma_lo_sin_revisar_de_todas_sus_vacantes(
    db: asyncpg.Connection, repo: SqlRepositorioDeRecordatorios
) -> None:
    empresa_id = await _empresa(db, tamano=30)
    hr = await _confirmado(db, empresa_id, "HR")
    director = await _confirmado(db, empresa_id, "Director")
    await _confirmado(db, empresa_id, "Colaborador")  # no ve postulaciones: no le llega
    await _make_user(db, empresa_id, "HR")  # sin confirmar el correo: tampoco
    almacen, chofer = await _vacante(db, empresa_id), await _vacante(db, empresa_id)
    await _postulaciones(db, almacen, 4, hace=timedelta(hours=30))
    await _postulaciones(db, chofer, 3, hace=timedelta(hours=28))

    e = await _de(repo, empresa_id)
    assert e is not None
    assert e.postulados == 7
    assert sorted(v.postulados for v in e.vacantes) == [3, 4]
    assert sorted(e.destinatarios) == sorted([hr, director])
    assert e.recordado_en is None and e.visto_en is None
    # El sexto en llegar: las 4 de almacén y la 2.ª de chofer, hace 28 h menos 2 min.
    assert e.cruzo_el_umbral_en is not None

    # Abre las postulaciones de almacén: quedan 3 sin revisar, ya no llega.
    assert await _marcar(db, empresa_id, almacen)
    assert await _de(repo, empresa_id) is None


async def test_con_5_o_en_una_vacante_cerrada_no_cuenta(
    db: asyncpg.Connection, repo: SqlRepositorioDeRecordatorios
) -> None:
    empresa_id = await _empresa(db, tamano=30)
    abierta, cerrada = await _vacante(db, empresa_id), await _vacante(db, empresa_id)
    await _postulaciones(db, abierta, 5, hace=timedelta(days=3))
    await _postulaciones(db, cerrada, 4, hace=timedelta(days=3))
    await _como_soporte(db, "update vacantes set status = 'closed' where id = $1::uuid", cerrada)
    assert await _de(repo, empresa_id) is None


async def test_despues_del_recordatorio_solo_cuentan_las_nuevas(
    db: asyncpg.Connection, repo: SqlRepositorioDeRecordatorios
) -> None:
    empresa_id = await _empresa(db, tamano=30)
    await _confirmado(db, empresa_id, "HR")
    vacante_id = await _vacante(db, empresa_id)
    await _postulaciones(db, vacante_id, 6, hace=timedelta(hours=26))
    e = await _de(repo, empresa_id)
    assert e is not None and e.postulados == 6

    antes = await repo.enviados_en_24_horas()
    await repo.registrar(e.empresa_id, postulados=6, destinatarios=1)
    assert await repo.enviados_en_24_horas() == antes + 1
    assert await _de(repo, empresa_id) is None

    # Llegan 6 más después del recordatorio: vuelven a contar, con su fecha.
    otra = await _vacante(db, empresa_id)
    await _llenar(db, otra, 6)
    nueva = await _de(repo, empresa_id)
    assert nueva is not None
    assert nueva.postulados == 6
    assert nueva.recordado_en is not None
