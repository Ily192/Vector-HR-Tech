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
 * Dueña: `services/hr-engine/app/domain/plan.py`; los aplica la base (migraciones
 * 0008 y 0010). Contrato: `contracts/limites-plan.json`. La UI los usa para
 * explicar el cupo; el número de vacantes que le quedan a una empresa lo da la
 * base (`mi_cupo_de_vacantes()`), no se calcula aquí. `incluyeIa`: si para la
 * empresa corren agentes y LLM; la IA es lo que se paga (ADR-019).
 */
export const LIMITES_DEL_PLAN = {
  gratis: {
    incluyeIa: false,
    modulos: ["career-site"],
    etapasVisibles: ["applied"],
    aplicacionesPorVacante: 50,
  },
  ia: {
    incluyeIa: true,
    modulos: ["career-site", "cockpit"],
    etapasVisibles: ETAPAS_DEL_PIPELINE,
    aplicacionesPorVacante: null,
  },
} as const satisfies Record<
  Plan,
  {
    incluyeIa: boolean;
    modulos: readonly Modulo[];
    etapasVisibles: readonly EtapaDelPipeline[];
    aplicacionesPorVacante: number | null;
  }
>;

/**
 * Skills de una vacante: hasta 15, de 1 a 60 caracteres cada una. Dueña:
 * `services/hr-engine/app/domain/coincidencia.py`; las aplica la base
 * (`skills_validas()`, 0010). Aquí no llevan zod: el panel las usa sin cargarlo.
 */
export const MAX_SKILLS_POR_VACANTE = 15;
export const MAX_LARGO_DE_SKILL = 60;

/**
 * Días de la ventana móvil en la que el plan gratis publica tantas vacantes nuevas
 * como vacantes activas permite (ADR-019). Reabrir una vacante no cuenta. Cuántas
 * le quedan a una empresa lo da la base (`mi_cupo_de_vacantes()`).
 */
export const VENTANA_DE_PUBLICACIONES_DIAS = 30;

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
