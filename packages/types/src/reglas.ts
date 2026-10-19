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

/** Planes de Vortex. Viajan en el JWT como `app_metadata.plan` (ADR-017). */
export type Plan = "gratis" | "ia";
/** Módulos que un plan habilita. Viajan como `app_metadata.modulos`. */
export type Modulo = "career-site" | "cockpit";

/**
 * Límites de cada plan.
 *
 * Dueña: `services/hr-engine/app/domain/plan.py`; los aplica la base (migración
 * 0008). Contrato: `contracts/limites-plan.json`. La UI los usa para explicar el
 * cupo; el número de vacantes que le quedan a una empresa lo da la base
 * (`mi_cupo_de_vacantes()`), no se calcula aquí.
 */
export const LIMITES_DEL_PLAN = {
  gratis: {
    modulos: ["career-site"],
    etapasVisibles: ["applied"],
    aplicacionesPorVacante: 50,
  },
  ia: {
    modulos: ["career-site", "cockpit"],
    etapasVisibles: ETAPAS_DEL_PIPELINE,
    aplicacionesPorVacante: null,
  },
} as const satisfies Record<
  Plan,
  {
    modulos: readonly Modulo[];
    etapasVisibles: readonly EtapaDelPipeline[];
    aplicacionesPorVacante: number | null;
  }
>;

/**
 * Vacantes activas del plan gratuito: 3 hasta 50 personas, 4 desde 51 (3 sin
 * tamaño). `ajuste` es el número que fijó Vector HR para esa empresa.
 *
 * @example limiteDeVacantes(120) // 4
 */
export function limiteDeVacantes(tamano: number | null, ajuste: number | null = null): number {
  if (ajuste !== null) return ajuste;
  return tamano !== null && tamano >= 51 ? 4 : 3;
}
