"""Guardas estructurales sobre la resolucion de nombres en el esquema.

Por que existe este modulo
--------------------------
Dos de los tres defectos que 0006 arregla eran la misma clase de bug: un nombre
sin calificar que se resuelve en tiempo de EJECUCION contra un `search_path` que
no es el que quien escribio la funcion tenia en la cabeza. (El tercero, la policy
de `empresas` sin clausula `TO`, es de privilegios y no de resolucion de nombres;
lo cubre el tercer test de este modulo.)

Ninguno era visible leyendo el SQL, ni parseandolo, ni corriendo los tests de
RLS de la epoca — solo aparecen al invocar la funcion concreta con el contexto
concreto. Y son especialmente traicioneros porque una migracion que los contiene
se aplica sin un solo warning.

Los tests funcionales de `test_rls.py` cubren las instancias que ya existieron.
Estos cubren la clase: si alguien anade manana una cuarta funcion con el mismo
patron, falla aqui aunque nadie escriba un test para ella.

Se apoyan en el catalogo de la base ya migrada, no en el texto de los `.sql`, asi
que tambien atrapan lo que llegue por otra via (dashboard de Supabase, hotfix
manual, etc.).

Que cubren y que NO
-------------------
El scan normaliza `prosrc` antes de buscar (ver `_SQL_CUERPO_NORMALIZADO`):
quita comentarios de linea, literales entre comillas simples, y **todas las
referencias ya calificadas con `public.`**. Lo que queda es texto donde cualquier
aparicion de un nombre de `public` es una referencia sin calificar de verdad.

Esa normalizacion importa, y la primera version de este modulo no la hacia:

  · Se apoyaba en `prosrc !~ 'public\\.<nombre>'`, que eximia al par
    (funcion, objeto) en cuanto la funcion mencionaba ese objeto calificado UNA
    vez en cualquier parte del cuerpo. `submit_psicometrico` tenia DOS casts al
    mismo tipo: bastaba con descalificar uno para volverse invisible. Y
    `enforce_empresa_id_from_application`, que hoy contiene `public.applications`,
    habria quedado exenta para siempre justo del bug que tuvo.

  · Necesitaba una allowlist por NOMBRE DE FUNCION para los dos triggers de
    `activity_log`, que nombran la tabla dentro del texto de su `raise exception`.
    Eximir funciones enteras enmascara para siempre cualquier referencia real que
    se les anada despues. Al quitar los literales, la allowlist sobra.

Limites que siguen en pie, y conviene no olvidar:

  · Las funciones se detectan solo en sintaxis de llamada (`nombre(`). Una
    referencia a una funcion de `public` que no sea una llamada directa no se ve.
  · El scan es textual sobre `prosrc`. Un nombre construido dinamicamente y
    ejecutado con `execute` no se detecta.
  · El tercer test comprueba solo LECTURA (`select`) y solo para `anon` y
    `authenticated`. Una policy de escritura que invoque una funcion sin EXECUTE
    para el rol no la atrapa: haria falta escribir de verdad en cada tabla.
"""

from __future__ import annotations

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


# Normaliza el cuerpo de una funcion antes de buscar nombres sin calificar:
#   1. fuera los comentarios de linea (`-- ...`)
#   2. fuera los literales entre comillas simples — ahi vive el texto de los
#      `raise exception`, que menciona tablas sin referenciarlas
#   3. fuera TODA referencia ya calificada (`public.lo_que_sea`), para que lo que
#      sobreviva sean solo las referencias desnudas
_SQL_CUERPO_NORMALIZADO = r"""
    regexp_replace(
        regexp_replace(
            regexp_replace(p.prosrc, '--[^\n]*', ' ', 'g'),
            '''[^'']*''', ' ', 'g'
        ),
        'public\.[A-Za-z0-9_]+', ' ', 'g'
    )
"""

# Objetos de `public` cuya mencion sin calificar rompe bajo search_path vacio.
# Relaciones y tipos enum se buscan como palabra suelta; las funciones solo en
# sintaxis de llamada, porque sus nombres chocan con nombres de columna muy
# comunes (`empresa_id` es funcion Y columna de casi todas las tablas).
_SQL_OBJETOS_PUBLIC = r"""
    select c.relname as nombre, 'relacion' as clase from pg_class c
      join pg_namespace cn on cn.oid = c.relnamespace
     where cn.nspname = 'public' and c.relkind in ('r','v','m')
    union all
    select t.typname, 'tipo' from pg_type t
      join pg_namespace tn on tn.oid = t.typnamespace
     where tn.nspname = 'public' and t.typtype = 'e'
    union all
    select pr.proname, 'funcion' from pg_proc pr
      join pg_namespace pn on pn.oid = pr.pronamespace
     where pn.nspname = 'public'
"""

