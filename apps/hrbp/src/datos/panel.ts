/**
 * Datos del panel de la empresa: lo único que habrá que cambiar para leer el
 * backend real.
 *
 * Hoy es un adaptador de ejemplo en memoria con la forma de `tipos.ts`. Hace de
 * hr-engine, así que aplica a su manera las reglas del plan (cupo de vacantes,
 * tope de aplicaciones) para que la demo se comporte como el producto; la regla
 * real y su test viven en `domain/plan.py` (ADR-017). Las pantallas no saben que
 * es un ejemplo: solo ven `ES_DE_EJEMPLO` para avisarlo.
 *
 * `?plan=ia` en la URL de entrada muestra el panel con los servicios de IA.
 */
import type { EtapaDelPipeline } from "@vortex/types/reglas";
import { ETAPAS_DEL_PIPELINE, LIMITES_DEL_PLAN, limiteDeVacantes } from "@vortex/types/reglas";

import type {
  Aplicado,
  BorradorDeVacante,
  GanchoDelPipeline,
  MisVacantes,
  OrigenDelInteres,
  PipelineDeVacante,
  ResultadoDePublicar,
  SesionEmpresa,
  VacanteDeLaEmpresa,
} from "./tipos";

/** `true` mientras los datos sean de ejemplo; las pantallas lo avisan. */
export const ES_DE_EJEMPLO = true;

const DIA_MS = 24 * 60 * 60 * 1000;
const haceDias = (dias: number, horas = 0) =>
  new Date(Date.now() - dias * DIA_MS - horas * 3_600_000).toISOString();

const NOMBRES = [
  "María Fernanda",
  "José Luis",
  "Ana Sofía",
  "Carlos Eduardo",
  "Daniela",
  "Jorge",
  "Valeria",
  "Luis Ángel",
  "Paola",
  "Ricardo",
];
const APELLIDOS = [
  "López",
  "Ramírez",
  "Treviño",
  "Garza",
  "Herrera",
  "Salinas",
  "Cantú",
  "Villarreal",
  "Ortiz",
  "Méndez",
];

function aplicadosDeEjemplo(vacanteId: string, total: number): Aplicado[] {
  return Array.from({ length: total }, (_, i) => ({
    id: `${vacanteId}-${i + 1}`,
    nombre: `${NOMBRES[i % NOMBRES.length]} ${APELLIDOS[(i * 3 + 1) % APELLIDOS.length]}`,
    aplicoEn: haceDias(0, i * 3 + 1),
    cvUrl: null,
  }));
}

interface Registro {
  vacante: VacanteDeLaEmpresa;
  aplicados: Aplicado[];
  gancho: GanchoDelPipeline | null;
  /** Conteos de las etapas después de "Aplicados" (plan con IA). */
  etapas?: Partial<Record<EtapaDelPipeline, number>>;
}

interface Estado {
  sesion: SesionEmpresa;
  limite: number | null;
  maxAplicaciones: number | null;
  registros: Registro[];
  interes: OrigenDelInteres[];
}

function vacante(
  id: string,
  titulo: string,
  dias: number,
  aplicaciones: number,
  extra: Partial<VacanteDeLaEmpresa> = {},
): VacanteDeLaEmpresa {
  return {
    id,
    titulo,
    estado: "open",
    modalidad: "hybrid",
    ubicacion: "Monterrey, NL",
    publicadaEn: haceDias(dias),
    aplicaciones,
    cupoCompleto: aplicaciones >= LIMITES_DEL_PLAN.gratis.aplicacionesPorVacante,
    ...extra,
  };
}

function estadoGratis(): Estado {
  return {
    sesion: {
      usuario: { nombre: "Mariana", iniciales: "MV" },
      empresa: { nombre: "Andes Logística" },
      plan: "Career site · gratis",
      modulos: ["career-site"],
    },
    // Andes Logística tiene 80 personas: 4 vacantes activas (la regla es de `domain/plan.py`).
    limite: limiteDeVacantes(80),
    maxAplicaciones: LIMITES_DEL_PLAN.gratis.aplicacionesPorVacante,
    interes: [],
    registros: [
      {
        vacante: vacante("coordinador-de-almacen", "Coordinador de almacén", 6, 47),
        aplicados: aplicadosDeEjemplo("coordinador-de-almacen", 47),
        gancho: { cvsEvaluados: 47, segundos: 38, califican: 13, cumplenTodasLasSkills: 6 },
      },
      {
        vacante: vacante("analista-de-inventarios", "Analista de inventarios", 12, 50, {
          modalidad: "onsite",
        }),
        aplicados: aplicadosDeEjemplo("analista-de-inventarios", 50),
        gancho: { cvsEvaluados: 50, segundos: 41, califican: 17, cumplenTodasLasSkills: 9 },
      },
      {
        vacante: vacante("chofer-repartidor", "Chofer repartidor", 1, 12, {
          modalidad: "onsite",
          ubicacion: "Apodaca, NL",
        }),
        aplicados: aplicadosDeEjemplo("chofer-repartidor", 12),
        gancho: { cvsEvaluados: 12, segundos: 11, califican: 4, cumplenTodasLasSkills: 2 },
      },
    ],
  };
}

