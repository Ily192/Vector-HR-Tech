# ADR-024: El plan gratis incluye el pipeline completo, a mano; la IA sigue siendo de pago

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decider:** Ilyra ("Las personas deben tener acceso a todos esos pasos, ningún servicios IA. Desbloquea esos pasos… Por ahora lo único que monetiza este panel es que la empresa desee publicar más de 3 vacantes y después ofrecemos en el panel el Fluve AI cuando lo tengamos listo.")
- **Enmienda:**
  - ADR-019 §2: la fila "Pipeline" y "la base aplica cada fila" (el PT403 de las etapas);
  - ADR-019, Consequences: la frase de la frontera;
  - ADR-017 §1 ("el pipeline limitado" / "el pipeline completo") y §3 (la fila "Etapas del pipeline" y "el resto de etapas se ve, pero cerrado").
- **Tags:** producto, plan-gratis, panel, multi-tenant

## Context

**Hasta hoy, en el plan gratis el pipeline era solo "Aplicados".**
- Evaluados, Shortlist, Entrevista y Oferta se veían en gris, con un candado y "Servicios IA".
- La base lo cortaba: el trigger `applications_etapas_del_plan` (0009) devolvía PT403 al mover una aplicación de una empresa gratuita a esas etapas.
- Cerrar sí se podía por la API (contratado, descartado, retirado), pero el panel no lo ofrecía. El único descarte con motivo era el de los evaluados con IA del plan de pago (0015).

**La web y una publicación en LinkedIn ya lo prometen:** "Sigues cada postulación y marcas a quién contrataste o descartaste" y "las sigues por etapa, descargas los CVs juntos y marcas a quién contrataste".

**Bloquear las etapas no ahorraba nada.** Mover a alguien de etapa es cambiar una columna: no llama a ningún modelo ni guarda nada nuevo. El candado solo le quitaba valor al plan gratis.

**Hoy no hay IA que ofrecer en el panel.**
- La evaluación con IA no pasó la prueba de sesgo con `gemini-3.5-flash-lite` (ADR-021).
- La búsqueda de perfiles no está construida.
- Por eso, desde el 2026-11-13, crear empleo ya no muestra el recuadro de los servicios.

## Decision

### 1. El pipeline completo es gratis, y se lleva a mano

- **Qué hace la empresa:**
  - mueve a cada candidato a cualquier etapa, hacia adelante o hacia atrás;
  - lo cierra como contratado, descartado o "se retiró".
- **Es igual en los dos planes.** En el de pago, la IA además pasa de "Aplicados" a "Revisados" lo que evalúa (ADR-021); el resto lo mueve una persona.
- **Ninguna etapa enciende la IA ni manda correos** (puntos 4 y 5).

### 2. Las etiquetas

Una sola tabla para los dos planes, en `@fluveai/types/etiquetas`. Se leen como grupos de personas: en el pipeline, en el filtro y en la etapa de cada candidato.

| Estado | Antes | Ahora | Por qué |
|---|---|---|---|
| `applied` | Aplicados | Aplicados | Igual que en la web |
| `evaluated` | Evaluados | **Revisados** | En el plan gratis lo revisa una persona; "Evaluados", junto al botón "Evaluarlos con IA", sonaba a IA |
| `shortlisted` | Shortlist | **Preseleccionados** | El término en español que usan las bolsas de empleo; la elige una persona |
| `interviewed` | Entrevista | **En entrevista** | Sirve antes y después de la entrevista |
| `offered` | Oferta | **Con oferta** | Un grupo de personas, como las demás |
| `hired` | Contratados | Contratados | |
| `rejected` | Descartados | Descartados | |
| `withdrawn` | Se retiraron | Se retiraron | Solo se muestra si alguien se retiró |

En el plan de pago, la lista de la IA sigue llamándose "Evaluados": es la evaluación con IA, con score y porqué. La etapa se llama "Revisados" en los dos planes.

### 3. Descartar: el mismo formulario, y el motivo solo es obligatorio si evaluó la IA

- **Si la IA puso score:** el motivo es obligatorio, de 10 a 500 caracteres (PT422, ADR-021 §4). La regla de 0015 no cambia.
- **Si no hay score**, como en todo el plan gratis: el motivo es opcional. Si se escribe, también mide de 10 a 500 caracteres.
- **Por qué opcional.** El motivo obligatorio protege contra una decisión que sugirió una máquina (condición de ADR-018). En el plan gratis ya decide una persona, y pedirle 10 letras por cada uno de 50 descartes no protege a nadie.
- **Dónde queda:** solo en la base (`applications.motivo_de_descarte`). No se le manda al candidato ni a nadie.

