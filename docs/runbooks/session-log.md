# Session log

Bitácora de sesiones de trabajo Ilyra + Claude. Más reciente arriba.

---

## 2026-09-09 · Sesión 5 — Auditar el registro, y un token a punto de hacerse público

**Duración:** media jornada · **Modo:** Auto · **Modelo:** Claude Opus 5

### Auditoría del registro de la sesión 4

El detalle está en la entrada del 2026-09-08, § "Auditoría del propio registro".
Resumen: cuatro lentes independientes leyendo los documentos contra el código
real, cada hallazgo con dos refutadores. 42 hallazgos en bruto, 6 verificados.
Encontró **tres bugs reales que la sesión 4 no vio** —el compose de desarrollo
montaba solo hasta `0005`, su shim arrastraba el bug de `auth.uid()` corregido
solo en el arnés, y la mitad del fix de `0006` §1 no la ejecutaba ningún test— y
dos sobreafirmaciones del propio registro.

Commits: `e0acf05` (código) y `5b19f75` (docs).

### El hallazgo de seguridad

Al ir a usar el token de GitHub que Ilyra dejó en `var-local.txt`, resultó que
**ese fichero y su gemelo `var-local.env` estaban sin trackear y sin ignorar**.

El `.gitignore` tenía `.env` y `.env.*`, pero ese patrón es ".env" más sufijo, no
"`<nombre>.env`", así que no cubría `var-local.env`; y a `var-local.txt` no lo
cubría nada. Un solo `git add -A` los habría commiteado, y
`Ily192/Vector-HR-Tech` es un repo **público**.

Comprobado que nunca estuvieron en la historia (`git log --all -- var-local.*`
vacío), así que no hubo fuga. Ignorados en `c4ced74`, junto con `*.token` y
`secrets.*`.

Lo que hace que valga la pena registrarlo: los ficheros se crearon **a mitad de
sesión**, después de las comprobaciones de estado anteriores. Un árbol limpio
verificado hace una hora no dice nada sobre el de ahora.

### El push, que sigue sin hacerse

Cuatro intentos, cuatro motivos distintos — y ninguno era el de la sesión
anterior:

1. **Sesión 3:** el clasificador de permisos bloqueaba `git push`.
2. **Sesión 4:** el token de `Ily192` no tenía el scope `workflow`, y los commits
   tocan `.github/workflows/`.
3. **Hoy, primer intento:** el comando documentado para arreglarlo,
   `gh auth refresh -h github.com -u Ily192 -s workflow`, **está roto**: `gh` no
   acepta `-u/--user`. Lo detectó la auditoría, no una ejecución.
4. **Hoy, segundo intento:** con el comando correcto, el device flow expiró
   (`context deadline exceeded`). Causa: **autoriza como la cuenta que esté
   abierta en el NAVEGADOR**, no como la cuenta activa de `gh`. La autorización
   acabó aplicándose a `ilyra-dev`, que ya tenía el scope.
5. **Hoy, tercer intento:** con el PAT fine-grained de `var-local.txt`, un 403.
   El token es de `Ily192` y tiene acceso al repo, pero solo de lectura:
   `x-accepted-github-permissions: contents=read`.

Trampa que conviene no repetir: `GET /repos/{owner}/{repo}` devolvía
`permissions.push: true`. En un PAT fine-grained ese campo refleja el rol del
**usuario**, no lo que el token tiene concedido. Para saber lo que puede el token
hay que mirar `x-accepted-github-permissions`.

### Otros cambios

- La cuenta `ilyra-dev` (de trabajo) se eliminó de `gh` a petición de Ilyra.
  Solo tenía permiso de lectura sobre el repo. Se verificó que **nada de
  Vortex-Ops llegó nunca a esa cuenta**: el único remoto configurado siempre fue
  `Ily192/Vector-HR-Tech` y el reflog de remotos no tiene una sola entrada de
  push.
- Memoria de sesión actualizada: se borró la que afirmaba que Docker necesitaba
  `wsl --install` (refutada en la sesión 4) y la del push por device flow;
  ahora la vía por defecto es el token de `var-local.txt`.

### Verificación final

| Comando | Resultado |
|---|---|
| `pytest tests/security` (Postgres real) | 46/46 |
| `pytest tests/unit --cov-fail-under=60` | 128 tests, cobertura 90% |
| `ruff check` + `ruff format --check` | limpio |
| `mypy app` (strict) | limpio |
| `git check-ignore var-local.*` | ignorados ✓ |

