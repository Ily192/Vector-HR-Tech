"""El pipeline manual del plan gratis contra Postgres real (migración 0021, ADR-024).

La empresa gratuita mueve a sus candidatos entre todas las etapas y los cierra como
contratados, descartados o retirados, con su sesión, como lo hace el panel. La base
lo deja hacer solo con las aplicaciones de su empresa, y sin tocar lo que ADR-019
protege: el tope de 50 recibidas, la oposición del candidato y el cockpit del plan
con IA. Que mover no encienda la IA lo prueba `test_evaluaciones_ia.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import asyncpg
import pytest

from .conftest import assume_anon, assume_tenant
from .test_gancho import _aplicaciones
from .test_plan_gratis import (
    CONTRATO,
    NO_INCLUIDO,
    _como_soporte,
    _empresa,
    _llenar,
    _sin_cupo,
    _vacante,
)
from .test_rls import _drop, _elevate

pytestmark = pytest.mark.asyncio

#: Las etapas que el contrato abre al plan gratis: desde ADR-024, todas.
ETAPAS_GRATIS: list[str] = CONTRATO["planes"]["gratis"]["etapas_visibles"]
#: Cómo se cierra una aplicación.
SALIDAS = ["hired", "rejected", "withdrawn"]

MOTIVO = "No tiene la licencia de manejo que pide el puesto."


async def _una(db: asyncpg.Connection, *, plan: str = "gratis", **kw: bool) -> tuple[str, str]:
    """Una empresa con una vacante y una aplicación por el career site."""
    empresa_id = await _empresa(db, plan=plan)
    vacante_id = await _vacante(db, empresa_id)
    (application_id,) = await _aplicaciones(db, empresa_id, vacante_id, 1, **kw)
    return empresa_id, application_id


async def _mover(
    db: asyncpg.Connection,
    empresa_id: str,
    application_id: str,
    etapa: str,
    *,
    role: str = "HR",
    motivo: str | None = None,
) -> str:
    """Como el panel: un update con la sesión de la empresa. Devuelve `UPDATE n`."""
    await assume_tenant(db, empresa_id, role=role)
    return await db.execute(
        "update applications"
        " set status = $2::application_status,"
        "     motivo_de_descarte = coalesce($3, motivo_de_descarte)"
        " where id = $1::uuid",
        application_id,
        etapa,
        motivo,
    )


async def _fila(db: asyncpg.Connection, application_id: str) -> asyncpg.Record:
    await _elevate(db)
    try:
        fila = await db.fetchrow(
            "select status::text as status, decided_at, motivo_de_descarte, sin_ia"
            " from applications where id = $1::uuid",
            application_id,
        )
    finally:
        await _drop(db)
    assert fila is not None
    return fila


# ───────────────────────── todas las etapas, a mano ─────────────────────────


async def test_el_contrato_abre_al_plan_gratis_las_mismas_etapas_que_al_de_pago() -> None:
    assert CONTRATO["planes"]["ia"]["etapas_visibles"] == ETAPAS_GRATIS
    assert ETAPAS_GRATIS == ["applied", "evaluated", "shortlisted", "interviewed", "offered"]
    assert CONTRATO["planes"]["gratis"]["incluye_ia"] is False


@pytest.mark.parametrize("etapa", ETAPAS_GRATIS + SALIDAS)
async def test_la_empresa_gratis_mueve_a_su_candidato_a_cualquier_etapa(
    db: asyncpg.Connection, etapa: str
) -> None:
    empresa_id, application_id = await _una(db)

    assert await _mover(db, empresa_id, application_id, etapa) == "UPDATE 1"

    assert (await _fila(db, application_id))["status"] == etapa


async def test_recorre_el_pipeline_y_puede_volver_atras(db: asyncpg.Connection) -> None:
    """Una persona se equivoca y lo corrige: ninguna etapa es de un solo sentido."""
    empresa_id, application_id = await _una(db)
    for etapa in [*ETAPAS_GRATIS[1:], "hired", "shortlisted", "rejected", "applied"]:
        assert await _mover(db, empresa_id, application_id, etapa) == "UPDATE 1"
        assert (await _fila(db, application_id))["status"] == etapa


@pytest.mark.parametrize("plan", ["gratis", "ia"])
async def test_direccion_tambien_mueve_candidatos(db: asyncpg.Connection, plan: str) -> None:
    empresa_id, application_id = await _una(db, plan=plan)
    assert await _mover(db, empresa_id, application_id, "shortlisted", role="Director") == (
        "UPDATE 1"
    )


# ─────────────────────── solo las aplicaciones propias ───────────────────────


async def test_otra_empresa_no_mueve_candidatos_ajenos(db: asyncpg.Connection) -> None:
    _, application_id = await _una(db)
    otra = await _empresa(db)

    assert await _mover(db, otra, application_id, "hired") == "UPDATE 0"

    assert (await _fila(db, application_id))["status"] == "applied"


@pytest.mark.parametrize("role", ["Colaborador", "SuperAdmin", "cliente"])
async def test_solo_hr_y_direccion_mueven_candidatos(db: asyncpg.Connection, role: str) -> None:
    """La policy `applications_tenant_write` (0004): SuperAdmin lee, pero no decide."""
    empresa_id, application_id = await _una(db)

    assert await _mover(db, empresa_id, application_id, "hired", role=role) == "UPDATE 0"

    assert (await _fila(db, application_id))["status"] == "applied"


async def test_sin_sesion_no_se_mueve_a_nadie(db: asyncpg.Connection) -> None:
    """Con la anon key, como el career site: o no tiene permiso o la RLS no le deja filas."""
    _, application_id = await _una(db)
    await assume_anon(db)
    try:
        resultado = await db.execute(
            "update applications set status = 'hired' where id = $1::uuid", application_id
        )
    except asyncpg.InsufficientPrivilegeError:
        resultado = "UPDATE 0"
    assert resultado == "UPDATE 0"
    assert (await _fila(db, application_id))["status"] == "applied"


# ─────────────────────── lo que ADR-019 protege, intacto ───────────────────────


async def test_mover_descartar_y_borrar_no_libera_cupo(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await _llenar(db, vacante_id, 50)

    await assume_tenant(db, empresa_id)
    descartadas = await db.execute(
        "update applications set status = 'rejected'"
        " where id in (select id from applications where vacante_id = $1::uuid limit 40)",
        vacante_id,
    )
    assert descartadas == "UPDATE 40"
    await db.execute(
        "update applications set status = 'hired'"
        " where vacante_id = $1::uuid and status = 'applied'",
        vacante_id,
    )
    await db.execute(
        "delete from applications"
        " where id in (select id from applications where vacante_id = $1::uuid limit 5)",
        vacante_id,
    )
    cupo = await db.fetchrow(
        "select recibidas, completo from cupos_de_aplicaciones() where vacante_id = $1::uuid",
        vacante_id,
    )
    assert cupo is not None
    assert (cupo["recibidas"], cupo["completo"]) == (50, True)

    await assume_anon(db)
    await _sin_cupo(
        db.fetchval("select aplicar_a_vacante($1::uuid, 'Otra', 'otra@example.test')", vacante_id)
    )


async def test_mover_no_retira_la_oposicion_del_candidato(db: asyncpg.Connection) -> None:
    empresa_id, application_id = await _una(db, sin_ia=True)
    for etapa in ETAPAS_GRATIS[1:]:
        await _mover(db, empresa_id, application_id, etapa)
    assert (await _fila(db, application_id))["sin_ia"] is True

    await assume_tenant(db, empresa_id)
    with pytest.raises(asyncpg.PostgresError) as exc:
        await db.execute(
            "update applications set status = 'hired', sin_ia = false where id = $1::uuid",
            application_id,
        )
    assert exc.value.sqlstate == NO_INCLUIDO
    assert (await _fila(db, application_id))["sin_ia"] is True


async def test_la_etapa_en_entrevista_no_abre_el_cockpit(db: asyncpg.Connection) -> None:
    """Mover a "En entrevista" es una etapa; agendar la entrevista sigue siendo de pago."""
    empresa_id, application_id = await _una(db)
    await _mover(db, empresa_id, application_id, "interviewed")

    with pytest.raises(asyncpg.PostgresError) as exc:
        await db.execute(
            "insert into entrevistas (empresa_id, application_id, slot)"
            " values ($1::uuid, $2::uuid, tstzrange(now(), now() + interval '1 hour'))",
            empresa_id,
            application_id,
        )
    assert exc.value.sqlstate == NO_INCLUIDO


# ─────────────────────────── la fecha y el motivo ───────────────────────────


async def test_al_cerrar_queda_la_fecha_y_al_volver_se_borra_con_el_motivo(
    db: asyncpg.Connection,
) -> None:
    empresa_id, application_id = await _una(db)

    await _mover(db, empresa_id, application_id, "hired")
    contratada = await _fila(db, application_id)
    assert contratada["decided_at"] is not None

    await _mover(db, empresa_id, application_id, "rejected", motivo=MOTIVO)
    descartada = await _fila(db, application_id)
    assert descartada["motivo_de_descarte"] == MOTIVO
    assert descartada["decided_at"] >= contratada["decided_at"]

    await _mover(db, empresa_id, application_id, "shortlisted")
    de_vuelta = await _fila(db, application_id)
    assert (de_vuelta["decided_at"], de_vuelta["motivo_de_descarte"]) == (None, None)


async def test_el_motivo_no_sobrevive_al_salir_de_descartados(db: asyncpg.Connection) -> None:
    """De descartado a contratado: el motivo era del descarte, ya no aplica."""
    empresa_id, application_id = await _una(db)
    await _mover(db, empresa_id, application_id, "rejected", motivo=MOTIVO)

    await _mover(db, empresa_id, application_id, "hired")

    fila = await _fila(db, application_id)
    assert (fila["status"], fila["motivo_de_descarte"]) == ("hired", None)
    assert fila["decided_at"] is not None


async def test_en_el_plan_gratis_el_motivo_es_opcional_pero_si_se_escribe_vale(
    db: asyncpg.Connection,
) -> None:
    empresa_id, application_id = await _una(db)
    with pytest.raises(asyncpg.CheckViolationError):
        await _mover(db, empresa_id, application_id, "rejected", motivo="No.")

    assert await _mover(db, empresa_id, application_id, "rejected") == "UPDATE 1"
    fila = await _fila(db, application_id)
    assert (fila["status"], fila["motivo_de_descarte"]) == ("rejected", None)


async def test_vector_hr_puede_fijar_la_fecha_de_la_decision(db: asyncpg.Connection) -> None:
    """Sin sesión de tenant (rol dueño o clave secreta) se corrige un registro a mano."""
    _, application_id = await _una(db)
    fecha = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)

    await _como_soporte(
        db,
        "update applications set status = 'hired', decided_at = $2 where id = $1::uuid",
        application_id,
        fecha,
    )

    assert (await _fila(db, application_id))["decided_at"] == fecha


async def test_un_alta_directa_ya_cerrada_lleva_su_fecha(db: asyncpg.Connection) -> None:
    """La empresa da de alta con su sesión a alguien que ya contrató (cuenta para las 50)."""
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await assume_tenant(db, empresa_id)
    candidato_id = await db.fetchval(
        "insert into candidatos (empresa_id, full_name, email) values ($1::uuid, 'Directa', $2)"
        " returning id",
        empresa_id,
        f"{uuid.uuid4().hex[:10]}@example.test",
    )
    application_id = str(
        await db.fetchval(
            "insert into applications (empresa_id, vacante_id, candidato_id, status)"
            " values ($1::uuid, $2::uuid, $3, 'hired') returning id",
            empresa_id,
            vacante_id,
            candidato_id,
        )
    )

    assert (await _fila(db, application_id))["decided_at"] is not None


async def test_el_plan_ia_sigue_usando_todas_las_etapas(db: asyncpg.Connection) -> None:
    empresa_id, application_id = await _una(db, plan="ia")
    for etapa in CONTRATO["planes"]["ia"]["etapas_visibles"][1:]:
        assert await _mover(db, empresa_id, application_id, etapa) == "UPDATE 1"
