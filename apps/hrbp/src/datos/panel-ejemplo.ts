/**
 * El panel con datos de ejemplo en memoria: la demo sin backend y los tests.
 *
 * Hace de base de datos, así que aplica a su manera las reglas del plan (cupo de
 * vacantes, publicaciones cada 30 días, tope de aplicaciones) para que la demo se
 * comporte como el producto. Las reglas reales y sus tests viven en las
 * migraciones 0008 y 0010 y en `domain/plan.py` (ADR-017, ADR-019). Siempre hay
 * alguien dentro: el ejemplo no pide entrar.
 *
 * `?plan=ia` en la URL de entrada muestra el panel con los servicios de IA.
 */
import type { EtapaDelPipeline } from "@vortex/types/reglas";
import {
  ETAPAS_DEL_PIPELINE,
  LIMITES_DEL_PLAN,
  VENTANA_DE_PUBLICACIONES_DIAS,
  limiteDeVacantes,
} from "@vortex/types/reglas";

import type {
  AdaptadorDelPanel,
  Aplicado,
  GanchoDelPipeline,
  OrigenDelInteres,
  SesionEmpresa,
  VacanteDeLaEmpresa,
} from "./tipos";

const DIA_MS = 24 * 60 * 60 * 1000;
const VENTANA_MS = VENTANA_DE_PUBLICACIONES_DIAS * DIA_MS;
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
    cvFormato: "pdf",
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
        gancho: {
          skills: 4,
          revisados: 45,
          enEspera: 2,
          ilegibles: 0,
          conLaMayoria: 13,
          conTodas: 6,
        },
      },
      {
        vacante: vacante("analista-de-inventarios", "Analista de inventarios", 40, 50, {
          modalidad: "onsite",
        }),
        aplicados: aplicadosDeEjemplo("analista-de-inventarios", 50),
        gancho: {
          skills: 5,
          revisados: 50,
          enEspera: 0,
          ilegibles: 0,
          conLaMayoria: 17,
          conTodas: 9,
        },
      },
      {
        vacante: vacante("chofer-repartidor", "Chofer repartidor", 1, 12, {
          modalidad: "onsite",
          ubicacion: "Apodaca, NL",
        }),
        aplicados: aplicadosDeEjemplo("chofer-repartidor", 12),
        gancho: {
          skills: 3,
          revisados: 10,
          enEspera: 2,
          ilegibles: 0,
          conLaMayoria: 4,
          conTodas: 2,
        },
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

/** Fechas de las vacantes publicadas en la ventana de 30 días, la más vieja primero. */
const publicacionesRecientes = () =>
  estado.registros
    .map((r) => r.vacante.publicadaEn)
    .filter((fecha) => Date.parse(fecha) > Date.now() - VENTANA_MS)
    .sort();

export const adaptadorDeEjemplo: AdaptadorDelPanel = {
  async obtenerSesion() {
    return estado.sesion;
  },

  async listarMisVacantes() {
    const vacantes = activos()
      .map((r) => r.vacante)
      .sort((a, b) => b.publicadaEn.localeCompare(a.publicadaEn));
    const { limite } = estado;
    const recientes = publicacionesRecientes();
    const [primera] = recientes;
    return {
      vacantes,
      cupo: {
        activas: vacantes.length,
        limite,
        libres: limite === null ? null : Math.max(0, limite - vacantes.length),
        maxAplicacionesPorVacante: estado.maxAplicaciones,
        publicacionesLibres: limite === null ? null : Math.max(0, limite - recientes.length),
        proximaPublicacion:
          limite !== null && primera && recientes.length >= limite
            ? new Date(Date.parse(primera) + VENTANA_MS).toISOString()
            : null,
      },
    };
  },

  async publicarVacante(borrador) {
    const { limite } = estado;
    if (limite !== null && activos().length >= limite) {
      return { ok: false, motivo: "sin-cupo" };
    }
    if (limite !== null && publicacionesRecientes().length >= limite) {
      return { ok: false, motivo: "sin-publicaciones" };
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
      // Como `resumen_del_gancho()`: en el plan gratis hay gancho aunque no haya CVs.
      gancho: estado.sesion.modulos.includes("cockpit")
        ? null
        : {
            skills: borrador.skills.length,
            revisados: 0,
            enEspera: 0,
            ilegibles: 0,
            conLaMayoria: 0,
            conTodas: 0,
          },
    });
    return { ok: true, vacanteId: id };
  },

  /** Borrado lógico: la vacante sale del career site y libera su cupo, no su publicación. */
  async eliminarVacante(vacanteId) {
    const registro = estado.registros.find((r) => r.vacante.id === vacanteId);
    if (registro) registro.vacante = { ...registro.vacante, estado: "closed" };
  },

  async obtenerPipeline(vacanteId) {
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
  },

  /** El ejemplo no tiene archivos que bajar. */
  async solicitarDescargaDeCvs() {
    return { url: null, motivo: "ejemplo" };
  },

  async registrarInteres(origen) {
    estado.interes.push(origen);
  },

  async entrar() {
    return { ok: true };
  },

  async salir() {},

  alCambiarLaSesion() {
    return () => {};
  },
};
