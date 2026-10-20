# ADR-019: El plan gratis no usa IA: descarga en .zip y una coincidencia de skills como gancho

- **Status:** Accepted
- **Date:** 2026-10-19
- **Decider:** Ilyra ("no me gusta la decisión de evaluar CVs para empresas en la etapa gratis: solo debería dejar descargar en un .zip los que se postularon, y con algún script sin IA evaluar el match de los CVs, pero solo como enganche para la adquisición de la plataforma")
- **Supersedes:** ADR-018, salvo §10, §11, §12 y §14 (abajo)
- **Tags:** producto, negocio, plan-gratis, privacidad

## Context

ADR-018 hacía que las aplicaciones de las empresas gratuitas se evaluaran con IA a ciegas, con topes de gasto y como instrucción de la empresa. Ilyra lo descartó: el plan gratis debe recibir aplicaciones y dejarlas descargar, y el gancho hacia el plan de pago tiene que salir de un script sin IA.

Nada de ADR-018 llegó a producción: Supabase Cloud no está provisionado y el worker de preselección no se escribió. Solo existían la migración 0009 y su dominio.

Ilyra pidió además seguir revisando los huecos de lógica para que la frontera entre lo gratis y lo de pago quede bien delimitada. La revisión del código encontró cinco:

1. **El hr-engine no miraba el plan.** Un run-token válido de una empresa gratuita encolaba evaluaciones con LLM. Bastaba con un error de configuración en Paperclip o una empresa que dejó de pagar con runs programados.
2. **El tope de 50 aplicaciones solo vivía en `aplicar_a_vacante()`.**
   - La empresa podía insertar aplicaciones con su sesión, sin tope.
   - Borrar aplicaciones liberaba cupo: bajar el .zip, borrar las 50 y recibir otras 50.
3. **El cockpit se podía usar por la API.** El panel esconde entrevistas, psicométricos y constancias al plan gratis, pero la base los aceptaba.
4. **El límite de vacantes activas no limitaba el uso.** Cerrar una vacante y publicar otra daba un plan gratis sin fin, de 3 en 3.
5. **La empresa podía retirar la oposición de un candidato** (`applications.sin_ia`) con un simple `update`.

También apareció un bug: `mi_cupo_de_vacantes()` (0008) le decía "0 libres" al plan con IA, porque `greatest(0, null)` es 0 en PostgreSQL.

## Decision

### 1. La IA es lo que se paga

Para una empresa gratuita no corre ningún agente ni se llama a ningún LLM: ni evaluación, ni búsqueda de perfiles, ni preselección.

- **Dónde se aplica:**
  - el hr-engine responde 403 a todo run de un plan sin IA, antes de crear la fila en `runs` o encolar (`domain/plan.py::verificar_ia`);
  - el contrato `limites-plan.json` lleva `incluye_ia` y lo prueban Python, SQL y TypeScript.
- **Por qué:**
  - el costo variable del plan gratis baja a casi cero, sin topes que vigilar;
  - no hay subencargado de IA ni decisiones automatizadas sobre los candidatos de quien no contrató la IA;
  - la frontera se explica en una frase.

### 2. Qué incluye cada plan

| | Gratis (career site) | Con IA (de pago) |
|---|---|---|
| Vacantes activas | 3 hasta 50 personas, 4 desde 51; Vector HR puede ajustarlo | Sin tope |
| Publicaciones nuevas | Tantas como vacantes activas cada 30 días; reabrir no cuenta | Sin tope |
| Aplicaciones por vacante | 50 recibidas, entren por donde entren. Borrar o descartar no libera cupo | Sin tope |
| Candidatos | Lista de aplicados y **descarga de todos los CVs en un .zip** | Igual |
| Pipeline | Aplicados, y cerrar: contratado, descartado o retirado | Todas las etapas |
| Gancho | Coincidencia de skills **sin IA**, solo en agregado (punto 3) | La evaluación con IA lo reemplaza |
| IA | Nada | Evaluación a ciegas con su porqué, búsqueda de perfiles, agentes |
| Cockpit | No: ni entrevistas, ni psicométricos, ni constancias | Sí |

La base aplica cada fila (PT409 y PT403, que PostgREST devuelve como 409 y 403) y el hr-engine aplica la de IA.

### 3. El gancho: una coincidencia de skills, sin IA