---

## 2026-09-08 · Sesión 4 — El bloqueante duro, resuelto (y lo que había detrás)

**Duración:** media jornada · **Modo:** Auto · **Modelo:** Claude Opus 5 (1M)

### Cómo empezó

"Continúa con los pendientes de ayer". El pendiente nº1 de `next-steps.md` era
un requisito duro antes de cualquier deploy: correr los tests de RLS contra un
Postgres real. La sesión 3 lo había dejado bloqueado con este diagnóstico:

> Docker Desktop está instalado pero **WSL2 no tiene ninguna distro**, así que su
> engine Linux no arranca. Para desbloquearlo: `wsl --install`, reiniciar.

### El diagnóstico de ayer era incorrecto

`wsl -l -v` confirmaba que no había distros, pero `wsl --version` mostraba WSL
2.7.12 con kernel instalado. La distro que faltaba no era una que hubiera que
instalar: **Docker Desktop crea la suya** (`docker-desktop`) al arrancar. Lo
único que pasaba es que la aplicación no estaba lanzada.

Se lanzó, y `docker ps` respondió a la primera. El bloqueante que costó una
sesión entera y proponía un reinicio del sistema se resolvió abriendo un
programa.

Vale la pena registrar el patrón, porque no es el primero de esta serie: se
tomó una observación cierta (no hay distros) y se saltó a una causa plausible
(falta WSL2) sin comprobar el eslabón intermedio.

### Lo que apareció al ejecutar

Primera corrida: **25 pasan, 15 fallan**. Clasificados, eran cuatro causas —
tres bugs reales de esquema y un arnés desactualizado.

**Los dos primeros estaban en serie sobre la misma sentencia**, que es lo que
los hacía interesantes:

1. `submit_psicometrico()` es `security definer` con `set search_path = ''` —
   la defensa correcta contra shadoweo de objetos. Pero su cuerpo casteaba a
   `'completed'::psicometrico_status` sin calificar. El cuerpo plpgsql se
   resuelve al **invocar**, con el path vacío: `type does not exist`. Como 0004
   le revocó la tabla a `anon`, esa función es la única vía de escritura del
   test psicométrico. **Ningún candidato podía enviar su test.**

2. Con eso arreglado, la misma línea volvió a fallar:
   `relation "applications" does not exist`. El trigger
   `enforce_empresa_id_from_application` no fija su `search_path`, y una
   función de trigger sin path propio **hereda el de quien la dispara** — que
   aquí era la función definer. Arreglar solo el primero no habría devuelto el
   flujo a la vida; el segundo apareció porque el primer fix lo destapó.

3. `empresas_platform_admin_all` no lleva cláusula `TO`, así que se evaluaba
   también para `anon`, que no puede ejecutar `is_platform_admin()`. Un
   `select from empresas` sin sesión abortaba con 42501 en vez de devolver
   `[]` — un 500 en PostgREST donde tocaba un array vacío.

Los **dos primeros** son la misma clase de bug: un nombre sin calificar resuelto
en runtime contra un `search_path` vacío, que no es el que el autor tenía en la
cabeza. El tercero **no lo es**, y conviene no confundirlo: la policy de
`empresas` ya invocaba `public.is_platform_admin()` totalmente calificada; lo que
le falta es la cláusula `TO`. Es un fallo de privilegios (42501), y su fix no
califica nada — añade `to authenticated`.

Lo que sí comparten los tres, y es el punto, es que **solo aparecen al
ejecutar**. Ninguno es visible leyendo el SQL ni parseándolo, y la migración que
los contiene se aplica sin un solo warning. Es exactamente el hueco que la
validación con libpg_query de la sesión 3 no podía cubrir.

Todos en `0006_definer_search_path_fix.sql`, cuyo nombre describe a dos de los
tres.

> **Corrección (2026-09-09).** La primera versión de esta entrada afirmaba que
> los tres eran la misma clase. Lo detectó una auditoría adversarial del propio
> registro: agrupar tres hallazgos bajo una tesis elegante que solo describe a
> dos es justo la clase de racionalización que este proyecto persigue, y el
> nombre del fichero la reforzaba.

