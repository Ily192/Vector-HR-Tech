"""El resumen del cockpit del plan con IA contra Postgres real (migración 0016, ADR-021).

`resumen_del_cockpit()` le da al cockpit sus números ya calculados: la UI no suma
ni compara ventanas de tiempo (ADR-016 §4). Estos tests fijan cada número, que
solo cuenta lo de la empresa de la sesión y que las dos reglas que el SQL copia
del hr-engine, el umbral de entrevista y los intentos, digan lo mismo que su dueña.

Cada test crea su propia empresa: el resumen es por empresa, así que no se pisan.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from app.domain.evaluacion_ia import MAX_INTENTOS
from app.domain.siguiente_paso import UMBRAL_ENTREVISTA, siguiente_paso

from .conftest import assume_anon, assume_tenant
from .test_gancho import _aplicaciones
from .test_plan_gratis import _empresa, _vacante
from .test_rls import _drop, _elevate

pytestmark = pytest.mark.asyncio

_REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pnpm-workspace.yaml").exists()
)
CONTRATO: dict[str, Any] = json.loads(
    (_REPO_ROOT / "packages/types/contracts/siguiente-paso.json").read_text(encoding="utf-8")
)

MOTIVO = "No tiene la experiencia que pide el puesto."


async def _dueno(db: asyncpg.Connection, sql: str, *args: Any) -> Any:
    """Como Vector HR: rol dueño y sin sesión de tenant, que algunos triggers miran."""
    await db.execute("select set_config('request.jwt.claims', '', false)")
    await _elevate(db)
    try:
        return await db.fetchval(sql, *args)
    finally:
        await _drop(db)


async def _cockpit(
    db: asyncpg.Connection, empresa_id: str, role: str = "HR"
) -> asyncpg.Record | None:
    await assume_tenant(db, empresa_id, role=role)
    return await db.fetchrow("select * from resumen_del_cockpit()")


def _json(valor: str | None) -> Any:
    """asyncpg entrega el jsonb como texto."""
    return None if valor is None else json.loads(valor)


async def _evaluar(
    db: asyncpg.Connection,
    empresa_id: str,
    application_id: str,
    score: float,
    status: str = "evaluated",
) -> None:
    """Lo que deja el barrido al guardar (0014), con la etapa a la que la movió una persona."""
    await _dueno(
        db,
        """
        update applications
           set fit_score = $2, fit_rationale = 'Encaja con lo que pide el puesto.',
               evaluada_en = now(), status = $3::application_status,
               motivo_de_descarte = case when $3::text = 'rejected' then $4 end
         where id = $1::uuid
        """,
        application_id,
        score,
        status,
        MOTIVO,
    )
    await _dueno(
        db,
        """
        insert into privado.evaluaciones_ia (application_id, empresa_id, intentos, evaluada_en)
        values ($1::uuid, $2::uuid, 1, now())
        """,
        application_id,
        empresa_id,
    )


async def _corrida(
    db: asyncpg.Connection,
    empresa_id: str,
    status: str = "completed",
    *,
    horas: float = 0,
    application_id: str | None = None,
    agente: str = "cv-evaluator",
) -> None:
    """Un run como los que deja el barrido (0014), de hace `horas`."""
    await _dueno(
        db,
        """
        insert into runs (empresa_id, agent_skill, status, cost_usd, started_at, finished_at,
                          payload)
        values ($1::uuid, $2, $3, 0.0025, now() - make_interval(secs => $4::float8 * 3600),
                now() - make_interval(secs => $4::float8 * 3600),
                jsonb_build_object('origen', 'interno', 'application_id', $5::text))
        """,
        empresa_id,
        agente,
        status,
        horas,
        application_id,
    )


# ─────────────────────────────── quién lo ve ───────────────────────────────


async def test_es_solo_para_la_empresa_con_ia_y_su_gente(db: asyncpg.Connection) -> None:
    con_ia = await _empresa(db, plan="ia")
    gratis = await _empresa(db, plan="gratis")

    assert await _cockpit(db, gratis) is None
    assert await _cockpit(db, con_ia, role="Colaborador") is None
    assert await _cockpit(db, con_ia, role="Director") is not None

    await assume_anon(db)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.fetchrow("select * from resumen_del_cockpit()")


async def test_sin_vacantes_todo_queda_en_cero(db: asyncpg.Connection) -> None:
    fila = await _cockpit(db, await _empresa(db, plan="ia"))

    assert fila is not None
    datos = dict(fila)
    assert _json(datos.pop("embudo")) == dict.fromkeys(
        ("applied", "evaluated", "shortlisted", "interviewed", "offered"), 0
    )
    assert datos == {
        "candidatos_en_proceso": 0,
        "candidatos_nuevos_24h": 0,
        "vacantes_publicadas": 0,
        "vacantes_nuevas_7d": 0,
        "evaluaciones_24h": 0,
        "porcentaje_sin_error": None,
        "en_espera": 0,
        "cvs_del_mes": 0,
        "tope_del_mes": 1000,
        "porcentaje_del_tope": 0,
        "tope_alcanzado": False,
        "decisiones_pendientes": 0,
        "decision": None,
        "vacante": None,
        "evaluados": 0,
        "mejores_evaluados": "[]",
        "registro": "[]",
    }


# ──────────────────────────── candidatos y vacantes ────────────────────────────


async def test_cuenta_candidatos_y_vacantes_abiertas_de_la_empresa(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    una = await _vacante(db, empresa_id)
    otra = await _vacante(db, empresa_id)
    cerrada = await _vacante(db, empresa_id)
    _, _, de_antier = await _aplicaciones(db, empresa_id, una, 3)
    (descartada,) = await _aplicaciones(db, empresa_id, otra, 1)
    await _aplicaciones(db, empresa_id, cerrada, 2)
    await _dueno(
        db,
        "update applications set applied_at = now() - interval '2 days' where id = $1::uuid",
        de_antier,
    )
    await _dueno(db, "update applications set status = 'rejected' where id = $1::uuid", descartada)
    await _dueno(
        db,
        "update vacantes set publicada_en = now() - interval '10 days' where id = $1::uuid",
        otra,
    )
    await assume_tenant(db, empresa_id)
    await db.execute("update vacantes set status = 'closed' where id = $1::uuid", cerrada)
    ajena = await _empresa(db, plan="ia")
    await _aplicaciones(db, ajena, await _vacante(db, ajena), 2)

    fila = await _cockpit(db, empresa_id)

    assert fila is not None
    # La descartada ya no está en proceso, pero llegó hoy; la de antier, al revés.
    assert (fila["candidatos_en_proceso"], fila["candidatos_nuevos_24h"]) == (3, 3)
    assert (fila["vacantes_publicadas"], fila["vacantes_nuevas_7d"]) == (2, 1)


# ───────────────────────────── la decisión del día ─────────────────────────────


async def test_listos_para_entrevista_con_el_umbral_de_la_duena(db: asyncpg.Connection) -> None:
    """El 7 del SQL es `UMBRAL_ENTREVISTA`: los casos del contrato y los dos lados del umbral.

    El score se guarda con un decimal, así que cada caso se compara ya redondeado.
    """
    scores = sorted(
        {round(c["score"], 1) for c in CONTRATO["casos"]}
        | {UMBRAL_ENTREVISTA - 0.1, UMBRAL_ENTREVISTA}
    )
    empresa_id = await _empresa(db, plan="ia")
    vacante_id = await _vacante(db, empresa_id)
    ids = await _aplicaciones(db, empresa_id, vacante_id, len(scores))
    for application_id, score in zip(ids, scores, strict=True):
        await _evaluar(db, empresa_id, application_id, score)

    fila = await _cockpit(db, empresa_id)

    assert fila is not None
    decision = _json(fila["decision"])
    a_entrevista = sorted((s for s in scores if siguiente_paso(s) == "entrevista"), reverse=True)
    assert decision["tipo"] == "entrevistar"
    assert decision["listos"] == len(a_entrevista)
    assert decision["scores"] == a_entrevista[:3]


async def test_la_decision_del_dia_va_primero_por_las_entrevistas(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    con_mas = await _vacante(db, empresa_id)
    con_menos = await _vacante(db, empresa_id)
    por_revisar = await _vacante(db, empresa_id)
    una, otra, movida = await _aplicaciones(db, empresa_id, con_mas, 3)
    (sola,) = await _aplicaciones(db, empresa_id, con_menos, 1)
    await _aplicaciones(db, empresa_id, por_revisar, 1, sin_ia=True)
    await _evaluar(db, empresa_id, una, 8.5)
    await _evaluar(db, empresa_id, otra, 9.1)
    # Una persona ya la preseleccionó: esa decisión está tomada.
    await _evaluar(db, empresa_id, movida, 9.5, status="shortlisted")
    await _evaluar(db, empresa_id, sola, 7.2)

    fila = await _cockpit(db, empresa_id)

    assert fila is not None
    decision = _json(fila["decision"])
    assert decision["tipo"] == "entrevistar"
    assert decision["vacante"] == {"id": con_mas, "titulo": "Vacante"}
    assert (decision["listos"], decision["scores"]) == (2, [9.1, 8.5])
    # Una por vacante y tipo: dos de entrevistas y una de revisar.
    assert fila["decisiones_pendientes"] == 3
    assert _json(fila["vacante"]) == {"id": con_mas, "titulo": "Vacante"}


async def test_sin_entrevistas_pendientes_decide_lo_que_hay_que_revisar_a_mano(
    db: asyncpg.Connection,
) -> None:
    empresa_id = await _empresa(db, plan="ia")
    vacante_id = await _vacante(db, empresa_id)
    agotada, con_intento_libre, ilegible = await _aplicaciones(db, empresa_id, vacante_id, 3)
    await _aplicaciones(db, empresa_id, vacante_id, 1, sin_ia=True)
    for application_id, intentos in (
        (agotada, MAX_INTENTOS),
        (con_intento_libre, MAX_INTENTOS - 1),
    ):
        await _dueno(
            db,
            "insert into privado.evaluaciones_ia (application_id, empresa_id, intentos)"
            " values ($1::uuid, $2::uuid, $3)",
            application_id,
            empresa_id,
            intentos,
        )
    await _dueno(
        db,
        "insert into privado.cvs_ilegibles (application_id, empresa_id) values ($1::uuid, $2::uuid)",
        ilegible,
        empresa_id,
    )

    fila = await _cockpit(db, empresa_id)

    assert fila is not None
    decision = _json(fila["decision"])
    assert decision["tipo"] == "revisar"
    assert (decision["sin_evaluar"], decision["ilegibles"], decision["sin_ia"]) == (1, 1, 1)
    assert fila["decisiones_pendientes"] == 1
    # La que aún tiene un intento la sigue tomando el barrido.
    assert fila["en_espera"] == 1


async def test_sin_nada_que_decidir_la_vacante_del_dia_es_la_de_mas_candidatos(
    db: asyncpg.Connection,
) -> None:
    empresa_id = await _empresa(db, plan="ia")
    grande = await _vacante(db, empresa_id)
    chica = await _vacante(db, empresa_id)
    await _aplicaciones(db, empresa_id, grande, 3)
    await _aplicaciones(db, empresa_id, chica, 1)

    fila = await _cockpit(db, empresa_id)

    assert fila is not None
    assert (fila["decision"], fila["decisiones_pendientes"]) == (None, 0)
    assert _json(fila["vacante"])["id"] == grande
    assert fila["en_espera"] == 4


# ──────────────────────── la vacante del día por dentro ────────────────────────


async def test_mejores_evaluados_y_embudo_de_la_vacante_del_dia(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    vacante_id = await _vacante(db, empresa_id)
    ids = await _aplicaciones(db, empresa_id, vacante_id, 7)
    etapas = [
        (9.0, "evaluated"),
        (8.0, "shortlisted"),
        (7.5, "interviewed"),
        (6.0, "evaluated"),
        (3.0, "rejected"),
        (9.8, "hired"),
    ]
    for application_id, (score, status) in zip(ids, etapas, strict=False):
        await _evaluar(db, empresa_id, application_id, score, status)
    await _dueno(db, "update applications set status = 'offered' where id = $1::uuid", ids[6])

    fila = await _cockpit(db, empresa_id)

    assert fila is not None
    # La contratada ya salió del proceso y la descartada también.
    mejores = _json(fila["mejores_evaluados"])
    assert [m["score"] for m in mejores] == [9.0, 8.0, 7.5]
    assert all(m["candidato"].startswith("Candidata ") and m["razonamiento"] for m in mejores)
    assert [m["id"] for m in mejores] == ids[:3]
    assert fila["evaluados"] == 4
    # Cuántas llegaron a cada etapa o más allá; la descartada solo cuenta al aplicar.
    assert _json(fila["embudo"]) == {
        "applied": 7,
        "evaluated": 6,
        "shortlisted": 4,
        "interviewed": 3,
        "offered": 2,
    }


# ─────────────────────────── evaluaciones y tope ───────────────────────────


async def test_evaluaciones_de_24_horas_y_su_porcentaje_sin_error(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    await _corrida(db, empresa_id)
    await _corrida(db, empresa_id)
    await _corrida(db, empresa_id, "failed")
    await _corrida(db, empresa_id, horas=30)
    await _corrida(db, empresa_id, agente="sourcer")
    await _corrida(db, await _empresa(db, plan="ia"))

    fila = await _cockpit(db, empresa_id)

    assert fila is not None
    # 2 de 3 es 66,7 %: hacia abajo, para que el 100 % sea solo sin errores.
    assert (fila["evaluaciones_24h"], fila["porcentaje_sin_error"]) == (2, 66)


async def test_cvs_del_mes_contra_el_tope_de_la_empresa(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    await _dueno(db, "update empresas set ia_cvs_por_mes = 4 where id = $1::uuid", empresa_id)
    vacante_id = await _vacante(db, empresa_id)
    ids = await _aplicaciones(db, empresa_id, vacante_id, 5)
    for application_id in ids[:4]:
        await _evaluar(db, empresa_id, application_id, 5.0)
    await _dueno(
        db,
        "update privado.evaluaciones_ia set evaluada_en = date_trunc('month', now()) - interval"
        " '1 day' where application_id = $1::uuid",
        ids[3],
    )

    async def tope() -> tuple[int, int, int, bool]:
        fila = await _cockpit(db, empresa_id)
        assert fila is not None
        return (
            fila["cvs_del_mes"],
            fila["tope_del_mes"],
            fila["porcentaje_del_tope"],
            fila["tope_alcanzado"],
        )

    assert await tope() == (3, 4, 75, False)
    await _evaluar(db, empresa_id, ids[4], 5.0)
    assert await tope() == (4, 4, 100, True)
    await _dueno(db, "update empresas set ia_cvs_por_mes = 0 where id = $1::uuid", empresa_id)
    assert await tope() == (4, 0, 100, True)


# ─────────────────────────── el registro de los agentes ───────────────────────────


async def test_el_registro_de_los_agentes_sin_nombres_ni_lo_ajeno(db: asyncpg.Connection) -> None:
    empresa_id = await _empresa(db, plan="ia")
    vacante_id = await _vacante(db, empresa_id)
    (evaluada,) = await _aplicaciones(db, empresa_id, vacante_id, 1)
    await _evaluar(db, empresa_id, evaluada, 8.5)
    ajena = await _empresa(db, plan="ia")
    (de_otra,) = await _aplicaciones(db, ajena, await _vacante(db, ajena), 1)

    await _corrida(db, empresa_id, horas=30, application_id=evaluada)
    for horas in (6, 5, 4):
        await _corrida(db, empresa_id, horas=horas)
    await _corrida(db, empresa_id, horas=3, application_id="no-es-un-uuid")
    await _corrida(db, empresa_id, horas=2, application_id=de_otra)
    await _corrida(db, empresa_id, "failed", horas=1, application_id=evaluada)
    await _corrida(db, empresa_id, horas=0.5, application_id=evaluada)
    await _corrida(db, empresa_id, "running", horas=0.1)

    fila = await _cockpit(db, empresa_id)

    assert fila is not None
    registro = _json(fila["registro"])
    # Las 6 terminadas más recientes de las últimas 24 h.
    assert [(e["aplazada"], e["vacante"], e["score"]) for e in registro] == [
        (False, "Vacante", 8.5),
        (True, "Vacante", 8.5),
        (False, None, None),
        (False, None, None),
        (False, None, None),
        (False, None, None),
    ]
    claves = {"id", "en", "agente", "aplazada", "vacante", "score"}
    assert all(set(e) == claves for e in registro)
    fechas = [datetime.fromisoformat(e["en"]) for e in registro]
    assert fechas == sorted(fechas, reverse=True)
