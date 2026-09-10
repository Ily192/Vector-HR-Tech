# Next steps — qué falta por ejecutar

> Lista viva. Actualizar al cierre de cada sesión.
> Última actualización: **2026-09-09** (sesión 5).

## TL;DR sesión 4 (2026-09-08)

**El bloqueante duro está resuelto: las migraciones se aplicaron y los tests de
RLS corrieron contra un Postgres real.** No hizo falta instalar WSL2 — el
diagnóstico de la sesión 3 era incorrecto. Docker Desktop simplemente no estaba
arrancado; al lanzarlo, crea su propia distro WSL2 (`docker-desktop`) y el
engine levanta. Coste real del bloqueante que costó una sesión entera: abrir la
aplicación.

Ejecutar reveló **tres bugs de esquema que ningún análisis estático podía ver**:
dos de resolución de nombres en runtime y uno de privilegios (una policy sin
cláusula `TO`) — ver § "Lo que se arregló en la sesión 4". Los dos de resolución
de nombres estaban en serie sobre la misma sentencia y dejaban el test
psicométrico completamente muerto: la primera llamada de cualquier candidato
reventaba.

Estado: **46/46 tests de seguridad en verde** (42 de RLS + 4 guardas
estructurales nuevas), migraciones 0001-0006 aplicadas desde cero sin errores.

> **Addendum 2026-09-09.** Una auditoría adversarial de este mismo registro
> encontró seis problemas confirmados, tres de ellos bugs reales que la sesión 4
> no vio: el compose de desarrollo seguía montando solo hasta `0005`, el shim de
> ese compose arrastraba el bug de `auth.uid()` que solo se arregló en el arnés,
> y la mitad del fix de `0006` §1 no la ejecutaba ningún test. Además, las
> guardas estructurales estaban sobrevendidas y el comando de `gh auth refresh`
> del runbook estaba roto. Todo corregido; el detalle en §§5-8.

## Pendientes — vista rápida

Ordenados por lo que desbloquea a lo demás. El detalle de cada uno está más
abajo en su sección.

### 🔴 Bloquea todo el Cycle 1

