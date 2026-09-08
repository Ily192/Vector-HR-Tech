"""Guardas estructurales sobre la resolucion de nombres en el esquema.

Por que existe este modulo
--------------------------
Los tres defectos que 0006 arregla eran todos la misma clase de bug: un nombre
sin calificar que se resuelve en tiempo de EJECUCION contra un `search_path`
que no es el que quien escribio la funcion tenia en la cabeza.

Ninguno era visible leyendo el SQL, ni parseandolo, ni corriendo los tests de
RLS de la epoca — solo aparecen al invocar la funcion concreta con el contexto
concreto. Y son especialmente traicioneros porque una migracion que los
contiene se aplica sin un solo warning.

Los tests funcionales de `test_rls.py` cubren las tres instancias que ya
existieron. Estos cubren la CLASE: si alguien añade manana una cuarta funcion
con el mismo patron, falla aqui aunque nadie escriba un test para ella.

Se apoyan en el catalogo de la base ya migrada, no en el texto de los .sql, asi
que tambien atrapan lo que llegue por otra via (dashboard de Supabase, hotfix
manual, etc.).
"""

from __future__ import annotations

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


# `activity_log_immutable` y `activity_log_no_truncate` nombran la tabla dentro
# del texto de su `raise exception`, no como relacion. El scan es textual, asi
# que hay que exceptuarlas explicitamente.
_MENCIONES_EN_MENSAJES_DE_ERROR = {
    "activity_log_immutable",
    "activity_log_no_truncate",
}


async def test_definer_functions_qualify_every_public_reference(
    db: asyncpg.Connection,
) -> None:
    """Ninguna funcion con `search_path` fijado puede nombrar un objeto de
    `public` sin calificar.

    Regresion de 0006 §1: `submit_psicometrico` casteaba a
    `'completed'::psicometrico_status` bajo `set search_path = ''`. El cuerpo
    plpgsql se resuelve al invocar, no al crear, asi que la migracion pasaba
    limpia y la funcion reventaba en la primera llamada de un candidato real.
    """
    filas = await db.fetch(
        """
        select p.proname, string_agg(distinct o.nombre, ', ') as refs
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
          cross join lateral (
              select c.relname as nombre from pg_class c
                join pg_namespace cn on cn.oid = c.relnamespace
               where cn.nspname = 'public' and c.relkind in ('r','v','m')
              union all
              select t.typname from pg_type t
                join pg_namespace tn on tn.oid = t.typnamespace
               where tn.nspname = 'public' and t.typtype = 'e'
          ) o
         where n.nspname = 'public'
           and array_to_string(p.proconfig, ',') like '%search_path=%'
           and p.prosrc ~ ('(^|[^.[:alnum:]_])' || o.nombre || '([^[:alnum:]_]|$)')
           and p.prosrc !~ ('public\\.' || o.nombre || '([^[:alnum:]_]|$)')
         group by 1
        """
    )
    ofensores = {
        r["proname"]: r["refs"]
        for r in filas
        if r["proname"] not in _MENCIONES_EN_MENSAJES_DE_ERROR
    }
    assert not ofensores, (
        "Funciones con search_path fijado que nombran objetos de public sin "
        f"calificar (fallaran al invocarlas): {ofensores}"
    )


async def test_trigger_functions_pin_their_search_path(
    db: asyncpg.Connection,
) -> None:
    """Toda funcion de trigger que resuelva objetos de `public` debe fijar su
    propio `search_path`.

    Regresion de 0006 §3: `enforce_empresa_id_from_application` no lo fijaba y
    leia `applications` sin calificar. Disparada por un UPDATE normal
    funcionaba; disparada desde dentro de `submit_psicometrico()` — que corre
    con `search_path = ''` — no resolvia la tabla.

    Una funcion de trigger sin search_path propio no tiene uno "por defecto":
    hereda el de quien la dispara. Eso la vuelve dependiente del contexto de
    llamada, que es justo lo que no se puede razonar leyendo la funcion.
    """
    filas = await db.fetch(
        """
        select distinct p.proname
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
          join pg_type rt on rt.oid = p.prorettype
          cross join lateral (
              select c.relname as nombre from pg_class c
                join pg_namespace cn on cn.oid = c.relnamespace
               where cn.nspname = 'public' and c.relkind in ('r','v','m')
              union all
              select t.typname from pg_type t
                join pg_namespace tn on tn.oid = t.typnamespace
               where tn.nspname = 'public' and t.typtype = 'e'
          ) o
         where n.nspname = 'public'
           and rt.typname = 'trigger'
           and coalesce(array_to_string(p.proconfig, ','), '') not like '%search_path=%'
           and p.prosrc ~ ('(^|[^.[:alnum:]_])' || o.nombre || '([^[:alnum:]_]|$)')
        """
    )
    ofensores = sorted(
        r["proname"] for r in filas if r["proname"] not in _MENCIONES_EN_MENSAJES_DE_ERROR
    )
    assert not ofensores, (
        "Funciones de trigger sin search_path propio que resuelven objetos de "
        f"public: {ofensores}. Fallaran si las dispara una funcion "
        "`security definer` con search_path fijado."
    )


async def test_policies_do_not_call_functions_their_role_cannot_execute(
    db: asyncpg.Connection,
) -> None:
    """Ningun rol con grants sobre una tabla puede recibir un error de permisos
    al evaluarse sus policies.

    Regresion de 0006 §2: `empresas_platform_admin_all` no llevaba clausula
    `TO`, asi que se evaluaba tambien para `anon`, que no tiene EXECUTE sobre
    `is_platform_admin()`. Un `select from empresas` sin sesion no devolvia
    cero filas: abortaba con 42501, que PostgREST traduce a un 500.

    En vez de inspeccionar las expresiones de las policies, este test hace la
    comprobacion por la via directa: se pone en la piel de cada rol y lee cada
    tabla sobre la que tiene SELECT. Cero filas es correcto; un error no.
    """
    for rol in ("anon", "authenticated"):
        # `information_schema` solo muestra grants visibles para el usuario
        # actual, y el fixture `db` entra como `authenticated`. Hay que leer el
        # catalogo como owner o la lista sale vacia y el test pasa en falso.
        await db.execute("reset role;")
        tablas = await db.fetch(
            """
            select distinct table_name
              from information_schema.role_table_grants
             where grantee = $1
               and table_schema = 'public'
               and privilege_type = 'SELECT'
             order by table_name
            """,
            rol,
        )
        await db.execute("set role authenticated;")
        assert tablas, f"El rol {rol} no tiene SELECT sobre ninguna tabla; fixture rota?"

        for fila in tablas:
            tabla = fila["table_name"]
            await db.execute("reset role;")
            await db.execute("select set_config('request.jwt.claims', '', false)")
            await db.execute(f"set role {rol};")
            try:
                await db.fetch(f'select * from public."{tabla}" limit 1')
            except asyncpg.exceptions.InsufficientPrivilegeError as exc:
                pytest.fail(
                    f"`{rol}` tiene SELECT sobre `{tabla}` pero la lectura aborta "
                    f"en vez de devolver cero filas: {exc}. Suele ser una policy "
                    f"sin clausula `TO` que invoca una funcion con EXECUTE "
                    f"restringido."
                )
            finally:
                await db.execute("reset role;")
                await db.execute("set role authenticated;")
