/**
 * Forma de los datos que el panel de la empresa recibe del backend.
 *
 * Todo llega ya decidido: cuántas vacantes le quedan a la empresa, si una vacante
 * llenó su cupo, qué etapas del pipeline habilita su plan y los números del
 * gancho. La UI los pinta; no los calcula (ADR-016). Las reglas tienen su dueña
 * en hr-engine (`domain/plan.py`, ADR-017).
 */
import type { Modality, Seniority, SiguientePaso, VacanteStatus } from "@vortex/types/hr";
import type { EtapaDelPipeline } from "@vortex/types/reglas";

/** Módulos de Vortex que el plan de la empresa habilita. Viajan en el JWT (ADR-015). */
export type Modulo = "career-site" | "cockpit";

export interface SesionEmpresa {
  usuario: { nombre: string; iniciales: string };
  empresa: { nombre: string };
  /** Nombre del plan tal como se muestra, p. ej. "Career site · gratis". */
  plan: string;
  modulos: readonly Modulo[];
}

/** Cuántas vacantes puede tener activas la empresa y cuántas le quedan. */
export interface CupoDeVacantes {
  activas: number;
  limite: number;
  libres: number;
  maxAplicacionesPorVacante: number;
}

export interface VacanteDeLaEmpresa {
  id: string;
  titulo: string;
  estado: VacanteStatus;
  modalidad: Modality;
  ubicacion: string;
  publicadaEn: string;
  aplicaciones: number;
  /** La vacante llegó al máximo de aplicaciones y dejó de recibirlas. */
  cupoCompleto: boolean;
}

export interface MisVacantes {
  vacantes: VacanteDeLaEmpresa[];
  cupo: CupoDeVacantes;
}

/** Lo que la empresa llena en "Crear empleo". */
export interface BorradorDeVacante {
  titulo: string;
  seniority: Seniority;
  modalidad: Modality;
  ubicacion: string;
  descripcion: string;
  salarioMin: number | null;
  salarioMax: number | null;
  moneda: string;
  /** Si el salario se muestra en el career site (`vacantes.salario_publico`). */
  salarioPublico: boolean;
}

/** Por qué el backend no publicó una vacante. */
export type MotivoDeRechazo = "sin-cupo" | "datos-invalidos";

export type ResultadoDePublicar =
  | { ok: true; vacanteId: string }
  | { ok: false; motivo: MotivoDeRechazo };

/**
 * Lo que los agentes encontraron en los CVs, sin identidades. Es el gancho del
 * plan gratis: la empresa ve los números, no a los candidatos.
 */
export interface GanchoDelPipeline {
  cvsEvaluados: number;
  segundos: number;
  califican: number;
  cumplenTodasLasSkills: number;
}

export interface Aplicado {
  id: string;
  nombre: string;
  aplicoEn: string;
  /** URL firmada del CV; `null` mientras el panel no esté conectado a Storage. */
  cvUrl: string | null;
}

export interface EtapaVisible {
  etapa: EtapaDelPipeline;
  /** `null` si el plan no habilita la etapa. */
  conteo: number | null;
}

export interface PipelineDeVacante {
  vacante: Pick<VacanteDeLaEmpresa, "id" | "titulo" | "publicadaEn" | "aplicaciones">;
  maxAplicaciones: number | null;
  etapas: EtapaVisible[];
  /** Los más recientes primero. */
  aplicados: Aplicado[];
  /** Solo en el plan gratis y cuando ya hubo evaluación. */
  gancho: GanchoDelPipeline | null;
}

/** De dónde vino el interés de la empresa por los servicios de IA. */
export type OrigenDelInteres = "crear-empleo" | "pipeline";

/** Fila de "mejores evaluados" del cockpit: evaluación a ciegas, sin nombre. */
export interface Evaluado {
  candidato: string;
  score: number;
  razonamiento: string;
  siguientePaso: SiguientePaso;
}
