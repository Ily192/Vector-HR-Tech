/**
 * Forma de los datos que el panel de la empresa recibe del backend.
 *
 * Todo llega ya decidido: cuántas vacantes le quedan a la empresa, si una vacante
 * llenó su cupo, qué etapas del pipeline habilita su plan y los números del
 * gancho. La UI los pinta; no los calcula (ADR-016). Las reglas tienen su dueña
 * en hr-engine (`domain/plan.py`, ADR-017).
 */
import type {
  ApplicationStatus,
  Modality,
  Seniority,
  SiguientePaso,
  VacanteStatus,
} from "@vortex/types/hr";
import type { EtapaDelPipeline, Modulo } from "@vortex/types/reglas";

export type { Modulo };

export interface SesionEmpresa {
  usuario: { nombre: string; iniciales: string };
  empresa: { nombre: string };
  /** Nombre del plan tal como se muestra, p. ej. "Career site · gratis". */
  plan: string;
  modulos: readonly Modulo[];
}

/**
 * Cuántas vacantes puede tener activas la empresa y cuántas le quedan, tal como
 * las devuelve `mi_cupo_de_vacantes()` (migración 0008). `null` = sin tope: el
 * plan con IA no los tiene.
 */
export interface CupoDeVacantes {
  activas: number;
  limite: number | null;
  libres: number | null;
  maxAplicacionesPorVacante: number | null;
  /** Vacantes nuevas que puede publicar en la ventana de 30 días (0010). */
  publicacionesLibres: number | null;
  /** Cuándo se libera la próxima publicación, si ya no le queda ninguna. */
  proximaPublicacion: string | null;
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
  /** Skills que pide la vacante (hasta 15): el gancho cuenta cuántos CVs las mencionan. */
  skills: string[];
}

/** Por qué el backend no publicó una vacante. */
export type MotivoDeRechazo = "sin-cupo" | "sin-publicaciones" | "datos-invalidos";

export type ResultadoDePublicar =
  | { ok: true; vacanteId: string }
  | { ok: false; motivo: MotivoDeRechazo };

/**
 * Cuántos CVs mencionan las skills de la vacante, sin IA y sin identidades
 * (`resumen_del_gancho()`, ADR-019). Es el gancho del plan gratis: la empresa ve
 * los números, no a los candidatos.
 */
export interface GanchoDelPipeline {
  /** Skills que pide la vacante. Con 0 no hay nada que contar. */
  skills: number;
  /** CVs revisados, de 5 en 5. */
  revisados: number;
  enEspera: number;
  /** CVs que no se pudieron leer: escaneados, protegidos o dañados. */
  ilegibles: number;
  /** Mencionan más de la mitad de las skills (incluye a los que las mencionan todas). */
  conLaMayoria: number;
  conTodas: number;
}

/**
 * Lo que la IA del plan de pago dijo de un CV (ADR-021), a ciegas: el modelo no vio
 * el nombre ni el contacto.
 */
export interface EvaluacionConIa {
  /** De 0 a 10. */
  score: number;
  razonamiento: string;
  fortalezas: string[];
  brechas: string[];
  /** La sugiere la política del dominio según el score; decide una persona. */
  siguientePaso: SiguientePaso;
}

export interface Aplicado {
  id: string;
  nombre: string;
  aplicoEn: string;
  estado: ApplicationStatus;
  /** URL firmada del CV; `null` si no se pudo firmar o con datos de ejemplo. */
  cvUrl: string | null;
  /** `null` si la aplicación llegó sin CV. */
  cvFormato: "pdf" | "docx" | null;
  /** `null` si no la evaluó la IA: plan gratis, en espera o el candidato se opuso. */
  evaluacion: EvaluacionConIa | null;
}

/** Cómo va la evaluación con IA de una vacante (`resumen_de_evaluaciones()`, 0014). */
export interface ResumenDeEvaluaciones {
  aplicaciones: number;
  evaluadas: number;
  /** Las que el barrido todavía va a tomar. */
  enEspera: number;
  /** Fallaron sus intentos: hay que revisarlas a mano. */
  sinEvaluar: number;
  /** CVs escaneados, protegidos o dañados. */
  ilegibles: number;
  /** Candidatos que pidieron no ser evaluados con procesos automatizados. */
  sinIa: number;
}

/** El descarte se guardó, o faltó el motivo que la base pide si evaluó la IA (0015). */
export type ResultadoDeDescartar = { ok: true } | { ok: false; motivo: "sin-motivo" };

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
  /** Solo en el plan con IA. */
  evaluaciones: ResumenDeEvaluaciones | null;
}

/**
 * El .zip con los CVs de una vacante, ya armado en el navegador: `url` es una URL
 * de objeto (`blob:`). `omitidos`: CVs que no se pudieron bajar y no van dentro.
 */
export type DescargaDeCvs =
  | { url: string; nombre: string; omitidos: number }
  | { url: null; motivo: "sin-cvs" | "ejemplo" };

/**
 * Resultado de pedir el enlace para entrar. `ok` no dice que el correo tenga
 * cuenta: la respuesta es la misma para no revelar quién usa el panel.
 */
export type ResultadoDeEntrar =
  | { ok: true }
  | { ok: false; motivo: "demasiados-intentos" | "error" };

/** La cuenta entró, pero no es de HR o Dirección de una empresa. */
export class SinAccesoAlPanel extends Error {
  constructor() {
    super("la cuenta no es de HR o Dirección de una empresa");
    this.name = "SinAccesoAlPanel";
  }
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

/**
 * Lo que el panel necesita del backend. Lo implementan el ejemplo en memoria
 * (`panel-ejemplo.ts`) y Supabase (`panel-supabase.ts`); `panel.ts` elige.
 */
export interface AdaptadorDelPanel {
  /** La sesión de la empresa, o `null` si nadie entró. */
  obtenerSesion(): Promise<SesionEmpresa | null>;
  listarMisVacantes(): Promise<MisVacantes>;
  publicarVacante(borrador: BorradorDeVacante): Promise<ResultadoDePublicar>;
  eliminarVacante(vacanteId: string): Promise<void>;
  obtenerPipeline(vacanteId: string): Promise<PipelineDeVacante | null>;
  /** Una persona descarta una aplicación y deja el motivo (ADR-021 §4). */
  descartar(aplicacionId: string, motivo: string): Promise<ResultadoDeDescartar>;
  solicitarDescargaDeCvs(vacanteId: string): Promise<DescargaDeCvs>;
  registrarInteres(origen: OrigenDelInteres): Promise<void>;
  entrar(correo: string): Promise<ResultadoDeEntrar>;
  salir(): Promise<void>;
  /** Avisa cuando alguien entra o sale. Devuelve cómo dejar de escuchar. */
  alCambiarLaSesion(avisar: () => void): () => void;
}
