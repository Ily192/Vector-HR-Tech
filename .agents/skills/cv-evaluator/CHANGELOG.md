# cv-evaluator · changelog

Va aparte del SKILL.md porque el cuerpo de ese fichero es el prompt: lo que se
escriba ahí lo lee el modelo.

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
