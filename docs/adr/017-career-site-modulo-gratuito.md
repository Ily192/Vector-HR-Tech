# ADR-017: El career site es el módulo gratuito de Vortex, no un sitio de marketing

- **Status:** Accepted
- **Date:** 2026-10-16
- **Decider:** Ilyra
- **Tags:** producto, career-site, hrbp, multi-tenant

## Context

Hoy el career-site mezcla dos públicos con objetivos distintos:

- **Candidatos**, que buscan una vacante y quieren aplicar.
- **Empresas**, a las que les pide "Agendar demo" y "Hablar con Vector HR" desde
  la cabecera, el hero, el cierre y la página `/contacto`.

El modelo de negocio es otro. Una empresa llega al career site porque se
inscribió desde la web de Vector HR. A cambio de ese registro, publica vacantes
gratis en el career site de Vortex. Pedirle una demo en un sitio al que ya tiene
acceso no tiene sentido. Y a un candidato, ese mensaje no le sirve.

Además, `hrbp` está pensado como el cockpit de un cliente que ya paga los
servicios de IA. No tiene un lugar para la empresa que solo publica.

## Decision

### 1. Una sola app para empresas, organizada en módulos

- **Career site** (gratis) es el **único módulo gratuito**. Incluye:
  - crear empleo;
  - sus vacantes;
  - el pipeline limitado (punto 3);
  - el perfil de empresa.
- **Servicios de IA** (de pago):
  - el pipeline completo;
  - la evaluación a ciegas con sus razonamientos;
  - la búsqueda de perfiles;
  - los agentes;
  - los reportes.

El código vive en `apps/hrbp`, que pasa a ser la app de la empresa. El nombre del
paquete se puede cambiar más adelante.

### 2. Alta por invitación

1. La empresa se inscribe al career site desde la web de Vector HR.
2. Vortex le envía una invitación por correo.
3. La empresa completa la cuenta desde ese enlace.

No hay registro abierto dentro de Vortex: sin invitación válida no se crea
ningún tenant. Ese registro es la contraprestación del plan gratuito.

### 3. Límites del plan gratuito

Los aplica el backend; la UI solo los muestra.

| Límite | Valor | Dónde se aplica |
|---|---|---|
| Vacantes activas | **3 o 4 según el tamaño de la empresa**. Por defecto: 3 hasta 50 personas y 4 desde 51. Vector HR puede ajustarlo por empresa. | `empresas.limite_vacantes`, comprobado al publicar |
| Aplicaciones por vacante | **50** | `aplicar_a_vacante()` |
| Etapas del pipeline | Solo **Aplicados** | RLS y caso de uso del pipeline |

- **Al llegar al límite de vacantes:** para publicar otra, la empresa tiene que
  eliminar una de las activas.
  - "Eliminar" quita la vacante del career site y libera el cupo. Por dentro es
    un borrado lógico (`status = 'closed'` y `deleted_at`), para no perder las
    aplicaciones ni romper la trazabilidad.
  - Los CVs siguen las reglas de retención del aviso de privacidad.
- **Al llegar a 50 aplicaciones:** la vacante deja de aceptar aplicaciones. El
  career site la muestra como "Cupo completo" y no deja aplicar. Ningún
  candidato aplica a una vacante que ya no puede recibirlo.
- **En el pipeline gratuito:**
  - la empresa ve la lista de aplicados;
  - puede **descargar todos los CVs a la vez** (un `.zip`, que según ADR-018 §10
    se arma en el navegador con URLs firmadas de Storage);
  - el resto de etapas se ve, pero cerrado.

### 4. El gancho: el patrón de LinkedIn ("quién vio tu perfil")

- **Qué se evalúa.** Las aplicaciones de las empresas gratuitas **también pasan
  por `cv-evaluator`**.
- **Qué ve la empresa.** El resultado agregado, no quién es quién. Por ejemplo:
  "Evaluamos tus 47 CVs en 38 segundos. 13 candidatos califican para la vacante
  y 6 cumplen todas las skills."
- **El CTA** ("Ver quiénes son") lleva a los servicios de IA.
- **Los números son reales.** Los calcula el backend con las evaluaciones
  guardadas (ADR-016) y la UI no los inventa ni los redondea al alza.
- **Qué se cuenta como "califica" y como "todas las skills".** Califica quien
  tiene un score igual o mayor que `UMBRALES_SIGUIENTE_PASO.psicometrico` (4).
  "Todas las skills" significa sin `gaps` frente a los requisitos de la vacante.
  Si la regla cambia, cambia en el backend.
