# ADR-018: Preseleccionar con IA las aplicaciones del plan gratis, a ciegas, con topes y por instrucción de la empresa

- **Status:** Superseded by ADR-019. Siguen vigentes §10 (el .zip en el navegador), §11 (el plan de las empresas reales), §12 (solo empleadores directos) y §14 (señales de venta)
- **Date:** 2026-10-19
- **Decider:** Ilyra, por delegación ("investiga cuál es la mejor solución a nivel de modelo de negocio a largo plazo, sustentabilidad, rentabilidad y factibilidad, y toma las mejores decisiones")
- **Tags:** producto, negocio, ia, privacidad, plan-gratis

> **ADR-019 reemplaza esta decisión.** Ilyra descartó evaluar con IA el plan gratis: la
> empresa gratuita descarga sus CVs en un .zip, y el gancho es una coincidencia de
> skills sin IA. La migración 0010 deshace lo que 0009 montó para evaluar.

## Context

ADR-017 decidió que las aplicaciones de las empresas gratuitas también pasan por `cv-evaluator` y que la empresa ve el gancho ("Evaluamos tus 47 CVs en 38 s. 13 califican y 6 cumplen todas las skills"). Quedaron abiertas cuatro preguntas:

1. **¿Vale la pena pagar el modelo** por empresas que no pagan, y cómo se acota ese gasto?
2. **¿Quién lanza la evaluación?** ADR-005 solo deja ejecutar engines con un run-token de Paperclip, y una empresa gratuita no tiene presupuesto en Paperclip.
3. **¿Es legal** evaluar con IA los CVs de una empresa que no contrató la IA y enseñarle el resultado solo a medias?
4. **¿Dónde se arma el .zip** de la descarga masiva?

Al revisar el código apareció un quinto problema. El score se guarda en `applications.fit_*`, y la empresa lee esa tabla con su sesión de Supabase. Cualquier evaluación del plan gratis quedaba desbloqueada por la API, sin pasar por la UI.

Hechos de partida (2026-10-19):

- **Supabase Cloud no está provisionado.** No hay empresas reales en producción.
- **El evaluador** usa `gemini-2.5-flash` a 0,30 / 2,50 USD por 1M de tokens.
- **El evaluador lee hoy `headline` y `summary`**, no el CV.

Para decidir se investigaron tres frentes, con fuentes al final:

- negocio (freemium y competidores de HR tech);
- costos (documentación oficial de Gemini y Supabase);
- marco legal en México, Colombia, Brasil, Chile, Perú y Argentina.

Además se aplicaron las skills `pricing-de-ia` y `costos-de-infraestructura`.

## Decision

### 1. Se evalúa de verdad, con el mismo evaluador y el mismo modelo que el plan de pago

- **El costo no es el problema.**
  - Un CV cuesta unos US$0,0025 con 2.5 Flash sin razonamiento (supuesto: ~5.000 tokens de entrada y ~400 de salida).
  - El peor caso del plan gratis (4 vacantes × 50 CVs) son US$0,50 por empresa.
  - El mercado cobra el screening con IA a US$0,10–0,20 por CV (Workable, Breezy, Litespace). Nuestro costo es ~2% de ese precio.
- **Los números tienen que ser los que la empresa verá al pagar.**
  - Al contratar se desbloquean exactamente las evaluaciones que se contaron (punto 8).
  - Un gancho con conteos estimados o con otro modelo es un *bait and switch*. Classmates.com pagó un acuerdo de hasta US$9,5M (2010, luego recortado a US$2,5M) por enganchar con "tus compañeros te buscan".
