"""El gancho del plan gratis y las etapas de pago, aplicados en la base (migración 0009, ADR-018).

La empresa gratuita ve cuántos de sus CVs califican, nunca quién: las
preevaluaciones viven en `privado`, fuera del alcance de su sesión, y solo
salen agregadas y por lotes por `resumen_del_gancho()`. Estos tests comprueban
también que esa copia en SQL diga lo mismo que `contracts/gancho.json`.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
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

#: SQLSTATE con el que la base rechaza una etapa que el plan no incluye (HTTP 403).
ETAPA_DE_PAGO = "PT403"


async def _aplicaciones(
    db: asyncpg.Connection, empresa_id: str, vacante_id: str, total: int, *, con_cv: bool = True
) -> list[str]:
    """Aplica `total` candidatos por la vía pública, como el career site."""
    await assume_anon(db)
    ids = []
    for _ in range(total):
        sufijo = uuid.uuid4().hex[:10]
        ids.append(
            str(
                await db.fetchval(
                    "select aplicar_a_vacante($1::uuid, $2, $3, $4)",
                    vacante_id,
                    f"Candidata {sufijo}",
                    f"{sufijo}@example.test",
                    f"{empresa_id}/{sufijo}.pdf" if con_cv else None,
                )
            )
        )
    return ids


async def _preevaluar(
    db: asyncpg.Connection,
    empresa_id: str,
    application_ids: list[str],
    evaluaciones: list[dict[str, Any]],
) -> None:
    """Guarda preevaluaciones como lo hará el hr-engine, una por segundo para fijar el orden."""
    await _elevate(db)
    try:
        for orden, (application_id, e) in enumerate(
            zip(application_ids, evaluaciones, strict=False)
        ):
            await db.execute(
                """
                insert into privado.preevaluaciones
                    (application_id, empresa_id, fit_score, fit_rationale, fit_gaps,
                     duracion_ms, modelo, evaluado_en)
                values ($1::uuid, $2::uuid, $3, 'Razonamiento de prueba', $4::text[], $5,
                        'gemini-2.5-flash', now() + make_interval(secs => $6))
                """,
                application_id,
                empresa_id,
                Decimal(str(e["score"])),
                e["gaps"],
                e["ms"],
                float(orden),
            )
    finally:
        await _drop(db)


async def _resumen(db: asyncpg.Connection, empresa_id: str, vacante_id: str, role: str = "HR"):
    await assume_tenant(db, empresa_id, role=role)
    return await db.fetchrow("select * from resumen_del_gancho($1::uuid)", vacante_id)


# ─────────────────────── la regla en SQL = el contrato ───────────────────────


@pytest.mark.parametrize("caso", CONTRATO["casos"], ids=lambda c: c["nombre"])
async def test_el_resumen_en_sql_cumple_el_contrato(
    db: asyncpg.Connection, caso: dict[str, Any]
) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    recibidas = len(caso["evaluaciones"]) + 2  # dos CVs que aún no se evaluaron
    ids = await _aplicaciones(db, empresa_id, vacante_id, recibidas)
    await _preevaluar(db, empresa_id, ids, caso["evaluaciones"])

    fila = await _resumen(db, empresa_id, vacante_id)
    esperado = caso["resumen"]
    assert dict(fila) == {
        "aplicaciones": recibidas,
        "en_espera": recibidas - esperado["cvs_evaluados"],
        **esperado,
    }


async def test_las_aplicaciones_sin_cv_no_quedan_en_espera(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await _aplicaciones(db, empresa_id, vacante_id, 3)
    await _aplicaciones(db, empresa_id, vacante_id, 2, con_cv=False)

    fila = await _resumen(db, empresa_id, vacante_id)
    assert (fila["aplicaciones"], fila["cvs_evaluados"], fila["en_espera"]) == (5, 0, 3)


# ─────────────────────────── quién ve el gancho ───────────────────────────


async def test_la_empresa_no_puede_leer_las_preevaluaciones(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    ids = await _aplicaciones(db, empresa_id, vacante_id, 1)
    await _preevaluar(db, empresa_id, ids, [{"score": 9, "gaps": [], "ms": 900}])

    for role in ("HR", "Director"):
        await assume_tenant(db, empresa_id, role=role)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await db.fetch("select * from privado.preevaluaciones")
    # Y en `applications` no hay nada que leer: el score no se escribe ahí.
    await assume_tenant(db, empresa_id)
    assert (
        await db.fetchval("select fit_score from applications where id = $1::uuid", ids[0]) is None
    )


async def test_el_resumen_es_solo_de_las_vacantes_propias(db: asyncpg.Connection) -> None:
    duena = await _empresa(db)
    otra = await _empresa(db)
    vacante_id = await _vacante(db, duena)
    assert await _resumen(db, otra, vacante_id) is None


async def test_sin_rol_de_hr_no_hay_resumen(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    assert await _resumen(db, empresa_id, vacante_id, role="Colaborador") is None


async def test_la_anon_key_no_puede_pedir_el_resumen(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    await assume_anon(db)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.fetch("select * from resumen_del_gancho($1::uuid)", vacante_id)


async def test_con_el_plan_ia_no_hay_gancho(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    vacante_id = await _vacante(db, empresa_id)
    assert await _resumen(db, empresa_id, vacante_id) is None


async def test_una_preevaluacion_no_puede_ser_de_otro_tenant(db: asyncpg.Connection) -> None:
    duena = await _empresa(db)
    otra = await _empresa(db)
    vacante_id = await _vacante(db, duena)
    ids = await _aplicaciones(db, duena, vacante_id, 1)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await _preevaluar(db, otra, ids, [{"score": 9, "gaps": [], "ms": 900}])


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
    assert exc.value.sqlstate == ETAPA_DE_PAGO


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


async def test_al_contratar_se_desbloquea_lo_que_ya_estaba_evaluado(
    db: asyncpg.Connection,
) -> None:
    empresa_id = await _empresa(db)
    vacante_id = await _vacante(db, empresa_id)
    evaluada, sin_evaluar = await _aplicaciones(db, empresa_id, vacante_id, 2)
    await _preevaluar(db, empresa_id, [evaluada], [{"score": 8.5, "gaps": ["SAP"], "ms": 900}])

    await _elevate(db)
    try:
        await db.execute("update empresas set plan = 'ia' where id = $1::uuid", empresa_id)
        assert (
            await db.fetchval(
                "select count(*) from privado.preevaluaciones where empresa_id = $1::uuid",
                empresa_id,
            )
            == 0
        )
    finally:
        await _drop(db)

    await assume_tenant(db, empresa_id)
    filas = {
        str(f["id"]): f
        for f in await db.fetch(
            "select id, status::text, fit_score, fit_gaps from applications"
            " where vacante_id = $1::uuid",
            vacante_id,
        )
    }
    assert filas[evaluada]["status"] == "evaluated"
    assert float(filas[evaluada]["fit_score"]) == 8.5
    assert filas[evaluada]["fit_gaps"] == ["SAP"]
    assert filas[sin_evaluar]["status"] == "applied"
    assert filas[sin_evaluar]["fit_score"] is None
