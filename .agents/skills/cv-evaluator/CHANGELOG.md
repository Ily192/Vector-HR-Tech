# cv-evaluator · changelog

Va aparte del SKILL.md porque el cuerpo de ese fichero es el prompt: lo que se
escriba ahí lo lee el modelo.

- **0.3.2 (2026-11-19):** modelo `gemini-3.5-flash-lite` → `gemini-3.8-flash`, con
  `thinking_level` low. Es el que pasa la prueba de sesgo de ADR-021 §9: con el set
  sintético no se movió ninguno de los 24 pares contrafactuales, y con 3.5 Flash-Lite se
  movían 4. Cuesta el doble, y su precio de lanzamiento vence el 2026-12-31. Decisión de
  Ilyra; ver la enmienda de ADR-008. El cuerpo (el prompt) no cambia.
- **0.3.1 (2026-11-12):** modelo `gemini-2.5-flash` (deprecado: responde 404 a claves
  nuevas y desde el 2026-12-01 se redirige) → `gemini-3.5-flash-lite`, al mismo precio.
  Razona con `thinking_level` minimal y ya no recibe `temperature` ni `top_p`. El cuerpo
  (el prompt) no cambia.
- **0.3.0 (2026-10-20):** el plan de pago evalúa el texto del CV, anonimizado por el
  hr-engine (ADR-021), contra el perfil completo de la vacante: puesto, nivel,
  modalidad, ubicación, skills y descripción. Explica las marcas `[nombre]`, `[correo]`,
  `[teléfono]` y `[enlace]`. Amplía la regla anti-sesgo: no inferir datos personales
  ni penalizar pausas laborales. Prohíbe nombrar a la persona en el rationale y
  aclara que el siguiente paso es una sugerencia. Pasa de voseo a español neutro.
  `rate_limit_per_minute` sube a 60 por el lote del barrido.
- **0.2.0 (2026-10-05):** este cuerpo pasa a ser, tal cual, el system instruction que
  recibe el modelo (`services/hr-engine/app/skills.py`). Antes el hr-engine usaba un
  prompt escrito a mano sin la calibración ni la regla anti-sesgo. Modelo:
  `gemini-1.5-flash` (retirado) → `gemini-2.5-flash`; fuera el fallback `gpt-4o-mini`,
  que nunca existió en el código.
- **0.1.0:** versión inicial.
