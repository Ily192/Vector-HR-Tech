"""Moderación de vacantes en la base (migración 0019, ADR-022).

El panel escribe sus vacantes por PostgREST con la sesión del tenant: la base es la
que impide que una vacante sin moderar salga al career site, que la empresa se
dé la insignia o que se publique sola. Y el SQL del hr-engine (rol dueño) se prueba
aquí contra Postgres real.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.application.moderar_vacantes import ModerarVacantesPendientes, ResolverRevision
from app.application.verificar_empresa import VerificarEmpresa
from app.domain.moderacion import EstadoDeModeracion, decidir, evaluar
from app.infrastructure.moderacion import SqlRepositorioDeModeracion

from .conftest import _asyncpg_dsn, assume_anon, assume_tenant
from .test_plan_gratis import _como_soporte, _empresa
from .test_rls import _drop, _elevate, _make_user

pytestmark = pytest.mark.asyncio

SinPermiso = asyncpg.exceptions.InsufficientPrivilegeError
NoDisponible = asyncpg.exceptions.InvalidParameterValueError


@pytest_asyncio.fixture
async def sesion(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    """La sesión del hr-engine: rol dueño, sin contexto de tenant."""
    motor = create_async_engine(
        _asyncpg_dsn().replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool
    )
    async with AsyncSession(motor) as s:
        yield s
    await motor.dispose()


async def _del_panel(
    db: asyncpg.Connection,
    empresa_id: str,
    *,
    titulo: str = "Analista de inventarios",
    jd: str = "Controlarás el inventario del almacén.",
    moderacion: str = "publicada",
) -> str:
    """Una vacante abierta creada como el panel: con sesión de tenant."""
    await assume_tenant(db, empresa_id)
    return str(
        await db.fetchval(
            """
            insert into vacantes (empresa_id, slug, title, jd, status, moderacion,
                                  motivos_moderacion, moderada_en)
            values ($1::uuid, $2, $3, $4, 'open', $5::moderacion_vacante,
                    '[{"regla": "x"}]'::jsonb, now())
            returning id
            """,
            empresa_id,
            f"v-{uuid.uuid4()}",
            titulo,
            jd,
            moderacion,
        )
    )


async def _moderacion(db: asyncpg.Connection, vacante_id: str) -> asyncpg.Record:
    await _elevate(db)
    try:
        return await db.fetchrow(
            "select moderacion::text, motivos_moderacion, moderada_en from vacantes"
            " where id = $1::uuid",
            vacante_id,
        )
    finally:
        await _drop(db)


async def _como_dueno(db: asyncpg.Connection, sql: str, *args: Any) -> None:
    await _como_soporte(db, sql, *args)


# ─────────────────────── lo que el panel no puede hacer ───────────────────────


async def test_la_del_panel_nace_pendiente_aunque_pida_publicada(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id, moderacion="publicada")
    fila = await _moderacion(db, vacante_id)
    assert fila["moderacion"] == "pendiente"
    assert fila["moderada_en"] is None
    assert fila["motivos_moderacion"] == "[]"


async def test_el_panel_no_puede_publicarla(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    await assume_tenant(db, empresa_id)
    await db.execute(
        "update vacantes set moderacion = 'publicada', moderada_en = now() where id = $1::uuid",
        vacante_id,
    )
    assert (await _moderacion(db, vacante_id))["moderacion"] == "pendiente"


async def test_el_panel_lee_su_estado_y_sus_motivos(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    await _como_dueno(
        db,
        "update vacantes set moderacion = 'rechazada',"
        """ motivos_moderacion = '[{"regla": "pago", "senal": "Cobra"}]' where id = $1::uuid""",
        vacante_id,
    )
    await assume_tenant(db, empresa_id)
    fila = await db.fetchrow(
        "select moderacion::text, motivos_moderacion from vacantes where id = $1::uuid", vacante_id
    )
    assert fila["moderacion"] == "rechazada"
    assert '"regla": "pago"' in fila["motivos_moderacion"]


async def test_editar_lo_que_ve_el_candidato_la_vuelve_a_pendiente(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    await _como_dueno(
        db, "update vacantes set moderacion = 'publicada' where id = $1::uuid", vacante_id
    )

    await assume_tenant(db, empresa_id)
    await db.execute("update vacantes set skills = '{Excel}' where id = $1::uuid", vacante_id)
    assert (await _moderacion(db, vacante_id))["moderacion"] == "publicada"  # las skills no

    await assume_tenant(db, empresa_id)
    await db.execute("update vacantes set jd = 'Paga tu kit' where id = $1::uuid", vacante_id)
    assert (await _moderacion(db, vacante_id))["moderacion"] == "pendiente"


async def test_editar_una_oculta_no_la_saca_de_la_revision(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    await _como_dueno(
        db, "update vacantes set moderacion = 'oculta' where id = $1::uuid", vacante_id
    )
    await assume_tenant(db, empresa_id)
    await db.execute("update vacantes set title = 'Otro' where id = $1::uuid", vacante_id)
    assert (await _moderacion(db, vacante_id))["moderacion"] == "en_revision"


async def test_cerrarla_no_cambia_la_moderacion(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    await _como_dueno(
        db, "update vacantes set moderacion = 'publicada' where id = $1::uuid", vacante_id
    )
    await assume_tenant(db, empresa_id)
    await db.execute("update vacantes set status = 'closed' where id = $1::uuid", vacante_id)
    assert (await _moderacion(db, vacante_id))["moderacion"] == "publicada"


async def test_la_empresa_no_se_da_la_insignia(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    await _make_user(db, empresa_id, role="HR")
    await assume_tenant(db, empresa_id, role="HR")
    resultado = await db.execute(
        "update empresas set verificada = true, publica_para = 'propia' where id = $1::uuid",
        empresa_id,
    )
    assert resultado == "UPDATE 0"
    await _elevate(db)
    try:
        assert not await db.fetchval(
            "select verificada from empresas where id = $1::uuid", empresa_id
        )
    finally:
        await _drop(db)


# ─────────────────────── lo público: solo las publicadas ───────────────────────


async def test_el_career_site_solo_ve_las_publicadas(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")  # cinco vacantes: sin el tope del plan gratis
    ids = {e: await _del_panel(db, empresa_id) for e in EstadoDeModeracion}
    for estado, vacante_id in ids.items():
        await _como_dueno(
            db,
            "update vacantes set moderacion = $2::moderacion_vacante where id = $1::uuid",
            vacante_id,
            estado.value,
        )
    await assume_anon(db)
    visibles = {
        str(r["id"])
        for r in await db.fetch(
            "select id from vacantes_publicas where id = any($1::uuid[])", list(ids.values())
        )
    }
    assert visibles == {ids[EstadoDeModeracion.PUBLICADA]}


@pytest.mark.parametrize("estado", ["pendiente", "en_revision", "rechazada", "oculta"])
async def test_no_se_aplica_a_una_vacante_sin_publicar(db: asyncpg.Connection, estado: str) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    await _como_dueno(
        db,
        "update vacantes set moderacion = $2::moderacion_vacante where id = $1::uuid",
        vacante_id,
        estado,
    )
    await assume_anon(db)
    with pytest.raises(NoDisponible, match="vacante no disponible"):
        await db.execute(
            "select aplicar_a_vacante($1::uuid, 'Ana', 'ana@example.test')", vacante_id
        )


async def test_el_rol_del_career_site_solo_ve_las_publicadas(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    pendiente = await _del_panel(db, empresa_id)
    publicada = await _del_panel(db, empresa_id)
    await _como_dueno(
        db, "update vacantes set moderacion = 'publicada' where id = $1::uuid", publicada
    )
    await db.execute("reset role")
    await db.execute("select set_config('request.jwt.claims', '', false)")
    await db.execute("set role career_site")
    vistas = {
        str(r["id"])
        for r in await db.fetch(
            "select id from vacantes where id = any($1::uuid[])", [pendiente, publicada]
        )
    }
    assert vistas == {publicada}


async def test_la_vista_suma_insignia_y_quien_publica(db: asyncpg.Connection) -> None:
    propia, reclutador = await _empresa(db), await _empresa(db)
    await _make_user(db, reclutador, role="HR")
    await _como_dueno(db, "update empresas set verificada = true where id = $1::uuid", propia)
    await _como_dueno(
        db,
        "update empresas set publica_para = 'clientes', verificada = true,"
        " linkedin = 'https://www.linkedin.com/in/ana' where id = $1::uuid",
        reclutador,
    )
    filas = {}
    for empresa_id in (propia, reclutador):
        vacante_id = await _del_panel(db, empresa_id)
        await _como_dueno(
            db, "update vacantes set moderacion = 'publicada' where id = $1::uuid", vacante_id
        )
        filas[empresa_id] = vacante_id

    await assume_anon(db)
    leer = (
        "select empresa_verificada, publicada_por, linkedin_de_quien_publica"
        " from vacantes_publicas where id = $1::uuid"
    )
    de_la_empresa = await db.fetchrow(leer, filas[propia])
    assert dict(de_la_empresa) == {
        "empresa_verificada": True,
        "publicada_por": None,
        "linkedin_de_quien_publica": None,
    }
    del_reclutador = await db.fetchrow(leer, filas[reclutador])
    # Un reclutador nunca lleva la insignia, aunque la columna diga otra cosa.
    assert del_reclutador["empresa_verificada"] is False
    assert del_reclutador["publicada_por"]
    assert del_reclutador["linkedin_de_quien_publica"] == "https://www.linkedin.com/in/ana"


async def test_una_rechazada_no_cuenta_en_el_tope(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=10)  # plan gratis: 3 activas
    ids = [await _del_panel(db, empresa_id) for _ in range(3)]
    await assume_tenant(db, empresa_id)
    assert (await db.fetchrow("select * from mi_cupo_de_vacantes()"))["libres"] == 0
    await _como_dueno(
        db, "update vacantes set moderacion = 'rechazada' where id = $1::uuid", ids[0]
    )
    await assume_tenant(db, empresa_id)
    cupo = await db.fetchrow("select * from mi_cupo_de_vacantes()")
    assert (cupo["activas"], cupo["libres"], cupo["publicaciones_libres"]) == (2, 1, 1)
    await _del_panel(db, empresa_id)  # el lugar se puede usar


# ─────────────────────── reportar una vacante ───────────────────────


async def _publicada(db: asyncpg.Connection) -> tuple[str, str]:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    await _como_dueno(
        db,
        "update vacantes set moderacion = 'publicada', moderada_en = now() - interval '1 day'"
        " where id = $1::uuid",
        vacante_id,
    )
    await _elevate(db)
    slug = await db.fetchval("select slug from vacantes where id = $1::uuid", vacante_id)
    await _drop(db)
    return vacante_id, slug


async def _reportar(
    db: asyncpg.Connection, slug: str, ip: str | None, motivo: str = "Cobra"
) -> str:
    await db.execute("reset role")
    await db.execute("select set_config('request.jwt.claims', '', false)")
    await db.execute("set role career_site")
    try:
        return await db.fetchval("select reportar_vacante($1, $2, $3)", slug, motivo, ip)
    finally:
        await db.execute("reset role")
        await db.execute("set role authenticated")


@pytest.mark.parametrize("rol", ["anon", "authenticated"])
async def test_solo_el_career_site_puede_reportar(db: asyncpg.Connection, rol: str) -> None:
    _, slug = await _publicada(db)
    await db.execute("reset role")
    await db.execute(f"set role {rol}")
    with pytest.raises(SinPermiso):
        await db.fetchval("select reportar_vacante($1, 'x', '1.1.1.1')", slug)


async def test_dos_personas_distintas_la_ocultan(db: asyncpg.Connection) -> None:
    vacante_id, slug = await _publicada(db)
    assert await _reportar(db, slug, "10.0.0.1") == "recibido"
    assert await _reportar(db, slug, "10.0.0.1") == "recibido"  # la misma IP no suma
    assert (await _moderacion(db, vacante_id))["moderacion"] == "publicada"
    assert await _reportar(db, slug, "10.0.0.2") == "oculta"
    fila = await _moderacion(db, vacante_id)
    assert fila["moderacion"] == "oculta"
    assert '"regla": "reportes"' in fila["motivos_moderacion"]
    await assume_anon(db)
    assert await db.fetchval("select count(*) from vacantes_publicas where slug = $1", slug) == 0


async def test_sin_ip_cuentan_como_una_sola_persona(db: asyncpg.Connection) -> None:
    vacante_id, slug = await _publicada(db)
    for _ in range(3):
        assert await _reportar(db, slug, None) == "recibido"
    assert (await _moderacion(db, vacante_id))["moderacion"] == "publicada"


async def test_la_ip_no_se_guarda(db: asyncpg.Connection) -> None:
    vacante_id, slug = await _publicada(db)
    await _reportar(db, slug, "203.0.113.7")
    await _elevate(db)
    try:
        ip_hash = await db.fetchval(
            "select ip_hash from privado.reportes_vacante where vacante_id = $1::uuid", vacante_id
        )
    finally:
        await _drop(db)
    assert len(ip_hash) == 64 and "203.0.113.7" not in ip_hash


async def test_tras_aprobarla_solo_cuentan_los_reportes_nuevos(db: asyncpg.Connection) -> None:
    vacante_id, slug = await _publicada(db)
    await _reportar(db, slug, "10.0.0.1")
    await _reportar(db, slug, "10.0.0.2")
    await _como_dueno(
        db,
        "update vacantes set moderacion = 'publicada', moderada_en = now() where id = $1::uuid",
        vacante_id,
    )
    assert await _reportar(db, slug, "10.0.0.3") == "recibido"
    assert (await _moderacion(db, vacante_id))["moderacion"] == "publicada"


async def test_un_reporte_de_una_vacante_no_publica_falla(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)  # pendiente
    await _elevate(db)
    slug = await db.fetchval("select slug from vacantes where id = $1::uuid", vacante_id)
    await _drop(db)
    with pytest.raises(NoDisponible, match="vacante no disponible"):
        await _reportar(db, slug, "10.0.0.1")


@pytest.mark.parametrize("motivo", ["", "   ", "x" * 301])
async def test_el_motivo_es_obligatorio_y_corto(db: asyncpg.Connection, motivo: str) -> None:
    _, slug = await _publicada(db)
    with pytest.raises(NoDisponible, match="motivo invalido"):
        await _reportar(db, slug, "10.0.0.1", motivo=motivo)


async def test_una_ip_tiene_tope_de_reportes_al_dia(db: asyncpg.Connection) -> None:
    for _ in range(10):
        _, slug = await _publicada(db)
        await _reportar(db, slug, "198.51.100.9")
    _, slug = await _publicada(db)
    with pytest.raises(asyncpg.PostgresError) as error:
        await _reportar(db, slug, "198.51.100.9")
    assert error.value.sqlstate == "PT429"


@pytest.mark.parametrize("rol", ["anon", "authenticated", "career_site"])
@pytest.mark.parametrize("tabla", ["reportes_vacante", "sal_de_reportes", "avisos_de_moderacion"])
async def test_nadie_de_afuera_lee_lo_privado(db: asyncpg.Connection, rol: str, tabla: str) -> None:
    await db.execute("reset role")
    await db.execute(f"set role {rol}")
    with pytest.raises(SinPermiso):
        await db.fetch(f"select * from privado.{tabla} limit 1")


# ─────────────────────── el SQL del hr-engine ───────────────────────


async def test_el_barrido_modera_con_el_contexto_de_la_empresa(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    verificada, sin_verificar = await _empresa(db), await _empresa(db)
    await _como_dueno(db, "update empresas set verificada = true where id = $1::uuid", verificada)
    limpia = await _del_panel(db, verificada)
    con_cobro = await _del_panel(db, verificada, jd="Para empezar debes pagar el curso.")
    primera = await _del_panel(db, sin_verificar)

    caso = ModerarVacantesPendientes(SqlRepositorioDeModeracion(sesion))
    await caso.ejecutar(lote=10_000)

    assert (await _moderacion(db, limpia))["moderacion"] == "publicada"
    rechazada = await _moderacion(db, con_cobro)
    assert rechazada["moderacion"] == "rechazada"
    assert '"regla": "pago"' in rechazada["motivos_moderacion"]
    assert (await _moderacion(db, primera))["moderacion"] == "en_revision"

    # La segunda de la empresa sin verificar ya no es la primera... cuando la primera se publica.
    await ResolverRevision(SqlRepositorioDeModeracion(sesion)).aprobar(UUID(primera))
    segunda = await _del_panel(db, sin_verificar)
    await caso.ejecutar(lote=10_000)
    assert (await _moderacion(db, segunda))["moderacion"] == "publicada"


async def test_el_texto_copiado_de_otra_cuenta_va_a_revision(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    una, otra = await _empresa(db), await _empresa(db)
    for e in (una, otra):
        await _como_dueno(db, "update empresas set verificada = true where id = $1::uuid", e)
    texto = (
        "Coordinarás la recepción, el inventario y los envíos de un almacén de 40 personas. " * 2
    )
    await _del_panel(db, una, jd=texto)
    copia = await _del_panel(db, otra, jd=texto.upper().replace("  ", " "))
    await ModerarVacantesPendientes(SqlRepositorioDeModeracion(sesion)).ejecutar(lote=10_000)
    fila = await _moderacion(db, copia)
    assert fila["moderacion"] == "en_revision"
    assert '"regla": "duplicada"' in fila["motivos_moderacion"]


async def test_guardar_solo_si_sigue_pendiente(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    repo = SqlRepositorioDeModeracion(sesion)
    (pendiente,) = [v for v in await repo.pendientes(10_000) if str(v.id) == vacante_id]
    await sesion.rollback()  # suelta el bloqueo del barrido
    await _como_dueno(db, "update vacantes set status = 'closed' where id = $1::uuid", vacante_id)
    assert not await repo.guardar(pendiente.id, decidir(pendiente, evaluar(pendiente)))


async def test_la_cola_y_los_avisos(db: asyncpg.Connection, sesion: AsyncSession) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    await _como_dueno(
        db, "update vacantes set moderacion = 'oculta' where id = $1::uuid", vacante_id
    )
    repo = SqlRepositorioDeModeracion(sesion)
    cola = await repo.cola_sin_avisar(10_000)
    (en_cola,) = [v for v in cola if str(v.id) == vacante_id]
    assert en_cola.estado is EstadoDeModeracion.OCULTA
    await repo.marcar_avisadas([en_cola.id])
    assert vacante_id not in {str(v.id) for v in await repo.cola_sin_avisar(10_000)}
    antes = (await repo.avisos_recientes()).ultimas_24_horas
    await repo.registrar_aviso(urgente=True, vacantes=1)
    despues = await repo.avisos_recientes()
    assert despues.ultimas_24_horas == antes + 1 and despues.ultimo is not None


async def test_rechazar_desde_la_revision_guarda_el_motivo(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _del_panel(db, empresa_id)
    await _como_dueno(
        db, "update vacantes set moderacion = 'en_revision' where id = $1::uuid", vacante_id
    )
    caso = ResolverRevision(SqlRepositorioDeModeracion(sesion))
    assert await caso.rechazar(UUID(vacante_id), "Pide un depósito")
    fila = await _moderacion(db, vacante_id)
    assert fila["moderacion"] == "rechazada"
    assert "Pide un depósito" in fila["motivos_moderacion"]
    # Una rechazada no se vuelve a rechazar: no está entre los estados de origen.
    assert not await caso.rechazar(UUID(vacante_id), "otra vez")


async def test_la_insignia_se_suma_y_no_se_quita_sola(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id = await _empresa(db)
    caso = VerificarEmpresa(SqlRepositorioDeModeracion(sesion))
    assert await caso.ejecutar(
        UUID(empresa_id),
        correo="rh@andes.com.mx",
        publica_para="propia",
        web="https://www.andes.com.mx",
        linkedin=None,
    )
    # Otra llamada sin coincidencia no la quita.
    assert await caso.ejecutar(
        UUID(empresa_id), correo="x@gmail.com", publica_para="propia", web=None, linkedin=None
    )
    # Pasar a reclutador sí.
    assert not await caso.ejecutar(
        UUID(empresa_id),
        correo="rh@andes.com.mx",
        publica_para="clientes",
        web=None,
        linkedin="https://www.linkedin.com/in/ana",
    )
    await _elevate(db)
    try:
        fila = await db.fetchrow(
            "select verificada, verificada_en, publica_para, linkedin from empresas"
            " where id = $1::uuid",
            empresa_id,
        )
    finally:
        await _drop(db)
    assert dict(fila) == {
        "verificada": False,
        "verificada_en": None,
        "publica_para": "clientes",
        "linkedin": "https://www.linkedin.com/in/ana",
    }


async def test_la_base_rechaza_una_web_sin_https(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await _como_dueno(
            db, "update empresas set web = 'http://andes.mx' where id = $1::uuid", empresa_id
        )
