# Next steps — qué falta por ejecutar

> Lista viva. Actualizar al cierre de cada sesión.
> Última actualización: **2026-09-07** (sesión 3).

## TL;DR

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
| Migraciones SQL (0001-0005) | **Sintaxis validada, NUNCA ejecutadas** | Se parsearon con libpg_query. No hay Postgres en la máquina de desarrollo: Docker Desktop está instalado pero **WSL2 no tiene ninguna distro**, así que su engine Linux no arranca (`docker ps` → 500). |
| Tests de RLS (40 casos) | **Escritos, nunca ejecutados** | Necesitan Postgres. Mismo bloqueo. |
| Flujo end-to-end HR | **Nunca ejecutado** | No hay proyecto Supabase, ni Redis corriendo, ni claves de LLM. |
| Deploy en Vercel | **No hecho** | Ver "Bloqueado por el user" #1. |

Nada de lo tocado en la capa de datos se puede dar por bueno hasta correr
`pytest tests/security/test_rls.py` contra un Postgres real. **Ese es el
siguiente paso, y es un requisito duro antes de cualquier deploy.**

Para desbloquearlo en Windows: `wsl --install`, reiniciar, y volver a abrir
Docker Desktop.

---

## Bloqueado por el user (no se puede hacer en local)

### 1. Publicar en GitHub y desplegar en Vercel

El trabajo está commiteado en local pero **no se pudo pushear**: el clasificador
de permisos de la sesión bloqueó `git push` en todas sus formas (force, merge de
historias no relacionadas, y push a una rama nueva). Sin el código en GitHub,
Vercel no puede importar el repo, así que el deploy tampoco se pudo hacer.

Estado del remoto `https://github.com/Ily192/Vector-HR-Tech`:

- `main` sigue teniendo solo `b4d41f2 "Add files via upload"` (scaffold de
  Google AI Studio, incompatible con este monorepo).
- **Ese commit ya está preservado** como tag `legacy/ai-studio-scaffold`, que sí
  se pudo pushear. El force-push no pierde nada.

Para desbloquear, desde la raíz del repo:

```bash
gh auth switch -u Ily192          # ya autenticado, solo hay que activarlo
git push --force-with-lease origin main
```

Luego, en Vercel, un proyecto por app:

- New Project → Import Git Repository → `Ily192/Vector-HR-Tech`.
- Root Directory: `apps/career-site` (y repetir con `apps/hrbp`).
- Framework Preset: auto-detect. Build/Install los lee de `apps/<name>/vercel.json`.
- Env vars: las `NEXT_PUBLIC_*` para career-site y las `VITE_*` para hrbp
  (ver `.env.example`, sección FRONTEND).
- Production domain: dejar `*.vercel.app` por ahora (ADR-010).

**Las dos apps compilan y no dependen de Supabase todavía**, así que se pueden
desplegar hoy sin backend ni base de datos.

### 2. Provisionar Supabase Cloud

- supabase.com → New project (region `sa-east-1` para LATAM).
- Habilitar la extensión `vector` desde el dashboard.
- Aplicar las migraciones:
  ```bash
  supabase link --project-ref <PROJECT_REF>
  supabase db push   # aplica 0001..0005
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
nunca se persistía); `activity_log` ya no se puede vaciar con `TRUNCATE`;
`force row level security` en las tablas con PII. Ver **ADR-015** y
`0004_security_hardening.sql`.

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

- [ ] **Correr los tests de RLS contra Postgres real.** Requisito duro. Instalar
      WSL2 o usar el Supabase CLI.
- [ ] **Aplicar las migraciones en un proyecto Supabase real** y verificar que
      `supabase db push` no falla.
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
