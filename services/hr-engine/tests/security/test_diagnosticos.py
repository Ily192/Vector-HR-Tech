"""El diagnóstico gratuito contra Postgres real (migración 0017).

`anon` solo puede registrar un diagnóstico por `registrar_diagnostico()`: no lee,
no cambia ni borra ninguno, y los frenos (3 por correo y 5 por IP en una hora, 300
en 24 horas) valen en la base. Al final, el SQL del barrido del aviso, con el rol
dueño como el worker.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.application.avisar_diagnosticos import AvisarDiagnosticos
from app.infrastructure.diagnosticos import SqlRepositorioDeDiagnosticos
from tests.unit.fakes import CorreoFalso, VerificadorFalso

from .conftest import EMPRESA_VECTOR, _asyncpg_dsn, assume_anon, assume_tenant
from .test_rls import _drop, _elevate

pytestmark = pytest.mark.asyncio

RESULTADO = {
    "version": 1,
    "procesos": [
        {
            "id": "nomina",
            "nombre": "Nómina",
            "horasSemana": 12,
            "etapa": "Automatizar",
            "horasRecuperablesMes": 31.2,
        },
    ],
    "horasRecuperablesMes": 31.2,
    "horasRecuperablesAnio": 374.4,
}


def _ip() -> str:
    return f"198.51.100.{uuid.uuid4().int % 250 + 1}-{uuid.uuid4().hex[:6]}"


def _correo() -> str:
    return f"prospecto-{uuid.uuid4().hex[:8]}@empresa.test"


def _parametros(**cambios: Any) -> dict[str, Any]:
    parametros: dict[str, Any] = {
        "p_nombre": "Mariana Ruiz",
        "p_empresa": "Andes Logística",
        "p_correo": _correo(),
        "p_origen": "linkedin",
        "p_utm_medium": "cpc",
        "p_utm_campaign": "diagnostico-octubre",
        "p_respuestas": {"p1": "a", "p2": ["b", "c"]},
        "p_resultado": RESULTADO,
        "p_horas_recuperables_mes": 31.2,
        "p_turnstile_token": "token-de-turnstile",
        "p_sin_fines_comerciales": False,
    }
    parametros.update(cambios)
    return parametros


async def _registrar(db: asyncpg.Connection, ip: str | None = None, **cambios: Any) -> None:
    """Como lo hace PostgREST con la clave pública: rol `anon` y las cabeceras de la
    petición en `request.headers`, con CF-Connecting-IP en minúsculas."""
    p = _parametros(**cambios)
    await assume_anon(db)
    cabeceras = {"cf-connecting-ip": ip or _ip(), "content-type": "application/json"}
    await db.execute("select set_config('request.headers', $1, false)", json.dumps(cabeceras))
    await db.execute(
        """
        select public.registrar_diagnostico(
            p_nombre => $1, p_empresa => $2, p_correo => $3, p_origen => $4,
            p_utm_medium => $5, p_utm_campaign => $6, p_respuestas => $7::jsonb,
            p_resultado => $8::jsonb, p_horas_recuperables_mes => $9::numeric,
            p_turnstile_token => $10, p_sin_fines_comerciales => $11)
        """,
        p["p_nombre"],
        p["p_empresa"],
        p["p_correo"],
        p["p_origen"],
        p["p_utm_medium"],
        p["p_utm_campaign"],
        None if p["p_respuestas"] is None else json.dumps(p["p_respuestas"]),
        None if p["p_resultado"] is None else json.dumps(p["p_resultado"]),
        None if p["p_horas_recuperables_mes"] is None else str(p["p_horas_recuperables_mes"]),
        p["p_turnstile_token"],
        p["p_sin_fines_comerciales"],
    )


async def _fila(db: asyncpg.Connection, correo: str) -> asyncpg.Record:
    await _elevate(db)
    try:
        filas = await db.fetch("select * from privado.diagnosticos where correo = $1", correo)
    finally:
        await _drop(db)
    assert len(filas) == 1
    return filas[0]


# ─────────────────────────────── anon registra ───────────────────────────────


async def test_anon_registra_un_diagnostico(db: asyncpg.Connection) -> None:
    correo = _correo()
    await _registrar(
        db,
        ip="203.0.113.7",
        p_nombre="  Mariana Ruiz  ",
        p_empresa=" Andes Logística ",
        p_correo=f"  {correo.upper()} ",
        p_origen="  ",
        p_horas_recuperables_mes=31.25,
    )

    fila = await _fila(db, correo)
    assert (fila["nombre"], fila["empresa"], fila["correo"]) == (
        "Mariana Ruiz",
        "Andes Logística",
        correo,
    )
    # Vacío es null, y las horas con un decimal.
    assert fila["origen"] is None
    assert (fila["utm_medium"], fila["utm_campaign"]) == ("cpc", "diagnostico-octubre")
    assert str(fila["horas_recuperables_mes"]) in {"31.2", "31.3"}
    assert json.loads(fila["resultado"]) == RESULTADO
    # La IP sale de la cabecera, nunca de los argumentos.
    assert fila["ip"] == "203.0.113.7"
    assert fila["turnstile_token"] == "token-de-turnstile"
    assert (fila["avisado_en"], fila["descartado_en"], fila["verificado_en"]) == (None, None, None)
    assert fila["intentos_aviso"] == 0
    assert fila["sin_fines_comerciales"] is False


@pytest.mark.parametrize(("marcada", "guardada"), [(True, True), (False, False), (None, False)])
async def test_la_casilla_de_no_contactar_se_guarda_y_null_es_false(
    db: asyncpg.Connection, marcada: bool | None, guardada: bool
) -> None:
    correo = _correo()
    await _registrar(db, p_correo=correo, p_sin_fines_comerciales=marcada)
    assert (await _fila(db, correo))["sin_fines_comerciales"] is guardada


async def test_sin_el_parametro_de_la_casilla_tambien_se_registra(db: asyncpg.Connection) -> None:
    """El parámetro tiene default: una llamada sin él no rompe."""
    correo = _correo()
    await assume_anon(db)
    await db.execute(
        "select set_config('request.headers', $1, false)",
        json.dumps({"cf-connecting-ip": _ip()}),
    )
    await db.execute(
        "select public.registrar_diagnostico(p_nombre => 'Ana', p_empresa => 'ACME',"
        " p_correo => $1, p_origen => null, p_utm_medium => null, p_utm_campaign => null,"
        " p_respuestas => '{}', p_resultado => '{}', p_horas_recuperables_mes => 1,"
        " p_turnstile_token => null)",
        correo,
    )
    assert (await _fila(db, correo))["sin_fines_comerciales"] is False


async def test_sin_utm_ni_token_tambien_se_registra(db: asyncpg.Connection) -> None:
    correo = _correo()
    await _registrar(
        db,
        p_correo=correo,
        p_origen=None,
        p_utm_medium=None,
        p_utm_campaign=None,
        p_turnstile_token=None,
    )
    fila = await _fila(db, correo)
    assert (fila["origen"], fila["utm_medium"], fila["turnstile_token"]) == (None, None, None)


@pytest.mark.parametrize(
    "cambios",
    [
        {"p_nombre": "   "},
        {"p_nombre": None},
        {"p_nombre": "x" * 121},
        {"p_empresa": ""},
        {"p_empresa": "x" * 161},
        {"p_correo": "no-es-un-correo"},
        {"p_correo": "dos@@x.test"},
        {"p_correo": "con espacio@x.test"},
        {"p_correo": "a@" + "x" * 250 + ".test"},
        {"p_origen": "x" * 65},
        {"p_utm_medium": "x" * 65},
        {"p_utm_campaign": "x" * 121},
        {"p_respuestas": None},
        {"p_respuestas": ["no", "es", "objeto"]},
        {"p_respuestas": {"relleno": "x" * 17_000}},
        {"p_resultado": "texto"},
        {"p_resultado": {"relleno": "x" * 17_000}},
        {"p_horas_recuperables_mes": None},
        {"p_horas_recuperables_mes": -1},
        {"p_horas_recuperables_mes": 10_000.1},
        {"p_turnstile_token": "x" * 2049},
    ],
)
async def test_lo_invalido_se_rechaza_sin_decir_que(
    db: asyncpg.Connection, cambios: dict[str, Any]
) -> None:
    with pytest.raises(asyncpg.PostgresError) as exc:
        await _registrar(db, **cambios)
    assert exc.value.sqlstate == "22023"
    assert str(exc.value) == "diagnóstico inválido"


# ─────────────────────────────── nadie más entra ───────────────────────────────


@pytest.mark.parametrize(
    "sql",
    [
        "select * from privado.diagnosticos",
        "insert into privado.diagnosticos (nombre, empresa, correo, respuestas, resultado,"
        " horas_recuperables_mes) values ('a', 'b', 'c@d.test', '{}', '{}', 1)",
        "update privado.diagnosticos set avisado_en = now()",
        "delete from privado.diagnosticos",
    ],
)
@pytest.mark.parametrize("rol", ["anon", "authenticated"])
async def test_anon_y_authenticated_no_tocan_la_tabla(
    db: asyncpg.Connection, sql: str, rol: str
) -> None:
    await _registrar(db)
    if rol == "anon":
        await assume_anon(db)
    else:
        await assume_tenant(db, EMPRESA_VECTOR, role="SuperAdmin")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.execute(sql)


async def test_la_tabla_no_esta_en_public(db: asyncpg.Connection) -> None:
    """PostgREST solo expone `public`: en `privado` no hay ruta /rest/v1/diagnosticos."""
    assert await db.fetchval("select to_regclass('public.diagnosticos')") is None


async def test_solo_anon_puede_ejecutar_la_rpc(db: asyncpg.Connection) -> None:
    firma = (
        "public.registrar_diagnostico(text, text, text, text, text, text, jsonb, jsonb,"
        " numeric, text, boolean)"
    )
    await _elevate(db)
    try:
        permisos = {
            rol: await db.fetchval("select has_function_privilege($1, $2, 'execute')", rol, firma)
            for rol in ("anon", "authenticated", "public")
        }
    finally:
        await _drop(db)
    assert permisos == {"anon": True, "authenticated": False, "public": False}

    await assume_tenant(db, EMPRESA_VECTOR)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.execute(
            f"select {firma.split('(')[0]}('a', 'b', 'c@d.test', null, null, null,"
            " '{}', '{}', 1, null, false)"
        )


# ─────────────────────────────────── frenos ───────────────────────────────────


async def test_mas_de_3_del_mismo_correo_en_una_hora_se_frenan(db: asyncpg.Connection) -> None:
    correo = _correo()
    for _ in range(3):
        await _registrar(db, p_correo=correo)
    with pytest.raises(asyncpg.PostgresError) as exc:
        # Aunque cambie la IP y las mayúsculas.
        await _registrar(db, p_correo=correo.upper())
    assert exc.value.sqlstate == "PT429"
    assert str(exc.value) == "demasiados diagnósticos; intenta más tarde"

    # Otro correo sigue pudiendo.
    await _registrar(db)


async def test_los_de_hace_mas_de_una_hora_no_cuentan(db: asyncpg.Connection) -> None:
    correo = _correo()
    for _ in range(3):
        await _registrar(db, p_correo=correo)
    await _elevate(db)
    await db.execute(
        "update privado.diagnosticos set creado_en = now() - interval '61 minutes'"
        " where correo = $1",
        correo,
    )
    await _drop(db)
    await _registrar(db, p_correo=correo)


async def test_mas_de_5_desde_la_misma_ip_en_una_hora_se_frenan(db: asyncpg.Connection) -> None:
    ip = _ip()
    for _ in range(5):
        await _registrar(db, ip=ip)
    with pytest.raises(asyncpg.PostgresError) as exc:
        await _registrar(db, ip=ip)
    assert exc.value.sqlstate == "PT429"
    await _registrar(db)


async def test_mas_de_300_en_un_dia_se_frenan(db: asyncpg.Connection) -> None:
    await _elevate(db)
    marca = f"relleno-{uuid.uuid4().hex[:8]}"
    try:
        await db.execute(
            """
            insert into privado.diagnosticos
                (nombre, empresa, correo, respuestas, resultado, horas_recuperables_mes,
                 creado_en)
            select 'Relleno', $1, 'r' || g || '@relleno.test', '{}', '{}', 0,
                   now() - interval '2 hours'
              from generate_series(1, 300 - (select count(*) from privado.diagnosticos
                                              where creado_en > now() - interval '1 day')) g
            """,
            marca,
        )
        await _drop(db)
        with pytest.raises(asyncpg.PostgresError) as exc:
            await _registrar(db)
        assert exc.value.sqlstate == "PT429"
    finally:
        await _elevate(db)
        await db.execute("delete from privado.diagnosticos where empresa = $1", marca)
        await _drop(db)
    await _registrar(db)


# ─────────────────────────── el barrido del aviso ───────────────────────────


@pytest_asyncio.fixture
async def sesion(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    """La sesión del worker: rol dueño."""
    motor = create_async_engine(
        _asyncpg_dsn().replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool
    )
    async with AsyncSession(motor) as s:
        yield s
    await motor.dispose()


async def _sin_pendientes(db: asyncpg.Connection) -> None:
    """Lo que dejaron los otros tests no entra en el barrido de este."""
    await _elevate(db)
    await db.execute(
        "update privado.diagnosticos set descartado_en = now()"
        " where avisado_en is null and descartado_en is null"
    )
    await _drop(db)


async def test_el_barrido_avisa_descarta_y_no_vuelve_a_tomar_lo_hecho(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    await _sin_pendientes(db)
    bueno, bot, agotado = _correo(), _correo(), _correo()
    await _registrar(db, p_correo=bueno, p_turnstile_token="bueno", p_sin_fines_comerciales=True)
    await _registrar(db, p_correo=bot, p_turnstile_token="bot")
    await _registrar(db, p_correo=agotado, p_turnstile_token="bueno")
    await _elevate(db)
    await db.execute(
        "update privado.diagnosticos set intentos_aviso = 5 where correo = $1", agotado
    )
    await _drop(db)

    correo = CorreoFalso()
    caso = AvisarDiagnosticos(
        SqlRepositorioDeDiagnosticos(sesion),
        VerificadorFalso({"bueno"}),
        correo,
        para="hola@vectorhrtech.com",
        max_por_dia=1000,
    )
    resultado = await caso.ejecutar()

    assert (resultado.avisados, resultado.descartados) == (1, 1)
    assert bueno in correo.enviados[0].cuerpo
    # El repositorio lee la casilla y el aviso la dice.
    assert "Contacto comercial: NO" in correo.enviados[0].cuerpo
    fila_buena, fila_bot, fila_agotada = (
        await _fila(db, bueno),
        await _fila(db, bot),
        await _fila(db, agotado),
    )
    assert fila_buena["avisado_en"] is not None and fila_buena["verificado_en"] is not None
    assert fila_bot["descartado_en"] is not None and fila_bot["avisado_en"] is None
    assert fila_agotada["avisado_en"] is None and fila_agotada["verificado_en"] is None

    # El siguiente barrido no tiene nada que hacer.
    assert (await caso.ejecutar()).avisados == 0
    assert len(correo.enviados) == 1


async def test_si_el_correo_falla_suma_un_intento_y_guarda_la_verificacion(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    await _sin_pendientes(db)
    correo = _correo()
    await _registrar(db, p_correo=correo, p_turnstile_token="bueno")

    await AvisarDiagnosticos(
        SqlRepositorioDeDiagnosticos(sesion),
        VerificadorFalso({"bueno"}),
        CorreoFalso(disponible=False),
        para="hola@vectorhrtech.com",
        max_por_dia=1000,
    ).ejecutar()

    fila = await _fila(db, correo)
    assert fila["intentos_aviso"] == 1
    assert fila["avisado_en"] is None
    assert fila["verificado_en"] is not None


async def test_dos_barridos_a_la_vez_no_toman_los_mismos(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    await _sin_pendientes(db)
    for _ in range(3):
        await _registrar(db)

    motor = create_async_engine(
        _asyncpg_dsn().replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool
    )
    try:
        async with AsyncSession(motor) as otra:
            primero = await SqlRepositorioDeDiagnosticos(sesion).reclamar(2)
            segundo = await SqlRepositorioDeDiagnosticos(otra).reclamar(10)
            assert len(primero) == 2
            assert len(segundo) == 1
            assert not {d.id for d in primero} & {d.id for d in segundo}
            await otra.rollback()
        await sesion.rollback()
    finally:
        await motor.dispose()


async def test_avisados_hoy_cuenta_desde_la_medianoche_utc(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    repo = SqlRepositorioDeDiagnosticos(sesion)
    antes = await repo.avisados_hoy()
    hoy, ayer = _correo(), _correo()
    await _registrar(db, p_correo=hoy)
    await _registrar(db, p_correo=ayer)
    await _elevate(db)
    await db.execute("update privado.diagnosticos set avisado_en = now() where correo = $1", hoy)
    await db.execute(
        "update privado.diagnosticos set avisado_en = date_trunc('day', now()) - interval '1 second'"
        " where correo = $1",
        ayer,
    )
    await _drop(db)
    await sesion.rollback()
    assert await repo.avisados_hoy() == antes + 1
