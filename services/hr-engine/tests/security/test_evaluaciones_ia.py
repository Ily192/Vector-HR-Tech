"""El SQL de la evaluación con IA del plan de pago contra Postgres real (migración 0014, ADR-021).

El barrido corre con el rol dueño y sin contexto de tenant: recorre todas las
empresas con IA. Estos tests fijan qué reclama, que guarda solo lo que sigue
vigente, que la cuenta respeta sus topes y que nada de eso se ve desde la API.

La base se comparte entre tests, así que cada uno mira solo sus propias aplicaciones.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.domain.entidades import FitScore, ResultadoScoring
from app.domain.evaluacion_ia import MAX_INTENTOS, MINUTOS_DE_RECLAMO
from app.repositories import evaluaciones as repo

from .conftest import _asyncpg_dsn, assume_anon, assume_tenant
from .test_gancho import _aplicaciones, _como_dueno
from .test_plan_gratis import _empresa, _vacante
from .test_rls import _drop, _elevate

pytestmark = pytest.mark.asyncio

RESULTADO = ResultadoScoring(
    fit=FitScore(
        score=7.5,
        rationale="Buen encaje con el control de inventarios.",
        gaps=("SQL",),
        strengths=("Excel",),
    ),
    cost_usd=0.0025,
    model="gemini-2.5-flash",
)


@pytest_asyncio.fixture
async def sesion(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    """La sesión del worker: rol dueño, sin contexto de tenant."""
    motor = create_async_engine(
        _asyncpg_dsn().replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool
    )
    async with AsyncSession(motor) as s:
        yield s
    await motor.dispose()


async def _vacante_con_aplicaciones(
    db: asyncpg.Connection, total: int, *, plan: str = "ia", **kw: bool
) -> tuple[str, str, list[str]]:
    empresa_id = await _empresa(db, plan=plan)
    vacante_id = await _vacante(db, empresa_id)
    return empresa_id, vacante_id, await _aplicaciones(db, empresa_id, vacante_id, total, **kw)


async def _reclamar(sesion: AsyncSession, limite: int = 10_000) -> list[repo.ReclamadaRow]:
    filas = await repo.reclamar(
        sesion, limite=limite, max_intentos=MAX_INTENTOS, minutos_de_reclamo=MINUTOS_DE_RECLAMO
    )
    await sesion.commit()
    return filas


async def _reclamadas(sesion: AsyncSession, mias: list[str]) -> set[str]:
    return {str(f.application_id) for f in await _reclamar(sesion)} & set(mias)


async def _guardar(sesion: AsyncSession, application_id: str, empresa_id: str) -> bool:
    guardada = await repo.guardar(
        sesion,
        application_id=UUID(application_id),
        empresa_id=UUID(empresa_id),
        score=RESULTADO.fit.score,
        rationale=RESULTADO.fit.rationale,
        gaps=list(RESULTADO.fit.gaps),
        strengths=list(RESULTADO.fit.strengths),
        costo_usd=RESULTADO.cost_usd,
        tope_usd=0.05,
        modelo=RESULTADO.model,
    )
    await sesion.commit()
    return guardada


async def _fila(db: asyncpg.Connection, sql: str, *args: object) -> asyncpg.Record | None:
    await _elevate(db)
    try:
        return await db.fetchrow(sql, *args)
    finally:
        await _drop(db)


async def _application(db: asyncpg.Connection, application_id: str) -> asyncpg.Record:
    fila = await _fila(
        db,
        """
        select a.status::text as status, a.fit_score, a.fit_gaps, a.fit_strengths,
               a.evaluada_en, ev.intentos, ev.reclamada_en, ev.evaluada_en as en_la_cuenta
          from applications a
          left join privado.evaluaciones_ia ev on ev.application_id = a.id
         where a.id = $1::uuid
        """,
        application_id,
    )
    assert fila is not None
    return fila


async def _resumen(db: asyncpg.Connection, empresa_id: str, vacante_id: str, role: str = "HR"):
    await assume_tenant(db, empresa_id, role=role)
    return await db.fetchrow("select * from resumen_de_evaluaciones($1::uuid)", vacante_id)


# ─────────────────────────────── qué reclama ───────────────────────────────


async def test_reclama_solo_lo_que_hay_que_evaluar(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, vacante_id, (nueva, ilegible, evaluada, movida) = await _vacante_con_aplicaciones(
        db, 4
    )
    (sin_cv,) = await _aplicaciones(db, empresa_id, vacante_id, 1, con_cv=False)
    (opuesta,) = await _aplicaciones(db, empresa_id, vacante_id, 1, sin_ia=True)
    await _como_dueno(
        db,
        "insert into privado.cvs_ilegibles (application_id, empresa_id) values ($1::uuid, $2::uuid)",
        ilegible,
        empresa_id,
    )
    await _como_dueno(db, "update applications set fit_score = 8 where id = $1::uuid", evaluada)
    # Una persona la movió antes de que la evaluara la IA: ya no es del barrido.
    await assume_tenant(db, empresa_id)
    await db.execute("update applications set status = 'shortlisted' where id = $1::uuid", movida)

    _, _, (de_gratis,) = await _vacante_con_aplicaciones(db, 1, plan="gratis")
    cerrada_empresa, cerrada, (de_cerrada,) = await _vacante_con_aplicaciones(db, 1)
    await assume_tenant(db, cerrada_empresa)
    await db.execute("update vacantes set status = 'closed' where id = $1::uuid", cerrada)

    mias = [nueva, ilegible, evaluada, movida, sin_cv, opuesta, de_gratis, de_cerrada]
    assert await _reclamadas(sesion, mias) == {nueva}


async def test_lo_reclamado_trae_el_cv_el_candidato_y_la_vacante(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, vacante_id, (application_id,) = await _vacante_con_aplicaciones(db, 1)
    await assume_tenant(db, empresa_id)
    await db.execute(
        "update vacantes set skills = '{Excel,Inventarios}', location = 'Monterrey, NL'"
        " where id = $1::uuid",
        vacante_id,
    )

    (fila,) = [f for f in await _reclamar(sesion) if str(f.application_id) == application_id]

    assert fila.plan == "ia"
    assert fila.ruta.startswith(f"{empresa_id}/")
    assert fila.nombre.startswith("Candidata ")
    assert fila.correo is not None and fila.correo.endswith("@example.test")
    assert (fila.titulo, fila.descripcion) == ("Vacante", "Descripción")
    assert fila.skills == ["Excel", "Inventarios"]
    assert fila.ubicacion == "Monterrey, NL"


async def test_un_reclamo_suma_un_intento_y_ningun_otro_barrido_la_toma(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    _, _, (application_id,) = await _vacante_con_aplicaciones(db, 1)

    assert await _reclamadas(sesion, [application_id]) == {application_id}
    assert (await _application(db, application_id))["intentos"] == 1
    assert await _reclamadas(sesion, [application_id]) == set()

    # Un reclamo viejo es de un barrido que murió: se puede volver a tomar.
    await _como_dueno(
        db,
        "update privado.evaluaciones_ia set reclamada_en = now() - make_interval(mins => $2)"
        " where application_id = $1::uuid",
        application_id,
        MINUTOS_DE_RECLAMO + 1,
    )
    assert await _reclamadas(sesion, [application_id]) == {application_id}
    assert (await _application(db, application_id))["intentos"] == 2


# ─────────────────────────────── qué guarda ────────────────────────────────


async def test_guardar_la_pasa_a_evaluados_y_registra_el_costo(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, _, (application_id,) = await _vacante_con_aplicaciones(db, 1)
    await _reclamar(sesion)
    antes = await repo.gastado_este_mes(sesion)

    assert await _guardar(sesion, application_id, empresa_id)

    fila = await _application(db, application_id)
    assert fila["status"] == "evaluated"
    assert float(fila["fit_score"]) == RESULTADO.fit.score
    assert (fila["fit_gaps"], fila["fit_strengths"]) == (["SQL"], ["Excel"])
    assert fila["evaluada_en"] is not None and fila["en_la_cuenta"] is not None
    assert fila["reclamada_en"] is None
    corrida = await _fila(
        db,
        "select status, cost_usd, payload from runs where payload->>'application_id' = $1"
        " and status = 'completed'",
        application_id,
    )
    assert corrida is not None
    assert float(corrida["cost_usd"]) == RESULTADO.cost_usd
    assert '"origen": "interno"' in corrida["payload"]
    assert await repo.gastado_este_mes(sesion) == pytest.approx(antes + RESULTADO.cost_usd)


async def test_si_el_candidato_se_opuso_no_se_guarda_pero_el_costo_si(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, _, (application_id,) = await _vacante_con_aplicaciones(db, 1)
    await _reclamar(sesion)
    await _como_dueno(
        db, "update applications set sin_ia = true where id = $1::uuid", application_id
    )

    assert not await _guardar(sesion, application_id, empresa_id)

    fila = await _application(db, application_id)
    assert (fila["status"], fila["fit_score"]) == ("applied", None)
    corrida = await _fila(
        db, "select payload from runs where payload->>'application_id' = $1", application_id
    )
    assert corrida is not None and '"guardada": false' in corrida["payload"]


async def test_si_la_empresa_dejo_el_plan_con_ia_no_se_guarda(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, _, (application_id,) = await _vacante_con_aplicaciones(db, 1)
    await _reclamar(sesion)
    await _como_dueno(
        db, "update empresas set plan = 'gratis'::plan_empresa where id = $1::uuid", empresa_id
    )

    assert not await _guardar(sesion, application_id, empresa_id)
    assert (await _application(db, application_id))["status"] == "applied"


# ─────────────────────────── intentos y ilegibles ──────────────────────────


async def test_tras_max_intentos_queda_sin_evaluar(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, vacante_id, (application_id,) = await _vacante_con_aplicaciones(db, 1)
    for _ in range(MAX_INTENTOS):
        assert await _reclamadas(sesion, [application_id]) == {application_id}
        await repo.aplazar(
            sesion, application_id=UUID(application_id), motivo="LLMUnavailableError", tope_usd=0.05
        )
        await sesion.commit()

    assert await _reclamadas(sesion, [application_id]) == set()
    resumen = await _resumen(db, empresa_id, vacante_id)
    assert (resumen["en_espera"], resumen["sin_evaluar"]) == (0, 1)
    fallidas = await _como_dueno(
        db,
        "select count(*) from runs where payload->>'application_id' = $1 and status = 'failed'"
        " and error_message = 'LLMUnavailableError'",
        application_id,
    )
    assert fallidas == MAX_INTENTOS


async def test_soltar_devuelve_el_intento(db: asyncpg.Connection, sesion: AsyncSession) -> None:
    _, _, (application_id,) = await _vacante_con_aplicaciones(db, 1)
    await _reclamar(sesion)

    await repo.soltar(sesion, application_id=UUID(application_id))
    await sesion.commit()

    fila = await _application(db, application_id)
    assert (fila["intentos"], fila["reclamada_en"]) == (0, None)
    assert await _reclamadas(sesion, [application_id]) == {application_id}


async def test_un_cv_ilegible_no_se_vuelve_a_reclamar(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, vacante_id, (application_id,) = await _vacante_con_aplicaciones(db, 1)
    await _reclamar(sesion)

    await repo.marcar_ilegible(
        sesion, application_id=UUID(application_id), empresa_id=UUID(empresa_id)
    )
    await sesion.commit()
    await _como_dueno(
        db,
        "update privado.evaluaciones_ia set reclamada_en = null where application_id = $1::uuid",
        application_id,
    )

    assert await _reclamadas(sesion, [application_id]) == set()
    assert (await _resumen(db, empresa_id, vacante_id))["ilegibles"] == 1


# ──────────────────────────────── los topes ────────────────────────────────


async def test_el_tope_del_mes_de_la_empresa(db: asyncpg.Connection, sesion: AsyncSession) -> None:
    empresa_id, _, (primera, segunda) = await _vacante_con_aplicaciones(db, 2)
    await _como_dueno(db, "update empresas set ia_cvs_por_mes = 1 where id = $1::uuid", empresa_id)

    # Por debajo del tope se reclama el lote entero: el tope puede pasarse por un lote.
    assert await _reclamadas(sesion, [primera, segunda]) == {primera, segunda}
    assert await _guardar(sesion, primera, empresa_id)
    await repo.soltar(sesion, application_id=UUID(segunda))
    await sesion.commit()

    # Con una evaluada este mes, la empresa llegó a su tope de 1.
    assert await _reclamadas(sesion, [segunda]) == set()


async def test_con_tope_cero_no_se_reclama_nada(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, _, ids = await _vacante_con_aplicaciones(db, 2)
    await _como_dueno(db, "update empresas set ia_cvs_por_mes = 0 where id = $1::uuid", empresa_id)
    assert await _reclamadas(sesion, ids) == set()


async def test_la_empresa_no_puede_subir_su_propio_tope(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    await assume_tenant(db, empresa_id, role="Director")
    resultado = await db.execute(
        "update empresas set ia_cvs_por_mes = 100000 where id = $1::uuid", empresa_id
    )
    assert resultado == "UPDATE 0"
    assert (
        await _como_dueno(db, "select ia_cvs_por_mes from empresas where id = $1::uuid", empresa_id)
        == 1000
    )


# ─────────────────────────────── la oposición ──────────────────────────────


async def test_la_oposicion_devuelve_a_aplicados_lo_que_evaluo_la_ia(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id, _, (evaluada, movida) = await _vacante_con_aplicaciones(db, 2)
    await _reclamar(sesion)
    for application_id in (evaluada, movida):
        assert await _guardar(sesion, application_id, empresa_id)
    await assume_tenant(db, empresa_id)
    await db.execute("update applications set status = 'shortlisted' where id = $1::uuid", movida)

    await _como_dueno(
        db, "update applications set sin_ia = true where id = any($1::uuid[])", [evaluada, movida]
    )

    for application_id, etapa in ((evaluada, "applied"), (movida, "shortlisted")):
        fila = await _application(db, application_id)
        assert fila["status"] == etapa
        assert fila["fit_score"] is None and fila["evaluada_en"] is None
        assert fila["fit_strengths"] == []
        # Sin su cuenta: tampoco cuenta para el tope del mes.
        assert fila["intentos"] is None


# ───────────────────────────── lo que se expone ────────────────────────────


async def test_vacantes_publicas_dice_si_la_empresa_evalua_con_ia(db: asyncpg.Connection) -> None:
    _, con_ia, _ = await _vacante_con_aplicaciones(db, 0)
    _, sin_ia, _ = await _vacante_con_aplicaciones(db, 0, plan="gratis")
    await assume_anon(db)
    filas = {
        str(f["id"]): f["evalua_con_ia"]
        for f in await db.fetch(
            "select id, evalua_con_ia from vacantes_publicas where id = any($1::uuid[])",
            [con_ia, sin_ia],
        )
    }
    assert filas == {con_ia: True, sin_ia: False}


@pytest.mark.parametrize("como", ["anon", "authenticated"])
async def test_la_cuenta_del_barrido_no_se_ve_desde_la_api(
    db: asyncpg.Connection, como: str
) -> None:
    empresa_id = await _empresa(db, plan="ia")
    if como == "anon":
        await assume_anon(db)
    else:
        await assume_tenant(db, empresa_id)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.fetch("select * from privado.evaluaciones_ia")


async def test_el_resumen_cuenta_cada_estado(db: asyncpg.Connection, sesion: AsyncSession) -> None:
    empresa_id, vacante_id, (evaluada, en_espera, ilegible) = await _vacante_con_aplicaciones(db, 3)
    await _aplicaciones(db, empresa_id, vacante_id, 1, sin_ia=True)
    await _como_dueno(
        db,
        "insert into privado.cvs_ilegibles (application_id, empresa_id) values ($1::uuid, $2::uuid)",
        ilegible,
        empresa_id,
    )
    await _reclamar(sesion)
    assert await _guardar(sesion, evaluada, empresa_id)
    await repo.soltar(sesion, application_id=UUID(en_espera))
    await sesion.commit()

    resumen = await _resumen(db, empresa_id, vacante_id)

    assert dict(resumen) == {
        "aplicaciones": 4,
        "evaluadas": 1,
        "en_espera": 1,
        "sin_evaluar": 0,
        "ilegibles": 1,
        "sin_ia": 1,
    }


async def test_el_resumen_es_solo_para_la_empresa_con_ia_y_su_gente(db: asyncpg.Connection) -> None:
    empresa_id, vacante_id, _ = await _vacante_con_aplicaciones(db, 1)
    otra = await _empresa(db, plan="ia")
    gratis_id, de_gratis, _ = await _vacante_con_aplicaciones(db, 1, plan="gratis")

    assert await _resumen(db, otra, vacante_id) is None
    assert await _resumen(db, gratis_id, de_gratis) is None
    assert await _resumen(db, empresa_id, vacante_id, role="Colaborador") is None
    assert (await _resumen(db, empresa_id, vacante_id))["aplicaciones"] == 1
