"""Multi-tenant RLS tests (ADR-004).

Cada test verifica una de las garantias que el control plane y los workers
asumen como dadas — si alguna falla, hay riesgo de data leakage entre tenants.

Convencion:
- `assume_tenant(db, EMPRESA_X, 'HR')` simula el JWT del usuario HR del tenant X.
- `assume_anon(db)` simula un cliente con la anon key (rol `anon`, sin claims).
- `_elevate(db)` / `_drop(db)` saltan a DB-owner para preparar fixtures y vuelven
  al rol `authenticated` que es bajo el que viven los tests.
- Sin llamadas previas el JWT esta vacio y RLS bloquea por default.

Los tests marcados como "regresion" cubren vias de escalada concretas que la
auditoria de seguridad previa al primer deploy encontro explotables.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from .conftest import EMPRESA_SIETE, EMPRESA_VECTOR, assume_anon, assume_tenant

pytestmark = pytest.mark.asyncio


async def _elevate(db: asyncpg.Connection) -> None:
    """Salir del rol authenticated → DB owner (bypasea RLS)."""
    await db.execute("reset role;")


async def _drop(db: asyncpg.Connection) -> None:
    """Volver a authenticated para que RLS aplique."""
    await db.execute("set role authenticated;")


async def _make_user(db: asyncpg.Connection, empresa_id: str, role: str = "Colaborador") -> str:
    """Crea auth.users + profiles como owner y devuelve el user_id."""
    user_id = str(uuid.uuid4())
    await _elevate(db)
    try:
        await db.execute(
            "insert into auth.users (id, email) values ($1::uuid, $2)",
            user_id,
            f"{user_id}@test.local",
        )
        await db.execute(
            """
            insert into profiles (id, empresa_id, email, full_name, role)
            values ($1::uuid, $2::uuid, $3, 'Test User', $4::role_type)
            """,
            user_id,
            empresa_id,
            f"{user_id}@test.local",
            role,
        )
    finally:
        await _drop(db)
    return user_id


# ────────────────────────── empresas / profiles ──────────────────────────


async def test_hr_sees_only_their_empresa(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "HR")
    rows = await db.fetch("select id from empresas")
    assert len(rows) == 1
    assert str(rows[0]["id"]) == EMPRESA_VECTOR


async def test_platform_admin_sees_all_empresas(db: asyncpg.Connection) -> None:
    user_id = await _make_user(db, EMPRESA_VECTOR, "Director")
    await _elevate(db)
    try:
        await db.execute("insert into platform_admins (user_id) values ($1::uuid)", user_id)
    finally:
        await _drop(db)

    await assume_tenant(db, EMPRESA_VECTOR, "Director", user_id=user_id)
    rows = await db.fetch("select id from empresas order by slug")
    assert len(rows) >= 2


async def test_tenant_role_superadmin_is_not_global(db: asyncpg.Connection) -> None:
    """Regresion: 'SuperAdmin' era un rol de tenant que otorgaba FOR ALL sobre
    TODAS las empresas. Un HR podia promover a un complice dentro de su propio
    tenant y obtener acceso global. Ahora el privilegio de plataforma vive en
    `platform_admins`, que ningun `authenticated` puede escribir.
    """
    await assume_tenant(db, EMPRESA_VECTOR, "SuperAdmin")
    rows = await db.fetch("select id from empresas")
    assert [str(r["id"]) for r in rows] == [EMPRESA_VECTOR]


async def test_authenticated_cannot_grant_platform_admin(
    db: asyncpg.Connection,
) -> None:
    """Regresion: si `platform_admins` fuera escribible, la escalada volveria."""
    user_id = await _make_user(db, EMPRESA_VECTOR, "Director")
    await assume_tenant(db, EMPRESA_VECTOR, "Director", user_id=user_id)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await db.execute("insert into platform_admins (user_id) values ($1::uuid)", user_id)


async def test_anon_cannot_read_empresas(db: asyncpg.Connection) -> None:
    await assume_anon(db)
    rows = await db.fetch("select id from empresas")
    assert rows == []


async def test_user_cannot_self_promote(db: asyncpg.Connection) -> None:
    """Regresion: `profiles_self_update` no tenia WITH CHECK restrictivo, asi
    que `update profiles set role='SuperAdmin' where id = auth.uid()` pasaba.
    """
    user_id = await _make_user(db, EMPRESA_VECTOR, "Colaborador")
    await assume_tenant(db, EMPRESA_VECTOR, "Colaborador", user_id=user_id)

    with pytest.raises(asyncpg.exceptions.RaiseError):
        await db.execute(
            "update profiles set role = 'SuperAdmin'::role_type where id = $1::uuid",
            user_id,
        )


async def test_user_cannot_move_themselves_to_another_tenant(
    db: asyncpg.Connection,
) -> None:
    """Regresion: mismo agujero, otra columna — cambiarse el empresa_id daba
    acceso completo al tenant destino tras refrescar el token.
    """
    user_id = await _make_user(db, EMPRESA_VECTOR, "Colaborador")
    await assume_tenant(db, EMPRESA_VECTOR, "Colaborador", user_id=user_id)

    with pytest.raises(asyncpg.exceptions.RaiseError):
        await db.execute(
            "update profiles set empresa_id = $2::uuid where id = $1::uuid",
            user_id,
            EMPRESA_SIETE,
        )


async def test_user_can_still_update_own_harmless_fields(
    db: asyncpg.Connection,
) -> None:
    """El endurecimiento no debe romper el caso legitimo."""
    user_id = await _make_user(db, EMPRESA_VECTOR, "Colaborador")
    await assume_tenant(db, EMPRESA_VECTOR, "Colaborador", user_id=user_id)

    result = await db.execute(
        "update profiles set full_name = 'Nombre Nuevo' where id = $1::uuid",
        user_id,
    )
    assert result.endswith(" 1")


# ────────────────────────── signup / invitaciones ──────────────────────────


async def test_signup_without_invitation_is_rejected(db: asyncpg.Connection) -> None:
    """Regresion (la mas grave): `handle_new_user` derivaba empresa_id y role
    de `raw_user_meta_data`, que es el `options.data` de `signUp()` y lo
    controla el cliente al 100%. Cualquiera con la anon key se daba de alta
    como SuperAdmin dentro del tenant que eligiera.
    """
    await _elevate(db)
    try:
        with pytest.raises(asyncpg.exceptions.RaiseError):
            await db.execute(
                """
                insert into auth.users (id, email, raw_user_meta_data)
                values (gen_random_uuid(), 'mallory@evil.test',
                        jsonb_build_object(
                            'empresa_id', $1::text,
                            'role', 'SuperAdmin'))
                """,
                EMPRESA_VECTOR,
            )
    finally:
        await _drop(db)


async def test_signup_with_invitation_ignores_metadata_role(
    db: asyncpg.Connection,
) -> None:
    """Con invitacion valida el alta funciona, pero el rol sale de la
    invitacion, no del metadata que manda el cliente.
    """
    token = "invite-token-para-test"
    email = "invitado@vector.test"
    await _elevate(db)
    try:
        await db.execute(
            """
            insert into invitations (empresa_id, email, role, token_hash)
            values ($1::uuid, $2, 'Colaborador',
                    encode(sha256($3::bytea), 'hex'))
            """,
            EMPRESA_VECTOR,
            email,
            token,
        )
        user_id = str(uuid.uuid4())
        await db.execute(
            """
            insert into auth.users (id, email, raw_user_meta_data)
            values ($1::uuid, $2,
                    jsonb_build_object('invite_token', $3::text,
                                       'role', 'SuperAdmin',
                                       'empresa_id', $4::text))
            """,
            user_id,
            email,
            token,
            EMPRESA_SIETE,
        )
        row = await db.fetchrow(
            "select empresa_id, role::text as role from profiles where id = $1::uuid",
            user_id,
        )
    finally:
        await _drop(db)

    assert row is not None
    assert str(row["empresa_id"]) == EMPRESA_VECTOR  # no el de la metadata
    assert row["role"] == "Colaborador"  # no SuperAdmin


async def test_invitation_token_is_single_use(db: asyncpg.Connection) -> None:
    token = "invite-token-single-use"
    email = "unavez@vector.test"
    await _elevate(db)
    try:
        await db.execute(
            """
            insert into invitations (empresa_id, email, role, token_hash)
            values ($1::uuid, $2, 'Colaborador',
                    encode(sha256($3::bytea), 'hex'))
            """,
            EMPRESA_VECTOR,
            email,
            token,
        )
        await db.execute(
            """
            insert into auth.users (id, email, raw_user_meta_data)
            values (gen_random_uuid(), $1,
                    jsonb_build_object('invite_token', $2::text))
            """,
            email,
            token,
        )
        with pytest.raises(asyncpg.exceptions.RaiseError):
            await db.execute(
                """
                insert into auth.users (id, email, raw_user_meta_data)
                values (gen_random_uuid(), $1,
                        jsonb_build_object('invite_token', $2::text))
                """,
                email,
                token,
            )
    finally:
        await _drop(db)


# ────────────────────────── candidatos ──────────────────────────


async def test_hr_cannot_read_other_tenant_candidates(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "HR")
    rows = await db.fetch("select id, empresa_id from candidatos")
    assert len(rows) > 0
    assert all(str(r["empresa_id"]) == EMPRESA_VECTOR for r in rows)


async def test_colaborador_cannot_read_candidatos(db: asyncpg.Connection) -> None:
    """Regresion: `candidatos` tenia `for all using (empresa_id = ...)` sin
    filtro de rol, asi que cualquier Colaborador leia toda la base de
    candidatos con su PII — y podia borrarla en cascada.
    """
    await assume_tenant(db, EMPRESA_VECTOR, "Colaborador")
    rows = await db.fetch("select id from candidatos")
    assert rows == []


async def test_colaborador_cannot_delete_candidatos(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "Colaborador")
    result = await db.execute("delete from candidatos")
    assert result.endswith(" 0")


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


async def test_public_can_read_open_vacantes_via_view(db: asyncpg.Connection) -> None:
    await assume_anon(db)
    rows = await db.fetch("select id from vacantes_publicas")
    assert len(rows) > 0


async def test_public_cannot_read_vacantes_table_directly(
    db: asyncpg.Connection,
) -> None:
    """Regresion: `vacantes_public_open_read` daba SELECT sobre la TABLA a
    `anon`. RLS filtra filas, no columnas, asi que cualquiera se llevaba de
    todos los tenants el `icp_text` (perfil ideal interno), el embedding y las
    bandas salariales. Ahora solo existe la vista, sin esas columnas.
    """
    await assume_anon(db)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await db.fetch("select icp_text, salary_max from vacantes")


async def test_public_view_hides_commercial_columns(db: asyncpg.Connection) -> None:
    await assume_anon(db)
    with pytest.raises(asyncpg.exceptions.UndefinedColumnError):
        await db.fetch("select salary_max from vacantes_publicas")


async def test_public_cannot_read_draft_vacantes(db: asyncpg.Connection) -> None:
    await _elevate(db)
    try:
        await db.execute(
            """
            insert into vacantes (empresa_id, slug, title, jd, status)
            values ($1::uuid, 'oculta', 'Vacante draft', 'jd', 'draft')
            """,
            EMPRESA_VECTOR,
        )
    finally:
        await _drop(db)

    await assume_anon(db)
    rows = await db.fetch("select id from vacantes_publicas where slug = 'oculta'")
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


async def test_application_cannot_reference_foreign_candidate(
    db: asyncpg.Connection,
) -> None:
    """Regresion: las FK simples a vacantes/candidatos se verifican con un scan
    interno que IGNORA RLS. Un HR del tenant A podia crear una application con
    su propio empresa_id pero un candidato_id del tenant B; el insert pasaba y
    cualquier worker con service_role exponia despues datos del tenant B.
    La FK compuesta (id, empresa_id) lo impide en el motor.
    """
    await _elevate(db)
    try:
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await db.execute(
                """
                insert into applications (empresa_id, vacante_id, candidato_id)
                values (
                    $1::uuid,
                    (select id from vacantes where empresa_id = $1::uuid limit 1),
                    (select id from candidatos where empresa_id = $2::uuid limit 1)
                )
                """,
                EMPRESA_VECTOR,
                EMPRESA_SIETE,
            )
    finally:
        await _drop(db)


# ────────────────────────── psicometricos ──────────────────────────


async def test_anon_cannot_read_psicometricos_table(db: asyncpg.Connection) -> None:
    """Regresion (critica): `psicometricos_public_token_read` se llamaba "por
    token" pero su predicado no mencionaba el token. Un anonimo hacia
    `select token, raw_answers from psicometricos` y se llevaba todos los tests
    activos de todos los tenants, con los tokens en claro.
    """
    await assume_anon(db)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await db.fetch("select * from psicometricos")


async def test_token_rpc_returns_only_the_matching_test(
    db: asyncpg.Connection,
) -> None:
    await assume_anon(db)
    rows = await db.fetch("select * from get_psicometrico_by_token($1)", "psy-tok-vec-001")
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"


async def test_token_rpc_rejects_unknown_token(db: asyncpg.Connection) -> None:
    await assume_anon(db)
    rows = await db.fetch("select * from get_psicometrico_by_token($1)", "no-existe")
    assert rows == []


async def test_token_rpc_hides_completed_test(db: asyncpg.Connection) -> None:
    await assume_anon(db)
    rows = await db.fetch("select * from get_psicometrico_by_token($1)", "psy-tok-siete-001")
    assert rows == []


async def test_token_rpc_hides_expired_test(db: asyncpg.Connection) -> None:
    # Usamos Siete porque su application del seed tiene psicometrico='completed';
    # asi el indice partial-unique sobre (application_id) WHERE status in
    # ('pending','in_progress') no choca al insertar uno nuevo pending.
    await _elevate(db)
    try:
        await db.execute(
            """
            insert into psicometricos
                (empresa_id, application_id, token_hash, status, expires_at)
            values
                ($1::uuid,
                 (select id from applications where empresa_id = $1::uuid limit 1),
                 encode(sha256($2::bytea), 'hex'),
                 'pending', now() - interval '1 day')
            """,
            EMPRESA_SIETE,
            "psy-tok-expired-001",
        )
    finally:
        await _drop(db)

    await assume_anon(db)
    rows = await db.fetch("select * from get_psicometrico_by_token($1)", "psy-tok-expired-001")
    assert rows == []


async def test_submit_rpc_cannot_move_test_between_tenants(
    db: asyncpg.Connection,
) -> None:
    """Regresion: el WITH CHECK de `psicometricos_public_token_update` era mas
    debil que su USING, asi que un anonimo podia reescribir `empresa_id`,
    `token` y `expires_at` de cualquier fila pendiente. El RPC solo toca
    columnas de respuesta.
    """
    await assume_anon(db)
    await db.execute(
        "select submit_psicometrico($1, $2::jsonb, null, false)",
        "psy-tok-vec-001",
        '{"q1": 3}',
    )

    await _elevate(db)
    try:
        row = await db.fetchrow(
            "select empresa_id, status::text as status, raw_answers "
            "from psicometricos where token_hash = encode(sha256($1::bytea), 'hex')",
            "psy-tok-vec-001",
        )
    finally:
        await _drop(db)

    assert row is not None
    assert str(row["empresa_id"]) == EMPRESA_VECTOR
    assert row["status"] == "in_progress"


async def test_submit_rpc_rejects_invalid_token(db: asyncpg.Connection) -> None:
    await assume_anon(db)
    with pytest.raises(asyncpg.exceptions.RaiseError):
        await db.execute(
            "select submit_psicometrico($1, $2::jsonb, null, false)",
            "token-que-no-existe",
            "{}",
        )


async def test_tenant_drift_blocked_on_psicometrico_insert(
    db: asyncpg.Connection,
) -> None:
    # Como DB owner bypaseamos RLS — pero el trigger sigue corriendo y debe
    # rechazar empresa_id que no matchea la application padre.
    await _elevate(db)
    try:
        with pytest.raises(
            (
                asyncpg.exceptions.RaiseError,
                asyncpg.exceptions.ForeignKeyViolationError,
            )
        ):
            await db.execute(
                """
                insert into psicometricos
                    (empresa_id, application_id, token_hash, status)
                values
                    ($1::uuid,
                     (select id from applications where empresa_id = $2::uuid limit 1),
                     encode(sha256('psy-tok-drift'::bytea), 'hex'),
                     'pending')
                """,
                EMPRESA_SIETE,
                EMPRESA_VECTOR,
            )
    finally:
        await _drop(db)


# ────────────────────────── runs ──────────────────────────


async def test_worker_can_persist_run_status(db: asyncpg.Connection) -> None:
    """Regresion: `runs` solo tenia policy de SELECT. El worker corre como
    `authenticated`, asi que su `update runs set status=...` afectaba 0 filas
    y no lanzaba error — el cost tracking nunca se persistia.
    """
    await assume_tenant(db, EMPRESA_VECTOR, "HR")
    run_id = await db.fetchval(
        """
        insert into runs (empresa_id, agent_skill, status)
        values ($1::uuid, 'sourcer', 'pending')
        returning id
        """,
        EMPRESA_VECTOR,
    )
    result = await db.execute(
        "update runs set status = 'completed', cost_usd = 0.42 where id = $1::uuid",
        run_id,
    )
    assert result.endswith(" 1")


async def test_runs_are_tenant_isolated(db: asyncpg.Connection) -> None:
    await assume_tenant(db, EMPRESA_VECTOR, "HR")
    await db.execute(
        """
        insert into runs (empresa_id, agent_skill, status)
        values ($1::uuid, 'sourcer', 'pending')
        """,
        EMPRESA_VECTOR,
    )

    await assume_tenant(db, EMPRESA_SIETE, "HR")
    rows = await db.fetch("select empresa_id from runs")
    assert all(str(r["empresa_id"]) == EMPRESA_SIETE for r in rows)


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
                "update activity_log set action = 'mutated' where action = 'test.created'"
            )

        with pytest.raises(asyncpg.exceptions.RaiseError):
            await db.execute("delete from activity_log where action = 'test.created'")
    finally:
        await _drop(db)


async def test_activity_log_cannot_be_truncated(db: asyncpg.Connection) -> None:
    """Regresion: los triggers de inmutabilidad eran FOR EACH ROW, y TRUNCATE
    no dispara triggers de fila — se podia borrar el log de auditoria entero
    sin tocar ninguna barrera.
    """
    await _elevate(db)
    try:
        with pytest.raises(asyncpg.exceptions.RaiseError):
            await db.execute("truncate activity_log")
    finally:
        await _drop(db)


# ────────────────────────── flujo publico de aplicacion ──────────────────────


async def test_anon_cannot_insert_candidatos_directly(db: asyncpg.Connection) -> None:
    """`anon` no tiene ninguna via directa de escritura: todo pasa por la RPC."""
    await assume_anon(db)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await db.execute(
            """
            insert into candidatos (empresa_id, full_name, email)
            values ($1::uuid, 'Spam', 'spam@evil.test')
            """,
            EMPRESA_VECTOR,
        )


async def test_aplicar_a_vacante_creates_application(db: asyncpg.Connection) -> None:
    await _elevate(db)
    try:
        vacante_id = await db.fetchval(
            "select id from vacantes where empresa_id = $1::uuid and status = 'open' limit 1",
            EMPRESA_VECTOR,
        )
    finally:
        await _drop(db)

    await assume_anon(db)
    application_id = await db.fetchval(
        "select aplicar_a_vacante($1::uuid, $2, $3)",
        vacante_id,
        "Candidata Nueva",
        "Candidata.Nueva@Example.test",
    )
    assert application_id is not None

    await _elevate(db)
    try:
        row = await db.fetchrow(
            """
            select a.empresa_id, c.email, c.source::text as source
              from applications a join candidatos c on c.id = a.candidato_id
             where a.id = $1::uuid
            """,
            application_id,
        )
    finally:
        await _drop(db)

    assert str(row["empresa_id"]) == EMPRESA_VECTOR
    assert row["email"] == "candidata.nueva@example.test"  # normalizado
    assert row["source"] == "career-site"


async def test_aplicar_a_vacante_is_idempotent(db: asyncpg.Connection) -> None:
    """Aplicar dos veces a la misma vacante no duplica la postulacion."""
    await _elevate(db)
    try:
        vacante_id = await db.fetchval(
            "select id from vacantes where empresa_id = $1::uuid and status = 'open' limit 1",
            EMPRESA_VECTOR,
        )
    finally:
        await _drop(db)

    await assume_anon(db)
    first = await db.fetchval(
        "select aplicar_a_vacante($1::uuid, $2, $3)",
        vacante_id,
        "Repetida",
        "repetida@example.test",
    )
    second = await db.fetchval(
        "select aplicar_a_vacante($1::uuid, $2, $3)",
        vacante_id,
        "Repetida",
        "repetida@example.test",
    )
    assert first == second


async def test_aplicar_a_vacante_rejects_draft_vacante(db: asyncpg.Connection) -> None:
    await _elevate(db)
    try:
        vacante_id = await db.fetchval(
            """
            insert into vacantes (empresa_id, slug, title, jd, status)
            values ($1::uuid, 'borrador-apply', 'Draft', 'jd', 'draft')
            returning id
            """,
            EMPRESA_VECTOR,
        )
    finally:
        await _drop(db)

    await assume_anon(db)
    with pytest.raises(asyncpg.exceptions.RaiseError):
        await db.execute(
            "select aplicar_a_vacante($1::uuid, $2, $3)",
            vacante_id,
            "Nadie",
            "nadie@example.test",
        )


async def test_aplicar_a_vacante_rejects_cv_path_of_other_tenant(
    db: asyncpg.Connection,
) -> None:
    """El path del CV tiene que colgar del tenant de la vacante; si no, `cv_url`
    podria apuntar al fichero de otra empresa.
    """
    await _elevate(db)
    try:
        vacante_id = await db.fetchval(
            "select id from vacantes where empresa_id = $1::uuid and status = 'open' limit 1",
            EMPRESA_VECTOR,
        )
    finally:
        await _drop(db)

    await assume_anon(db)
    with pytest.raises(asyncpg.exceptions.RaiseError):
        await db.execute(
            "select aplicar_a_vacante($1::uuid, $2, $3, $4)",
            vacante_id,
            "Path Ajeno",
            "pathajeno@example.test",
            f"{EMPRESA_SIETE}/algun-candidato/cv.pdf",
        )


async def test_aplicar_a_vacante_rejects_invalid_email(db: asyncpg.Connection) -> None:
    await _elevate(db)
    try:
        vacante_id = await db.fetchval(
            "select id from vacantes where empresa_id = $1::uuid and status = 'open' limit 1",
            EMPRESA_VECTOR,
        )
    finally:
        await _drop(db)

    await assume_anon(db)
    with pytest.raises(asyncpg.exceptions.RaiseError):
        await db.execute(
            "select aplicar_a_vacante($1::uuid, $2, $3)",
            vacante_id,
            "Sin Arroba",
            "no-es-un-email",
        )