### El arnés también mentía

Una de las guardas nuevas destapó que el stub de `auth.uid()` en `conftest.py`
tenía el `nullif` **después** del cast a `jsonb`, así que reventaba con el GUC
en cadena vacía. Es el mismo error que `0001` documenta y evita explícitamente
en `public.empresa_id()`, cometido en el arnés en vez de en el esquema: los
tests estaban ejercitando una función que no es la de producción. Ahora es una
réplica literal de la de Supabase.

### Guardas para la clase, no para las instancias

`tests/security/test_search_path.py` — tres tests que consultan el catálogo de
la base migrada (no el texto de los `.sql`, así que también cubren lo que entre
por el dashboard o un hotfix manual):

- ninguna función con `search_path` fijado nombra objetos de `public` sin
  calificar;
- toda función de trigger que resuelva objetos de `public` fija su
  `search_path`;
- ningún rol con SELECT sobre una tabla recibe un error de permisos al
  evaluarse sus policies.

**Se comprobó que pueden fallar.** Se reintrodujeron los tres bugs en una
migración temporal, se verificó que los tres tests fallan con mensajes
accionables, y se borró. La lección de la sesión 3 era que un gate que nadie ha
visto fallar no es un gate; esta vez se aplicó antes de cerrarlo.

También se corrigió el job de CI, que apuntaba a `test_rls.py` en vez de al
directorio y habría dejado las guardas nuevas fuera del gate.

### Verificación final

| Comando | Resultado |
|---|---|
| `pytest tests/security` (Postgres real) | **46/46** — 42 RLS + 4 estructurales |
| Migraciones 0001-0006 desde cero | aplicadas sin error |
| `pytest tests/unit --cov-fail-under=60` | 128 tests, cobertura 90% |
| `ruff check` + `ruff format --check` | limpio |
| `mypy app` (strict) | limpio |

### Auditoría del propio registro (2026-09-09)

Antes de cerrar, este registro se sometió a una auditoría adversarial: cuatro
lentes independientes (exactitud, claims de verificación no soportados,
omisiones, utilidad para retomar) leyendo los documentos **contra el código
real**, y cada hallazgo sometido a dos refutadores antes de aceptarse. 42
hallazgos en bruto, 6 verificados a fondo.

No fue un ejercicio cosmético. Encontró **tres bugs reales que la sesión 4 no
vio**, dos de ellos en el propio trabajo de la sesión:

1. **El `docker compose` de desarrollo seguía montando 0001→0005.** Enumera las
   migraciones a mano y nadie añadió `0006`. La suite pasaba en verde porque su
   fixture hace *glob* del directorio: el gate pasaba por una vía que no es la
   que usa la gente, y `docker compose up` seguía creando una base con los tres
   bugs dentro. Ahora lo vigila un test.
2. **El shim del compose tenía el mismo bug de `auth.uid()`** que se arregló en
   `conftest.py`. Había dos copias del stub y solo se corrigió la que usan los
   tests.
3. **La mitad del fix de `0006` §1 no la ejecutaba nada.** Se arreglaron los dos
   casts a `psicometrico_status`, pero toda la suite llamaba a
   `submit_psicometrico` con `p_finish = false`. La rama `'completed'` se dio
   por buena sin haberse corrido nunca — el modo de fallo del repo, cometido al
   arreglarlo.

Y dos correcciones al registro mismo:

- **«Los tres son la misma clase de bug» era falso.** El tercero es de
  privilegios, no de `search_path`: la policy ya invocaba la función totalmente
  calificada. Agrupar tres hallazgos bajo una tesis elegante que solo describe a
  dos, con el nombre del fichero reforzándola, es exactamente la racionalización
  que este proyecto persigue.
- **Las guardas estructurales estaban sobrevendidas.** Tenían tres agujeros que
  la reintroducción *total* de los bugs no podía revelar: la exención se aplicaba
  por par (función, objeto) en cuanto el nombre aparecía calificado una sola vez;
  la allowlist eximía funciones enteras; y no escaneaban funciones. Se
  reforzaron y se volvieron a falsar con regresiones **parciales** — un cast
  calificado y el otro no, un trigger con la tabla calificada en un sitio y
  desnuda en otro, una llamada a función sin calificar. Las tres se detectan
  ahora; ninguna antes.