### 4. Lo que monetiza el panel, y lo que se paga

| | Gratis | De pago |
|---|---|---|
| Vacantes activas | 3 hasta 50 personas, 4 desde 51 | Sin tope |
| Publicaciones nuevas | Tantas como activas cada 30 días | Sin tope |
| Aplicaciones por vacante | 50 recibidas; mover, descartar o borrar no libera cupo | Sin tope |
| Pipeline | **Todas las etapas, a mano**, con contratado, descartado y retirado | Igual |
| IA | Nada: el gancho es la coincidencia de skills sin IA (ADR-019 §3) | Evaluación a ciegas (ADR-021) |
| Cockpit | No: ni entrevistas agendadas, ni psicométricos, ni constancias | Sí |

- **Lo único que se cobra hoy es pasar del plan.** Eso es publicar más vacantes, un reclutamiento masivo o recibir más de 50 CVs por vacante. Los límites no cambian.
  - El panel lo ofrece por correo: "¿Necesitas …? Escríbenos a hola@vectorhrtech.com", con el asunto ya escrito.
  - Aparece en Mis vacantes, en Crear empleo con el cupo lleno y bajo "Recibidas: N de 50" (`pantallas/mas-del-plan.tsx`).
  - Lo decidió Ilyra el 2026-11-19.
- **La IA (Fluve AI) se ofrecerá desde el panel cuando esté lista.** Hasta entonces el gancho de skills se queda (ADR-019 §3), pero sin el botón "Evaluarlos con IA" ni la frase de los servicios de IA (decisión del 2026-11-19).
  - La captura de interés de 0013 sigue en la base y en los adaptadores para cuando vuelva.
  - El gancho dice "Comparamos 45 de tus CVs con las 4 skills" y no "Revisamos", para no sonar a una persona: en el plan gratis, la etapa "Revisados" sí la hace una persona.

### 5. La base lo aplica (migración 0021)

**Lo que se abre:**
- Se borra el trigger `applications_etapas_del_plan` y su función (0009).
- Quién mueve a quién lo sigue decidiendo lo que ya existía:
  - la policy `applications_tenant_write` (0004): solo HR y Dirección de la empresa del JWT. SuperAdmin lee, pero no decide;
  - las FK compuestas (0004): una aplicación no cuelga de la vacante ni del candidato de otra empresa.

**La fecha y el motivo**, con un trigger nuevo (`applications_al_cambiar_de_etapa`, que reemplaza al de 0015 sin cambiar su regla):
- al cerrar (contratado, descartado o retirado) se fija `decided_at`; Vector HR, sin sesión de tenant, puede poner otra;
- al volver a una etapa del pipeline se borra `decided_at`;
- el motivo del descarte se borra cuando la aplicación deja de estar descartada: es un dato del candidato que ya no aplica.

**Lo que sigue prohibido** (lo prueban `tests/security/test_pipeline_manual.py` y `test_evaluaciones_ia.py`):
- mover aplicaciones de otra empresa, o hacerlo con otro rol (Colaborador, SuperAdmin, cliente) o sin sesión;
- liberar cupo: el tope cuenta las recibidas (`privado.aplicaciones_recibidas`, 0010);
- retirar la oposición del candidato (`sin_ia`, PT403, 0010);
- usar el cockpit: "En entrevista" es una etapa, y agendar la entrevista sigue siendo de pago (PT403, 0010);
- correr IA: el hr-engine sigue respondiendo 403 a los runs de un plan sin IA (`verificar_ia`) y el contrato sigue con `incluye_ia: false`.

### 6. Sin IA y sin correos

- **El barrido de evaluación** solo toma aplicaciones de empresas `ia` que siguen en "Aplicados" (ADR-021). Mover en el plan gratis no lo toca.
- **Al contratar**, la IA evalúa lo que sigue en "Aplicados". Lo que una persona ya movió no se vuelve a decidir con IA.
- **Ningún correo al cambiar de etapa,** ni al candidato ni a la empresa. La cuota gratis de Resend es de los códigos de acceso (ADR-023).

### 7. El panel