- **Es lo que hace el mercado.** LinkedIn y Computrabajo ya calculan un puntaje real en sus planes gratis.
- **Hallazgo de esta investigación (PR #66).**
  - 2.5 Flash razona por defecto y ese razonamiento se cobra como salida.
  - El costo registrado lo omitía.
  - Ahora se suma, y el razonamiento se apaga con `SCORING_THINKING_BUDGET=0`.

### 2. Es una instrucción de la empresa, no una finalidad de Vortex

En toda la región, Vortex trata los CVs como **encargado** de la empresa, que es la responsable:

- México: LFPDPPP 2025, art. 2 XII; Reglamento, art. 50.
- Colombia: Ley 1581, art. 3 d.
- Brasil: LGPD, art. 39.
- Chile: Ley 21.719, art. 15 bis.

Si el encargado usa los datos para un fin propio, como vender, pasa a ser responsable sin base legal: MX Reg. 53, BR art. 42 §1 I, CL 15 bis y PE Ley 29733 art. 30. Por eso:

- **La preselección es parte del servicio gratuito** y la empresa la pide para cada vacante: `vacantes.preseleccion_ia` está encendida por defecto y se apaga desde "Crear empleo" (MX Reg. 52 II b).
  - Al apagarla se borra lo evaluado en esa vacante.
  - Los términos del plan gratis y el contrato de encargo la listan como instrucción. El proveedor del LLM figura como subencargado.
- **Sin uso propio de los datos.** Ni entrenamiento, ni marketing, ni analítica entre clientes.
  - Las señales de venta (punto 14) salen del uso del panel, no de los CVs.
  - **Solo el nivel de pago de la API de Gemini.**
    - En el gratuito, Google usa los prompts para mejorar sus productos y pueden leerlos revisores humanos.
    - Sus propios términos piden no enviar ahí datos personales.
    - En el de pago, no los usa para mejorar productos.
    - Fuente: [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms), "Unpaid Services" y "Paid Services".

### 3. Qué ve la empresa gratuita

- **El resumen, por lotes de 5 CVs** (`resumen_del_gancho()`).
  - Si los números cambiaran con cada aplicación, comparar antes y después diría si esa persona califica.
  - Con lotes, lo mínimo que se deduce es un grupo de 5. LinkedIn tampoco muestra *insights* con menos de 3 postulantes.
- **Una evaluación de muestra, a ciegas** (`muestra_del_gancho()`).
  - Se elige al llegar a 10 evaluadas: la 6.ª por score de esas 10.
  - Desde entonces es siempre la misma, aunque se borre.
  - Enseña cómo se evalúa sin regalar a la mejor candidata, que para una pyme con una sola vacante es todo el valor.
  - Es el patrón del mercado: el empleo gratis de LinkedIn incluye "una evaluación de un postulante de mejor encaje", y "quién vio tu perfil" muestra 3 visitantes.
- **Qué significa cada número.**
  - **Califica:** score ≥ 4, el umbral del psicométrico.
  - **Cumple todas las skills:** califica y no tiene gaps.
  - Las dos reglas viven en `domain/gancho.py` y se prueban contra `contracts/gancho.json` en Python y en SQL.
- **Nada que ordene, filtre o descargue según el resultado oculto.** La lista de aplicados y el .zip son iguales con o sin evaluación.

### 4. Cuándo se evalúa: al abrir el pipeline y mientras la empresa esté activa

- **El panel llama a `registrar_visita_al_pipeline()`** al abrir una vacante.
- **El hr-engine solo preselecciona vacantes vistas en los últimos 14 días.**
  - La primera visita es la demostración: "Evaluando tus 47 CVs…" y, al minuto, el gancho.
  - Mientras la empresa siga entrando, las aplicaciones nuevas se evalúan al llegar.
- **No se gasta en cuentas inactivas ni se tratan CVs que nadie va a mirar.** También es minimización de datos.

### 5. Topes y regla de continuidad

| Tope | Valor | Al llegar |
|---|---|---|
| CVs por empresa al mes | límite de vacantes × 50 (150 o 200) | El gancho espera al mes siguiente |
| Gasto por empresa al mes | US$2 | Igual |
| Gasto del plan gratis al mes | `FREE_TIER_MONTHLY_BUDGET_USD`, US$25 por defecto (~10.000 CVs) | Aviso al 80% y pausa al 100% |

- **Cada CV se evalúa una sola vez por vacante.** Volver a aplicar no crea otra aplicación.
- **Los CVs ilegibles** (`privado.cvs_ilegibles`) no se reintentan.
- **La regla de continuidad (`pricing-de-ia`):** agotar un tope nunca detiene el proceso de la empresa.
  - Publicar, recibir y descargar CVs siguen igual.
  - Solo el gancho dice "N CVs en espera".

### 6. A ciegas de verdad

"Ciego" no es "anónimo".

- **El hr-engine extrae el texto del PDF** y quita lo que identifica o discrimina:
  - nombre, correo, teléfono y enlaces;
  - foto (no pasa al texto);
  - edad o fecha de nacimiento, sexo, estado civil, nacionalidad y dirección.
- **El SKILL.md prohíbe inferir datos sensibles** (MX art. 8, CO art. 5).
- **Por qué no se manda el PDF:** con el PDF, el modelo vería la foto y el encabezado.
- **Los CVs escaneados sin texto** se marcan como ilegibles.

### 7. Retención y derechos

- **La preevaluación se borra:**
  - con la aplicación;
  - cuando el candidato se opone (`applications.sin_ia`, que también limpia el score del plan con IA);
  - cuando la empresa apaga la preselección;
  - **30 días después de cerrar la vacante** (`privado.purgar_preevaluaciones()`, a diario).
- **Esos 30 días** son también el último aviso comercial: "Tus 50 CVs evaluados se borran el día X".
- **El candidato puede acceder a su evaluación sin muro de pago.** La pide y la recibe él, no la empresa. Esto va en el portal del candidato y es condición de lanzamiento (abajo).

### 8. Al contratar se desbloquea lo que ya existe

Cuando una empresa pasa de `gratis` a `ia`, un trigger copia las preevaluaciones a `applications` y las mueve a "Evaluados":

- no se vuelve a pagar el modelo;
- no cambia ningún número;
- la empresa ve al instante quiénes eran los 13.

### 9. Sin run-token: es un trabajo interno del hr-engine

- **No es una run de agente.** La preselección gratis la lanza el planificador del hr-engine (Celery beat), así que no pasa por Paperclip ni lleva run-token.
- **Mantiene lo que ADR-005 protege:**
  - atribución: cada evaluación deja su fila en `runs` (`origen = preseleccion-gratis`) con su costo;
  - tope de gasto: el del punto 5;
  - ninguna llave global expuesta.
- **Acceso a la base:** escribe en `privado` con el rol dueño y lee lo de cada empresa con su contexto de tenant (ADR-004).

### 10. La descarga masiva se arma en el navegador

Esto sustituye el ".zip que genera el backend" de ADR-017 §3.

- **Cómo funciona:**
  - el panel pide las URLs firmadas con `createSignedUrls` (una llamada, expiran en minutos);
  - descarga los PDFs y los empaqueta con `client-zip`: 2,6 kB gz, MIT, *streaming* y sin comprimir, porque los PDFs ya lo están;
  - se carga con import dinámico, así que no cuenta en los 90 KB del bundle.
- **Por qué no en un servidor:**
  - el control de acceso es la policy `cvs_tenant_read` de Storage, y un servidor no la mejora;
  - un servidor pagaría el egress dos veces;
  - el hr-engine no está desplegado.

### 11. El plan de las empresas reales

No hay empresas en producción. Al provisionar Supabase Cloud:

| Empresa | Plan | Por qué |
|---|---|---|
| Vector HR Tech | `ia` | Interna: demos y QA |
| Siete | `ia`, piloto a US$0 hasta cerrar la validación F3 | Es el cliente alfa y el perfil del ICP (consultora que recluta para clientes). Su piloto valida el producto de pago, no el gratis |
| Cualquier otra | `gratis` al aceptar la invitación | `ia` solo con contrato firmado |

Así lo deja el runbook (`docs/runbooks/next-steps.md`, "Provisionar Supabase Cloud").

### 12. El plan gratis es para empleadores directos

- **Las consultoras, RPO y agencias no entran al plan gratis.** Publicarían gratis las vacantes de sus clientes, y son el ICP de Pro y Scale.
- **En su lugar reciben una prueba guiada del plan con IA**, con ventas.
- **Es lo que hace LinkedIn:** las firmas de *search* y *staffing* no pueden publicar empleos gratis.
- **Dónde se aplica:** en el alta por invitación, con la pregunta "¿Reclutas para tu empresa o para clientes?".

### 13. Cómo se traslada al precio (skill `pricing-de-ia`)

- **Unidad operativa:**
  - "vacantes activas con IA": predice el volumen de CVs, la empresa la conoce y crece con ella;
  - cada plan trae una **bolsa de CVs evaluados** incluida;
  - el excedente se cobra en CVs, nunca en tokens.
- **Regla de continuidad:** al agotar la bolsa se sigue evaluando y se avisa al 80%. Nunca se corta a mitad de un proceso.
- **Beta declarada:** el precio está en revisión y puede cambiar con aviso.
- **Experimento recomendado:** "desbloquear esta vacante", con pago único, frente al salto directo a Starter (US$149).
  - En LATAM se paga por vacante: OCC cobra MX$1.599–2.419 + IVA por aviso.
  - La evidencia sobre *reverse trials* no es concluyente (ChartMogul 2026: 4–6%, sin significancia).

### 14. Señales de venta (PQL)

- **Las señales:**
  - llegar a 50 de 50 aplicaciones;
  - abrir el pipeline 2 o más veces;
  - descargar los CVs en bloque;
  - pulsar "Ver quiénes son";
  - publicar una segunda vacante.
- **A quién van:** a Vector HR, que también recibe las empresas de más de 50 personas.
- **Por qué con ventas:** el freemium con apoyo de ventas convierte 5–7% frente al 3–5% del autoservicio (Lenny Rachitsky y Kyle Poyar, 2023).

## Costo por empresa (skill `costos-de-infraestructura`)

| Concepto | Plan gratis (peor caso al mes) | Fuente |
|---|---|---|
| Preselección con IA | ≤ US$0,50 (200 CVs) y nunca más de US$2 | Pricing de Gemini, 2026-10-16 |
| Storage de CVs | ~60 MB: Supabase Pro incluye 100 GB (≈ 1.600 empresas al tope) | Supabase pricing |
| Egress de la descarga masiva | ~60 MB: incluye 250 GB (≈ 4.000 empresas) | Supabase, "Egress" |

| Fijo de infraestructura | Al mes | Nota |
|---|---|---|
| Supabase Pro | US$25 | Trae US$10 en créditos de cómputo. No es dinero gratis: se consumen |
| hr-engine en Fly.io | ~US$8 | ADR-012 |
| Vercel | US$0 hoy; US$20 por desarrollador al mes con Pro | Hobby "restricts users to non-commercial, personal use only" ([Hobby plan](https://vercel.com/docs/plans/hobby), 2026-09-14). Con el primer cliente de pago hay que pasar a Pro |
| Redis (Upstash) | Por medir | Celery consulta el broker de forma continua y puede pasar del free tier de 10.000 comandos al día |

- **Lectura.** Con conversiones freemium de 3–5%, 100 empresas gratis darían 3–5 clientes Starter: unos US$450–750 de MRR. Su preselección cuesta como mucho US$50 al mes.
  - En el plan de pago, la IA es ~2% del precio: 1.000 CVs cuestan US$2,50 contra US$149.
- **El costo que falta son las horas de gente:** puesta en marcha, soporte y acompañamiento.
  - No hay dato. Se mide con el piloto de Siete antes de fijar los precios definitivos.
  - Es la regla de la skill: no se inventan cifras.

## Condiciones para activarlo en producción

La base ya aplica lo que le toca: puntos 3, 5, 7 y 8. Antes de encender la preselección con candidatos reales falta:

- [ ] **Términos del plan gratis y contrato de encargo** con la preselección como instrucción y el LLM como subencargado: CL 15 bis, CO DUR 1074 art. 2.2.2.25.5.2, MX Reg. 51-55.
- [ ] **Aviso al candidato antes de aplicar**, con casilla de autorización en Colombia, Argentina y Perú. Va en el formulario del career site. Texto base:
  > [Empresa] (responsable) usa Vortex, de Vector HR Tech (encargado). Un sistema de IA compara tu CV con los requisitos de la vacante sin recibir tu nombre. La IA no descarta a nadie: decide una persona de [Empresa]. El resultado es un dato tuyo: puedes acceder a él, corregirlo, oponerte a la evaluación con IA y pedir revisión humana en [canal]. Se borra 30 días después de cerrar la vacante o si retiras tu postulación.
  - Faltan la lógica y las consecuencias (CL 14 ter l; PE Reg. 6.1.8) y, en México, los medios ARCO y cómo se avisan los cambios (art. 15 V-VI).
- [ ] **Opción "evaluarme sin IA"** en el formulario, que enciende `applications.sin_ia`, y un canal de revisión humana: MX 26 II, CL 8 bis, PE 23, BR 20.
- [ ] **Acceso del candidato a su evaluación** sin muro de pago (portal del candidato): MX 21-22, BR 18 II, CL 5, PE Ley 19.
- [ ] **Evaluación de impacto con pruebas de sesgo:** CO CE 002/2024 IV, CL 15 ter a, BR Res. 2/2022 art. 4, PE Reg. 40.
- [ ] **Plan de pago: la regla solo sugiere.** Descartar exige una acción humana con motivo. CL 8 bis no dice "únicamente": una decisión "basada en" la IA ya cuenta.
- [ ] **Key de Gemini de producción probada con `gemini-2.5-flash`.** Desde el 18-09-2026, Google limita 2.5 a quien ya lo usaba (ADR-008).

## Implementación

| PR | Qué |
|---|---|
| #66 | El costo del scoring suma el razonamiento y 2.5 Flash puntúa sin él |
| Este | Migración 0009: `privado` (preevaluaciones, CVs ilegibles, muestras y visitas), `resumen_del_gancho()`, `muestra_del_gancho()`, `registrar_visita_al_pipeline()`, etapas de pago bloqueadas (PT403), desbloqueo al contratar, interruptor, oposición y purga. `domain/gancho.py` y `contracts/gancho.json` |
| Siguiente | El worker del hr-engine: extraer y anonimizar el CV, topes, Celery beat cada minuto y purga diaria |
| Siguiente | Panel: gancho con muestra, interruptor en "Crear empleo" y descarga masiva con `client-zip` |

## Consequences

**Positivas:**

- **El gancho es verdad y se puede auditar.** Lo contado es lo que se desbloquea, y lo desbloqueado no se paga dos veces.
- **El gasto del plan gratis tiene techo y es predecible.** Escala con el uso real, no con las altas.
- **La empresa decide si quiere la preselección, y el candidato puede oponerse.** El diseño se sostiene como encargo en los seis países.
- **La API ya no filtra el score del plan gratis**, y las etapas de pago no se pueden saltar.

**Negativas / trabajo que implica:**

- **Las condiciones de lanzamiento** son trabajo legal y de producto antes de producción.
- **El evaluador tiene que leer el CV completo y anonimizado**, no solo `headline` y `summary`. Eso cambia el insumo de `cv-evaluator` y exige correr sus evals.
- **Una consultora puede declararse empleador directo.** El riesgo se acota con la invitación y la revisión de Vector HR.

**Neutras:**

- **Los números del gancho avanzan de 5 en 5.** Es menos inmediato, pero protege lo que se vende.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| No evaluar el plan gratis y mostrar cifras genéricas | Sin números de su vacante no hay curiosidad (ADR-017). Con números inventados, el riesgo es el de Classmates |
| Evaluar con un modelo más barato solo para el gratis | Al pagar, los números cambiarían o se revelaría una evaluación de menor calidad |
| Evaluar en cada aplicación desde el primer día | Se gasta en cuentas que nunca vuelven y se tratan CVs que nadie mira. La visita al pipeline acota las dos cosas |
| Evaluar recién al momento de pagar | Es lo más prudente en privacidad, pero no hay gancho sin evaluación previa. La purga a 30 días y el interruptor acotan el riesgo |
| Guardar el score en `applications` y ocultarlo con privilegios de columna | El hr-engine escribe con el mismo rol `authenticated` que la empresa (ADR-004). Revocar columnas rompía el flujo de pago |
| Conteos que cambian con cada aplicación | Comparar antes y después destapa a cada candidato |
| Mostrar la mejor evaluación como muestra | Para una pyme con una vacante, es el producto entero |
| *Reverse trial* (todo desbloqueado 14 días) | Evidencia no concluyente: 4–6% sin significancia. Regala el producto en vez del paso previo (ADR-017). Queda como experimento frente al desbloqueo por vacante |
| Zip generado en el backend | No mejora la seguridad que ya da Storage, paga egress doble y depende del hr-engine, que no está desplegado |
| Webhook de base de datos (pg_net) para evaluar al insertar | Es asíncrono y sin reintentos documentados. El barrido de Celery es idempotente y reintenta solo |

## Referencias

**Oficiales (técnicas), revisadas el 2026-10-19:**
- Gemini API:
  - [Pricing](https://ai.google.dev/gemini-api/docs/pricing): actualizado el 2026-10-16; el razonamiento se cobra como salida; Batch y Flex al 50%.
  - [Thinking](https://ai.google.dev/gemini-api/docs/thinking): `thinkingBudget = 0` lo apaga en 2.5 Flash; `max_output_tokens` incluye el razonamiento.
  - [Deprecations](https://ai.google.dev/gemini-api/docs/deprecations) y [changelog](https://ai.google.dev/gemini-api/docs/changelog): acceso a 2.5 limitado desde el 18-09-2026.
  - [Document processing](https://ai.google.dev/gemini-api/docs/document-processing): 258 tokens por página en 2.5.
- Supabase:
  - [Pricing](https://supabase.com/pricing): Pro a US$25 con 250 GB de egress y 100 GB de storage.
  - [`createSignedUrls`](https://supabase.com/docs/reference/javascript/storage-from-createsignedurls): opción `download` y error por ruta, según el código de `storage-js` 2.118.
  - [Database Webhooks](https://supabase.com/docs/guides/database/webhooks) y [pg_net](https://supabase.com/docs/guides/database/extensions/pg_net#limitations): sin reintentos.
- [client-zip](https://github.com/Touffy/client-zip) 2.5.1: 2,6 kB gz, MIT, *streaming*.
- PostgREST, [Errors](https://docs.postgrest.org/en/stable/references/errors.html): `PT403` se responde como 403.

**Negocio:**
- [Lenny Rachitsky y Kyle Poyar, conversión free-to-paid](https://www.lennysnewsletter.com/p/what-is-a-good-free-to-paid-conversion) (2023).
- [ChartMogul, SaaS Conversion Report](https://chartmogul.com/reports/saas-conversion-report/) (2026).
- LinkedIn:
  - [quién vio tu perfil](https://www.linkedin.com/help/billing/answer/4508);
  - [empleos gratis y promocionados](https://www.linkedin.com/help/linkedin/answer/a519737/differences-between-free-and-promoted-jobs?lang=en);
  - [firmas de staffing](https://www.linkedin.com/help/linkedin/answer/a1511845).
- Precios por CV:
  - [Workable](https://www.workable.com/pricing);
  - [Breezy](https://breezy.hr/pricing);
  - [Litespace](https://www.litespace.io/pricing);
  - [OCC](https://www.occ.com.mx/empresas/precios).
- [Acuerdo de Classmates.com](https://betanews.com/2011/08/25/classmates-com-pays-2-5-million-settlement-for-lying-to-users) (2011).

**Legal** (investigación legal-tech, no asesoría legal):
- México: [LFPDPPP, DOF 20-03-2025](https://dof.gob.mx/nota_detalle.php?codigo=5752569&fecha=20/03/2025) y [Reglamento 2011](https://dof.gob.mx/nota_detalle.php?codigo=5226005&fecha=21/12/2011). No está verificado que el Reglamento siga vigente.
- Colombia:
  - [Ley 1581](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981);
  - [DUR 1074/2015](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=76608);
  - [SIC, Circular Externa 002/2024](https://sedeelectronica.sic.gov.co/sites/default/files/normativa/Circular%20Externa%20No.%20002%20del%2021%20de%20agosto%20de%202024.pdf).
- Brasil: [LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm), arts. 6, 20, 39 y 42.
- Chile: [Ley 21.719](https://www.bcn.cl/leychile/Navegar?idNorma=1209272), vigente desde el 1-12-2026, con una postergación en trámite.
- Perú: [Ley 29733](https://www.leyes.congreso.gob.pe/Documentos/Leyes/29733.pdf), DS 016-2024-JUS y DS 115-2025-PCM. Este último clasifica la IA de selección como de riesgo alto.
- Argentina: [Ley 25.326](https://servicios.infoleg.gob.ar/infolegInternet/anexos/60000-64999/64790/texact.htm) y Res. AAIP 4/2019.