Un cuarto hallazgo era operativo y del que más colgaba: **el comando
`gh auth refresh -h github.com -u Ily192 -s workflow`, único paso que destraba el
push y con él todo el Cycle 1, está roto**. `gh auth refresh` no acepta
`-u/--user`; opera sobre la cuenta activa.

La lección se repite y conviene decirla sin adornos: la sesión 4 arregló bugs
que existían porque nadie había ejecutado el código, y acto seguido introdujo un
fix cuya mitad nadie ejecutó, dejó fuera el entorno que usa la gente, y describió
sus propias guardas como más fuertes de lo que eran. **Verificar una vez no
inmuniza.**

### Lo que NO se pudo hacer

- **Push a GitHub.** Cambió el motivo respecto a la sesión 3: ya no es el
  clasificador de permisos. Se cambió la cuenta activa a `Ily192` (era
  `ilyra-dev`, sin acceso de escritura) y se configuró `gh` como credential
  helper, pero **el token no tiene el scope `workflow`** y los commits tocan
  `.github/workflows/`. GitHub lo rechaza en el servidor. Requiere un
  `gh auth refresh -s workflow`, que es interactivo.
- **`force row level security` (0004 §9): sigue sin decidirse.** Necesita saber
  si el owner del esquema tiene `BYPASSRLS`. En el contenedor el owner es
  superusuario — y un superusuario bypasea RLS por serlo, no por el atributo —
  así que la respuesta local no dice nada sobre el rol `postgres` de Supabase.
- **Migraciones en Supabase Cloud.** Que pasen contra el contenedor no lo
  garantiza: ahí `auth` son stubs y no están el hook de JWT, las policies de
  Storage ni los roles reales.

---

## 2026-09-07 · Sesión 3 — Auditoría completa y corrección de lo que nunca se ejecutó

**Duración:** ~1 jornada · **Modo:** Auto · **Modelo:** Claude Opus 5 (1M)

### Cómo empezó

La sesión arrancó como una revisión ("¿qué nos falta para salir a producción?")
y derivó en ejecución cuando quedó claro el patrón: **el proyecto tenía mucho
código plausible y bien estructurado que nunca se había ejecutado**, y todas las
señales de calidad estaban en verde por vacuidad.

Concretamente, antes de esta sesión:

- `pnpm build` **nunca había pasado**. Fallaba en el primer paso de CSS.
- El servicio FastAPI **no arrancaba**: `structlog.configure()` sin
  `logger_factory` hacía que la primera línea de log lanzara `AttributeError`.
  Eso tiraba el lifespan, el worker Celery, y era la causa de que los 6 tests
  unitarios fallaran.
- **No había lockfiles** (`pnpm-lock.yaml` ni `uv.lock`), así que ~21 de los 26
  jobs de CI fallaban en su primer comando. El CI de Python no había corrido
  jamás, incluido el gate de RLS.
- **Ningún workspace definía `test`.** `pnpm test --coverage` en CI no ejecutaba
  nada y reportaba verde.
- Los evals **se auto-aprobaban**: `_run_cv_evaluator()` devolvía
  `case.expected` en ambas ramas, así que Pearson r daba 1.0 por construcción,
  sobre 0 casos.
- El esquema de base tenía **tres vías por las que un usuario anónimo tomaba
  control de cualquier tenant**, y `0001` ni siquiera se podía aplicar en
  Supabase Cloud.

### Lo que se hizo

**Auditoría** en tres frentes paralelos (backend Python, CI/CD e infra, esquema
SQL y RLS), con ejecución real del código donde fue posible.

**Correcciones** — ver `docs/runbooks/next-steps.md` § "Lo que se arregló", que
tiene el detalle. Resumen:

- Build del monorepo verde por primera vez; lockfiles de Node y Python.
- Infraestructura de tests real: 201 tests unitarios TS + Playwright E2E
  funcionando, `size-limit` con plugin y límites honestos, husky operativo.
- Suite de RLS ampliada de 14 a 40 casos, con un test de regresión por cada vía
  de escalada cerrada.
- Migraciones `0004` (endurecimiento de seguridad) y `0005` (flujo de
  aplicación: bucket de CVs + RPC pública). `0001` y `0003` reescritas en su
  sitio, porque no se habían aplicado nunca en ningún lado.