- **El costo** de evaluar el plan gratuito tiene un tope: 50 aplicaciones × 4
  vacantes por empresa. Se registra en `runs` como cualquier otra evaluación.
- **Privacidad.** El aviso de privacidad que acepta el candidato al aplicar
  tiene que decir que su CV se evalúa con IA, sin usar su nombre, por cuenta de
  la empresa.

> **ADR-018** desarrolla este punto.
> - Cuándo se evalúa: al abrir el pipeline y mientras la empresa esté activa.
> - Topes por empresa y del plan.
> - Resumen por lotes de 5 y una evaluación de muestra a ciegas.
> - Base legal: es una instrucción de la empresa, que puede apagarla.
> - Desbloqueo al contratar.

### 5. El career site público es uno solo

- **Para candidatos** ("Vortex Empleos"): ven **todas** las vacantes publicadas
  por todas las empresas, con filtros, el salario cuando la empresa lo da, y la
  aplicación. No tiene CTAs de venta a empresas. El único enlace para empresas
  es "¿Publicas vacantes? Entra a tu panel".
- **Para cada empresa:** en su panel ve "su" career site, es decir, sus vacantes
  tal como las ven los candidatos. No hay página pública por empresa.

### 6. Dónde se vende

La venta indirecta dentro de Vortex está en dos lugares, los dos ligados a lo
que la empresa está haciendo en ese momento:

1. **El brochure breve en "Crear empleo".** Se puede ocultar y tiene un solo CTA
   ("Quiero saber más"), que avisa al contacto de Vector HR de esa empresa.
2. **El gancho del pipeline** (punto 4).

Además:

- los módulos de pago no aparecen en el menú de una empresa gratuita;
- la venta a empresas que todavía no conocen Vector HR (landing, demo, NOM-035)
  se queda en la web de Vector HR, fuera del career site.

### 7. El backend decide el plan

- El plan de la empresa, sus módulos y sus límites viajan en `app_metadata`,
  igual que el tenant (ADR-015).
- RLS y los casos de uso los respetan.
- La UI solo lee `modulos` y los contadores de la sesión o de la API (ADR-016).

### 8. Capas (Clean Architecture del hr-engine)

| Capa | Qué va | Notas |
|---|---|---|
| **Domain** | `domain/plan.py`: `Plan`, `LimitesDelPlan`, `limite_de_vacantes(tamano)`, `MAX_APLICACIONES_GRATIS = 50` y las etapas visibles por plan. `domain/gancho.py`: `ResumenGancho` y las reglas "califica" y "todas las skills", que reutilizan `siguiente_paso.py` | Puro y con tests. Ningún número del gancho sale de un prompt |
| **Application** | `PublicarVacante` (falla con `LimiteDeVacantesError`), `EliminarVacante`, `ResumenPipelineGratis`, `DescargarCvs`, `InvitarEmpresa` | Probados con adaptadores falsos, como `EvaluateCandidate` |
| **Infrastructure** | Repositorios SQL; adaptador de invitaciones (Supabase Auth admin, solo en servidor); adaptador de Storage (URLs firmadas); el endpoint FastAPI como adaptador de entrada fino | El SDK de Supabase no entra en el dominio |
| **Base de datos** | El tope de 50 se aplica también dentro de `aplicar_a_vacante()`, y el de vacantes con un trigger | Defensa en profundidad (ADR-004): el career-site llama al RPC con la clave anónima, sin pasar por el hr-engine |

Cuando exista `domain/plan.py`, `@vortex/types` espejará los límites (`LIMITES_PLAN_GRATIS`) con un contrato JSON como el de `siguiente-paso.json` (ADR-016). Así la UI muestra "3 de 4" sin decidir nada.

### Implementación

**Límites del plan (2026-10-19, migración 0008):**

- **Dónde se aplican.** El panel escribe sus vacantes con su sesión de Supabase y el career site aplica con la anon key, así que **la base es la que corta**. Lo hace un trigger en `vacantes`, el tope dentro de `aplicar_a_vacante()` y `mi_cupo_de_vacantes()`, que es lo que el panel muestra como "3 de 4".
- **La regla y sus copias.** `domain/plan.py` es la dueña y `@vortex/types/reglas` (`LIMITES_DEL_PLAN`, `limiteDeVacantes`) la espeja. Las tres copias (Python, SQL, TS) se prueban contra `contracts/limites-plan.json`.
- **Error.** Pasarse de un tope lanza SQLSTATE `PT409`, que PostgREST devuelve como 409 Conflict.
- **Sin contador de aplicaciones.** En vez de la columna contador que preveía este ADR, se cuentan las aplicaciones con la fila de la vacante bloqueada (`for update`). Así no hay que mantener el contador sincronizado y dos aplicaciones simultáneas no pasan las dos con el último cupo.
- **Casos de uso.** `PublicarVacante` y `EliminarVacante` no se crearon en el hr-engine: hoy ningún flujo publica a través de él. Se harán si el panel llega a publicar por el API.
- **El plan con IA no tiene topes.** Este ADR solo fija los del gratis. Las empresas que ya existían quedan como `gratis`; el plan con IA se activa a mano cuando hay contrato.