| # | Pendiente | Quién | Estado |
|---|---|---|---|
| 1 | ~~Dar `Contents: write` + `Workflows: write` al token~~ | Ilyra | ✅ hecho 2026-09-09 |
| 2 | ~~Push de `main` a GitHub~~ | Claude | ✅ hecho — `6d61dcb` publicado |
| 3 | ~~Deploy en Vercel (career-site + hrbp)~~ | Claude | ✅ hecho 2026-09-09 — [career-site](https://vortex-career-site.vercel.app) · [hrbp](https://vortex-hrbp.vercel.app) |

### 🟠 Bloquea el backend

| # | Pendiente | Notas |
|---|---|---|
| 4 | **Provisionar Supabase Cloud** y aplicar 0001..0006 | Incluye activar el hook de JWT, sin el cual todas las policies de HR deniegan |
| 5 | **Secrets en GitHub Actions** | Doppler → repository secrets |
| 6 | **Resolver `force row level security`** (`0004` §9) | Necesita saber si el owner tiene `BYPASSRLS` en Supabase real; el contenedor local no lo puede contestar |
| 7 | **Elegir un solo camino de escritura para `runs`** | Recomendación: `set_tenant_context` + policy (ADR-004). Toca `app/workers/run_state.py` |
| 8 | **Rate limiting / captcha en `aplicar_a_vacante()`** | Antes de exponer el formulario público |
| 9 | **Destino de deploy del backend** | ADR-012 eligió Fly.io; no hay `fly.toml` ni step de `flyctl` |
| 10 | **Backups y entorno de staging** | El RTO de 30 min no se sostiene hoy |

### 🟡 Producto (Cycle 1)

| # | Pendiente | Notas |
|---|---|---|
| 11 | **2.1** Formulario de aplicación en career-site | El SQL ya está (`0005`); falta Server Action + UI |
| 12 | **2.3** Kanban HRBP con `@dnd-kit` + Realtime | Hoy `App.tsx` son 100 líneas con KPIs hardcodeados |
| 13 | **2.2** Scaffold de candidate app | Rutas `/`, `/applications/:id`, `/test/:token`, `/profile` |
| 14 | **2.4** Skill `chro-intake` (SKILL.md + golden set) | |
| 15 | **2.5** Poblar `golden.jsonl` y conectar el evaluador al modelo | Necesita claves de LLM |
| 16 | **2.7** E2E Playwright del flujo completo | Necesita la base |
| 17 | **2.8** Loom demo de 5 min | |

> **Sin decidir:** cuál de los ítems de producto se ataca primero. Se preguntó al
> cierre de la sesión 4 y quedó sin respuesta.

### 🟢 Higiene (no bloquea nada)

- Acotar con `TO authenticated` las 20 policies que siguen sin cláusula `TO`.
- Deuda técnica de la tabla del final: LGPD, cifrado de columna, feature flags,
  Doppler, OpenTelemetry, branch protection, cadena de hash de `activity_log`,
  recall de pgvector.

---

## TL;DR sesión 3

La sesión 3 fue una auditoría completa del repo seguida de correcciones. El
hallazgo central: **casi ninguna señal de calidad del proyecto era real**. El
monorepo nunca había compilado, el servicio Python no arrancaba, los 6 tests
unitarios fallaban, el CI no podía correr un solo job de Python, los evals se
auto-aprobaban con 0 casos, y el esquema de base tenía tres vías por las que un
usuario anónimo tomaba control de cualquier tenant.

Lo que estaba bien —y es mucho— era el **diseño**: la arquitectura, el modelo
de datos, la estrategia de RLS, el patrón de workers, los ADRs. El problema era
que nada de la ruta de I/O real se había ejecutado nunca, así que todo estaba
en verde por vacuidad.

**Estado tras la sesión 3:** el build pasa, el servicio arranca, hay tests de
verdad, y las vías de escalada están cerradas en el SQL. **Lo que sigue sin
verificarse contra infraestructura real es todo lo que necesita Postgres,
Redis o un LLM** — ver "Qué NO está verificado" abajo, que es la sección más
importante de este documento.

---

## Qué NO está verificado (leer antes que nada)

| Área | Estado | Por qué |
|---|---|---|
| Migraciones SQL (0001-0006) | ✅ **Aplicadas desde cero contra Postgres real** | `pgvector/pgvector:pg15`, la misma imagen que usa CI. Sin errores. Ojo: eso es el contenedor ad-hoc de los tests. El `docker compose` de desarrollo montaba solo hasta `0005` hasta el 2026-09-09 — ver §8. |
| Tests de RLS (42 casos) | ✅ **42/42 en verde** | Más 4 guardas estructurales: 46/46. |
| `force row level security` (0004 §9) | **Sigue sin decidirse** | Depende de si el owner del esquema tiene `BYPASSRLS`. En el contenedor local el owner es `vortex`, que es **superusuario** — y un superusuario bypasea RLS por serlo, no por el atributo. No dice nada sobre cómo Supabase configura su rol `postgres`. Solo se resuelve contra un proyecto Supabase real. |
| Migraciones en Supabase Cloud | **No aplicadas** | Un Postgres plano con los stubs de `auth` no es Supabase: faltan el hook de JWT, las policies de Storage y los roles reales. Ver "Bloqueado por el user" #2. |
| Flujo end-to-end HR | **Nunca ejecutado** | No hay proyecto Supabase, ni Redis corriendo, ni claves de LLM. |
| Deploy en Vercel | ✅ **Hecho** | `vortex-career-site` y `vortex-hrbp`, ambos enlazados al repo. Verificado HTTP 200 y cabeceras de seguridad aplicadas. |

### Cómo levantar la base de pruebas (2 minutos)

El bloqueo de la sesión 3 —"WSL2 no tiene ninguna distro"— era un diagnóstico
equivocado. Docker Desktop **crea su propia distro** (`docker-desktop`) al
arrancar; lo único que pasaba es que no estaba lanzado. No hace falta
`wsl --install` ni reiniciar.

La shell por defecto de esta máquina es PowerShell; el bloque de abajo es **bash**
(Git Bash), que es donde se ejecutó. Las continuaciones con `\` y los `VAR=x cmd`
en línea no funcionan en PowerShell.

```bash
# 1. Abrir Docker Desktop. Desde PowerShell:
#    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
#    Espera a que `docker ps` responda; crea él solo su distro WSL2.

# 2. Postgres con pgvector. El `rm -f` es lo que hace el bloque
#    reproducible: sin él, la segunda vez falla con "name already in use".
docker rm -f vortex-rls-pg 2>/dev/null
docker run -d --name vortex-rls-pg \
  -e POSTGRES_USER=vortex -e POSTGRES_PASSWORD=vortex -e POSTGRES_DB=vortex_test \
  -p 5432:5432 pgvector/pgvector:pg15

# 3. Correr la suite (aplica 0001..0006 desde cero en cada sesión de pytest)
cd services/hr-engine
DATABASE_URL="postgresql+asyncpg://vortex:vortex@localhost:5432/vortex_test" \
JWT_SECRET="test-secret-do-not-use" \
  uv run pytest tests/security -q
```

Si `uv` no está en el PATH (es lo normal en esta máquina):
`python -m pip install uv` y luego `python -m uv run ...`.

⚠️ **Este contenedor ocupa el puerto 5432, igual que el `docker compose` de
desarrollo** (`infra/docker/docker-compose.dev.yml`, base `vortex_dev`). No
pueden correr los dos a la vez. Son entornos distintos a propósito: el de arriba
es desechable y lo recrea el fixture en cada sesión de pytest; el del compose
persiste en un volumen y es el que usa el onboarding.

---

## Bloqueado por el user (no se puede hacer en local)

### 1. Publicar en GitHub y desplegar en Vercel

El trabajo está commiteado en local pero **sigue sin pushearse**. El motivo
cambió en la sesión 4: ya no es el clasificador de permisos (que en la sesión 3
bloqueó `git push` en todas sus formas), sino un **scope de OAuth que falta**.

El token de la cuenta `Ily192` tiene `gist, read:org, repo` pero **no
`workflow`**, y los commits tocan `.github/workflows/`. GitHub lo rechaza en el
servidor:

```
! [remote rejected] main -> main (refusing to allow an OAuth App to create or
  update workflow `.github/workflows/ci.yml` without `workflow` scope)
```

Se configuró ya lo que sí se podía: `gh auth switch -u Ily192` (la cuenta activa
era `ilyra-dev`, que no tiene acceso de escritura al repo) y `gh auth setup-git`,
para que git use el token de `gh` en vez de las credenciales de Git Credential
Manager.

**✅ HECHO el 2026-09-09.** `main` está publicado en
`Ily192/Vector-HR-Tech` (`b4d41f2...6d61dcb`, force-push). Verificado: local y
remoto coinciden en `6d61dcb`, el tag `legacy/ai-studio-scaffold` sigue en su
sitio, y de los 289 objetos publicados ninguno es un `var-local.*`, `.token`,
`.pem` ni `.key`.

**La vía es el token, no `gh`.** Ilyra dejó un PAT fine-grained en
`var-local.txt` (raíz del repo, ignorado por git) y pidió usarlo siempre para los
push. El device flow de `gh` se descartó tras fallar dos veces.

El token necesita, en *Repository permissions* de
<https://github.com/settings/personal-access-tokens>:

| Permiso | Valor | Por qué |
|---|---|---|
| **Contents** | Read and write | para hacer push |
| **Workflows** | Read and write | los commits tocan `.github/workflows/` |

El push, con el token inyectado solo para ese comando:

```bash
export GITHUB_TOKEN=$(python -c "
import pathlib,re
t=pathlib.Path('var-local.txt').read_text(encoding='utf-8-sig').strip()
m=re.search(r'GITHUB_TOKEN\s*=\s*(\S+)', t); print(m.group(1) if m else '')
")
git -c credential.helper= \
    -c credential.helper='!f(){ echo username=x-access-token; echo password=$GITHUB_TOKEN; }; f' \
    push --force-with-lease=main:b4d41f296bc4cd85e35e23959b33015226832b54 origin main
```

⚠️ **Tres trampas verificadas, para no repetirlas:**

- `GET /repos/{owner}/{repo}` devuelve `permissions.push: true` aunque el token
  no pueda escribir: ese campo refleja el rol del **usuario**, no lo concedido al
  token.
- **`x-accepted-github-permissions` tampoco sirve para eso.** Esa cabecera dice
  qué permisos acepta el **endpoint**, y es la misma para cualquier token — así
  que un `contents=read` ahí no significa que el token sea de solo lectura. Se
  interpretó mal durante esta sesión. **No hay forma limpia de introspeccionar lo
  que un PAT fine-grained tiene concedido: el test real es intentar la operación**
  y mirar si da 403.
- `gh auth refresh` **no acepta `-u/--user`** (gh 2.97.0) y su device flow
  autoriza como la cuenta abierta en el **navegador**, no como la activa de `gh`.
  Por ahí se perdió una sesión entera.

Sin el código en GitHub, Vercel no puede importar el repo, así que el deploy
sigue bloqueado detrás de esto.

Estado del remoto `https://github.com/Ily192/Vector-HR-Tech`:

- `main` sigue teniendo solo `b4d41f2 "Add files via upload"` (scaffold de
  Google AI Studio, incompatible con este monorepo).
- **Ese commit ya está preservado** como tag `legacy/ai-studio-scaffold`, que sí
  se pudo pushear. El force-push no pierde nada.

Una vez pusheado, en Vercel, un proyecto por app:

- New Project → Import Git Repository → `Ily192/Vector-HR-Tech`.
- Root Directory: `apps/career-site` (y repetir con `apps/hrbp`).
- Framework Preset: auto-detect. Build/Install los lee de `apps/<name>/vercel.json`.
- Env vars: las `NEXT_PUBLIC_*` para career-site y las `VITE_*` para hrbp
  (ver `.env.example`, sección FRONTEND).
- Production domain: dejar `*.vercel.app` por ahora (ADR-010).

**Las dos apps compilan y no dependen de Supabase todavía**, así que se pueden
desplegar hoy sin backend ni base de datos.

### 1-bis. Vercel — HECHO el 2026-09-09

Dos proyectos creados vía API y enlazados a `Ily192/Vector-HR-Tech`
(el namespace de GitHub ya estaba conectado a la cuenta de Vercel):

| Proyecto | Root Directory | Framework | URL |
|---|---|---|---|
| `vortex-career-site` | `apps/career-site` | Next.js | <https://vortex-career-site.vercel.app> |
| `vortex-hrbp` | `apps/hrbp` | Vite | <https://vortex-hrbp.vercel.app> |

Verificado: `/`, `/vacantes` y el cockpit devuelven **HTTP 200** con los títulos
correctos, y las cabeceras de seguridad de los `vercel.json`
(`Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`,
`Referrer-Policy`, y `Permissions-Policy` en hrbp) se aplican de verdad.

**No se configuró ninguna variable de entorno**: las dos apps compilan y
funcionan sin Supabase, tal y como decía este documento. Habrá que añadir las
`NEXT_PUBLIC_*` y `VITE_*` cuando exista el proyecto Supabase (#2).

⚠️ **El primer intento de despliegue falló en los dos proyectos**:

```
ERR_PNPM_RECURSIVE_EXEC_FIRST_FAIL  Command "turbo-ignore" not found
```

El `ignoreCommand` de ambos `vercel.json` llamaba a `pnpm turbo-ignore`, pero
`turbo-ignore` es un paquete npm **aparte** y no estaba en las dependencias del
monorepo. Esa config no habría funcionado nunca — el mismo patrón que este repo
lleva cuatro sesiones persiguiendo. Corregido a `npx --yes turbo-ignore@2`
(commit `1a3f0b8`), que es la forma documentada por Turborepo y no obliga a
tocar el lockfile.

Como los proyectos están enlazados por Git, **a partir de ahora cada push a
`main` despliega solo**.

### 2. Provisionar Supabase Cloud

- supabase.com → New project (region `sa-east-1` para LATAM).
- Habilitar la extensión `vector` desde el dashboard.
- Aplicar las migraciones:
  ```bash
  supabase link --project-ref <PROJECT_REF>
  supabase db push   # aplica 0001..0006
  ```
- **Activar el hook de JWT**: Dashboard → Authentication → Hooks → Custom Access
  Token → `public.custom_access_token_hook`. **Sin esto todas las policies de HR
  deniegan.** No es opcional.
- Dar de alta el primer admin de plataforma a mano (la tabla `platform_admins`
  no es escribible por ningún usuario):
  ```sql
  insert into platform_admins (user_id, note) values ('<uuid>', 'Ilyra · bootstrap');
  ```
- Copiar `URL`, `anon key` y `service_role key` a Doppler.

**No correr `seed.sql` contra el proyecto real.** Ahora tiene una guarda de
entorno que aborta fuera de bases `*dev*`/`*test*`, pero los tokens del seed
están en el repo público.

### 3. Secrets en GitHub Actions

Doppler → integración con GitHub → sync del env `prd` a repository secrets.

- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID_CAREER_SITE`,
  `VERCEL_PROJECT_ID_HRBP`
  (⚠️ con guion bajo: los nombres de secrets de GitHub no admiten guiones, y la
  versión anterior de este documento pedía `VERCEL_PROJECT_ID_career-site`, que
  es imposible de crear)
- `SENTRY_TOKEN`, `CODECOV_TOKEN`, `LHCI_GITHUB_APP_TOKEN`
- `TURBO_TOKEN` + var `TURBO_TEAM` (opcional, cache remoto)

`COOLIFY_*` ya no hacen falta: `release.yml` está desactivado y su destino de
deploy se replantea en Cycle 2 sobre Fly.io (ADR-012).

---

## Lo que se arregló en la sesión 4

Todo salió de ejecutar por primera vez las migraciones contra un Postgres real.

Los **dos primeros** (§1 y §2 de abajo) son **la misma clase**: un nombre sin
calificar que se resuelve en tiempo de ejecución contra un `search_path` vacío,
que no es el que quien escribió la función tenía en la cabeza. El **tercero**
(§3) **no lo es**: la policy ya invocaba `public.is_platform_admin()` totalmente
calificada, y lo que falla es la ausencia de cláusula `TO` — Postgres evalúa el
predicado para un rol sin EXECUTE sobre la función y aborta con 42501. Es un
fallo de privilegios; el fix añade `to authenticated` y no califica nada.

Lo que comparten los tres es que **solo aparecen al ejecutar**: ninguno es
visible leyendo el SQL, ni parseándolo, ni aplicando la migración — que se
aplica sin un solo warning.

Están todos en `0006_definer_search_path_fix.sql`, cuyo nombre describe a dos de
los tres, con la explicación larga en el propio fichero.

⚠️ **La numeración de abajo NO coincide con la del fichero.** Aquí van en el
orden en que aparecieron; en `0006` van en el orden en que se aplican:

| Aquí | En `0006` | Bug |
|---|---|---|
| 1 | §1 | `submit_psicometrico`, cast sin calificar |
| 2 | **§3** | trigger que hereda el `search_path` |
| 3 | **§2** | policy de `empresas` sin `TO` |

### 1. `submit_psicometrico()` reventaba en la primera llamada

0004 §3 movió el flujo público del test psicométrico a funciones
`security definer` con `set search_path = ''` — que es la defensa correcta
contra el shadoweo de objetos. Pero el cuerpo quedó con dos casts sin
calificar:

```sql
status = case when p_finish then 'completed'::psicometrico_status ...
```

El cuerpo de una función plpgsql se resuelve al **invocarla**, con el
`search_path` de la propia función, que aquí está vacío. Resultado:
`ERROR: type "psicometrico_status" does not exist`.

Como 0004 le revocó `psicometricos` a `anon`, esa función es la única vía de
escritura: **ningún candidato podía enviar su test**. La clausula `RETURNS` de
la función hermana nombra el mismo tipo sin calificar y no falla, porque esa sí
se resuelve al crear — por eso la migración se aplicaba limpia.

### 2. El mismo bug, encadenado, en un trigger

Con el cast arreglado, la suite volvió a fallar en la misma línea con
`relation "applications" does not exist`.

`enforce_empresa_id_from_application()` (0002) no fija su `search_path` y lee
`applications` sin calificar. Una función de trigger sin `search_path` propio
no tiene uno "por defecto": **hereda el de quien la dispara**. 0004 §5 la
extendió —correctamente— a `BEFORE UPDATE` de `psicometricos`, y el único
UPDATE del flujo público lo hace `submit_psicometrico()`, que corre con el
path vacío.

Los dos bugs estaban **en serie sobre la misma sentencia**, así que arreglar
solo el primero no habría devuelto el flujo a la vida. El segundo apareció
únicamente porque el primer fix destapó lo que había detrás.

### 3. `select from empresas` sin sesión abortaba en vez de devolver `[]`

`empresas_platform_admin_all` (0004 §1) no lleva cláusula `TO`, así que su rol
implícito es PUBLIC y Postgres la evalúa **también para `anon`**, que no tiene
EXECUTE sobre `is_platform_admin()`.

No es fuga de datos —el error ocurre antes de leer ninguna fila— pero PostgREST
lo traduce a un 500 en `/rest/v1/empresas` en vez del `[]` que corresponde. Se
acotó la policy a `authenticated`, el único rol que puede satisfacerla.

Verificado contra la base: de las 9 relaciones sobre las que `anon` conserva
grants, `empresas` era la única que reventaba.

### 4. El arnés de tests estaba probando otra función que la de producción

El stub de `auth.uid()` en `conftest.py` tenía el `nullif` **después** del cast
a `jsonb`, así que con el GUC en cadena vacía —que es como la fixture
representa "sin sesión"— lanzaba `22P02` y tumbaba la query. Es exactamente el
error que `0001` documenta y evita en `public.empresa_id()`, cometido en el
arnés en vez de en el esquema. Ahora es una réplica literal de la de Supabase.

Lo destapó una de las guardas nuevas, no un test funcional.

### 5. Guardas estructurales (`tests/security/test_search_path.py`)

Cuatro tests que cubren la **clase** de bug, no las instancias concretas:

- ninguna función con `search_path` fijado nombra objetos de `public` sin
  calificar — relaciones, tipos enum **y funciones**;
- toda función de trigger que resuelva objetos de `public` fija su
  `search_path`;
- ningún rol con SELECT sobre una tabla recibe un error de permisos al
  evaluarse sus policies (se pone en la piel de `anon` y `authenticated` y lee
  cada tabla: cero filas es correcto, un error no);
- el `docker-compose.dev.yml` monta **todas** las migraciones (ver §8).

Los tres primeros se apoyan en el catálogo de la base migrada, no en el texto de
los `.sql`, así que también atrapan lo que llegue por el dashboard de Supabase o
un hotfix manual.

#### Qué NO cubren

Las guardas normalizan el cuerpo de cada función antes de buscar: quitan
comentarios, literales entre comillas y las referencias ya calificadas con
`public.`. Aun así quedan límites, y están anotados en el docstring del módulo:

- Las funciones solo se detectan en sintaxis de llamada (`nombre(`), porque sus
  nombres chocan con nombres de columna (`empresa_id` es función **y** columna
  de casi todas las tablas).
- Un nombre construido dinámicamente y ejecutado con `execute` no se ve.
- El tercer test comprueba **solo lectura** y **solo** `anon` y `authenticated`.
  Una policy de *escritura* con el mismo defecto no la atrapa.

#### Se verificó que pueden fallar — dos veces

Primero con los tres bugs reintroducidos enteros en una migración temporal: los
tres tests fallaron con mensajes accionables. Es la lección de la sesión 3
aplicada — un gate que no se ha visto fallar no es un gate.

**Pero la primera versión de estas guardas estaba sobrevendida**, y lo destapó
una auditoría adversarial del propio registro de sesión (2026-09-09). Tenía tres
agujeros que la reintroducción total no podía revelar:

1. Se apoyaba en `prosrc !~ 'public\.<nombre>'`, que eximía al par
   (función, objeto) en cuanto la función mencionaba ese objeto calificado **una
   sola vez** en cualquier parte del cuerpo. `submit_psicometrico` tenía dos
   casts al mismo tipo: bastaba descalificar uno para volverse invisible. Y
   `enforce_empresa_id_from_application`, que tras `0006` contiene
   `public.applications`, habría quedado exenta **para siempre** justo del bug
   que tuvo.
2. Necesitaba una allowlist **por nombre de función** para los dos triggers de
   `activity_log`, que nombran la tabla dentro del texto de su `raise`. Eximir
   funciones enteras enmascara cualquier referencia real que se les añada
   después. Al quitar los literales en la normalización, la allowlist sobra y se
   eliminó.
3. No escaneaba **funciones** en absoluto, solo relaciones y tipos. Una llamada
   sin calificar a `public.empresa_id()` bajo `search_path` vacío revienta igual
   que el bug §1, y el gate no la veía.

Se reforzaron y se volvió a falsar, esta vez con regresiones **parciales**: un
cast calificado y el otro no, un trigger con la tabla calificada en un sitio y
desnuda en otro, y una llamada a función sin calificar. Las tres se detectan
ahora; ninguna se detectaba antes. Se comprobó además que una función que solo
nombra tablas dentro de un literal **no** produce falso positivo.

En el mismo pase apareció un falso positivo real que conviene recordar:
`aplicar_a_vacante` usa `candidatos.headline` y `applications.status` dentro de
`on conflict do update set`. Ahí el nombre desnudo es el **alias de la tabla
destino**, no una relación resuelta por `search_path`, y la función pasa sus
tests con el path vacío. Marcarla habría llevado a "arreglar" SQL que funciona;
la guarda ahora ignora la forma `nombre.columna`.

### 6. Cambios en `test_rls.py` que el diff podría hacer parecer un debilitamiento

Tres cambios en la suite que **no** relajan ninguna garantía, pero que leídos en
frío en el diff lo parecen. Quedan aquí para que nadie los "revierta":

- **Ocho aserciones de excepción cambiaron de clase.** Las funciones del esquema
  rechazan input inválido con `raise ... using errcode = '22023'`, y asyncpg
  mapea cada SQLSTATE a su propia clase — así que `pytest.raises(RaiseError)`
  (que es `P0001`) no capturaba esos rechazos **aunque el rechazo fuera
  correcto**. Se cambiaron a `InvalidParameterValueError` (alias `RejectedInput`
  en el módulo) y, en los dos casos del trigger que congela columnas de
  `profiles`, a `InsufficientPrivilegeError` (`42501`). Se arregló el test, no el
  SQL: el errcode explícito es deliberado, porque PostgREST lo traduce a 400 y
  un `P0001` genérico se confunde con un fallo interno.
- **`_make_user()` se reescribió entero.** Insertaba en `profiles` a mano, lo
  cual dejó de funcionar cuando `0004` hizo obligatoria la invitación: el propio
  insert en `auth.users` dispara `handle_new_user()`, que aborta sin
  `invite_token`. Ahora pasa por el flujo real (crea invitación → inserta en
  `auth.users` con el token → el trigger crea el profile). Efecto secundario
  bueno: cada fixture ejercita el camino de alta.
- **Los parámetros de `sha256()` van por `::text::bytea`.** Con `$1::bytea` a
  secas, asyncpg infiere `bytea` y exige un objeto `bytes`; el cast por `text`
  reproduce exactamente lo que hace el SQL de producción (`p_token::bytea`).

### 7. Un hueco de cobertura en el propio fix de `0006`

`0006` §1 arregló los **dos** casts a `psicometrico_status` de
`submit_psicometrico`, pero toda la suite llamaba a la función con
`p_finish = false`. La rama `'completed'::public.psicometrico_status` —la mitad
del fix— **no la ejecutaba nada**, así que se dio por buena sin haberse corrido
nunca. Es el modo de fallo del repo, cometido justo al arreglarlo.

Lo destapó la auditoría del 2026-09-09. Añadidos
`test_submit_rpc_can_finish_the_test` (cierra un test y verifica `status`,
`completed_at` y los Big5) y `test_submit_rpc_rejects_a_finished_test` (un test
cerrado no se puede reabrir con el mismo token).

### 8. El entorno de desarrollo seguía creando una base con los tres bugs

Dos defectos en la ruta que el onboarding manda usar, ninguno de los cuales
tocaba la suite de tests:

- **`docker-compose.dev.yml` montaba las migraciones 0001→0005.** Enumera los
  ficheros a mano —tiene que hacerlo, porque el shim de `auth` debe correr antes
  que `0001` y el entrypoint ordena alfabéticamente— y se quedó en `0005` cuando
  se añadió `0006`. El fixture de pytest hace *glob* del directorio, así que los
  tests pasaban en verde mientras `docker compose up` creaba una base **con los
  tres bugs dentro**: el candidato no podía enviar su psicométrico y
  `select from empresas` sin sesión reventaba. Es el caso de libro del modo de
  fallo del repo: el gate pasa por una vía que no es la que usa la gente. Ahora
  lo vigila `test_dev_compose_mounts_every_migration`.
- **El shim `00_supabase_shim.sql` arrastraba el mismo bug de `auth.uid()`**
  que se corrigió en `conftest.py` (§4): el `nullif` después del cast a `jsonb`.
  Había dos copias del stub y solo se arregló una — la que usan los tests, no la
  que usa el entorno de desarrollo.

### 9. CI

El job de RLS apuntaba a `tests/security/test_rls.py`, así que las guardas
nuevas habrían quedado fuera del gate. Ahora corre el directorio entero.

### 10. Docstring de `runs.py`

Afirmaba que `runs` solo tenía policy `for select` y que un INSERT bajo
`authenticated` fallaba. **0004 lo dejó obsoleto** y el test
`test_worker_can_persist_run_status` lo confirma: con contexto de tenant,
inserta y actualiza. Corregido, con la decisión pendiente documentada in situ.

⚠️ Ojo con qué demuestra ese test: verifica el camino que el código **no** usa
hoy (sesión `authenticated` con `set_tenant_context`). Que `runs.py` siga
funcionando por su camino actual —sesión sin contexto de tenant— no lo cubre
ningún test. Ver la decisión pendiente en § Cycle 1.

---

## Lo que se arregló en la sesión 3

### Build y toolchain

- **El monorepo nunca había compilado.** Tres defectos reales: el `@import` de
  los estilos compartidos iba después de las directivas `@tailwind` (Tailwind
  veía `@layer base` sin su `@tailwind base`); el preset de Tailwind era un
  `.js` sin tipos y no satisfacía `Partial<Config>`; y `typedRoutes` fallaba
  porque el hero enlazaba a `/contacto`, que no existía. Ahora `pnpm build` pasa.
- **`pnpm-lock.yaml` commiteado.** Sin él, `pnpm install --frozen-lockfile`
  abortaba y con eso caían 4 jobs de CI y el build de Vercel.
- **`uv.lock` generado.** Sin él caían los 5 jobs de Python, incluido el de RLS.

### Seguridad de la base (lo más grave)

Tres vías por las que un anónimo con la anon key tomaba control de un tenant:

1. **Signup con privilegios a elección.** `handle_new_user` sacaba `empresa_id`
   y `role` de `raw_user_meta_data`, que es el `options.data` de `signUp()` y lo
   controla el cliente. Cualquiera se daba de alta como `SuperAdmin` en el
   tenant que quisiera. Ahora hace falta una invitación (tabla `invitations`,
   token hasheado, email validado).
2. **Auto-promoción.** `profiles_self_update` no tenía `WITH CHECK`, así que
   `update profiles set role='SuperAdmin' where id = auth.uid()` pasaba. Cerrado
   con `WITH CHECK` + trigger que congela `role` y `empresa_id`.
3. **Psicométricos abiertos.** La policy "por token" no mencionaba el token:
   `select token, raw_answers from psicometricos` devolvía todos los tests
   activos de todos los tenants, con los tokens en claro. Y su `WITH CHECK` era
   más débil que su `USING`, así que un anónimo podía reescribir `empresa_id` y
   los resultados Big5 de cualquier fila. Ahora `anon` no toca la tabla; el
   flujo pasa por dos funciones `security definer` y el token se guarda hasheado.

Más: `SuperAdmin` deja de ser un rol de tenant con alcance global (pasa a
`platform_admins`); FK compuestas `(id, empresa_id)` para que una `application`
no pueda referenciar un candidato de otra empresa; `vacantes` deja de exponer
`icp_text` y bandas salariales a `anon` (vista `vacantes_publicas`); `runs` gana
policy de escritura (su `UPDATE` afectaba 0 filas en silencio y el cost tracking
nunca se persistía); `activity_log` ya no se puede vaciar con `TRUNCATE`. Ver **ADR-015** y
`0004_security_hardening.sql`.

Se evaluó activar `force row level security` y **se descartó**: FORCE alcanza
también al owner cuando ejecuta una función `security definer` o una vista con
`security_invoker = false`, que es cómo está construido todo el acceso público
(vista de vacantes, RPCs del test psicométrico, signup, aplicación). Con FORCE
esas rutas devolverían cero filas. Funcionaría si el owner tuviera `BYPASSRLS`,
cosa que no se pudo verificar sin Postgres. Queda como TODO en `0004` §9.

También se movieron `auth.empresa_id()`/`auth.role()` a `public`: la versión
anterior **no se podía aplicar en Supabase Cloud** (`must be owner of function
role`) y además pisaba la función nativa que usan las policies de Storage.

### Flujo de aplicación (nuevo, `0005`)

`anon` no tenía ninguna vía de INSERT, así que "candidato aplica" era imposible.
Se añadió el bucket `cvs` con policies por path y la RPC
`public.aplicar_a_vacante()`. Falta la capa anti-abuso (rate limit / captcha)
antes de exponerla.

### Entorno local

El `docker compose` de desarrollo **no podía inicializar el esquema**: montaba
las migraciones de Supabase en un Postgres plano sin schema `auth`, así que el
entrypoint abortaba. Ahora hay un shim (`infra/docker/initdb/`) que corre antes,
y el compose incluye `hr-engine-api` y `hr-engine-worker`.

### Honestidad de la documentación

`deploy.md` y `rollback.md` describían un sistema que no existe (Coolify, que
ADR-012 descartó; `alembic upgrade head` sin alembic configurado; `unleash flag
disable` sin Unleash integrado; PITR que el plan free no incluye). Llevan ahora
un aviso de estado real al principio. Seguir esos runbooks durante un incidente
habría costado tiempo crítico.

### CI

`release.yml` se disparaba en **cada push a `main`** e intentaba desplegar a
Coolify; pasa a `workflow_dispatch`. `nightly.yml` corría a diario contra
scripts que no existen; también pasa a manual. El job de evals nunca se había
ejecutado (`pull_request.changed_files` es un entero, no una lista de rutas);
ahora usa `paths-filter`. Añadidos `--cov-fail-under=60`, la ruta del
`coverage.xml` para Codecov, `.lighthouserc.json`, y el arreglo del nombre de
secret con guion en `preview-deploy.yml`.

### Evals

`_run_cv_evaluator()` devolvía `case.expected` en **ambas** ramas: la predicción
era el ground truth, así que `pass_rate` y `pearson_r` daban 1.0 por
construcción y la suite no podía fallar. En CI eso se habría subido como
evidencia de la calidad del modelo. Ahora lanza excepción, y
`--fail-below-threshold` falla con 0 casos en vez de pasar.

---

## Cycle 1 — MVP HR Pipeline

### Bloqueantes antes de cualquier deploy de backend

- [x] ~~**Correr los tests de RLS contra Postgres real.**~~ Hecho en la sesión 4:
      43/43 en verde contra `pgvector/pgvector:pg15`. Destapó tres bugs de
      esquema (§ "Lo que se arregló en la sesión 4"). De las dos preguntas que
      solo una base real podía contestar:
      - **`BYPASSRLS` del owner: sigue abierta.** En el contenedor el owner es
        superusuario, y un superusuario bypasea RLS por serlo, no por el
        atributo. No dice nada sobre el rol `postgres` de Supabase. `force row
        level security` sigue sin decidirse (`0004` §9).
      - **Escritura de `runs`: contestada.** La policy `runs_tenant_write` de
        `0004` funciona bajo `authenticated` con contexto de tenant (verificado
        por `test_worker_can_persist_run_status`). Quedan los dos caminos vivos
        y hay que elegir — ver la decisión pendiente abajo.
- [ ] **Elegir un solo camino de escritura para `runs`.** Hoy `runs.py` corre
      sin contexto de tenant y confía en la comparación de `empresa_id` contra
      el run-token firmado. ADR-004 (defensa en profundidad) pide lo otro: usar
      `set_tenant_context` y apoyarse en la policy, para que el motor atrape el
      cross-tenant aunque el código se equivoque. Mover el worker toca
      `app/workers/run_state.py` y el ciclo de vida de la sesión. La
      recomendación es (2); está documentada en el docstring de `runs.py`.
- [ ] **Aplicar las migraciones en un proyecto Supabase real** y verificar que
      `supabase db push` no falla. Que pasen contra el contenedor **no** lo
      garantiza: el contenedor usa stubs de `auth` y no tiene el hook de JWT,
      las policies de Storage ni los roles reales de Supabase.
- [ ] **Rate limiting / captcha en `aplicar_a_vacante()`** antes de exponer el
      formulario público.
- [ ] **Destino de deploy del backend.** ADR-012 eligió Fly.io y no existe ni
      un `fly.toml` ni un step de `flyctl` en ningún workflow.
- [ ] **Backups.** La única estrategia documentada es PITR de Supabase, que es
      del plan Pro; ADR-012 planifica el free tier. El RTO de 30 min no se
      sostiene hoy.
- [ ] **Entorno de staging.** Hoy se promueve de CI directo a "prod".

### Producto pendiente

- [ ] **2.1** Career-site: formulario de aplicación en `/vacantes/[slug]/aplicar`
      con subida de CV. El SQL ya está (`0005`); falta la Server Action y la UI.
      Hoy el detalle de vacante tiene un botón deshabilitado y datos mock.
- [ ] **2.2** Candidate app: scaffold Vite + React, rutas `/`,
      `/applications/:id`, `/test/:token`, `/profile`. El HTML legacy del test
      psicométrico va a `apps/candidate/public/psicometrico/` (ADR-014).
- [ ] **2.3** HRBP cockpit: `/vacantes/:id` kanban con `@dnd-kit/core` +
      Supabase Realtime. Hoy `App.tsx` son 100 líneas con KPIs hardcodeados.
- [ ] **2.4** Skill `chro-intake` — SKILL.md + golden set.
- [ ] **2.5** Poblar `evals/cv-evaluator/golden.jsonl` con ≥10 CVs reales
      anonimizados y **conectar `_run_cv_evaluator()` al modelo**.
- [ ] **2.7** E2E Playwright del flujo completo. La infraestructura ya está
      (`packages/e2e`); falta el test del flujo real, que necesita la base.
- [ ] **2.8** Loom demo de 5 min.

### DoD Cycle 1

- Subir CV en career-site → ver score en hrbp en < 2 min wall-clock.
- Coverage ≥ 60% en `services/hr-engine` (ya enforceado en CI).
- Lighthouse ≥ 85 en career-site (ya enforceado en `.lighthouserc.json`).
- RLS tests en verde **contra Postgres real**.
- Pearson r de `cv-evaluator` ≥ 0.75 sobre ≥10 casos reales.
- Loom demo grabado.

---

## Cycles 2-4 (resumen)

- **Cycle 2:** Fly.io para hr-engine + vendoring de Paperclip y OpenClaw
  (ADR-009). Workers `scheduler`, `interviewer`, `onboarder`, `constancia_gen`.
  Adapter de WhatsApp. 50 candidatos reales con Siete.
- **Cycle 3:** sales-engine multi-tenant.
- **Cycle 4:** lanzamiento open-source + Stripe billing + 5 clientes Pro.

---

## Deuda técnica conocida y no resuelta

| Tema | Detalle |
|---|---|
| LGPD / Habeas Data | `docs/08` promete retención por tipo de dato y endpoints de export/erasure. El esquema no tiene `deleted_at`, ni `retention_until`, ni jobs de purga, ni tabla de consentimientos. |
| Cifrado de columna | `psicometricos.raw_answers` y `entrevistas.transcript` están en claro. `docs/08` dice que deberían estar cifrados. |
| Feature flags | ADR-003 depende de ellos y `rollback.md` los usa como kill-switch. Unleash está en `.env.example` y no hay SDK en ningún paquete. |
| Doppler | Referenciado en todos lados, sin `doppler.yaml` ni integración. Los secretos no tienen fuente de verdad. |
| OpenTelemetry | 5 paquetes declarados en `pyproject.toml`. Verificar si el agente los conectó o los quitó. |
| Branch protection | Diferida. Con `main` desprotegido, cualquier push va directo. |
| `activity_log` | La cadena de hash (`prev_hash`/`hash`) no la calcula ni valida nada; es decorativa. Sin particionado ni purga. |
| Recall de pgvector | `match_candidates` no filtra por `empresa_id` en el SQL y confía en RLS, que se aplica **después** del scan del índice. Con muchos tenants, un tenant chico puede recibir 0 resultados teniendo candidatos perfectos. |
| Policies sin cláusula `TO` | Tras `0006`, **20 de las 21** policies del esquema siguen sin `TO`, así que se evalúan para todo rol, incluidos los que jamás podrían satisfacerlas. Solo una rompía —`empresas_platform_admin_all`, la única que invocaba una función con EXECUTE restringido— y ya lleva `to authenticated`. Las otras 20 son coste de planner y una mina para el futuro. Acotarlas es higiene pendiente. Nota sobre el alcance de la comprobación que sostiene el «solo una rompía»: fue **SELECT-only** y sobre `anon` y `authenticated`; una policy de escritura con el mismo defecto no se habría visto. |

---

## Decisiones pendientes

| Tema | Pregunta | Cuándo |
|---|---|---|
| WhatsApp provider | 360dialog vs Twilio vs Meta direct | Cycle 2 |
| Cliente piloto pagado | Siete vs LinkedIn outbound frío | Cooldown Cycle 1 |
| Plan de Supabase | Free tier sin PITR vs Pro con backups | Antes del primer cliente real |
| Open-source | Liberar Paperclip + OpenClaw + 4 skills | Cycle 4 |
| Dominio propio | `vortex-ops.com` o `vector-hr.tech` | Cooldown 4 (post-MRR $1.5k) |

---

## Riesgos en watch (top 3)

1. **R-07 Bus factor 1.** Mitigación: docs obsesivas + repo público mes 4.
2. **R-15 Burnout.** Mitigación: respetar cooldown, no trabajar fines de semana.
3. **R-12 Vibe coding sin review.** Esta sesión es el caso de estudio: mucho
   código plausible, bien estructurado y jamás ejecutado, con todas las señales
   de calidad en verde por vacuidad. La mitigación real no es más disciplina,
   es **hacer que los gates puedan fallar**.
