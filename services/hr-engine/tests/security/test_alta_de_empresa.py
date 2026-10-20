"""El alta de empresas contra Postgres real (0001, 0003, 0008).

La invitación que guarda el alta tiene que ser la que `handle_new_user` acepta
cuando Auth crea la cuenta: si el hash no coincide, la persona invitada no entra.
Aquí Auth se simula como lo hace: insertando en `auth.users` con el metadata.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.application.dar_de_alta_empresa import DarDeAltaEmpresa
from app.domain.alta import SolicitudDeAlta, hash_del_token
from app.infrastructure.altas import SqlRepositorioDeAltas

from .conftest import _asyncpg_dsn
from .test_gancho import _como_dueno
from .test_rls import _drop, _elevate

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def sesion(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    """La sesión del comando de alta: rol dueño, sin contexto de tenant."""
    motor = create_async_engine(
        _asyncpg_dsn().replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool
    )
    async with AsyncSession(motor) as s:
        yield s
    await motor.dispose()


def _solicitud(**cambios: object) -> SolicitudDeAlta:
    marca = uuid4().hex[:8]
    datos: dict[str, object] = {
        "empresa": f"Ferretería Norte {marca}",
        "correo": f"ana-{marca}@ferreterianorte.test",
        "nombre": "Ana Ruiz",
        "tamano": 80,
    }
    return SolicitudDeAlta.nueva(**{**datos, **cambios})  # type: ignore[arg-type]


class AuthQueCreaLaCuenta:
    """Lo que hace Supabase Auth al invitar: crea el usuario con el metadata, y el
    trigger `on_auth_user_created` corre `handle_new_user` en la misma sentencia."""

    def __init__(self, db: asyncpg.Connection) -> None:
        self._db = db
        self.usuarios: dict[str, str] = {}

    async def invitar(self, correo: str, token: str, nombre: str) -> None:
        usuario = str(uuid4())
        await _como_dueno(
            self._db,
            "insert into auth.users (id, email, raw_user_meta_data)"
            " values ($1::uuid, $2, jsonb_build_object('invite_token', $3::text,"
            " 'full_name', $4::text))",
            usuario,
            correo,
            token,
            nombre,
        )
        self.usuarios[correo] = usuario

    async def reenviar(self, correo: str) -> None:
        raise AssertionError("el alta no reenvía")


async def _fila(db: asyncpg.Connection, sql: str, *args: object) -> asyncpg.Record | None:
    await _elevate(db)
    try:
        return await db.fetchrow(sql, *args)
    finally:
        await _drop(db)


async def test_la_invitacion_del_alta_liga_la_cuenta_a_su_empresa(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    repositorio, auth = SqlRepositorioDeAltas(sesion), AuthQueCreaLaCuenta(db)
    solicitud = _solicitud(rol="Director")
    alta = await DarDeAltaEmpresa(repositorio, auth).ejecutar(solicitud)

    perfil = await _fila(
        db,
        "select empresa_id::text, role::text, full_name from public.profiles where id = $1::uuid",
        auth.usuarios[solicitud.correo],
    )
    assert perfil is not None
    assert tuple(perfil) == (str(alta.empresa_id), "Director", "Ana Ruiz")

    empresa = await _fila(
        db,
        "select plan::text, tamano_empleados, slug, public.limite_de_vacantes(id)"
        " from public.empresas where id = $1::uuid",
        alta.empresa_id,
    )
    assert empresa is not None
    assert tuple(empresa) == ("gratis", 80, alta.slug, 4)

    invitacion = await _fila(
        db,
        "select consumed_at is not null, consumed_by::text from public.invitations"
        " where empresa_id = $1::uuid",
        alta.empresa_id,
    )
    assert invitacion is not None
    assert tuple(invitacion) == (True, auth.usuarios[solicitud.correo])


async def test_el_estado_de_la_cuenta_sigue_a_auth(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    repositorio, auth = SqlRepositorioDeAltas(sesion), AuthQueCreaLaCuenta(db)
    solicitud = _solicitud()
    assert await repositorio.estado_de_la_cuenta(solicitud.correo) == "sin-cuenta"

    await DarDeAltaEmpresa(repositorio, auth).ejecutar(solicitud)
    assert await repositorio.estado_de_la_cuenta(solicitud.correo) == "pendiente"

    await _como_dueno(
        db,
        "update auth.users set email_confirmed_at = now() where id = $1::uuid",
        auth.usuarios[solicitud.correo],
    )
    assert await repositorio.estado_de_la_cuenta(solicitud.correo) == "confirmada"


async def test_un_slug_repetido_no_crea_empresa_ni_invitacion(sesion: AsyncSession) -> None:
    repositorio = SqlRepositorioDeAltas(sesion)
    primera, segunda = _solicitud(), _solicitud()
    slug = f"ferreteria-norte-{uuid4().hex[:8]}"

    assert await repositorio.crear_empresa_con_invitacion(primera, slug, hash_del_token("a"))
    assert (
        await repositorio.crear_empresa_con_invitacion(segunda, slug, hash_del_token("b")) is None
    )


async def test_deshacer_borra_la_empresa_y_su_invitacion(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    repositorio = SqlRepositorioDeAltas(sesion)
    solicitud = _solicitud()
    empresa_id = await repositorio.crear_empresa_con_invitacion(
        solicitud, f"ferreteria-norte-{uuid4().hex[:8]}", hash_del_token("c")
    )
    assert empresa_id is not None

    await repositorio.deshacer(empresa_id)
    restantes = await _fila(
        db,
        "select (select count(*) from public.empresas where id = $1::uuid),"
        " (select count(*) from public.invitations where email = $2)",
        empresa_id,
        solicitud.correo,
    )
    assert restantes is not None
    assert tuple(restantes) == (0, 0)
