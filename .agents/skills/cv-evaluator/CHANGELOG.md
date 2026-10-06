# cv-evaluator · changelog

Va aparte del SKILL.md porque el cuerpo de ese fichero es el prompt: lo que se
escriba ahí lo lee el modelo.

- **0.2.0 (2026-10-05):** este cuerpo pasa a ser, tal cual, el system instruction que
  recibe el modelo (`services/hr-engine/app/skills.py`). Antes el hr-engine usaba un
  prompt escrito a mano sin la calibración ni la regla anti-sesgo. Modelo:
  `gemini-1.5-flash` (retirado) → `gemini-2.5-flash`; fuera el fallback `gpt-4o-mini`,
  que nunca existió en el código.
- **0.1.0:** versión inicial.
