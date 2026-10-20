# ADR-021: La evaluación con IA del plan de pago, a ciegas y como trabajo interno del hr-engine

- **Status:** Accepted
- **Date:** 2026-10-20
- **Decider:** Ilyra delegó la decisión técnica ("piensa como un PM y un dev senior para tomar las mejores decisiones a largo plazo"). Es la tarjeta "evaluación con IA del plan de pago (MVP, día 3)".
- **Retoma:** de ADR-018 lo que aplica al plan de pago: §1 (modelo y costo), §6 (a ciegas), §7 (retención) y §9 (sin run-token). Corrige ADR-019 §6: la evaluación ya no se configura en Paperclip.
- **Tags:** hr-engine, ia, privacidad, costos

## Context

**La IA es lo que se paga** (ADR-019 §1), y hoy ninguna aplicación se evalúa:
- `cv-evaluator` solo corre con un run-token de Paperclip, y Paperclip no está desplegado (Cycle 2).
- Lee solo el titular y el resumen del candidato. El career site pide el titular como opcional y no pide resumen.

**Lo que ya existe sirve:**
- El worker del plan gratis baja el CV de Storage y saca su texto con el mismo extractor que tiene que usar la IA (`CoincidirCvsPendientes`, ADR-019 §4).
- El evaluador, el esquema de salida (`contracts/cv-evaluation.json`) y la política del siguiente paso (`domain/siguiente_paso.py`) ya están probados.
- La base ya deja pasar "Evaluados" solo a las empresas `ia` (0009) y borra el score cuando el candidato se opone (`sin_ia`, 0010).

**Lo necesitan** la demo de Vector HR, que es `ia`, y el primer cliente de pago.

## Decision

### 1. Qué se evalúa

- **Cada aplicación de una empresa `ia`**, una sola vez. Condiciones:
  - CV legible;
  - sin `sin_ia`;
  - sin score todavía.
- **Las que ya existían al pasar de `gratis` a `ia` también.** Contratar evalúa lo que la empresa ya recibió, sin configurar nada.

### 2. Cómo se lanza: un barrido de Celery beat, sin Paperclip

- **`evaluaciones.barrer` cada minuto**, como el barrido del plan gratis.
  - Toma un lote (`EVALUACIONES_LOTE`, 50) y evalúa varias en paralelo (`EVALUACIONES_EN_PARALELO`, 8).
  - Reclama las filas con `for update skip locked`: dos barridos nunca evalúan la misma aplicación.
- **Objetivo:** el score visible en menos de 2 minutos desde que el candidato aplica. Es la tarjeta de e2e del sprint 3.
- **Mantiene lo que ADR-005 protege** (ADR-018 §9):
  - **Atribución:** cada evaluación deja su fila en `runs`, con `agent_skill = cv-evaluator`, `payload.origen = interno` y su costo.
  - **Plan:** antes de gastar se comprueba `verificar_ia`.
  - **Llaves:** ninguna llave global expuesta.
- **Fallas:**
  - Si el modelo no está disponible (caído, sin key o con el circuito abierto), la aplicación espera al siguiente barrido sin gastar su intento. Sin ninguna key configurada, el barrido no reclama nada.
  - Si falla por otra causa, como una respuesta inválida, gasta un intento. Tras 3 queda "sin evaluar: revisar a mano".
  - Un CV ilegible no se manda al modelo y queda marcado igual que en el plan gratis.
- **El endpoint con run-token no cambia.** Queda para los agentes que orqueste Paperclip.

### 3. Qué recibe el modelo: a ciegas de verdad

**El texto del CV, anonimizado en el dominio del hr-engine antes de salir.** Se reemplaza o se quita:
- El nombre del candidato y cada una de sus partes.
- El correo, el teléfono y los enlaces (LinkedIn incluido).
- Las líneas de datos personales: edad o fecha de nacimiento, sexo o género, estado civil, nacionalidad, dirección o domicilio, religión, discapacidad y documentos (CURP, RFC, NSS, DNI, cédula, pasaporte).
- La foto no pasa al texto.

**Con la vacante:**
- **Va:** título, descripción, skills, nivel, modalidad y ubicación.
- **No va:** el nombre de la empresa.

**Límites:**
- El CV se recorta a 12.000 caracteres (unas 3.000 palabras).
- El texto anonimizado no se guarda, solo el resultado.

**Defensa en profundidad:** el anonimizador trabaja con reglas y no es perfecto. Por eso el SKILL.md (versión 0.3.0) prohíbe inferir o usar datos sensibles y nombrar a la persona en el porqué.

**Por qué no se manda el PDF** (ADR-018 §6): el modelo vería la foto y el encabezado.

### 4. Qué devuelve y quién decide

- **El modelo devuelve:**
  - score de 0 a 10;
  - el porqué;
  - fortalezas y brechas.

  Es el contrato de siempre, que no cambia.
- **En la aplicación:**
  - pasa a "Evaluados" (`status = evaluated`) con `fit_*`;
  - suma `fit_strengths` y `evaluada_en` (migración 0014).
- **El siguiente paso es una sugerencia de la política determinista:**
  - < 4: no avanzar;
  - de 4 a 7: psicométrico;
  - ≥ 7: entrevista.
- **Descartar exige una persona.** La IA no descarta a nadie: el panel pide una acción humana con motivo (condición de ADR-018).

### 5. Modelo y datos

- **`gemini-2.5-flash` sin razonamiento** (ADR-018 §1). Cuesta unos US$0,0025 por CV: ~5.000 tokens de entrada y ~400 de salida.
- **Solo con la key del nivel de pago.** En el gratuito, Google usa los prompts para mejorar sus productos.
- **Respaldo de OpenAI**, que no entrena con lo que recibe su API.
- **Los dos figuran como subencargados** en el contrato con la empresa.