- **"Pipeline":** cuántos candidatos hay ahora en cada etapa, con su barra, y abajo el cierre (Contratados, Descartados y, si hay, Se retiraron).
  - Cada etapa se pulsa para filtrar la lista.
  - Abajo, "Recibidas: 47 de 50", con el aviso de que mover o descartar no libera lugares.
- **"Candidatos":** cada uno con cuándo aplicó, su CV y un selector con su etapa.
  - Elegir una etapa la guarda. La pantalla la muestra al instante y vuelve atrás si la base no la guardó.
  - Elegir "Descartados" abre el formulario del motivo.
  - Se ven 10, y "Ver los N" muestra todos.
- **La página se llama "Candidatos"** (antes "Aplicados") para no confundirla con la etapa. En Mis vacantes, el botón dice "Ver candidatos".
- **Siguen igual:** el enlace a cada CV, la descarga en .zip y el gancho.
- **Los datos de ejemplo** reparten a los candidatos por todas las etapas, con contratados y descartados, para la demo y el video. Son nombres inventados.

### 8. El contrato

`limites-plan.json` abre al plan gratis las cinco etapas (`etapas_visibles`), igual que al de pago. Las tres copias lo prueban:
- `domain/plan.py` (`test_contrato_limites_plan.py`);
- `@fluveai/types/reglas` (`reglas.test.ts`);
- la base (`test_pipeline_manual.py`: la empresa gratuita mueve a cada etapa del contrato).

## Consequences

**Positivas:**
- **El panel cumple lo que promete la web:** seguir cada postulación por etapa y marcar a quién se contrató o descartó.
- **La frontera se sigue diciendo en una frase:** gratis es publicar, recibir, descargar y llevar el pipeline a mano; la IA es de pago; hoy se cobra publicar más.
- **Costo variable cero:** mover no llama a ningún modelo ni manda correos.
- **La base lo sostiene aunque alguien se salte la UI.**

**Negativas:**
- **Las etapas dejan de empujar al plan de pago.** El empuje queda en el límite de vacantes y, cuando esté lista, en la IA.
- **"Revisados" mezcla dos cosas en el plan de pago:** lo que revisó la IA y lo que movió una persona. El score dice cuál es cuál.
- **No hay historial de etapas.** Solo queda la etapa actual y `decided_at`. Si una empresa pide saber cuándo pasó cada cosa, hace falta una tabla de movimientos.
- **"Se retiró" lo marca la empresa.** El candidato todavía no puede retirarse solo.

**Neutras:**
- `etapas_visibles` sigue en el contrato, igual en los dos planes, por si un plan futuro vuelve a diferenciarlas.
- El trigger de 0015 cambia de nombre; su regla del PT422 es la misma.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Dejar el candado | Contradice lo que promete la web, y mover una columna no cuesta nada |
| Abrir solo contratado y descartado | La base ya los dejaba; no da "por etapa" |
| Un kanban con arrastrar y soltar | Más código para el bundle de 90 KB y peor en el teléfono y con teclado. El selector y el filtro hacen lo mismo |
| Una RPC `mover_aplicacion()` con `security definer` | Repetiría lo que ya hace la policy de 0004. El update directo es el mismo camino que usa descartar |
| Motivo obligatorio en todo descarte | Fricción sin un riesgo que la justifique cuando decide una persona |
| Etiquetas distintas por plan | La misma etapa cambiaría de nombre al contratar |
| Registrar cada movimiento en una tabla | No lo pide nadie todavía; `decided_at` basta para saber cuándo se cerró |

## Lo que queda abierto

Resuelto el 2026-11-19 (ver §4):
- El botón "Evaluarlos con IA" se oculta hasta Fluve AI.
- El gancho dice "Comparamos".
- Pasar del plan se pide por correo desde el panel.

Sigue abierto:
- **El cockpit no se abre:** ni las entrevistas agendadas, ni los psicométricos, ni las constancias. El pipeline no los necesita.
- **El motivo de descarte sigue opcional**, y no hay historial de etapas.

## Implementación

| PR | Qué |
|---|---|
| Este | Migración 0021; contrato y `domain/plan.py`; etiquetas y `ETAPAS_DE_SALIDA` en `@fluveai/types`; panel (pipeline con etapas, filtro y selector, descartar sin IA, datos de ejemplo); tests de unidad, de seguridad y el flujo e2e del plan gratis |