### Referencias oficiales

- Next.js 16.4.1, guía *Data Security → Data Access Layer* (incluida en `node_modules/next/dist/docs/01-app/02-guides/data-security.md`). Base de `apps/career-site/src/lib/`: la capa de datos se ejecuta solo en el servidor (`server-only`) y devuelve DTOs mínimos.
- Supabase, [Custom Access Token Hook](https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook):
  - los datos propios van bajo `app_metadata`;
  - hay que conservar los claims obligatorios;
  - el plan se lee de una tabla con acceso de `supabase_auth_admin`.
- PostgREST, [Errors → Raise errors with HTTP Status Codes](https://docs.postgrest.org/en/stable/references/errors.html): un SQLSTATE `PTxyz` se responde con el estado HTTP `xyz`; `P0001` y los no listados, con 400.
- PostgreSQL, `CREATE VIEW`: quien consulta una vista necesita permiso para ejecutar las funciones que la vista llama. Por eso `anon` tiene EXECUTE sobre `limite_de_aplicaciones()`.
- Supabase, [`createSignedUrls`](https://supabase.com/docs/reference/javascript/storage-from-createsignedurls): firma varias rutas en una llamada y recibe `expiresIn` en segundos. Sirve para la descarga masiva.
- Supabase, [`inviteUserByEmail`](https://supabase.com/docs/reference/javascript/auth-admin-inviteuserbyemail): envía el enlace de invitación.
  - La página de referencia no detalla las opciones (`data`, `redirectTo`) ni qué clave se necesita.
  - Que haga falta la service role y que se ejecute solo en el servidor **no está verificado** en esa página; hay que comprobarlo en la guía de Auth admin antes de implementarlo.

## Consequences

**Positivas:**

- **Un público por página.** El candidato ve vacantes; la empresa, su panel.
- **No canibaliza el producto.** Lo gratuito es el paso anterior (publicar y
  recibir CVs), no una versión recortada de la evaluación.
- **El gancho se apoya en el propio producto.** La empresa ve que ya se
  evaluaron sus CVs y qué encontró la evaluación, sin ver quién es quién.
- **Pasar a pago no exige migrar nada.** Las aplicaciones y las evaluaciones ya
  están dentro de Vortex: contratar los servicios es desbloquear lo que ya
  existe.

**Negativas / trabajo que implica:**

- **Migración:**
  - `empresas.plan`, `empresas.limite_vacantes` y el tamaño de la empresa;
  - `vacantes.deleted_at`;
  - un contador de aplicaciones por vacante;
  - `vacantes_publicas` con el nombre y el slug de la empresa (nunca su
    `empresa_id`) y si el cupo está completo.
- **Hook de ADR-015:** tiene que propagar el plan y los módulos al JWT.
- **Casos de uso nuevos en el hr-engine:**
  - el resumen del pipeline gratuito (los números del gancho);
  - la descarga masiva de CVs.
- **Invitaciones:** un flujo de invitación por correo (tabla de invitaciones con
  token de un solo uso y caducidad) y el formulario de inscripción en la web de
  Vector HR.
- **Costo de LLM:** evaluar el plan gratuito tiene un costo, con tope (punto 4).
- **career-site:**
  - se reescriben la home, `/contacto` y la cabecera;
  - se actualizan los tests que fijan el texto comercial y el smoke E2E.

**Neutras:**

- El dominio y el hosting no cambian.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Mantener el career site como landing de venta con vacantes | Mezcla públicos y contradice el modelo: la empresa ya es cliente gratuito. |
| Prueba gratuita de los servicios de IA en lugar de career site gratis | Regala el producto en vez del paso previo; enseña a usarlo sin pagar. |
| Mostrar los módulos de pago con candado en todo el menú | Más presión comercial en todo el panel. La venta se limita a dos lugares ligados a lo que la empresa está haciendo. |
| Gancho con cifras genéricas ("la IA podría ayudarte") | Sin números de su propia vacante no hay curiosidad. Con números inventados se pierde la confianza. |
| Borrado físico de la vacante al eliminarla | Se pierden aplicaciones y trazabilidad; el borrado lógico libera el cupo igual. |