- **Qué compara.** Las skills que pide la vacante, que la empresa escribe al crearla (hasta 15, en `vacantes.skills`), contra el texto del CV.
- **Cómo compara** (`domain/coincidencia.py`): un Ctrl+F que no se tropieza.
  - Ignora mayúsculas y acentos.
  - Busca frases completas: "Java" no aparece dentro de "JavaScript".
  - Admite el plural de la skill.
  - Reconoce variantes de escritura y traducciones directas ("Node.js" y "NodeJS", "Inglés" y "English").
  - Nunca cuenta lo que una skill "implica": quien sabe PostgreSQL sabe SQL, pero si el CV no dice SQL, no lo menciona.
  - Las skills de una o dos letras ("Go", "R", "QA") respetan mayúsculas.
- **Qué ve la empresa:** solo el resumen, por lotes de 5 (`resumen_del_gancho()`). Por ejemplo: "Revisamos 45 de tus CVs contra las 4 skills de la vacante: 13 mencionan la mayoría y 6, todas".
  - "La mayoría" es más de la mitad.
  - Los lotes vienen de ADR-018: si el número cambiara con cada aplicación, comparar antes y después diría qué menciona ese CV.
- **Dice "mencionan", nunca "califican".** El gancho cuenta menciones; juzgar la experiencia es la evaluación con IA.
  - Por eso el botón dice "Evaluarlos con IA" y no "Ver quiénes son": el plan de pago no destapa a los 6, evalúa a todos.
  - Prometer otra cosa sería el *bait and switch* que ADR-018 citaba (Classmates).
- **Por qué no se ve candidato por candidato:** filtrar por palabras clave ya es *screening*, que es lo que se paga. A la empresa no se le esconde nada suyo: tiene el .zip y puede leer cada CV.
- **Sin skills no hay gancho.** El panel le pide a la empresa que las agregue.
- **Sin muestra.** La evaluación de muestra con IA de ADR-018 desaparece. Si el CTA necesita enseñar la evaluación de pago, lo hace con un candidato ficticio.

### 4. Dónde se calcula

- **En el hr-engine, con un worker (Celery beat)**, que es el siguiente PR:
  - baja el CV de Storage con la clave secreta;
  - saca el texto (pypdf para PDF; el XML del DOCX; un .doc o un PDF escaneado cuentan como ilegibles);
  - compara y guarda en `privado.coincidencias` las skills mencionadas, junto con las skills de la vacante que usó.
- **Sin LLM:** no deja fila en `runs`, no tiene topes de gasto y no lleva run-token.
- **Si la empresa cambia las skills,** lo calculado deja de contar y se recalcula.
- **Por qué no en el navegador:** la empresa recibiría el resultado de cada CV y el gancho dejaría de serlo.
- **Por qué no en el career site:** la regla tiene una sola dueña (el dominio del hr-engine), y recalcular al cambiar las skills exige volver a leer los CVs.

### 5. Datos y retención

- **Qué se guarda:** solo qué skills de la vacante menciona cada CV. El texto del CV no se guarda.
- **Dónde:** en el esquema `privado`, fuera de la API.
- **Cuándo se borra:**
  - con la aplicación;
  - cuando el candidato se opone (`sin_ia`, que ahora cubre cualquier evaluación automatizada);
  - al pasar al plan con IA;
  - 30 días después de cerrar la vacante (`privado.purgar_coincidencias()`).

### 6. Al contratar no se desbloquea nada

Al pasar de `gratis` a `ia` se borran las coincidencias: el gancho ya cumplió. Las aplicaciones siguen en "Aplicados" y la evaluación con IA corre sobre ellas en el flujo de pago, que se configura en Paperclip al activar la empresa (runbook).

### 7. Los huecos de la frontera, cerrados (migración 0010)

| Hueco | Cómo se cierra |
|---|---|
| El hr-engine corría IA sin mirar el plan | 403 al registrar el run (punto 1) |
| El tope de 50 solo en `aplicar_a_vacante()`, y borrar liberaba cupo | Trigger en `applications` para cualquier vía, con un contador de recibidas en `privado` que solo sube. Es el contador que ADR-017 preveía y que 0008 cambió por un `count(*)` |
| Cockpit usable por la API | Crear entrevistas, psicométricos o constancias exige el plan con IA (PT403). Solo se corta lo nuevo: si una empresa deja de pagar, un candidato a medio test lo puede terminar |
| Cerrar y publicar otra sin fin | En 30 días se publican tantas vacantes nuevas como activas permite el plan. Es el modelo de LinkedIn: "a maximum of 1 free job at a time and a limited number of free jobs in a 30-day window". La fecha de publicación la fija la base |
| La empresa retiraba la oposición del candidato | PT403. Solo la retira Vector HR, a pedido del candidato, y el career site ya la recibe (`aplicar_a_vacante(p_sin_ia)`) |

