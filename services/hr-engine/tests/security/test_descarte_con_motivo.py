"""Descartar lo que evaluó la IA exige un motivo, contra Postgres real (migración 0015, ADR-021 §4).

La IA solo sugiere: una persona decide y deja el motivo. La regla está en la base,
así que vale para el panel y para cualquier otra vía con la sesión de la empresa.
"""

from __future__ import annotations

import asyncpg
import pytest

from .conftest import assume_tenant
from .test_gancho import _aplicaciones, _como_dueno
from .test_plan_gratis import _empresa, _vacante

pytestmark = pytest.mark.asyncio

MOTIVO = "No tiene la experiencia en inventarios que pide el puesto."


async def _aplicacion(db: asyncpg.Connection, *, plan: str = "ia", evaluada: bool = True):
    empresa_id = await _empresa(db, plan=plan)
    vacante_id = await _vacante(db, empresa_id)
    (application_id,) = await _aplicaciones(db, empresa_id, vacante_id, 1)
    if evaluada:
        await _como_dueno(
            db,
            "update applications set fit_score = 3.5, fit_rationale = 'Pocas skills del puesto.',"
            " status = 'evaluated' where id = $1::uuid",
            application_id,
        )
    return empresa_id, application_id


async def _descartar(
    db: asyncpg.Connection, empresa_id: str, application_id: str, motivo: str | None
) -> None:
    """Como lo hace el panel: con la sesión de HR de la empresa."""
    await assume_tenant(db, empresa_id)
    await db.execute(
        "update applications set status = 'rejected', motivo_de_descarte = $2 where id = $1::uuid",
        application_id,
        motivo,
    )


async def test_descartar_lo_que_evaluo_la_ia_sin_motivo_es_422(db: asyncpg.Connection) -> None:
    empresa_id, application_id = await _aplicacion(db)
    with pytest.raises(asyncpg.PostgresError) as exc:
        await _descartar(db, empresa_id, application_id, None)
    assert exc.value.sqlstate == "PT422"


async def test_un_motivo_en_blanco_tampoco_vale(db: asyncpg.Connection) -> None:
    empresa_id, application_id = await _aplicacion(db)
    with pytest.raises(asyncpg.PostgresError):
        await _descartar(db, empresa_id, application_id, "          ")


async def test_un_motivo_de_menos_de_10_caracteres_no_se_acepta(db: asyncpg.Connection) -> None:
    empresa_id, application_id = await _aplicacion(db)
    with pytest.raises(asyncpg.CheckViolationError):
        await _descartar(db, empresa_id, application_id, "No.")


async def test_con_motivo_se_descarta_y_queda_la_fecha(db: asyncpg.Connection) -> None:
    empresa_id, application_id = await _aplicacion(db)

    await _descartar(db, empresa_id, application_id, MOTIVO)

    fila = await db.fetchrow(
        "select status::text, motivo_de_descarte, decided_at from applications where id = $1::uuid",
        application_id,
    )
    assert fila is not None
    assert (fila["status"], fila["motivo_de_descarte"]) == ("rejected", MOTIVO)
    assert fila["decided_at"] is not None


@pytest.mark.parametrize("plan", ["gratis", "ia"])
async def test_sin_evaluacion_de_la_ia_no_se_pide_motivo(db: asyncpg.Connection, plan: str) -> None:
    empresa_id, application_id = await _aplicacion(db, plan=plan, evaluada=False)

    await _descartar(db, empresa_id, application_id, None)

    assert (
        await db.fetchval(
            "select status::text from applications where id = $1::uuid", application_id
        )
        == "rejected"
    )