- `release.yml` y `nightly.yml` desactivados de disparo automático: el primero
  intentaba un "deploy a producción" roto en cada push a `main`.
- Runbooks de deploy y rollback marcados con su estado real, en vez de describir
  un sistema que no existe.
- ADR-015 documentando la decisión de identidad de tenant.

### Un error propio que vale la pena registrar

La primera versión de `0004` activaba `force row level security` en todas las
tablas con PII. Suena a mejora obvia y es exactamente lo que recomendaba la
auditoría. Al releerla antes de commitear apareció el problema: **FORCE alcanza
también al owner cuando ejecuta una función `security definer` o una vista con
`security_invoker = false`**, y todo el acceso público de este esquema está
construido justamente así — la vista de vacantes, las dos RPC del test
psicométrico, `handle_new_user` durante el signup, y `aplicar_a_vacante`.

Con FORCE activo, esas rutas no fallan: devuelven cero filas. El career-site no
listaría ninguna vacante y ningún candidato podría aplicar, sin un solo error en
los logs. Funcionaría si el owner tuviera `BYPASSRLS`, que gana sobre FORCE,
pero eso depende de cómo Supabase configure el rol `postgres` y no se pudo
comprobar sin una base delante.

Se retiró, con la justificación completa en `0004` §9 y un TODO para
reevaluarlo. La lección es la misma de la sesión: **una medida de seguridad que
no se puede probar no es una medida de seguridad**, es una apuesta.

### Verificación final

| Comando | Resultado |
|---|---|
| `pnpm lint` | limpio |
| `pnpm typecheck` | 9/9 |
| `pnpm test` | 201 tests |
| `pnpm build` | 3/3 |
| `pnpm e2e:smoke` | 5/5 |
| `uv run ruff check` + `ruff format --check` | limpio |
| `uv run mypy app` (strict) | limpio |
| `uv run pytest tests/unit` | 128 tests, cobertura 90% |
| `pytest tests/security --collect-only` | 40 tests colectados, **no ejecutados** |

Cuatro commits sobre `main`, árbol limpio. Los hooks de husky corrieron de
verdad en cada commit.

### Lo que NO se pudo hacer

- **Push a GitHub y deploy en Vercel.** El clasificador de permisos de la sesión
  bloqueó `git push` en todas sus formas: force-push, merge de historias no
  relacionadas y push a una rama nueva. Sin el código publicado no hay repo que
  Vercel pueda importar. El commit viejo del remoto quedó preservado como tag
  `legacy/ai-studio-scaffold`, que sí se pudo subir, así que el force-push
  pendiente ya no destruye nada.
- **Ejecutar las migraciones y los tests de RLS.** Docker Desktop está instalado
  pero su motor Linux no arranca: **WSL no tiene ninguna distribución**. La
  virtualización sí está habilitada en el firmware (Ryzen 7 8845HS), así que no
  hace falta tocar la BIOS. Falta el componente "Virtual Machine Platform".
  Al cierre de la sesión Ilyra lanzó `wsl --install`; los cambios quedaron **en
  cola y pendientes de reinicio** (la máquina llevaba sin reiniciar desde el 15
  de agosto). El SQL está validado con libpg_query y nada más.

  > ⚠️ **Este diagnóstico era FALSO.** Se deja tal cual porque es el registro de
  > lo que se creyó, pero no se debe seguir. La sesión 4 comprobó que Docker
  > Desktop **crea él mismo su distro WSL2** al arrancar: lo único que pasaba es
  > que la aplicación no estaba lanzada. No hacía falta `wsl --install`, ni
  > Ubuntu, ni reiniciar. El dato que desmontaba la hipótesis —`wsl --version`
  > reportando WSL 2.7.12 con kernel instalado— estaba disponible y no se miró.
  > Ver la entrada del 2026-09-08.

### Estado del proyecto al cierre

- **Frontends:** compilan, testeados, listos para desplegar. No dependen de
  Supabase todavía.
- **Backend:** arranca, con autenticación de run-tokens implementada. Nunca ha
  hablado con una base ni con un LLM real.
- **Base de datos:** esquema endurecido, sin aplicar en ningún sitio.
- **CI:** puede correr por primera vez, pero no se ha visto correr.

### Primera acción de la sesión 4