El cupo que muestra el panel también lo da la base: `mi_cupo_de_vacantes()` informa las publicaciones libres y cuándo se libera la próxima, y `cupos_de_aplicaciones()` da el "47 de 50" de cada vacante (ADR-016).

### 8. Lo que se deja como está, a propósito

- **Altas manuales de candidatos.** La empresa puede agregar un candidato con su sesión, y cuenta para las 50.
- **Usuarios.** No hay tope de usuarios en el gratis. Las consultoras, que son las que traerían clientes como usuarios, no entran al plan gratis (ADR-018 §12).
- **Bajar de plan.**
  - Lo que se creó con IA sigue visible.
  - Se cortan los runs nuevos y lo nuevo del cockpit.
  - Las vacantes por encima del límite siguen abiertas, pero no se publica otra hasta bajar del tope.
  - Una vacante con 50 o más recibidas deja de recibir.

### 9. Lo que sigue vigente de ADR-018

- **§10.** El .zip se arma en el navegador (`createSignedUrls` y `client-zip` con import dinámico).
- **§11.** El plan de las empresas reales: solo Vector HR con `ia` (interna, para demos); el resto `gratis`. Siete dejó de ser piloto el 2026-10-20.
- **§12.** El plan gratis es solo para empleadores directos.
- **§14.** Las señales de venta (PQL). Cambian dos:
  - "pulsar Ver quiénes son" pasa a ser "pulsar Evaluarlos con IA";
  - se suma "agotar las publicaciones de los 30 días".
- **§13.** La unidad de precio aplica tal cual al plan de pago.

## Costo por empresa (skill `costos-de-infraestructura`)

| Concepto | Plan gratis, peor caso al mes | Nota |
|---|---|---|
| LLM | US$0 | La IA es solo de pago |
| Storage de CVs | ~60 MB (4 vacantes × 50 CVs de ~300 kB) | Supabase Pro incluye 100 GB |
| Egress del .zip | ~60 MB por descarga completa | Incluye 250 GB |
| Coincidencia de skills | Milisegundos de CPU por CV en el hr-engine | Sin costo propio: va en la máquina fija de Fly.io (~US$8, ADR-012) |

El costo de una empresa gratuita es casi todo fijo. Lo variable es Storage y egress, que el plan Pro absorbe hasta miles de empresas. El costo que falta medir sigue siendo el de la gente (ADR-018).

## Condiciones antes de producción

Menos que con ADR-018, porque el plan gratis ya no trata datos con IA:

- [ ] **Aviso al candidato** en el formulario del career site. Texto base:
  > [Empresa] (responsable) usa Vortex, de Vector HR Tech (encargado). Vortex compara las palabras de tu CV con las skills de la vacante y le da a [Empresa] solo un conteo de cuántos CVs las mencionan, sin decirle cuáles. No usa IA ni decide nada. Puedes oponerte marcando "Evaluar mi CV sin procesos automatizados". Si [Empresa] contrata los servicios de IA, tu CV se evalúa con IA y una persona decide.
  - Faltan los medios ARCO y los plazos de conservación (MX art. 15).
- [ ] **Términos del plan gratis y contrato de encargo,** con la coincidencia de skills como parte del servicio. En el plan gratis no hay subencargado de IA.
- [ ] **Anti-spam en el formulario** (Cloudflare Turnstile y límite por IP). Con 50 cupos por vacante, el spam es una denegación de servicio para la empresa. 0005 ya lo advertía.
- [ ] Las condiciones de IA de ADR-018 (evaluación de impacto, key de Gemini, revisión humana) pasan al lanzamiento del plan de pago, con su primer cliente.

## Implementación

