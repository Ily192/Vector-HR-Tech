/**
 * Reglas de negocio que la UI necesita mostrar pero no decide.
 *
 * Cada una tiene su dueña en el backend y aquí solo se espeja, con un contrato
 * JSON que prueban los dos lados. La UI las usa para explicar o anticipar lo que
 * hará el backend, nunca para tomar la decisión en su lugar (ADR-016).
 */
import type { ApplicationStatus, SiguientePaso } from "./hr";

/**
 * Umbrales de score que fijan el siguiente paso de un candidato.
 *
 * Dueña: `services/hr-engine/app/domain/siguiente_paso.py`
 * (`UMBRAL_PSICOMETRICO`, `UMBRAL_ENTREVISTA`). Contrato:
 * `contracts/siguiente-paso.json`.
 */
export const UMBRALES_SIGUIENTE_PASO = {
  /** Por debajo de este score se rechaza. */
  psicometrico: 4,
  /** Desde este score se pasa directo a entrevista. */
  entrevista: 7,
} as const;

/**
 * Siguiente paso que el backend asignará a un score: `< 4` rechazar,
 * `[4, 7)` psicométrico, `≥ 7` entrevista.
 *
 * @example siguientePaso(8.5) // "entrevista"
 */
export function siguientePaso(score: number): SiguientePaso {
  if (score < UMBRALES_SIGUIENTE_PASO.psicometrico) return "rechazar";
  if (score < UMBRALES_SIGUIENTE_PASO.entrevista) return "psicometrico";
  return "entrevista";
}

/**
 * Etapas del pipeline activo, en orden. Las de salida (`hired`, `rejected`,
 * `withdrawn`) no forman parte del embudo y se cuentan aparte.
 */
export const ETAPAS_DEL_PIPELINE = [
  "applied",
  "evaluated",
  "shortlisted",
  "interviewed",
  "offered",
] as const satisfies readonly ApplicationStatus[];
export type EtapaDelPipeline = (typeof ETAPAS_DEL_PIPELINE)[number];
