"""El alta desde la web contra Postgres real (0001, 0003, 0008, 0009 y 0018).

- `privado.altas_web` no la ve nadie de la API: ni anon ni authenticated.
- El código de alta crea la cuenta como lo hace Auth (`/otp` con `data`), y
  `handle_new_user` la liga a la empresa con el token de la invitación.
- Un `lead_id` repetido no crea otra empresa.
- La limpieza solo ve las empresas que nadie confirmó, y nunca una con vacantes
  o con alguien que ya escribió su código.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.application.alta_desde_la_web import DarDeAltaDesdeLaWeb
from app.domain.alta_web import SolicitudDeAltaWeb
from app.infrastructure.altas import SqlRepositorioDeAltas
from app.infrastructure.altas_web import SqlRepositorioDeAltasWeb

from .conftest import _asyncpg_dsn, assume_anon, assume_tenant
from .test_gancho import _como_dueno
from .test_rls import _drop, _elevate

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


def _solicitud(**cambios: object) -> SolicitudDeAltaWeb:
    marca = uuid4().hex[:8]
    datos: dict[str, object] = {
        "lead_id": f"lead-{marca}",
        "nombre": "Ana Ruiz",
        "correo": f"ana-{marca}@ferreterianorte.test",
        "publica_para": "propia",
        "empresa": f"Ferretería Norte {marca}",
        "cargo": "Jefa de RH",
        "web_empresa": "https://ferreterianorte.test",
        "linkedin": None,
        "verificacion": "dominio",
        "pais": "mx",
        "tamano": "51-200",
        "sector": "comercio",
        "contrataciones_mes": "3-5",
        "puestos": ["ventas", "operativos"],
        "ip": "203.0.113.7",
    }
    return SolicitudDeAltaWeb.nueva(**{**datos, **cambios})  # type: ignore[arg-type]


class AuthDelCodigo:
    """Lo que hace Auth con `POST /otp` y `create_user`: crea el usuario con `data`
    como metadata, y `on_auth_user_created` corre `handle_new_user` en la misma
    sentencia. La cuenta queda sin confirmar hasta que se escribe el código."""

    def __init__(self, db: asyncpg.Connection) -> None:
        self._db = db
        self.usuarios: dict[str, str] = {}
        self.entradas: list[str] = []

    async def mandar_codigo_de_alta(
        self, correo: str, token: str, nombre: str, ip: str | None
    ) -> None:
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

    async def mandar_codigo_de_entrada(self, correo: str, ip: str | None) -> None:
        self.entradas.append(correo)

    async def borrar_usuario(self, usuario_id: UUID) -> None:
        await _como_dueno(self._db, "delete from auth.users where id = $1::uuid", str(usuario_id))


class SinTope:
    async def consumir(self, ip_hash: str | None, correo: str) -> None:
        return None


def _caso(sesion: AsyncSession, auth: AuthDelCodigo) -> DarDeAltaDesdeLaWeb:
    return DarDeAltaDesdeLaWeb(
        SqlRepositorioDeAltas(sesion),
        SqlRepositorioDeAltasWeb(sesion),
        auth,
        SinTope(),
        "https://panel.vectorhrtech.com",
    )


async def _fila(db: asyncpg.Connection, sql: str, *args: object) -> asyncpg.Record | None:
    await _elevate(db)
    try:
        return await db.fetchrow(sql, *args)
    finally:
        await _drop(db)


async def test_la_api_no_ve_las_altas(db: asyncpg.Connection) -> None:
    await assume_anon(db)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await db.fetch("select * from privado.altas_web")
    await assume_tenant(db, str(uuid4()))
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await db.fetch("select * from privado.altas_web")
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await db.execute(
            "insert into privado.altas_web (lead_id, correo, publica_para, verificacion, pais,"
            " sector, contrataciones_mes) values ('x', 'a@b.c', 'propia', 'dominio', 'mx',"
            " 'otro', '0')"
        )


async def test_el_codigo_de_alta_liga_la_cuenta_a_su_empresa(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    auth = AuthDelCodigo(db)
    solicitud = _solicitud()
    respuesta = await _caso(sesion, auth).ejecutar(solicitud, "hash-de-la-ip")
    assert respuesta.estado == "codigo_enviado"

    fila = await _fila(
        db,
        "select a.resultado, a.ip_hash, a.web_empresa, a.tamano, a.puestos,"
        " e.plan::text, e.tamano_empleados, public.limite_de_vacantes(e.id),"
        " p.role::text, p.full_name, a.empresa_id = p.empresa_id"
        " from privado.altas_web a"
        " join public.empresas e on e.id = a.empresa_id"
        " join public.profiles p on p.id = $2::uuid"
        " where a.lead_id = $1",
        solicitud.lead_id,
        auth.usuarios[solicitud.correo],
    )
    assert fila is not None
    assert tuple(fila) == (
        "empresa_creada",
        "hash-de-la-ip",
        "https://ferreterianorte.test",
        "51-200",
        ["ventas", "operativos"],
        "gratis",
        51,
        4,
        "HR",
        "Ana Ruiz",
        True,
    )


async def test_un_lead_repetido_no_crea_otra_empresa(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    auth = AuthDelCodigo(db)
    solicitud = _solicitud()
    await _caso(sesion, auth).ejecutar(solicitud, None)
    await _caso(sesion, auth).ejecutar(solicitud, None)

    cuantas = await _fila(
        db,
        "select count(*) from public.empresas where name = $1",
        solicitud.alta.empresa,
    )
    assert cuantas is not None and cuantas[0] == 1
    assert len(auth.usuarios) == 1


async def test_con_cuenta_no_crea_empresa_y_lo_anota(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    auth = AuthDelCodigo(db)
    primera = _solicitud()
    await _caso(sesion, auth).ejecutar(primera, None)
    otra = _solicitud(correo=primera.correo)
    await _caso(sesion, auth).ejecutar(otra, None)

    assert auth.entradas == [primera.correo]
    fila = await _fila(
        db,
        "select resultado, empresa_id from privado.altas_web where lead_id = $1",
        otra.lead_id,
    )
    assert fila is not None and tuple(fila) == ("cuenta_existente", None)


async def _alta_vieja(db: asyncpg.Connection, sesion: AsyncSession) -> tuple[UUID, str]:
    auth = AuthDelCodigo(db)
    solicitud = _solicitud()
    await _caso(sesion, auth).ejecutar(solicitud, None)
    empresa_id = await _como_dueno(
        db,
        "update privado.altas_web set creado_en = now() - interval '8 days'"
        " where lead_id = $1 returning empresa_id",
        solicitud.lead_id,
    )
    return UUID(str(empresa_id)), auth.usuarios[solicitud.correo]


async def test_la_limpieza_solo_ve_las_que_nadie_confirmo(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    repositorio = SqlRepositorioDeAltasWeb(sesion)
    olvidada, usuario_olvidado = await _alta_vieja(db, sesion)
    confirmada, usuario_confirmado = await _alta_vieja(db, sesion)
    con_vacante, _ = await _alta_vieja(db, sesion)
    reciente = _solicitud()
    await _caso(sesion, AuthDelCodigo(db)).ejecutar(reciente, None)

    await _como_dueno(
        db,
        "update auth.users set email_confirmed_at = now() where id = $1::uuid",
        usuario_confirmado,
    )
    await _como_dueno(
        db,
        "insert into public.vacantes (empresa_id, slug, title, jd, status)"
        " values ($1::uuid, 'vacante', 'Vacante', 'Descripción', 'draft')",
        str(con_vacante),
    )

    assert await repositorio.marcar_confirmadas() >= 1
    pendientes = await repositorio.pendientes_desde(datetime.now(UTC) - timedelta(days=7))
    por_empresa = {p.empresa_id: p.usuarios for p in pendientes}
    assert por_empresa.get(olvidada) == (UUID(usuario_olvidado),)
    assert confirmada not in por_empresa
    assert con_vacante not in por_empresa

    confirmado_en = await _fila(
        db, "select confirmado_en from privado.altas_web where empresa_id = $1::uuid", confirmada
    )
    assert confirmado_en is not None and confirmado_en[0] is not None

    await repositorio.borrar_empresa(olvidada)
    restantes = await _fila(
        db,
        "select (select count(*) from public.empresas where id = $1::uuid),"
        " (select count(*) from privado.altas_web where empresa_id = $1::uuid),"
        " (select count(*) from public.invitations where empresa_id = $1::uuid)",
        olvidada,
    )
    assert restantes is not None and tuple(restantes) == (0, 0, 0)
