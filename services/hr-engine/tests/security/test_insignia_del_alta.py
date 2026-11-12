"""La insignia de la empresa al confirmar el código del alta desde la web (ADR-022).

El alta (0018, PR 1) crea la empresa y una cuenta sin confirmar. Cuando la persona
escribe el código, Auth pone `email_confirmed_at`, y `ConfirmarAltasDeLaWeb` —en
cada barrido de la moderación y antes de la limpieza de 7 días— lo traduce en la
insignia y en `altas_web.confirmado_en`, la misma marca que lee la limpieza.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.application.moderar_vacantes import ModerarVacantesPendientes
from app.application.verificar_empresa import ConfirmarAltasDeLaWeb, VerificarEmpresa
from app.infrastructure.altas_web import SqlRepositorioDeAltasWeb
from app.infrastructure.moderacion import SqlRepositorioDeModeracion

from .conftest import _asyncpg_dsn, assume_tenant
from .test_altas_web import AuthDelCodigo, _caso, _fila, _solicitud
from .test_gancho import _como_dueno

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def sesion(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    """La sesión del hr-engine: rol dueño, sin contexto de tenant."""
    motor = create_async_engine(
        _asyncpg_dsn().replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool
    )
    async with AsyncSession(motor) as s:
        yield s
    await motor.dispose()


def _confirmar(sesion: AsyncSession) -> ConfirmarAltasDeLaWeb:
    return ConfirmarAltasDeLaWeb(
        SqlRepositorioDeAltasWeb(sesion), VerificarEmpresa(SqlRepositorioDeModeracion(sesion))
    )


async def _alta(
    db: asyncpg.Connection, sesion: AsyncSession, **cambios: object
) -> tuple[UUID, str]:
    """Un alta desde la web, sin confirmar: devuelve su empresa y su usuario."""
    auth = AuthDelCodigo(db)
    solicitud = _solicitud(**cambios)
    await _caso(sesion, auth).ejecutar(solicitud, None)
    fila = await _fila(
        db, "select empresa_id from privado.altas_web where lead_id = $1", solicitud.lead_id
    )
    assert fila is not None
    return UUID(str(fila["empresa_id"])), auth.usuarios[solicitud.correo]


async def _escribe_el_codigo(db: asyncpg.Connection, usuario: str) -> None:
    await _como_dueno(
        db, "update auth.users set email_confirmed_at = now() where id = $1::uuid", usuario
    )


async def _empresa(db: asyncpg.Connection, empresa_id: UUID) -> asyncpg.Record:
    fila = await _fila(
        db,
        "select e.verificada, e.verificada_en, e.publica_para, e.web, e.linkedin,"
        " a.confirmado_en"
        " from public.empresas e join privado.altas_web a on a.empresa_id = e.id"
        " where e.id = $1::uuid",
        empresa_id,
    )
    assert fila is not None
    return fila


async def test_sin_escribir_el_codigo_no_hay_insignia_ni_marca(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, _ = await _alta(db, sesion)
    await _confirmar(sesion).ejecutar()
    fila = await _empresa(db, empresa_id)
    assert (fila["verificada"], fila["confirmado_en"], fila["web"]) == (False, None, None)


async def test_al_escribir_el_codigo_gana_la_insignia_si_el_dominio_coincide(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, usuario = await _alta(db, sesion)  # ana-…@ferreterianorte.test
    await _escribe_el_codigo(db, usuario)

    await _confirmar(sesion).ejecutar()

    fila = await _empresa(db, empresa_id)
    assert fila["verificada"] is True and fila["verificada_en"] is not None
    assert (fila["publica_para"], fila["web"]) == ("propia", "https://ferreterianorte.test")
    assert fila["confirmado_en"] is not None

    # La segunda vez ya está marcada: no la vuelve a tomar.
    vistas = await SqlRepositorioDeAltasWeb(sesion).confirmadas_sin_marcar(10_000)
    assert empresa_id not in {a.empresa_id for a in vistas}


async def test_con_gmail_guarda_sus_datos_sin_insignia(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, usuario = await _alta(
        db, sesion, correo="dueno.ferreteria@gmail.com", verificacion="revision"
    )
    await _escribe_el_codigo(db, usuario)
    await _confirmar(sesion).ejecutar()
    fila = await _empresa(db, empresa_id)
    assert (fila["verificada"], fila["web"]) == (False, "https://ferreterianorte.test")
    assert fila["confirmado_en"] is not None


async def test_un_reclutador_queda_como_tal_y_sin_insignia(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, usuario = await _alta(
        db,
        sesion,
        publica_para="clientes",
        tamano=None,
        verificacion="revision",
        linkedin="https://www.LinkedIn.com/in/ana-ruiz",
    )
    await _escribe_el_codigo(db, usuario)
    await _confirmar(sesion).ejecutar()
    fila = await _empresa(db, empresa_id)
    assert (fila["verificada"], fila["publica_para"]) == (False, "clientes")
    assert fila["linkedin"] == "https://www.LinkedIn.com/in/ana-ruiz"


async def test_la_limpieza_no_borra_una_confirmada_por_este_camino(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, usuario = await _alta(db, sesion)
    await _como_dueno(
        db,
        "update privado.altas_web set creado_en = now() - interval '8 days'"
        " where empresa_id = $1::uuid",
        str(empresa_id),
    )
    await _escribe_el_codigo(db, usuario)
    await _confirmar(sesion).ejecutar()
    pendientes = await SqlRepositorioDeAltasWeb(sesion).pendientes_desde(
        datetime.now(UTC) - timedelta(days=7)
    )
    assert empresa_id not in {p.empresa_id for p in pendientes}


async def test_su_primera_vacante_se_publica_sola(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    """De punta a punta: alta, código, insignia y la primera vacante, sin revisión."""
    empresa_id, usuario = await _alta(db, sesion)
    await _escribe_el_codigo(db, usuario)
    await _confirmar(sesion).ejecutar()

    await assume_tenant(db, str(empresa_id))
    vacante_id = await db.fetchval(
        "insert into vacantes (empresa_id, slug, title, jd, status)"
        " values ($1::uuid, 'ferreteria-' || gen_random_uuid(), 'Vendedor de mostrador',"
        " 'Atención en mostrador y control de inventario.', 'open') returning id",
        str(empresa_id),
    )
    await ModerarVacantesPendientes(SqlRepositorioDeModeracion(sesion)).ejecutar(lote=10_000)
    fila = await _fila(db, "select moderacion::text from vacantes where id = $1", vacante_id)
    assert fila is not None and fila["moderacion"] == "publicada"