# Un objeto se considera referenciado sin calificar si aparece en el cuerpo
# normalizado precedido de algo que no sea `.` ni parte de un identificador.
#
# Para relaciones y tipos se exige ademas que NO vaya seguido de `.`: un
# `nombre.columna` es una cualificacion de columna, no una relacion resuelta por
# search_path. El caso concreto que lo motivo es el `on conflict do update set`
# de `aplicar_a_vacante`, donde `candidatos.headline` y `applications.status`
# referencian el ALIAS de la tabla destino del INSERT — Postgres expone ahi la
# fila existente bajo el nombre de la tabla, sin resolver nada contra el
# search_path. La funcion corre con `search_path = ''` y sus tests pasan; marcarla
# habria sido "arreglar" SQL que funciona.
#
# Excluir la forma `nombre.` no crea un punto ciego: cualquier uso real de una
# relacion sin calificar exige nombrarla en un FROM / JOIN / INTO / UPDATE, y
# ahi nunca lleva punto detras.
#
# Para funciones se exige el parentesis de llamada, porque sus nombres chocan con
# nombres de columna muy comunes.
_SQL_REFERENCIA_DESNUDA = r"""
    case when o.clase = 'funcion'
         then cuerpo.txt ~ ('(^|[^.[:alnum:]_])' || o.nombre || '[[:space:]]*\(')
         else cuerpo.txt ~ ('(^|[^.[:alnum:]_])' || o.nombre || '([^.[:alnum:]_]|$)')
    end
"""


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
        f"""
        with cuerpo as (
            select p.oid, p.proname, {_SQL_CUERPO_NORMALIZADO} as txt
              from pg_proc p
              join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public'
               and array_to_string(p.proconfig, ',') like '%search_path=%'
        )
        select cuerpo.proname,
               string_agg(distinct o.clase || ':' || o.nombre, ', ') as refs
          from cuerpo
          cross join lateral ({_SQL_OBJETOS_PUBLIC}) o
         where {_SQL_REFERENCIA_DESNUDA}
         group by cuerpo.proname
         order by cuerpo.proname
        """
    )
    ofensores = {r["proname"]: r["refs"] for r in filas}
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
        f"""
        with cuerpo as (
            select p.oid, p.proname, {_SQL_CUERPO_NORMALIZADO} as txt
              from pg_proc p
              join pg_namespace n on n.oid = p.pronamespace
              join pg_type rt on rt.oid = p.prorettype
             where n.nspname = 'public'
               and rt.typname = 'trigger'
               and coalesce(array_to_string(p.proconfig, ','), '') not like '%search_path=%'
        )
        select distinct cuerpo.proname
          from cuerpo
          cross join lateral ({_SQL_OBJETOS_PUBLIC}) o
         where {_SQL_REFERENCIA_DESNUDA}
         order by cuerpo.proname
        """
    )
    ofensores = [r["proname"] for r in filas]
    assert not ofensores, (
        "Funciones de trigger sin search_path propio que resuelven objetos de "
        f"public: {ofensores}. Fallaran si las dispara una funcion "
        "`security definer` con search_path fijado."
    )


async def test_policies_do_not_call_functions_their_role_cannot_execute(
    db: asyncpg.Connection,
) -> None:
    """Ningun rol con SELECT sobre una tabla puede recibir un error de permisos
    al evaluarse sus policies.

    Regresion de 0006 §2: `empresas_platform_admin_all` no llevaba clausula
    `TO`, asi que se evaluaba tambien para `anon`, que no tiene EXECUTE sobre
    `is_platform_admin()`. Un `select from empresas` sin sesion no devolvia
    cero filas: abortaba con 42501, que PostgREST traduce a un 500.

    Este es el unico de los tres defectos de 0006 que NO es de resolucion de
    nombres, y por eso el test tampoco inspecciona texto: se pone en la piel de
    cada rol y lee cada tabla sobre la que tiene SELECT. Cero filas es correcto;
    un error no.

    Alcance: solo LECTURA, y solo `anon` y `authenticated`. Una policy de
    escritura con el mismo defecto no se detecta aqui.
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


async def test_dev_compose_mounts_every_migration(
    db: asyncpg.Connection,
) -> None:
    """El `docker-compose.dev.yml` tiene que montar TODAS las migraciones.

    No usa la base — vive aqui porque es la misma familia de defecto que el
    resto del modulo: un gate que pasa por una via que nadie usa.

    El compose enumera los ficheros de `infra/supabase/migrations/` a mano, uno
    por linea, porque el entrypoint de Postgres los ordena alfabeticamente y el
    shim de `auth` tiene que correr antes que 0001 (`0001...` ordena ANTES que
    `00_supabase_shim.sql`, asi que montar el directorio entero no vale).

    Enumerar a mano se desincroniza sola: 0006 se anadio en la sesion 4 y el
    compose se quedo en 0005. La suite de pytest no lo noto porque su fixture
    hace glob del directorio — pasaba en verde mientras el entorno que el
    onboarding manda levantar seguia creando una base con los tres bugs dentro.
    """
    from pathlib import Path

    aqui = Path(__file__).resolve()
    raiz = next(p for p in aqui.parents if (p / "pnpm-workspace.yaml").exists())
    migraciones = sorted(p.name for p in (raiz / "infra/supabase/migrations").glob("*.sql"))
    compose = (raiz / "infra/docker/docker-compose.dev.yml").read_text(encoding="utf-8")

    faltan = [m for m in migraciones if m not in compose]
    assert not faltan, (
        f"docker-compose.dev.yml no monta estas migraciones: {faltan}. "
        f"El entorno de desarrollo crearia una base sin ellas."
    )
