"""El gancho sin IA del plan gratis y la oposición del candidato (migraciones 0009-0010, ADR-019).

La empresa gratuita ve cuántos de sus CVs mencionan las skills de la vacante,
nunca cuáles: las coincidencias viven en `privado`, fuera del alcance de su
sesión, y solo salen agregadas y por lotes por `resumen_del_gancho()`. Estos tests
comprueban también que esa copia en SQL diga lo mismo que `contracts/gancho.json`.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from .conftest import assume_anon, assume_tenant
from .test_plan_gratis import _empresa, _vacante
from .test_rls import _drop, _elevate

pytestmark = pytest.mark.asyncio

_REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pnpm-workspace.yaml").exists()
)
CONTRATO: dict[str, Any] = json.loads(
    (_REPO_ROOT / "packages/types/contracts/gancho.json").read_text(encoding="utf-8")
)

#: SQLSTATE con el que la base rechaza lo que el plan o el candidato no permiten (HTTP 403).
PROHIBIDO = "PT403"


async def _aplicaciones(
    db: asyncpg.Connection,
    empresa_id: str,
    vacante_id: str,
    total: int,
    *,
    con_cv: bool = True,
    sin_ia: bool = False,
) -> list[str]:
    """Aplica `total` candidatos por la vía pública, como el career site."""
    await assume_anon(db)
    ids = []
    for _ in range(total):
        sufijo = uuid.uuid4().hex[:10]
        ids.append(
            str(
                await db.fetchval(
                    "select aplicar_a_vacante($1::uuid, $2, $3, $4, null, null, $5)",
                    vacante_id,
                    f"Candidata {sufijo}",
                    f"{sufijo}@example.test",
                    f"{empresa_id}/{sufijo}.pdf" if con_cv else None,
                    sin_ia,
                )
            )
        )
    return ids


async def _skills(db: asyncpg.Connection, empresa_id: str, vacante_id: str, skills: list[str]):
    await assume_tenant(db, empresa_id)
    await db.execute(
        "update vacantes set skills = $2::text[] where id = $1::uuid", vacante_id, skills
    )


async def _coincidencias(
    db: asyncpg.Connection,
    empresa_id: str,
    application_ids: list[str],
    skills: list[str],
    encontradas: list[list[str]],
) -> None:
    """Guarda coincidencias como lo hará el hr-engine, una por segundo para fijar el orden."""
    await _elevate(db)
    try:
        for orden, (application_id, e) in enumerate(
            zip(application_ids, encontradas, strict=False)
        ):
            await db.execute(
                """
                insert into privado.coincidencias
                    (application_id, empresa_id, skills, encontradas, calculado_en)
                values ($1::uuid, $2::uuid, $3::text[], $4::text[],
                        now() + make_interval(secs => $5))
                """,
                application_id,
                empresa_id,
                skills,
                e,
                float(orden),
            )
    finally:
        await _drop(db)


async def _como_dueno(db: asyncpg.Connection, sql: str, *args: Any) -> Any:
    await _elevate(db)
    try:
        return await db.fetchval(sql, *args)
    finally:
        await _drop(db)


async def _resumen(db: asyncpg.Connection, empresa_id: str, vacante_id: str, role: str = "HR"):
    await assume_tenant(db, empresa_id, role=role)
    return await db.fetchrow("select * from resumen_del_gancho($1::uuid)", vacante_id)


async def _vacante_con_skills(
    db: asyncpg.Connection, skills: list[str], *, plan: str = "gratis"
) -> tuple[str, str]:
    empresa_id = await _empresa(db, plan=plan)
    vacante_id = await _vacante(db, empresa_id)
    await _skills(db, empresa_id, vacante_id, skills)
    return empresa_id, vacante_id


# ─────────────────────── la regla en SQL = el contrato ───────────────────────


@pytest.mark.parametrize("caso", CONTRATO["casos"], ids=lambda c: c["nombre"])
async def test_el_resumen_en_sql_cumple_el_contrato(
    db: asyncpg.Connection, caso: dict[str, Any]
) -> None:
    empresa_id, vacante_id = await _vacante_con_skills(db, caso["skills"])
    recibidas = len(caso["encontradas"]) + 2  # dos CVs que aún no se revisaron
    ids = await _aplicaciones(db, empresa_id, vacante_id, recibidas)
    await _coincidencias(db, empresa_id, ids, caso["skills"], caso["encontradas"])

    fila = await _resumen(db, empresa_id, vacante_id)
    esperado = caso["resumen"]
    assert dict(fila) == {
        "aplicaciones": recibidas,
        "skills": len(caso["skills"]),
        "en_espera": recibidas - esperado["revisados"],
        "ilegibles": 0,
        **esperado,
    }


async def test_sin_skills_no_hay_nada_que_contar(db: asyncpg.Connection) -> None:
    """La vacante sin skills devuelve la fila igual: el panel le pide agregarlas."""
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await _aplicaciones(db, empresa_id, vacante_id, 3)

    fila = await _resumen(db, empresa_id, vacante_id)
    assert dict(fila) == {
        "aplicaciones": 3,
        "skills": 0,
        "revisados": 0,
        "en_espera": 0,
        "ilegibles": 0,
        "con_la_mayoria": 0,
        "con_todas": 0,
    }


async def test_si_la_empresa_cambia_las_skills_lo_calculado_deja_de_contar(
    db: asyncpg.Connection,
) -> None:
    skills = ["Excel", "SAP"]
    empresa_id, vacante_id = await _vacante_con_skills(db, skills)
    ids = await _aplicaciones(db, empresa_id, vacante_id, 5)
    await _coincidencias(db, empresa_id, ids, skills, [skills] * 5)
    assert (await _resumen(db, empresa_id, vacante_id))["con_todas"] == 5

    await _skills(db, empresa_id, vacante_id, ["Excel", "SAP", "Inglés"])
    fila = await _resumen(db, empresa_id, vacante_id)
    assert (fila["revisados"], fila["en_espera"], fila["con_todas"]) == (0, 5, 0)


async def test_las_aplicaciones_sin_cv_no_quedan_en_espera(db: asyncpg.Connection) -> None:
    empresa_id, vacante_id = await _vacante_con_skills(db, ["Python"])
    await _aplicaciones(db, empresa_id, vacante_id, 3)
    await _aplicaciones(db, empresa_id, vacante_id, 2, con_cv=False)

    fila = await _resumen(db, empresa_id, vacante_id)
    assert (fila["aplicaciones"], fila["revisados"], fila["en_espera"]) == (5, 0, 3)


async def test_los_que_se_oponen_y_los_ilegibles_no_quedan_en_espera(
    db: asyncpg.Connection,
) -> None:
    empresa_id, vacante_id = await _vacante_con_skills(db, ["Python"])
    ids = await _aplicaciones(db, empresa_id, vacante_id, 3)
    await _aplicaciones(db, empresa_id, vacante_id, 1, sin_ia=True)
    await _como_dueno(
        db,
        "insert into privado.cvs_ilegibles (application_id, empresa_id)"
        " values ($1::uuid, $2::uuid)",
        ids[0],
        empresa_id,
    )
    fila = await _resumen(db, empresa_id, vacante_id)
    assert (fila["aplicaciones"], fila["en_espera"], fila["ilegibles"]) == (4, 2, 1)


# ─────────────────────────── quién ve el gancho ───────────────────────────


async def test_la_empresa_no_puede_leer_lo_privado(db: asyncpg.Connection) -> None:
    empresa_id, vacante_id = await _vacante_con_skills(db, ["Python"])
    ids = await _aplicaciones(db, empresa_id, vacante_id, 1)
    await _coincidencias(db, empresa_id, ids, ["Python"], [["Python"]])

    for role in ("HR", "Director"):
        await assume_tenant(db, empresa_id, role=role)
        for sql in (
            "select * from privado.coincidencias",
            "select * from privado.cvs_ilegibles",
            "select * from privado.aplicaciones_recibidas",
            "select privado.purgar_coincidencias()",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await db.fetch(sql)
    # Y en `applications` no hay nada que leer: la coincidencia no se escribe ahí.
    await assume_tenant(db, empresa_id)
    fila = await db.fetchrow(
        "select fit_score, fit_gaps from applications where id = $1::uuid", ids[0]
    )
    assert tuple(fila) == (None, [])


async def test_el_resumen_es_solo_de_las_vacantes_propias(db: asyncpg.Connection) -> None:
    _, vacante_id = await _vacante_con_skills(db, ["Python"])
    otra = await _empresa(db)
    assert await _resumen(db, otra, vacante_id) is None


async def test_sin_rol_de_hr_no_hay_resumen(db: asyncpg.Connection) -> None:
    empresa_id, vacante_id = await _vacante_con_skills(db, ["Python"])
    assert await _resumen(db, empresa_id, vacante_id, role="Colaborador") is None


async def test_la_anon_key_no_puede_pedir_el_resumen(db: asyncpg.Connection) -> None:
    _, vacante_id = await _vacante_con_skills(db, ["Python"])
    await assume_anon(db)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.fetch("select * from resumen_del_gancho($1::uuid)", vacante_id)


async def test_con_el_plan_ia_no_hay_gancho(db: asyncpg.Connection) -> None:
    empresa_id, vacante_id = await _vacante_con_skills(db, ["Python"], plan="ia")
    assert await _resumen(db, empresa_id, vacante_id) is None


async def test_una_coincidencia_no_puede_ser_de_otro_tenant(db: asyncpg.Connection) -> None:
    duena, vacante_id = await _vacante_con_skills(db, ["Python"])
    otra = await _empresa(db)
    ids = await _aplicaciones(db, duena, vacante_id, 1)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await _coincidencias(db, otra, ids, ["Python"], [["Python"]])


async def test_solo_se_guardan_skills_de_la_vacante(db: asyncpg.Connection) -> None:
    empresa_id, vacante_id = await _vacante_con_skills(db, ["Python"])
    ids = await _aplicaciones(db, empresa_id, vacante_id, 1)
    with pytest.raises(asyncpg.CheckViolationError):
        await _coincidencias(db, empresa_id, ids, ["Python"], [["Python", "Nombre: Ana"]])


@pytest.mark.parametrize(
    "skills",
    [["Python"] * 16, ["  "], ["x" * 61]],
    ids=["mas-de-15", "en-blanco", "demasiado-larga"],
)
async def test_la_base_rechaza_skills_invalidas(db: asyncpg.Connection, skills: list[str]) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    with pytest.raises(asyncpg.CheckViolationError):
        await _skills(db, empresa_id, vacante_id, skills)


async def test_no_queda_nada_de_la_preseleccion_con_ia(db: asyncpg.Connection) -> None:
    """0010 deshace lo que 0009 montó para evaluar con IA el plan gratis."""
    await _elevate(db)
    try:
        for funcion in (
            "public.muestra_del_gancho(uuid)",
            "public.registrar_visita_al_pipeline(uuid)",
            "privado.purgar_preevaluaciones(int)",
        ):
            assert await db.fetchval("select to_regprocedure($1)", funcion) is None
        for tabla in (
            "privado.preevaluaciones",
            "privado.muestras_del_gancho",
            "privado.pipeline_visto",
        ):
            assert await db.fetchval("select to_regclass($1)", tabla) is None
        assert not await db.fetchval(
            "select exists (select 1 from information_schema.columns"
            " where table_name = 'vacantes' and column_name = 'preseleccion_ia')"
        )
    finally:
        await _drop(db)


# ──────────────────────────── etapas por plan ────────────────────────────


@pytest.mark.parametrize("etapa", ["evaluated", "shortlisted", "interviewed", "offered"])
async def test_la_empresa_gratis_no_mueve_candidatos_a_etapas_de_pago(
    db: asyncpg.Connection, etapa: str
) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    (application_id,) = await _aplicaciones(db, empresa_id, vacante_id, 1)
    await assume_tenant(db, empresa_id)
    with pytest.raises(asyncpg.PostgresError) as exc:
        await db.execute(
            "update applications set status = $2::application_status where id = $1::uuid",
            application_id,
            etapa,
        )
    assert exc.value.sqlstate == PROHIBIDO


@pytest.mark.parametrize("etapa", ["rejected", "hired", "withdrawn"])
async def test_la_empresa_gratis_puede_cerrar_una_aplicacion(
    db: asyncpg.Connection, etapa: str
) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    (application_id,) = await _aplicaciones(db, empresa_id, vacante_id, 1)
    await assume_tenant(db, empresa_id)
    await db.execute(
        "update applications set status = $2::application_status where id = $1::uuid",
        application_id,
        etapa,
    )


async def test_el_plan_ia_usa_todas_las_etapas(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    vacante_id = await _vacante(db, empresa_id)
    (application_id,) = await _aplicaciones(db, empresa_id, vacante_id, 1)
    await assume_tenant(db, empresa_id)
    for etapa in ("evaluated", "shortlisted", "interviewed", "offered"):
        await db.execute(
            "update applications set status = $2::application_status where id = $1::uuid",
            application_id,
            etapa,
        )


# ───────────────────────────── al contratar ─────────────────────────────


async def test_al_contratar_se_borra_el_gancho(db: asyncpg.Connection) -> None:
    """Lo que contó el gancho no se desbloquea: lo reemplaza la evaluación con IA."""
    empresa_id, vacante_id = await _vacante_con_skills(db, ["Python"])
    revisada, ilegible = await _aplicaciones(db, empresa_id, vacante_id, 2)
    await _coincidencias(db, empresa_id, [revisada], ["Python"], [["Python"]])
    await _como_dueno(
        db,
        "insert into privado.cvs_ilegibles (application_id, empresa_id)"
        " values ($1::uuid, $2::uuid)",
        ilegible,
        empresa_id,
    )

    await _como_dueno(db, "update empresas set plan = 'ia' where id = $1::uuid", empresa_id)

    for tabla in ("privado.coincidencias", "privado.cvs_ilegibles"):
        contar = f"select count(*) from {tabla} where empresa_id = $1::uuid"
        assert await _como_dueno(db, contar, empresa_id) == 0
    await assume_tenant(db, empresa_id)
    filas = await db.fetch(
        "select status::text, fit_score from applications where vacante_id = $1::uuid",
        vacante_id,
    )
    assert {tuple(f) for f in filas} == {("applied", None)}


# ─────────────────────── la oposición del candidato ───────────────────────


async def test_el_candidato_se_opone_al_aplicar_y_no_lo_puede_perder(
    db: asyncpg.Connection,
) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await assume_anon(db)
    aplicar = "select aplicar_a_vacante($1::uuid, 'Ana', 'ana@example.test', null, null, null, $2)"
    application_id = await db.fetchval(aplicar, vacante_id, False)
    # Al volver a aplicar se puede sumar la oposición...
    assert await db.fetchval(aplicar, vacante_id, True) == application_id
    # ...pero no quitarla.
    assert await db.fetchval(aplicar, vacante_id, False) == application_id

    sin_ia = "select sin_ia from applications where id = $1::uuid"
    assert await _como_dueno(db, sin_ia, application_id) is True


async def test_la_oposicion_borra_la_coincidencia(db: asyncpg.Connection) -> None:
    empresa_id, vacante_id = await _vacante_con_skills(db, ["Python"])
    (application_id,) = await _aplicaciones(db, empresa_id, vacante_id, 1)
    await _coincidencias(db, empresa_id, [application_id], ["Python"], [["Python"]])

    await assume_tenant(db, empresa_id)
    await db.execute("update applications set sin_ia = true where id = $1::uuid", application_id)
    contar = "select count(*) from privado.coincidencias where application_id = $1::uuid"
    assert await _como_dueno(db, contar, application_id) == 0


async def test_la_oposicion_borra_el_score_del_plan_con_ia(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    vacante_id = await _vacante(db, empresa_id)
    (application_id,) = await _aplicaciones(db, empresa_id, vacante_id, 1)
    await _como_dueno(
        db,
        "update applications set fit_score = 8, fit_rationale = 'Encaja', fit_gaps = '{SQL}'"
        " where id = $1::uuid",
        application_id,
    )
    await assume_tenant(db, empresa_id)
    await db.execute("update applications set sin_ia = true where id = $1::uuid", application_id)
    fila = await db.fetchrow(
        "select fit_score, fit_rationale, fit_gaps from applications where id = $1::uuid",
        application_id,
    )
    assert tuple(fila) == (None, None, [])


@pytest.mark.parametrize("role", ["HR", "Director"])
async def test_la_empresa_no_puede_retirar_la_oposicion(db: asyncpg.Connection, role: str) -> None:
    empresa_id = await _empresa(db, plan="ia")
    vacante_id = await _vacante(db, empresa_id)
    (application_id,) = await _aplicaciones(db, empresa_id, vacante_id, 1, sin_ia=True)

    await assume_tenant(db, empresa_id, role=role)
    with pytest.raises(asyncpg.PostgresError) as exc:
        await db.execute(
            "update applications set sin_ia = false where id = $1::uuid", application_id
        )
    assert exc.value.sqlstate == PROHIBIDO


async def test_vector_hr_si_puede_retirarla_si_el_candidato_lo_pide(
    db: asyncpg.Connection,
) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    (application_id,) = await _aplicaciones(db, empresa_id, vacante_id, 1, sin_ia=True)

    # Sin sesión de tenant: el rol dueño, como lo haría soporte.
    await _elevate(db)
    try:
        await db.execute("select set_config('request.jwt.claims', '', false)")
        await db.execute(
            "update applications set sin_ia = false where id = $1::uuid", application_id
        )
        assert (
            await db.fetchval("select sin_ia from applications where id = $1::uuid", application_id)
            is False
        )
    finally:
        await _drop(db)


# ─────────────────────────────── la purga ───────────────────────────────


async def test_la_purga_borra_solo_lo_de_vacantes_cerradas_hace_30_dias(
    db: asyncpg.Connection,
) -> None:
    empresa_id = await _empresa(db, ajuste=5)
    vieja, reciente, abierta = [await _vacante(db, empresa_id) for _ in range(3)]
    ilegibles = []
    for vacante_id in (vieja, reciente, abierta):
        await _skills(db, empresa_id, vacante_id, ["Python"])
        revisada, ilegible = await _aplicaciones(db, empresa_id, vacante_id, 2)
        await _coincidencias(db, empresa_id, [revisada], ["Python"], [["Python"]])
        ilegibles.append(ilegible)
    for ilegible in ilegibles:
        await _como_dueno(
            db,
            "insert into privado.cvs_ilegibles (application_id, empresa_id)"
            " values ($1::uuid, $2::uuid)",
            ilegible,
            empresa_id,
        )
    await assume_tenant(db, empresa_id)
    for vacante_id in (vieja, reciente):
        await db.execute("update vacantes set status = 'closed' where id = $1::uuid", vacante_id)
    await _como_dueno(
        db, "update vacantes set closed_at = now() - interval '31 days' where id = $1::uuid", vieja
    )

    assert await _como_dueno(db, "select privado.purgar_coincidencias()") == 1
    for tabla in ("privado.coincidencias", "privado.cvs_ilegibles"):
        contar = f"select count(*) from {tabla} where empresa_id = $1::uuid"
        assert await _como_dueno(db, contar, empresa_id) == 2