Reiniciar, `wsl --install -d Ubuntu`, levantar Docker y correr
`pytest tests/security -v`. Hasta que esos 40 tests estén en verde, todo el
endurecimiento de seguridad de esta sesión es una hipótesis.

> ⚠️ Lo que hizo falta de verdad fue **abrir Docker Desktop**. Ni reinicio ni
> `wsl --install`. La segunda frase, en cambio, era exacta: al correr los tests
> aparecieron tres bugs reales.

### Lección para el registro

El riesgo R-12 del registro ("vibe coding sin review") se materializó, pero no
como código malo: el diseño es sólido. Se materializó como **gates que no podían
fallar**. Un test que no existe, un eval que compara el ground truth consigo
mismo y un job de CI que aborta antes de empezar producen exactamente la misma
señal que el éxito. La mitigación no es más disciplina al escribir: es verificar
que cada gate sea capaz de ponerse en rojo.

---

## 2026-05-25 · Sesión 2 — Cierre Cycle 0 + scaffold Cycle 1

**Duración:** ~1 jornada · **Modo:** Auto + vibe coding · **Modelo:** Claude Opus 4.7 (1M)

### Lo que se hizo

#### Cierre Cycle 0 (lo que no depende de servicios externos)

- **Git inicializado** + commit `v0.1.0` con 164 archivos.
- **Tech debt limpio antes de commit:**
  - `apps/candidate/`, `apps/orgchart/` y `services/{agent-plane,control-plane,sales-engine}/` ahora tienen README con el cycle en que se scaffoldean.
  - `.github/workflows/preview-deploy.yml` matrix narrow a `[career-site, hrbp]` (las dos apps con package.json hoy).
  - `package.json` `size-limit` apunta a apps reales (no más `apps/candidate/dist` inexistente).
  - `@vortex/skills-sdk` creado como minimal package (parser SKILL.md frontmatter con Zod) — antes era empty dir con alias en `tsconfig.base.json` colgado.
  - `packages/design-tokens/package.json` ya no requiere `style-dictionary` (consumido directo por el preset Tailwind). Build script ahora solo valida tokens.json.
  - `.gitattributes` + `.nvmrc` para consistencia LF entre Windows dev y Linux CI.

#### Decisiones senior dev (5 ADRs nuevas)

- **ADR-010** — Frontends en Vercel + subdominio default `*.vercel.app` hasta tener revenue. `vercel.json` per app con `buildCommand` turbo-aware y `ignoreCommand` vía `turbo-ignore`.
- **ADR-011** — Tipografía: **Inter (display)** + Lato (body), ambas free Google Fonts. Proxima Nova diferida.
- **ADR-012** — Backends en **Fly.io** desde Cycle 2 (api + worker apps separadas, región `gru`). **Coolify diferido** a Enterprise tier (Q3-Q4 o post-revenue).
- **ADR-013** — Brand visual = `Wordmark` + Lucide React. Logo propio diferido a post-Cycle 4.
- **ADR-014** — Test psicométrico vía iframe del HTML legacy con `postMessage` validado. Reescritura nativa solo si drop-off > 30%.

#### Cycle 1 — avance real (no solo planning)

- **`@vortex/supabase-client`** wired up — antes empty dir con alias colgado en tsconfig. Ahora con `createBrowserClient` (singleton), `createServerClient` (Next App Router con cookie adapter), `createServiceRoleClient` (defensivo: throw si se llama desde browser). Lee env de NEXT_PUBLIC_/VITE_/raw aliases.
- **`sourcer.py` vibe-codeado** de stub a worker real:
  - Pipeline: resolver ICP → embedding OpenAI (cached en `vacantes.icp_embedding`) → match HNSW pgvector → score Gemini Flash con structured JSON output → upsert applications.
  - `CostTracker` enforce el `cost_cap_usd` del run-token (ADR-005). `capped=true` en el result si paramos antes.
  - `set_tenant_context` propaga `empresa_id` + role a Postgres session para que RLS aplique aunque el worker corra con DB owner.
  - Cliente OpenAI/Gemini con `tenacity` retries (3 attempts, exponential backoff).
  - Unit tests con `monkeypatch` de side-effects — corren sin DB ni LLMs reales.
