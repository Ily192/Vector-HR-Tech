"""Multi-tenant RLS tests (ADR-004).

Cada test verifica una de las garantías que el control plane y los workers
asumen como dadas — si alguna falla, hay riesgo de data leakage entre tenants.

Convención:
- `assume_tenant(db, EMPRESA_X, 'HR')` simula el JWT del usuario HR del tenant X.
- `_elevate(db)` / `_drop(db)` saltan a DB-owner para preparar fixtures y vuelven
  al rol `authenticated` que es bajo el que viven los tests.
- Sin llamadas previas el JWT está vacío y RLS bloquea por default.
"""

from __future__ import annotations

import asyncpg
import pytest

from .conftest import EMPRESA_SIETE, EMPRESA_VECTOR, assume_tenant

pytestmark = pytest.mark.asyncio


async def _elevate(db: asyncpg.Connection) -> None:
    """Salir del rol authenticated → DB owner (bypasea RLS)."""
    await db.execute("reset role;")


async def _drop(db: asyncpg.Connection) -> None:
    """Volver a authenticated para que RLS aplique."""
    await db.execute("set role authenticated;")


# ────────────────────────── empresas / profiles ──────────────────────────


async def test_hr_sees_only_their_empresa(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "HR")
    rows = await db.fetch("select id from empresas")
    assert len(rows) == 1
    assert str(rows[0]["id"]) == EMPRESA_VECTOR


async def test_superadmin_sees_all_empresas(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "SuperAdmin")
    rows = await db.fetch("select id from empresas order by slug")
    assert len(rows) >= 2


async def test_anon_cannot_read_empresas(db: asyncpg.Connection) -> None:
    # Sin claims; auth.empresa_id() devuelve null → ninguna política aplica.
    rows = await db.fetch("select id from empresas")
    assert rows == []


# ────────────────────────── candidatos ──────────────────────────


async def test_hr_cannot_read_other_tenant_candidates(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "HR")
    rows = await db.fetch("select id, empresa_id from candidatos")
    assert len(rows) > 0
    assert all(str(r["empresa_id"]) == EMPRESA_VECTOR for r in rows)


async def test_hr_cannot_insert_into_other_tenant(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "HR")
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await db.execute(
            """
            insert into candidatos (empresa_id, full_name, email)
            values ($1::uuid, 'Mallory', 'mallory@evil.test')
            """,
            EMPRESA_SIETE,
        )


async def test_hr_cannot_update_other_tenant_candidate(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "HR")
    result = await db.execute(
        """
        update candidatos set headline = 'pwned'
        where empresa_id = $1::uuid
        """,
        EMPRESA_SIETE,
    )
    # RLS hace que el UPDATE no matchee ninguna fila → "UPDATE 0".
    assert result.endswith(" 0")


# ────────────────────────── vacantes ──────────────────────────


async def test_public_can_read_open_vacantes(db: asyncpg.Connection) -> None:
    # Sin tenant — el career-site lee con anon key.
    rows = await db.fetch("select id, status from vacantes")
    assert len(rows) > 0
    assert all(r["status"] == "open" for r in rows)


async def test_public_cannot_read_draft_vacantes(db: asyncpg.Connection) -> None:
    await _elevate(db)
    await db.execute(
        """
        insert into vacantes (empresa_id, slug, title, jd, status)
        values ($1::uuid, 'oculta', 'Vacante draft', 'jd', 'draft')
        """,
        EMPRESA_VECTOR,
    )
    await _drop(db)

    rows = await db.fetch("select status from vacantes where slug = 'oculta'")
    assert rows == []


# ────────────────────────── applications ──────────────────────────


async def test_applications_tenant_isolation(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "HR")
    vector_rows = await db.fetch("select empresa_id from applications")
    assert len(vector_rows) > 0
    assert all(str(r["empresa_id"]) == EMPRESA_VECTOR for r in vector_rows)

    await assume_tenant(db, EMPRESA_SIETE, "HR")
    siete_rows = await db.fetch("select empresa_id from applications")
    assert len(siete_rows) > 0
    assert all(str(r["empresa_id"]) == EMPRESA_SIETE for r in siete_rows)


# ────────────────────────── psicometricos ──────────────────────────


async def test_public_can_read_active_psicometrico_by_token(
    db: asyncpg.Connection,
) -> None:
    # Anon (candidato con link) — debe ver pending no expirados de cualquier tenant.
    rows = await db.fetch(
        "select token, status from psicometricos where token = 'psy-tok-vec-001'"
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"


async def test_public_cannot_read_completed_psicometrico(
    db: asyncpg.Connection,
) -> None:
    rows = await db.fetch(
        "select token from psicometricos where token = 'psy-tok-siete-001'"
    )
    # Status='completed' → política público no aplica, anon no lo ve.
    assert rows == []


async def test_public_cannot_read_expired_psicometrico(db: asyncpg.Connection) -> None:
    # Usamos Siete porque su application del seed tiene psicometrico='completed';
    # así el índice partial-unique sobre (application_id) WHERE status in
    # ('pending','in_progress') no choca al insertar uno nuevo pending.
    await _elevate(db)
    try:
        await db.execute(
            """
            insert into psicometricos
                (empresa_id, application_id, token, status, expires_at)
            values
                ($1::uuid,
                 (select id from applications where empresa_id = $1::uuid limit 1),
                 $2, 'pending', now() - interval '1 day')
            """,
            EMPRESA_SIETE,
            "psy-tok-expired-001",
        )
    finally:
        await _drop(db)

    rows = await db.fetch(
        "select token from psicometricos where token = 'psy-tok-expired-001'"
    )
    assert rows == []


async def test_tenant_drift_blocked_on_psicometrico_insert(
    db: asyncpg.Connection,
) -> None:
    # Como DB owner bypaseamos RLS — pero el trigger sigue corriendo y debe
    # rechazar empresa_id que no matchea la application padre.
    await _elevate(db)
    try:
        with pytest.raises(asyncpg.exceptions.RaiseError):
            await db.execute(
                """
                insert into psicometricos
                    (empresa_id, application_id, token, status)
                values
                    ($1::uuid,
                     (select id from applications where empresa_id = $2::uuid limit 1),
                     'psy-tok-drift', 'pending')
                """,
                EMPRESA_SIETE,
                EMPRESA_VECTOR,
            )
    finally:
        await _drop(db)


# ────────────────────────── activity_log ──────────────────────────


async def test_activity_log_is_append_only(db: asyncpg.Connection) -> None:
    await _elevate(db)
    try:
        await db.execute(
            """
            insert into activity_log (empresa_id, action, hash)
            values ($1::uuid, 'test.created', 'hash-1')
            """,
            EMPRESA_VECTOR,
        )

        with pytest.raises(asyncpg.exceptions.RaiseError):
            await db.execute(
                "update activity_log set action = 'mutated' "
                "where action = 'test.created'"
            )

        with pytest.raises(asyncpg.exceptions.RaiseError):
            await db.execute(
                "delete from activity_log where action = 'test.created'"
            )
    finally:
        await _drop(db)