### 6. Topes y continuidad

| Tope | Valor | Al llegar |
|---|---|---|
| Por empresa al mes | `empresas.ia_cvs_por_mes`, 1.000 por defecto (US$2,50). Vector HR lo ajusta | Las nuevas esperan; aviso a Vector HR al 80 % |
| Toda la plataforma al mes | `IA_PRESUPUESTO_MENSUAL_USD`, US$25 (~10.000 CVs) | Pausa de las evaluaciones nuevas y aviso |

- **Son topes de seguridad, no la bolsa comercial.**
  - La bolsa de CVs incluidos por plan es precio (ADR-018 §13).
  - Al agotarla se sigue evaluando y se cobra el excedente en CVs.
- **El costo de cada evaluación se registra en `runs`.** El tope por run sigue en modo medición (`ENFORCE_RUN_COST_CAP`): el CV recortado ya acota lo que puede costar.
- **La regla de continuidad (`pricing-de-ia`):** agotar un tope nunca detiene el proceso de la empresa.
  - Publicar, recibir, descargar y mover candidatos a mano siguen igual.
  - Lo no evaluado se queda en "Aplicados", y el panel dice cuántas aplicaciones esperan.

### 7. El aviso al candidato depende del plan

- **Qué dice el career site** a cada candidato:
  - Si la empresa usa IA, el aviso con IA (texto base en ADR-018, "Condiciones").
  - Si no, el del plan gratis (ADR-019).
- **Cómo lo sabe:** `vacantes_publicas` expone `evalua_con_ia`, un booleano, y no el plan.
- **La casilla para oponerse no cambia:** "Evaluar mi CV sin procesos automatizados" enciende `sin_ia`.

### 8. Retención y derechos

- **Dónde vive la evaluación:** en la aplicación.
- **Cuándo se borra:**
  - con la aplicación;
  - cuando el candidato se opone, porque el trigger de 0010 ya limpia `fit_*`.
- **El texto del CV no se guarda** en ningún lado: se extrae, se anonimiza, se evalúa y se descarta.
- **El candidato puede ver su evaluación sin pagar** desde el portal del candidato. Es condición para producción (abajo).

### 9. Calidad y sesgo

- **El set de evaluación con CVs reales vive fuera del repo**, que es público y esos CVs son datos personales. El arnés lo lee de una ruta privada (`EVALS_CV_EVALUATOR_DIR`). En el repo solo hay casos sintéticos.
- **Pruebas de sesgo antes de producción:** pares contrafactuales, es decir, el mismo CV con distintos marcadores de género, edad u origen. El score no debe moverse.

## Condiciones antes de evaluar candidatos reales

Son las de ADR-018, puestas al día:

- [ ] Key de Gemini del nivel de pago, probada con `gemini-2.5-flash`.
- [ ] Términos del plan de pago y contrato de encargo, con los LLM como subencargados.
- [x] Aviso al candidato con IA en el career site (§7): #82.
- [x] Descartar con acción humana y motivo en el panel (§4): #85, y la base lo exige (0015).
- [ ] Acceso del candidato a su evaluación (portal del candidato).
- [ ] Evaluación de impacto con las pruebas de sesgo (§9).

## Implementación

| PR | Qué |
|---|---|
| #80 | ADR-021 |
| #81 | **hr-engine.**<br>• Anonimizador en el dominio.<br>• `EvaluarAplicacionesPendientes`, que reusa el extractor del plan gratis.<br>• Scoring con el texto del CV y SKILL.md 0.3.0.<br>• `evaluaciones.barrer` en beat, con topes y runs internos.<br>• Migración 0014: `ia_cvs_por_mes`, `fit_strengths`, `evaluada_en` y `vacantes_publicas.evalua_con_ia` |
| #82 | **Career site:** el aviso con IA |
| #84 | Una caída del modelo o la falta de key no gastan intentos |
| #85 | **Panel.**<br>• "Evaluados" con score, porqué y sugerencia, del mejor encaje al menor.<br>• Descartar con motivo. La base lo exige si evaluó la IA: migración 0015, PT422.<br>• Cuántas aplicaciones esperan, cuántas hay que revisar a mano y cuántos CVs son ilegibles |
| Siguiente | **El cockpit con datos reales** |
| Siguiente | **Arnés de evals** con la ruta privada y los pares contrafactuales |

## Consequences

**Positivas:**
- **Sin Paperclip:** el plan de pago funciona sin desplegar otro servicio, con el mismo stack del VPS (ADR-020).
- **Un solo extractor** para los dos planes: lo que el plan gratis lee es lo que la IA evalúa.
- **Cada evaluación con su costo en `runs`:** se puede medir el margen por cliente.

**Negativas:**
- **Latencia:** hasta un minuto de espera por el beat. Cabe en el objetivo de 2 minutos.
- **El anonimizador por reglas se puede saltar** con formatos raros. Se mitiga con el SKILL.md y las pruebas de sesgo, no se elimina.
- **Hay dos caminos al evaluador:** el barrido interno y el endpoint con run-token. Comparten el caso de uso y el scoring.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Correrlo con Paperclip y run-tokens | Paperclip no está desplegado: sería otro servicio para algo que el beat ya resuelve |
| Evaluar al abrir el pipeline (ADR-018 §4) | En el plan de pago el valor es tenerlo listo al entrar. Ya hay minimización: solo empresas `ia` y solo CVs legibles |
| Mandar el PDF al modelo | Vería la foto y el encabezado: deja de ser a ciegas |
| Lanzarlo con un webhook de la base al insertar | Más piezas (pg_net, reintentos, firma) para ganar menos de un minuto |