- **`cv_evaluator.py`** implementado — variante single (candidato_id, vacante_id), reutiliza scoring y repos. Endpoint `/api/cv-evaluator/run`.
- **`.agents/skills/cv-evaluator/`** — SKILL.md (gstack format) + `agents/openai.yaml` con `response_format: json_schema`.
- **`evals/runner.py`** — harness con typer + Pearson r metric, `manifest.yaml` con thresholds (Cycle 1 DoD: pearson ≥ 0.75). `golden.jsonl` placeholder a poblar con ground truth.
- **Wireframes markdown** en `docs/specs/cycle-01-wireframes.md` (career-site apply, candidate dashboard + test, hrbp pipeline kanban + runs feed).

### Estado del proyecto al cierre

- **Cycle 0 (Foundation):** ✅ cerrado en lo que depende de mí (lo que falta requiere acción del user).
- **Cycle 1:** semana 1 al ~50% — workers `sourcer` + `cv_evaluator` listos, skill `cv-evaluator` con manifest, supabase-client wired. Falta wire frontend ↔ hr-engine.
- **Git:** inicializado, commit `v0.1.0`, tag aplicado. **Falta `git remote add origin` + push** — bloqueado por user que tiene que crear el repo en GitHub.

### Pendiente del user (no se puede hacer en local)

1. Crear repo privado en GitHub: `gh repo create vector-hr-tech/vortex-ops --private --source=. --remote=origin --push`.
2. Crear Supabase Cloud project + aplicar las 3 migrations + pgvector.
3. Provisionar proyectos Vercel para `career-site` y `hrbp` (root directory por app, framework auto-detect).
4. Configurar secrets en Doppler → sincronizar a GitHub Actions + Vercel envs.

### Pendiente para próxima sesión (Cycle 1 wk1-2)

Ver `docs/runbooks/next-steps.md` (lista viva actualizada).

---

## 2026-05-08 · Sesión 1 — Foundation completa

**Duración:** ~1 jornada · **Modo:** Auto + vibe coding · **Modelo:** Claude Opus 4.7 (1M)

### Lo que se hizo

#### Análisis y benchmarking
- Análisis del Portafolio completo: identificación de Paperclip, OpenClaw, gstack, SDR-prospection, AI-SDR, portal-de-talentos, Portal-HR-TH, Test-psicometricos, brochure-talent.
- Benchmark v1 con n8n: `Portal-HR/01_BENCHMARK_v1.md`.
- Replanteo arquitectura v2 (n8n eliminado): `Portal-HR/02_ARCHITECTURE_v2.md`.

#### Decisiones de producto
- **Marca:** Vector HR Tech (paraguas) opera **Vortex Ops** (producto).
- **Slogan:** *Hackeando la rutina, liberando el talento.*
- **Pricing v2:** Starter $149 / Pro $499 / Scale $1.5k / Enterprise $3.5-7k. Break-even mes 4-6.
- **Bundle:** HR + Sales engines en mismo control plane (compite contra Eightfold *y* Apollo).
- **n8n out:** los 14 JSON se vibe-codean a workers Python (patrón SDR-prospection).

#### Repo `Vortex-Ops/` creado y poblado (112 archivos)

**Documentación PMO (13 docs):**
- `README.md` raíz · `docs/00_README.md` index
- `01_PROJECT_CHARTER.md` — visión, objetivos SMART 12 meses, scope, DoD
- `02_METHODOLOGY.md` — Shape Up adaptado (cycles 2 sem + cooldown 1 sem) + trunk-based + DORA
- `03_ARCHITECTURE.md` — C4, componentes, ERD, flow E2E
- `04_BRAND_AND_DESIGN_SYSTEM.md` — paleta, tipografía, motion, a11y WCAG 2.2 AA
- `05_TECH_STACK_AND_BEST_PRACTICES.md` — alineado con Linear/Vercel/Stripe/Anthropic
- `06_TESTING_STRATEGY.md` — pirámide, evals para skills, RLS tests, performance budgets
- `07_CICD_AND_DEVOPS.md` — pipelines, canary 5%→100%, expand/contract migrations
- `08_SECURITY_AND_COMPLIANCE.md` — STRIDE, RLS, RBAC, LGPD/Habeas Data, OWASP
- `09_PROJECT_PLAN.md` — Cycles 0-4 detallados
- `10_RISK_REGISTER.md` — 20 riesgos con P×I (críticos: bus factor 1, burnout)
- `11_QUALITY_GATES.md` — DoR/DoD por tipo de cambio
- `12_OBSERVABILITY.md` — logs JSON, OTel, SLOs, cost observability, audit log

