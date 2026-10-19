"""Límites del plan gratuito aplicados en la base (migración 0008, ADR-017).

El panel escribe sus vacantes con la sesión de Supabase y el career site aplica con
la anon key: ninguno pasa por el hr-engine, así que la base es la que corta.
Estos tests comprueban también que la copia en SQL diga lo mismo que el contrato
`packages/types/contracts/limites-plan.json`.

Cada test crea su propia empresa para no tocar el seed que usan los demás.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from .conftest import assume_anon, assume_tenant
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
    assert dict(cupo) == {"activas": 3, "limite": 4, "libres": 1, "max_aplicaciones": 50}


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