function estadoConIa(): Estado {
  return {
    sesion: {
      usuario: { nombre: "Ilyra", iniciales: "IR" },
      empresa: { nombre: "Grupo Cobalto" },
      plan: "Servicios de IA",
      modulos: ["cockpit", "career-site"],
    },
    limite: null,
    maxAplicaciones: LIMITES_DEL_PLAN.ia.aplicacionesPorVacante,
    interes: [],
    registros: [
      {
        vacante: vacante("senior-software-engineer", "Senior Software Engineer", 9, 84, {
          modalidad: "remote",
          ubicacion: "Remoto · LATAM",
          cupoCompleto: false,
        }),
        aplicados: aplicadosDeEjemplo("senior-software-engineer", 84),
        gancho: null,
        etapas: { evaluated: 41, shortlisted: 12, interviewed: 3, offered: 2 },
      },
    ],
  };
}

function estadoInicial(): Estado {
  const plan = new URLSearchParams(window.location.search).get("plan");
  return plan === "ia" ? estadoConIa() : estadoGratis();
}

let estado = estadoInicial();

/** Vuelve al estado de entrada. Solo para tests. */
export function reiniciarDatosDeEjemplo() {
  estado = estadoInicial();
}

const activos = () => estado.registros.filter((r) => r.vacante.estado === "open");

export async function obtenerSesion(): Promise<SesionEmpresa> {
  return estado.sesion;
}

export async function listarMisVacantes(): Promise<MisVacantes> {
  const vacantes = activos()
    .map((r) => r.vacante)
    .sort((a, b) => b.publicadaEn.localeCompare(a.publicadaEn));
  return {
    vacantes,
    cupo: {
      activas: vacantes.length,
      limite: estado.limite,
      libres: estado.limite === null ? null : Math.max(0, estado.limite - vacantes.length),
      maxAplicacionesPorVacante: estado.maxAplicaciones,
    },
  };
}

export async function publicarVacante(borrador: BorradorDeVacante): Promise<ResultadoDePublicar> {
  if (estado.limite !== null && activos().length >= estado.limite) {
    return { ok: false, motivo: "sin-cupo" };
  }
  if (!borrador.titulo.trim() || !borrador.descripcion.trim()) {
    return { ok: false, motivo: "datos-invalidos" };
  }
  const id = `${borrador.titulo
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")}-${estado.registros.length + 1}`;
  estado.registros.push({
    vacante: {
      id,
      titulo: borrador.titulo.trim(),
      estado: "open",
      modalidad: borrador.modalidad,
      ubicacion: borrador.ubicacion.trim(),
      publicadaEn: new Date().toISOString(),
      aplicaciones: 0,
      cupoCompleto: false,
    },
    aplicados: [],
    gancho: null,
  });
  return { ok: true, vacanteId: id };
}

/** Borrado lógico: la vacante sale del career site y libera su cupo. */
export async function eliminarVacante(vacanteId: string): Promise<void> {
  const registro = estado.registros.find((r) => r.vacante.id === vacanteId);
  if (registro) registro.vacante = { ...registro.vacante, estado: "closed" };
}

export async function obtenerPipeline(vacanteId: string): Promise<PipelineDeVacante | null> {
  const registro = activos().find((r) => r.vacante.id === vacanteId);
  if (!registro) return null;
  const { vacante: v, etapas } = registro;
  const conIa = estado.sesion.modulos.includes("cockpit");
  return {
    vacante: {
      id: v.id,
      titulo: v.titulo,
      publicadaEn: v.publicadaEn,
      aplicaciones: v.aplicaciones,
    },
    maxAplicaciones: estado.maxAplicaciones,
    etapas: ETAPAS_DEL_PIPELINE.map((etapa) => ({
      etapa,
      conteo: etapa === "applied" ? v.aplicaciones : conIa ? (etapas?.[etapa] ?? 0) : null,
    })),
    aplicados: registro.aplicados,
    gancho: registro.gancho,
  };
}

/**
 * Pide el .zip con los CVs de una vacante. El real devolverá una URL firmada
 * de Storage; el ejemplo no tiene archivos y devuelve `null`.
 */
export async function solicitarDescargaDeCvs(_vacanteId: string): Promise<{ url: string | null }> {
  return { url: null };
}

/** Avisa a Vector HR que la empresa quiere saber de los servicios de IA. */
export async function registrarInteres(origen: OrigenDelInteres): Promise<void> {
  estado.interes.push(origen);
}