| PR | Qué |
|---|---|
| #68 | Migración 0010, `domain/coincidencia.py`, `domain/gancho.py`, `verificar_ia` en el hr-engine, contratos, tipos y el gancho del panel con datos de ejemplo |
| #69 | Worker del hr-engine (`CoincidirCvsPendientes`): Storage con la clave secreta, texto con pypdf y del XML del DOCX (defusedxml), Celery beat cada minuto y purga diaria. Marca cada CV como ilegible antes de leerlo, para que un PDF malicioso no bloquee los barridos |
| #73 | Panel conectado a Supabase: entrar con enlace al correo (y la invitación), campo de skills en "Crear empleo", gancho real, cupos de vacantes y de publicaciones, descarga en .zip armada en el navegador y migración 0013, que guarda el interés por la IA ("Evaluarlos con IA", "Quiero saber más") como señal de venta (§14). Aún no se registran "abrir el pipeline 2 o más veces" ni "descargar en bloque" |
| Este | Alta de empresas: `python -m app.cli.alta_empresa` crea la empresa con plan gratis y su invitación de un solo uso, y manda el correo con la API de administración de Auth; si no sale, no queda nada a medias. `--reenviar` para quien no ha entrado |
| Siguiente | Despliegue: Supabase Cloud, Vercel y Fly.io |

## Consequences

**Positivas:**

- **La frontera se dice en una frase:** gratis es publicar, recibir y descargar; la IA es de pago. La base y el hr-engine la sostienen aunque alguien se salte la UI.
- **El plan gratis cuesta casi nada por empresa** y no depende del acceso a Gemini.
- **Menos riesgo legal:** sin IA ni decisiones automatizadas en el gratis, y con datos mínimos.
- **El gancho es verificable.** Cualquiera puede contar las menciones en el .zip, y el texto no promete lo que el plan de pago no da.

**Negativas / trabajo que implica:**

- **Un gancho por menciones convence menos** que uno evaluado con IA. Se compensa con el CTA honesto, la demo con un candidato ficticio y las señales de venta con apoyo de Vector HR.
- **La empresa tiene que escribir las skills:** sin ellas no hay gancho.
- **Publicar cada 30 días** tantas vacantes como activas puede frenar a una pyme que contrata seguido. Es el momento de ofrecerle el plan de pago, y Vector HR puede ajustar el límite por empresa.

**Neutras:**

- 0010 deshace parte de 0009. Ninguna de las dos se aplicó en producción.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Evaluar con IA el plan gratis (ADR-018) | Ilyra la descartó. Además costaba, sumaba un subencargado de IA y obligaba a condiciones legales de IA para usuarios que no pagan |
| Solo el .zip, sin gancho | Se pierde la palanca de adquisición que Ilyra quiere conservar |
| Mostrar la coincidencia candidato por candidato | Regala el *screening*, que es lo que se vende |
| Calcularla en el navegador | La empresa recibiría el resultado de cada CV |
| Calcularla en el career site al aplicar | La regla quedaría fuera del dominio, y cambiar las skills obligaría a releer los CVs igual |
| Conteo de las filas que quedan (0008) | Borrar aplicaciones liberaba cupo |
| Solo límite de vacantes activas | Cerrar y publicar otra daba un plan gratis sin fin |
| Tope de usuarios en el plan gratis | Fricción sin un abuso que lo justifique hoy: las consultoras ya están fuera del gratis |

## Referencias

- [LinkedIn, empleos gratis y promocionados](https://www.linkedin.com/help/linkedin/answer/a519737/differences-between-free-and-promoted-jobs?lang=en), revisado el 2026-10-19:
  - "a maximum of 1 free job at a time and a limited number of free jobs in a 30-day window";
  - el empleo se oculta al llegar a su límite de postulantes.
- PostgreSQL 15:
  - [Overview of Trigger Behavior](https://www.postgresql.org/docs/15/trigger-definition.html) no dice qué trigger AFTER de fila dispara con `ON CONFLICT DO UPDATE`. Que volver a aplicar no ocupe cupo lo comprueba `test_volver_a_aplicar_con_el_cupo_lleno_devuelve_la_misma_aplicacion`, contra Postgres real.
  - [Conditional Expressions](https://www.postgresql.org/docs/15/functions-conditional.html#FUNCTIONS-GREATEST-LEAST): `GREATEST` ignora los NULL y solo devuelve NULL si todos lo son.
- ADR-016 (la lógica vive en el backend), ADR-017 (el career site es el módulo gratuito), ADR-018 (lo que se conserva).
