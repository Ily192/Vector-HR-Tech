"""Límites del plan gratuito aplicados en la base (migraciones 0008 y 0010, ADR-017 y 019).

El panel escribe sus vacantes con la sesión de Supabase y el career site aplica con
la anon key: ninguno pasa por el hr-engine, así que la base es la que corta.
Estos tests comprueban también que la copia en SQL diga lo mismo que el contrato
`packages/types/contracts/limites-plan.json`.

Cada test crea su propia empresa para no tocar el seed que usan los demás.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from .conftest import _asyncpg_dsn, assume_anon, assume_tenant
from .test_rls import _drop, _elevate, _make_user

pytestmark = pytest.mark.asyncio

_REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pnpm-workspace.yaml").exists()
)
CONTRATO: dict[str, Any] = json.loads(
    (_REPO_ROOT / "packages/types/contracts/limites-plan.json").read_text(encoding="utf-8")
)

#: SQLSTATE con el que la base rechaza pasarse de un tope; PostgREST lo traduce a 409.
SIN_CUPO = "PT409"
#: SQLSTATE de lo que el plan no incluye; PostgREST lo traduce a 403.
NO_INCLUIDO = "PT403"


async def _empresa(
    db: asyncpg.Connection,
    *,
    plan: str = "gratis",
    tamano: int | None = None,
    ajuste: int | None = None,
) -> str:
    empresa_id = str(uuid.uuid4())
    await _elevate(db)
    try:
        await db.execute(
            """
            insert into empresas (id, name, slug, plan, tamano_empleados, limite_vacantes)
            values ($1::uuid, 'Empresa de prueba', $2, $3::plan_empresa, $4, $5)
            """,
            empresa_id,
            f"prueba-{empresa_id}",
            plan,
            tamano,
            ajuste,
        )
    finally:
        await _drop(db)
    return empresa_id


async def _vacante(db: asyncpg.Connection, empresa_id: str, status: str = "open") -> str:
    """Inserta una vacante como el tenant, igual que lo hará el panel."""
    await assume_tenant(db, empresa_id)
    return str(
        await db.fetchval(
            """
            insert into vacantes (empresa_id, slug, title, jd, status)
            values ($1::uuid, $2, 'Vacante', 'Descripción', $3::vacante_status)
            returning id
            """,
            empresa_id,
            f"v-{uuid.uuid4()}",
            status,
        )
    )


async def _sin_cupo(coro: Any) -> asyncpg.PostgresError:
    with pytest.raises(asyncpg.PostgresError) as exc:
        await coro
    assert exc.value.sqlstate == SIN_CUPO
    return exc.value


# ─────────────────────── la regla en SQL = el contrato ───────────────────────


@pytest.mark.parametrize(
    "caso", CONTRATO["casos_limite_de_vacantes"], ids=lambda c: f"{c['tamano']}-{c['ajuste']}"
)
async def test_limite_de_vacantes_en_sql_cumple_el_contrato(
    db: asyncpg.Connection, caso: dict[str, Any]
) -> None:
    empresa_id = await _empresa(db, tamano=caso["tamano"], ajuste=caso["ajuste"])
    await _elevate(db)
    try:
        assert (
            await db.fetchval("select limite_de_vacantes($1::uuid)", empresa_id) == caso["limite"]
        )
        assert (
            await db.fetchval("select limite_de_aplicaciones($1::uuid)", empresa_id)
            == CONTRATO["max_aplicaciones_gratis"]
        )
    finally:
        await _drop(db)


async def test_el_plan_con_ia_no_tiene_topes_en_sql(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia", tamano=10, ajuste=2)
    await _elevate(db)
    try:
        assert await db.fetchval("select limite_de_vacantes($1::uuid)", empresa_id) is None
        assert await db.fetchval("select limite_de_aplicaciones($1::uuid)", empresa_id) is None
    finally:
        await _drop(db)


# ─────────────────────────── tope de vacantes ───────────────────────────


async def test_la_cuarta_vacante_de_una_empresa_chica_se_rechaza(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=30)
    for _ in range(3):
        await _vacante(db, empresa_id)
    error = await _sin_cupo(_vacante(db, empresa_id))
    assert "limite de vacantes" in str(error)
    # Un borrador no ocupa cupo.
    await _vacante(db, empresa_id, status="draft")


async def test_publicar_un_borrador_con_el_cupo_lleno_se_rechaza(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=30)
    for _ in range(3):
        await _vacante(db, empresa_id)
    borrador = await _vacante(db, empresa_id, status="draft")
    await _sin_cupo(db.execute("update vacantes set status = 'open' where id = $1::uuid", borrador))


async def test_eliminar_es_borrado_logico_y_libera_el_cupo(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=30)
    ids = [await _vacante(db, empresa_id) for _ in range(3)]

    await db.execute("update vacantes set status = 'closed' where id = $1::uuid", ids[0])
    fila = await db.fetchrow(
        "select deleted_at, closed_at from vacantes where id = $1::uuid", ids[0]
    )
    assert fila["deleted_at"] is not None
    assert fila["closed_at"] is not None

    # Libera el cupo de activas, pero la publicación nueva espera a que la cerrada
    # salga de la ventana de 30 días (0010).
    cupo = await db.fetchrow("select libres, publicaciones_libres from mi_cupo_de_vacantes()")
    assert tuple(cupo) == (1, 0)
    await _como_soporte(
        db,
        "update vacantes set publicada_en = now() - interval '31 days' where id = $1::uuid",
        ids[0],
    )
    await _vacante(db, empresa_id)  # el cupo liberado se puede usar


async def test_una_empresa_grande_tiene_cuatro_vacantes(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=120)
    for _ in range(4):
        await _vacante(db, empresa_id)
    await _sin_cupo(_vacante(db, empresa_id))


async def test_el_ajuste_de_vector_hr_manda_sobre_el_tamano(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=10, ajuste=5)
    for _ in range(5):
        await _vacante(db, empresa_id)
    await _sin_cupo(_vacante(db, empresa_id))


async def test_el_plan_con_ia_publica_sin_tope(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia", tamano=10)
    for _ in range(6):
        await _vacante(db, empresa_id)


async def test_el_panel_lee_su_cupo_de_la_base(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=60)
    for _ in range(3):
        await _vacante(db, empresa_id)
    await assume_tenant(db, empresa_id)
    cupo = await db.fetchrow("select * from mi_cupo_de_vacantes()")
    assert dict(cupo) == {
        "activas": 3,
        "limite": 4,
        "libres": 1,
        "max_aplicaciones": 50,
        "publicaciones_libres": 1,
        "proxima_publicacion": None,
    }


async def test_el_cupo_del_plan_con_ia_no_tiene_tope(db: asyncpg.Connection) -> None:
    """0008 devolvía `libres = 0`: `greatest(0, null)` es 0, no null."""
    empresa_id = await _empresa(db, plan="ia")
    await _vacante(db, empresa_id)
    await assume_tenant(db, empresa_id)
    cupo = await db.fetchrow("select * from mi_cupo_de_vacantes()")
    assert dict(cupo) == {
        "activas": 1,
        "limite": None,
        "libres": None,
        "max_aplicaciones": None,
        "publicaciones_libres": None,
        "proxima_publicacion": None,
    }


async def test_sin_sesion_no_hay_cupo_que_leer(db: asyncpg.Connection) -> None:
    assert await db.fetch("select * from mi_cupo_de_vacantes()") == []
    await assume_anon(db)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.fetch("select * from mi_cupo_de_vacantes()")


# ───────────────────────── tope de aplicaciones ─────────────────────────


async def _llenar(db: asyncpg.Connection, vacante_id: str, total: int) -> None:
    """Aplica `total` candidatos distintos por la vía pública."""
    await assume_anon(db)
    for i in range(total):
        await db.fetchval(
            "select aplicar_a_vacante($1::uuid, $2, $3)",
            vacante_id,
            f"Candidata {i}",
            f"candidata{i}@example.test",
        )


async def test_la_aplicacion_51_se_rechaza_y_la_vista_marca_cupo_completo(
    db: asyncpg.Connection,
) -> None:
    empresa_id = await _empresa(db, tamano=30)
    vacante_id = await _vacante(db, empresa_id)
    await _llenar(db, vacante_id, 49)

    await assume_anon(db)
    publica = "select cupo_completo from vacantes_publicas where id = $1::uuid"
    assert await db.fetchval(publica, vacante_id) is False

    await _llenar(db, vacante_id, 50)  # la 50 entra; las 49 anteriores se repiten
    await assume_anon(db)
    assert await db.fetchval(publica, vacante_id) is True

    error = await _sin_cupo(
        db.fetchval(
            "select aplicar_a_vacante($1::uuid, $2, $3)",
            vacante_id,
            "La 51",
            "la51@example.test",
        )
    )
    assert "ya no recibe aplicaciones" in str(error)


async def test_volver_a_aplicar_con_el_cupo_lleno_devuelve_la_misma_aplicacion(
    db: asyncpg.Connection,
) -> None:
    empresa_id = await _empresa(db, ajuste=1)
    vacante_id = await _vacante(db, empresa_id)
    await _llenar(db, vacante_id, 50)
    await assume_anon(db)
    primera = await db.fetchval(
        "select aplicar_a_vacante($1::uuid, $2, $3)",
        vacante_id,
        "Candidata 0",
        "candidata0@example.test",
    )
    assert primera is not None


async def test_el_plan_con_ia_recibe_mas_de_50_aplicaciones(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    vacante_id = await _vacante(db, empresa_id)
    await _llenar(db, vacante_id, 52)
    await assume_anon(db)
    assert (
        await db.fetchval(
            "select cupo_completo from vacantes_publicas where id = $1::uuid", vacante_id
        )
        is False
    )


async def _alta_directa(db: asyncpg.Connection, empresa_id: str, vacante_id: str) -> str:
    """La empresa da de alta un candidato y su aplicación con su sesión, sin el career site."""
    await assume_tenant(db, empresa_id)
    candidato_id = await db.fetchval(
        "insert into candidatos (empresa_id, full_name, email) values ($1::uuid, 'Directa', $2)"
        " returning id",
        empresa_id,
        f"{uuid.uuid4().hex[:10]}@example.test",
    )
    return str(
        await db.fetchval(
            "insert into applications (empresa_id, vacante_id, candidato_id)"
            " values ($1::uuid, $2::uuid, $3) returning id",
            empresa_id,
            vacante_id,
            candidato_id,
        )
    )


async def test_la_empresa_no_salta_el_tope_insertando_por_la_api(db: asyncpg.Connection) -> None:
    """Hasta 0010 el tope solo vivía en `aplicar_a_vacante()`."""
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await _llenar(db, vacante_id, 49)
    await _alta_directa(db, empresa_id, vacante_id)  # la 50 entra

    error = await _sin_cupo(_alta_directa(db, empresa_id, vacante_id))
    assert "ya no recibe aplicaciones" in str(error)


async def test_borrar_aplicaciones_no_libera_cupo(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await _llenar(db, vacante_id, 50)

    await assume_tenant(db, empresa_id)
    borradas = await db.execute(
        "delete from applications where id in"
        " (select id from applications where vacante_id = $1::uuid limit 3)",
        vacante_id,
    )
    assert borradas == "DELETE 3"

    await assume_anon(db)
    publica = "select cupo_completo from vacantes_publicas where id = $1::uuid"
    assert await db.fetchval(publica, vacante_id) is True
    await _sin_cupo(
        db.fetchval("select aplicar_a_vacante($1::uuid, 'Otra', 'otra@example.test')", vacante_id)
    )


async def test_el_panel_lee_las_recibidas_de_la_base(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    llena, a_medias = await _vacante(db, empresa_id), await _vacante(db, empresa_id)
    await _llenar(db, llena, 50)
    await _llenar(db, a_medias, 3)
    await assume_tenant(db, empresa_id)
    await db.execute("delete from applications where vacante_id = $1::uuid", a_medias)

    filas = {
        str(f["vacante_id"]): dict(f)
        for f in await db.fetch("select * from cupos_de_aplicaciones()")
    }
    assert filas[llena] == {
        "vacante_id": uuid.UUID(llena),
        "recibidas": 50,
        "limite": 50,
        "completo": True,
    }
    # Se borraron las 3, pero se recibieron: el cupo cuenta las recibidas.
    assert filas[a_medias]["recibidas"] == 3

    await assume_tenant(db, empresa_id, role="Colaborador")
    assert await db.fetch("select * from cupos_de_aplicaciones()") == []
    await assume_anon(db)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.fetch("select * from cupos_de_aplicaciones()")


async def test_dos_altas_simultaneas_no_pasan_las_dos_con_el_ultimo_cupo(
    db: asyncpg.Connection,
) -> None:
    """El alta directa no bloquea la vacante: lo serializa el contador."""
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await _llenar(db, vacante_id, 49)
    await assume_tenant(db, empresa_id)
    candidatos = [
        await db.fetchval(
            "insert into candidatos (empresa_id, full_name, email) values ($1::uuid, $2, $3)"
            " returning id",
            empresa_id,
            f"Simultanea {i}",
            f"simultanea{i}@example.test",
        )
        for i in range(2)
    ]
    alta = (
        "insert into applications (empresa_id, vacante_id, candidato_id)"
        " values ($1::uuid, $2::uuid, $3)"
    )

    primera, segunda = [await asyncpg.connect(_asyncpg_dsn()) for _ in range(2)]
    try:
        for conn in (primera, segunda):
            await assume_tenant(conn, empresa_id)
        t1, t2 = primera.transaction(), segunda.transaction()
        await t1.start()
        await t2.start()
        await primera.execute(alta, empresa_id, vacante_id, candidatos[0])
        en_espera = asyncio.create_task(
            segunda.execute(alta, empresa_id, vacante_id, candidatos[1])
        )
        await asyncio.sleep(0.3)
        assert not en_espera.done()  # espera a que la primera termine
        await t1.commit()
        with pytest.raises(asyncpg.PostgresError) as exc:
            await en_espera
        assert exc.value.sqlstate == SIN_CUPO
        await t2.rollback()
    finally:
        await primera.close()
        await segunda.close()


# ─────────────────────────── JWT: plan y módulos ───────────────────────────


@pytest.mark.parametrize("plan", ["gratis", "ia"])
async def test_el_jwt_lleva_el_plan_y_sus_modulos(db: asyncpg.Connection, plan: str) -> None:
    empresa_id = await _empresa(db, plan=plan)
    user_id = await _make_user(db, empresa_id, role="HR")
    evento = {
        "user_id": user_id,
        "claims": {
            "sub": user_id,
            "role": "authenticated",
            "aud": "authenticated",
            "app_metadata": {"provider": "email"},
        },
    }
    await _elevate(db)
    try:
        salida = json.loads(
            await db.fetchval(
                "select custom_access_token_hook($1::jsonb)::text", json.dumps(evento)
            )
        )
    finally:
        await _drop(db)

    claims = salida["claims"]
    assert claims["role"] == "authenticated"  # el claim reservado no se toca
    assert claims["aud"] == "authenticated"
    meta = claims["app_metadata"]
    assert meta["provider"] == "email"  # se conserva lo que ya traía
    assert meta["empresa_id"] == empresa_id
    assert meta["plan"] == plan
    assert meta["modulos"] == CONTRATO["planes"][plan]["modulos"]


# ─────────────────────── el cockpit es del plan con IA ───────────────────────


async def _una_aplicacion(db: asyncpg.Connection, empresa_id: str) -> str:
    vacante_id = await _vacante(db, empresa_id)
    await assume_anon(db)
    return str(
        await db.fetchval(
            "select aplicar_a_vacante($1::uuid, 'Ana', $2)",
            vacante_id,
            f"{uuid.uuid4().hex[:10]}@example.test",
        )
    )


async def _crear_en_el_cockpit(db: asyncpg.Connection, empresa_id: str, tabla: str) -> None:
    """Lo que el panel de pago crea, hecho con la sesión de la empresa."""
    if tabla == "constancias":
        profile_id = await _make_user(db, empresa_id, role="Colaborador")
        await assume_tenant(db, empresa_id)
        await db.execute(
            "insert into constancias (empresa_id, profile_id, type)"
            " values ($1::uuid, $2::uuid, 'laboral')",
            empresa_id,
            profile_id,
        )
        return
    application_id = await _una_aplicacion(db, empresa_id)
    await assume_tenant(db, empresa_id)
    if tabla == "psicometricos":
        await db.execute(
            "insert into psicometricos (empresa_id, application_id, token_hash, status)"
            " values ($1::uuid, $2::uuid,"
            " encode(sha256(gen_random_uuid()::text::bytea), 'hex'), 'pending')",
            empresa_id,
            application_id,
        )
    else:
        await db.execute(
            "insert into entrevistas (empresa_id, application_id, slot)"
            " values ($1::uuid, $2::uuid, tstzrange(now(), now() + interval '1 hour'))",
            empresa_id,
            application_id,
        )


@pytest.mark.parametrize("tabla", ["psicometricos", "entrevistas", "constancias"])
@pytest.mark.parametrize("plan", ["gratis", "ia"])
async def test_el_cockpit_solo_se_usa_con_el_plan_con_ia(
    db: asyncpg.Connection, plan: str, tabla: str
) -> None:
    """Hasta 0010 el panel los escondía, pero la API los aceptaba."""
    empresa_id = await _empresa(db, plan=plan)
    if CONTRATO["planes"][plan]["incluye_ia"]:
        await _crear_en_el_cockpit(db, empresa_id, tabla)
        return
    with pytest.raises(asyncpg.PostgresError) as exc:
        await _crear_en_el_cockpit(db, empresa_id, tabla)
    assert exc.value.sqlstate == NO_INCLUIDO


async def test_si_la_empresa_deja_de_pagar_el_candidato_termina_su_test(
    db: asyncpg.Connection,
) -> None:
    """Solo se corta lo nuevo: lo que estaba en marcha se puede terminar."""
    empresa_id = await _empresa(db, plan="ia")
    application_id = await _una_aplicacion(db, empresa_id)
    token = f"psy-{uuid.uuid4().hex}"
    await assume_tenant(db, empresa_id)
    await db.execute(
        "insert into psicometricos (empresa_id, application_id, token_hash, status)"
        " values ($1::uuid, $2::uuid, encode(sha256($3::text::bytea), 'hex'), 'pending')",
        empresa_id,
        application_id,
        token,
    )
    await _elevate(db)
    try:
        await db.execute("update empresas set plan = 'gratis' where id = $1::uuid", empresa_id)
    finally:
        await _drop(db)

    await assume_anon(db)
    await db.execute(
        "select submit_psicometrico($1, $2::jsonb, null, true)", token, json.dumps({"q1": 2})
    )
    await _elevate(db)
    try:
        estado = await db.fetchval(
            "select status::text from psicometricos"
            " where token_hash = encode(sha256($1::text::bytea), 'hex')",
            token,
        )
    finally:
        await _drop(db)
    assert estado == "completed"


# ─────────────────── publicaciones: las mismas que activas, cada 30 días ───────────────────

VENTANA = CONTRATO["ventana_de_publicaciones_dias"]


async def _como_soporte(db: asyncpg.Connection, sql: str, *args: Any) -> None:
    """Rol dueño sin sesión de tenant, como Vector HR con la clave secreta."""
    await _elevate(db)
    try:
        await db.execute("select set_config('request.jwt.claims', '', false)")
        await db.execute(sql, *args)
    finally:
        await _drop(db)


async def test_cerrar_y_publicar_otra_no_da_vacantes_sin_fin(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=30)
    ids = [await _vacante(db, empresa_id) for _ in range(3)]
    await db.execute("update vacantes set status = 'closed' where id = $1::uuid", ids[0])

    error = await _sin_cupo(_vacante(db, empresa_id))
    assert "limite de publicaciones" in str(error)
    # Un borrador sí se puede guardar: no cuenta hasta publicarse.
    borrador = await _vacante(db, empresa_id, status="draft")
    await _sin_cupo(db.execute("update vacantes set status = 'open' where id = $1::uuid", borrador))


async def test_reabrir_una_vacante_no_cuenta_como_publicacion(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=30)
    ids = [await _vacante(db, empresa_id) for _ in range(3)]
    await db.execute("update vacantes set status = 'closed' where id = $1::uuid", ids[0])
    await db.execute("update vacantes set status = 'open' where id = $1::uuid", ids[0])


@pytest.mark.parametrize(("dias", "entra"), [(VENTANA + 1, True), (VENTANA - 1, False)])
async def test_la_ventana_es_la_del_contrato(
    db: asyncpg.Connection, dias: int, entra: bool
) -> None:
    empresa_id = await _empresa(db, tamano=30)
    ids = [await _vacante(db, empresa_id) for _ in range(3)]
    await db.execute("update vacantes set status = 'closed' where id = $1::uuid", ids[0])
    await _como_soporte(
        db,
        "update vacantes set publicada_en = now() - make_interval(days => $2) where id = $1::uuid",
        ids[0],
        dias,
    )
    if entra:
        await _vacante(db, empresa_id)
    else:
        await _sin_cupo(_vacante(db, empresa_id))


async def test_la_empresa_no_puede_mover_su_fecha_de_publicacion(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=30)
    vacante_id = await _vacante(db, empresa_id)
    leer = "select publicada_en from vacantes where id = $1::uuid"
    antes = await db.fetchval(leer, vacante_id)
    assert antes is not None

    await db.execute(
        "update vacantes set publicada_en = now() - interval '1 year' where id = $1::uuid",
        vacante_id,
    )
    assert await db.fetchval(leer, vacante_id) == antes
    otra = await db.fetchval(
        "insert into vacantes (empresa_id, slug, title, jd, status, publicada_en)"
        " values ($1::uuid, $2, 'Vacante', 'Descripción', 'draft', now() - interval '1 year')"
        " returning id",
        empresa_id,
        f"v-{uuid.uuid4()}",
    )
    assert await db.fetchval(leer, otra) is None  # un borrador no está publicado


async def test_el_panel_sabe_cuando_podra_publicar_otra(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, tamano=30)
    ids = [await _vacante(db, empresa_id) for _ in range(3)]
    await _como_soporte(
        db,
        "update vacantes set publicada_en = now() - interval '10 days' where id = $1::uuid",
        ids[1],
    )
    await assume_tenant(db, empresa_id)
    cupo = await db.fetchrow("select * from mi_cupo_de_vacantes()")
    assert cupo["publicaciones_libres"] == 0
    dias = await db.fetchval(
        "select extract(day from $1::timestamptz - now())::int", cupo["proxima_publicacion"]
    )
    assert dias == VENTANA - 10 - 1  # se libera 20 días después, menos lo que va del día


# ─────────────────────── el slug en el career site (0012) ───────────────────────


async def test_dos_empresas_no_pueden_usar_el_mismo_slug(db: asyncpg.Connection) -> None:
    """El career site es uno solo y la vacante vive en /vacantes/<slug>."""
    una, otra = await _empresa(db), await _empresa(db)
    slug = f"analista-{uuid.uuid4().hex[:8]}"
    for empresa_id in (una, otra):
        await assume_tenant(db, empresa_id)
        insertar = db.execute(
            "insert into vacantes (empresa_id, slug, title, jd, status)"
            " values ($1::uuid, $2, 'Analista', 'Descripción', 'draft')",
            empresa_id,
            slug,
        )
        if empresa_id == una:
            await insertar
        else:
            with pytest.raises(asyncpg.UniqueViolationError):
                await insertar
