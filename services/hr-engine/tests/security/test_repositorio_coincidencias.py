"""El SQL del worker de coincidencias contra Postgres real (migración 0010, ADR-019).

El worker corre con el rol dueño y sin contexto de tenant: recorre todas las
empresas gratuitas. Estos tests fijan qué toma como pendiente y que solo guarda lo
que sigue vigente.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.application.coincidir_cvs import CoincidirCvsPendientes
from app.domain.entidades import CvPendiente
from app.infrastructure.coincidencias import ExtractorDeTextoDeCv, SqlRepositorioDeCoincidencias
from app.repositories import coincidencias as repo
from tests.unit.fakes import AlmacenEnMemoria
from tests.unit.test_adaptadores_coincidencias import _pdf

from .conftest import _asyncpg_dsn, assume_tenant
from .test_gancho import _aplicaciones, _coincidencias, _como_dueno, _resumen, _skills
from .test_plan_gratis import _empresa, _vacante

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def sesion(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    """La sesión del worker: rol dueño, sin contexto de tenant."""
    motor = create_async_engine(
        _asyncpg_dsn().replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool
    )
    async with AsyncSession(motor) as s:
        yield s
    await motor.dispose()


async def _pendientes(sesion: AsyncSession) -> set[str]:
    return {str(p.application_id) for p in await repo.pendientes(sesion, 10_000)}


async def _vacante_con_cvs(
    db: asyncpg.Connection, skills: list[str], total: int, *, plan: str = "gratis", **kw: bool
) -> tuple[str, str, list[str]]:
    empresa_id = await _empresa(db, plan=plan)
    vacante_id = await _vacante(db, empresa_id)
    await _skills(db, empresa_id, vacante_id, skills)
    return empresa_id, vacante_id, await _aplicaciones(db, empresa_id, vacante_id, total, **kw)


async def test_pendientes_son_solo_los_que_el_gancho_necesita(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, vacante_id, (nuevo, ilegible, al_dia, desfasado) = await _vacante_con_cvs(
        db, ["Python"], 4
    )
    (sin_cv,) = await _aplicaciones(db, empresa_id, vacante_id, 1, con_cv=False)
    (opuesto,) = await _aplicaciones(db, empresa_id, vacante_id, 1, sin_ia=True)
    await _como_dueno(
        db,
        "insert into privado.cvs_ilegibles (application_id, empresa_id) values ($1::uuid, $2::uuid)",
        ilegible,
        empresa_id,
    )
    await _coincidencias(db, empresa_id, [al_dia], ["Python"], [["Python"]])
    # Calculado con las skills de antes: hay que recalcularlo.
    await _coincidencias(db, empresa_id, [desfasado], ["Java"], [["Java"]])

    _, _, (con_ia,) = await _vacante_con_cvs(db, ["Python"], 1, plan="ia")
    _, _, (sin_skills,) = await _vacante_con_cvs(db, [], 1)
    cerrada_empresa, cerrada, (de_cerrada,) = await _vacante_con_cvs(db, ["Python"], 1)
    await assume_tenant(db, cerrada_empresa)
    await db.execute("update vacantes set status = 'closed' where id = $1::uuid", cerrada)

    pendientes = await _pendientes(sesion)
    assert {nuevo, desfasado} <= pendientes
    assert not {ilegible, al_dia, sin_cv, opuesto, con_ia, sin_skills, de_cerrada} & pendientes

    (fila,) = [p for p in await repo.pendientes(sesion, 10_000) if str(p.application_id) == nuevo]
    assert (str(fila.empresa_id), fila.skills) == (empresa_id, ["Python"])
    assert fila.ruta.startswith(f"{empresa_id}/")


async def test_guarda_solo_si_la_vacante_sigue_pidiendo_esas_skills(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, vacante_id, (cv,) = await _vacante_con_cvs(db, ["Python", "SQL"], 1)
    await repo.marcar_ilegible(sesion, application_id=UUID(cv), empresa_id=UUID(empresa_id))
    await sesion.commit()

    # La empresa cambió las skills mientras se leía el CV.
    assert not await repo.guardar(
        sesion, application_id=UUID(cv), skills=["Python"], encontradas=["Python"]
    )
    assert await repo.guardar(
        sesion, application_id=UUID(cv), skills=["Python", "SQL"], encontradas=["SQL"]
    )
    await sesion.commit()

    fila = await _como_dueno(
        db,
        "select encontradas from privado.coincidencias where application_id = $1::uuid",
        cv,
    )
    assert fila == ["SQL"]
    # Guardarla quita la marca de ilegible que el caso de uso pone antes de leer.
    ilegibles = "select count(*) from privado.cvs_ilegibles where application_id = $1::uuid"
    assert await _como_dueno(db, ilegibles, cv) == 0
    assert cv not in await _pendientes(sesion)
    assert vacante_id


async def test_no_guarda_la_de_un_candidato_que_se_opuso(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    _, _, (cv,) = await _vacante_con_cvs(db, ["Python"], 1, sin_ia=True)
    assert not await repo.guardar(
        sesion, application_id=UUID(cv), skills=["Python"], encontradas=["Python"]
    )


async def test_marcar_y_desmarcar_ilegible_se_pueden_repetir(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, _, (cv,) = await _vacante_con_cvs(db, ["Python"], 1)
    for _ in range(2):
        await repo.marcar_ilegible(sesion, application_id=UUID(cv), empresa_id=UUID(empresa_id))
    await sesion.commit()
    assert cv not in await _pendientes(sesion)
    for _ in range(2):
        await repo.desmarcar_ilegible(sesion, application_id=UUID(cv))
    await sesion.commit()
    assert cv in await _pendientes(sesion)


async def test_purgar_borra_lo_de_vacantes_cerradas_hace_mas_de_los_dias(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, vacante_id, (cv,) = await _vacante_con_cvs(db, ["Python"], 1)
    await _coincidencias(db, empresa_id, [cv], ["Python"], [["Python"]])
    await assume_tenant(db, empresa_id)
    await db.execute("update vacantes set status = 'closed' where id = $1::uuid", vacante_id)
    await _como_dueno(
        db,
        "update vacantes set closed_at = now() - interval '31 days' where id = $1::uuid",
        vacante_id,
    )

    assert await repo.purgar(sesion, dias=30) >= 1
    await sesion.commit()
    contar = "select count(*) from privado.coincidencias where application_id = $1::uuid"
    assert await _como_dueno(db, contar, cv) == 0


async def test_de_cv_pendiente_al_gancho_con_un_pdf_de_verdad(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    """Todo el camino: el SQL del worker, pypdf y el resumen que ve la empresa."""
    skills = ["Python", "SQL", "Docker"]
    empresa_id, vacante_id, _ = await _vacante_con_cvs(db, skills, 5)

    class SoloEstaEmpresa(SqlRepositorioDeCoincidencias):
        """Las demás pruebas también dejan CVs pendientes: este barrido no los toca."""

        async def pendientes(self, limite: int) -> list[CvPendiente]:
            todos = await super().pendientes(10_000)
            return [p for p in todos if str(p.empresa_id) == empresa_id][:limite]

    relleno = "Analista con experiencia en proyectos de datos para clientes de la region."
    menciones = ["Python, SQL y Docker", "Python y SQL", "Python", "Excel", "SQL y Docker"]
    pendientes = await SoloEstaEmpresa(sesion).pendientes(10)
    almacen = AlmacenEnMemoria(
        cvs={
            cv.ruta: _pdf(texto, relleno, relleno)
            for cv, texto in zip(pendientes, menciones, strict=True)
        }
    )

    caso = CoincidirCvsPendientes(SoloEstaEmpresa(sesion), almacen, ExtractorDeTextoDeCv())
    assert (await caso.ejecutar(lote=10)).revisados == 5

    fila = await _resumen(db, empresa_id, vacante_id)
    assert (fila["revisados"], fila["en_espera"], fila["con_la_mayoria"], fila["con_todas"]) == (
        5,
        0,
        3,
        1,
    )