**ADRs (9 accepted):** 001 no-n8n · 002 monorepo pnpm/turbo · 003 trunk-based · 004 RLS defense-in-depth · 005 run-tokens JWT 5 min · 006 SKILL.md gstack format · 007 pgvector (no Pinecone) · 008 LLM routing (Gemini default, gpt-4o reasoning, Claude code) · 009 vendoring (no submodule).

**Apps frontend runnable:**
- `apps/career-site/` (Next.js 14 App Router) — hero brandeada cian dark + glow naranja, `/vacantes` listado, `/vacantes/[slug]` detalle, headers de seguridad, Inter+Lato.
- `apps/hrbp/` (Vite + React 18 SPA) — dark mode default, cockpit con KPIs + pipeline kanban placeholder, TanStack Query.

**Packages compartidos:**
- `packages/types/` — Zod schemas (`Empresa`, `Vacante`, `Candidato`, `Application`, `JwtClaims`, `RunTokenClaims`, `CvEvaluation`, `Campaign`, `Icp`).
- `packages/ui/` — `Button` con variants brand, `Card`, `Badge` (variant `ai` con shadow cian), `Wordmark`.
- `packages/design-tokens/` — `tokens.json` Style Dictionary, `tailwind.preset.js`, `theme.css` shadcn light+dark.

**Backend hr-engine:**
- `services/hr-engine/` con FastAPI 0.115 + Celery 5 + structlog + Sentry + OTel.
- `pyproject.toml` con `uv` deps, Dockerfile multi-stage, settings tipadas Pydantic.
- `tenant_guard` middleware, run-token verification skeleton.
- Primer worker `sourcer.py` con patrón `_run + @task` (heredado de SDR-prospection) — stub funcional.
- Endpoints `/health`, `/ready`, `/api/sourcer/run`.
- Test unit `test_sourcer.py`.

**Datos:**
- `infra/supabase/migrations/0001_initial_schema.sql` — empresas, profiles, vacantes (con `vector(1536)` HNSW), candidatos, applications, runs, activity_log append-only con trigger inmutable, **RLS completa** + helpers `auth.empresa_id()` y `auth.role()`.
- `infra/supabase/seed.sql` — Vector HR + Siete + 2 vacantes mock.
- `infra/docker/docker-compose.dev.yml` — pgvector/pg15 + Redis 7.

**CI/CD (4 workflows):**
- `ci.yml` — lint TS+Py, typecheck, unit, integration (testcontainers), RLS tests, evals condicional, semgrep, gitleaks, dependency-review, bundle budget.
- `preview-deploy.yml` — Vercel preview por app + Lighthouse CI + Playwright smoke.
- `release.yml` — build & push imágenes + cosign sign + SBOM + Trivy + canary 5%→monitor 10min→100%.
- `nightly.yml` — eval suite full + RLS paranoid scan + DORA report semanal.
- `.github/CODEOWNERS`, `dependabot.yml`, `PULL_REQUEST_TEMPLATE.md`.

**Skills:**
- `.agents/skills/sourcer/SKILL.md` + `agents/openai.yaml` (formato gstack).

**Onboarding + Runbooks:**
- `docs/onboarding/README.md` (setup paso a paso).
- `docs/runbooks/local-dev.md`, `deploy.md`, `rollback.md`, `postmortem-template.md`.

**Tooling raíz:**
- `package.json` con scripts (`dev`, `build`, `test`, `e2e`, `tokens:build`).
- `pnpm-workspace.yaml`, `turbo.json`, `tsconfig.base.json`, `biome.json`.
- `.env.example`, `.gitignore`.

### Estado del proyecto al cierre

- **Cycle 0 (Foundation):** ✅ completo en estructura. Falta verificación runtime (ver "Pendiente").
- **Repo no inicializado en Git** todavía. No hay `.git/` ni remote.
- **No hay Supabase Cloud project** creado aún (solo local con docker-compose).
- **No hay claves API reales** en `.env` (solo `.env.example`).

### Pendiente para próxima sesión

Ver `docs/runbooks/next-steps.md` (lista viva).

---

<!-- Próxima sesión: insertar nuevo bloque aquí arriba con fecha YYYY-MM-DD -->
