/**
 * El panel con datos de ejemplo en memoria: la demo sin backend y los tests.
 *
 * Hace de base de datos, así que aplica a su manera las reglas del plan (cupo de
 * vacantes, publicaciones cada 30 días, tope de aplicaciones, el motivo al
 * descartar) para que la demo se comporte como el producto. Las reglas reales y sus
 * tests viven en las migraciones 0008, 0010, 0015 y 0021 y en `domain/plan.py`
 * (ADR-017, ADR-019, ADR-024). Siempre hay alguien dentro: el ejemplo no pide entrar.
 *
 * Los candidatos son inventados: nombres y apellidos comunes combinados, sin datos
 * de nadie. Están repartidos por todas las etapas, como un pipeline a medio camino.
 *
 * `?plan=ia` en la URL de entrada muestra el panel con los servicios de IA.
 */
import type { ApplicationStatus } from "@fluveai/types/hr";
import {
  LIMITES_DEL_PLAN,
  VENTANA_DE_PUBLICACIONES_DIAS,
  limiteDeVacantes,
  siguientePaso,
} from "@fluveai/types/reglas";

import type {
  AdaptadorDelPanel,
  Aplicado,
  EvaluacionConIa,
  GanchoDelPipeline,
  OrigenDelInteres,
  ResumenCockpit,
  ResumenDeEvaluaciones,
  SesionEmpresa,
  VacanteDeLaEmpresa,
} from "./tipos";

const DIA_MS = 24 * 60 * 60 * 1000;
const VENTANA_MS = VENTANA_DE_PUBLICACIONES_DIAS * DIA_MS;
const haceDias = (dias: number) => new Date(Date.now() - dias * DIA_MS).toISOString();
const haceMinutos = (minutos: number) => new Date(Date.now() - minutos * 60_000).toISOString();

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
  "Alejandro",
  "Gabriela",
  "Héctor",
  "Karla",
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
  "Rodríguez",
  "Flores",
  "Sandoval",
];

/**
 * Un nombre inventado distinto para cada uno de los primeros 180 (14 nombres y 13
 * apellidos): en cada vuelta de los nombres, los apellidos se corren un lugar.
 */
const nombreDeEjemplo = (i: number) =>
  `${NOMBRES[i % NOMBRES.length]} ${
    APELLIDOS[(i * 3 + 1 + Math.floor(i / NOMBRES.length)) % APELLIDOS.length]
  }`;

/**
 * `total` aplicados a una vacante publicada hace `dias`, repartidos en ese tiempo:
 * el primero es el más reciente. Todos en "Aplicados" hasta que `conEtapas` los mueva.
 */
function aplicadosDeEjemplo(vacanteId: string, total: number, dias: number): Aplicado[] {
  return Array.from({ length: total }, (_, i) => ({
    id: `${vacanteId}-${i + 1}`,
    nombre: nombreDeEjemplo(i),
    aplicoEn: haceMinutos(Math.round(((i + 1) * dias * 24 * 60) / (total + 1))),
    estado: "applied",
    cvUrl: null,
    cvFormato: i % 5 === 3 ? "docx" : "pdf",
    evaluacion: null,
  }));
}

/** La letra de cada etapa en los repartos de `estadoGratis`. */
const ETAPA_DE_LA_LETRA: Record<string, ApplicationStatus> = {
  A: "applied",
  R: "evaluated",
  P: "shortlisted",
  E: "interviewed",
  O: "offered",
  C: "hired",
  D: "rejected",
  X: "withdrawn",
};

/**
 * Pone a cada aplicado en su etapa, como lo dejaría una persona que revisa seguido:
 * `reparto` tiene una letra por aplicado, del más reciente al que aplicó primero
 * (A Aplicados, R Revisados, P Preseleccionados, E En entrevista, O Con oferta,
 * C Contratados, D Descartados, X Se retiraron). Los espacios solo agrupan de 10 en 10.
 */
function conEtapas(aplicados: Aplicado[], reparto: string): Aplicado[] {
  const letras = reparto.replace(/\s+/g, "");
  if (letras.length !== aplicados.length) {
    throw new Error(`el reparto tiene ${letras.length} letras para ${aplicados.length} aplicados`);
  }
  return aplicados.map((a, i) => ({
    ...a,
    estado: ETAPA_DE_LA_LETRA[letras.charAt(i)] ?? a.estado,
  }));
}

/** Lo que diría la IA de un backend: tres tramos, como la calibración del SKILL.md. */
function evaluacionDeEjemplo(score: number): EvaluacionConIa {
  const [razonamiento, fortalezas, brechas] =
    score >= 7
      ? [
          "Lleva cinco años con Python y FastAPI en productos con varias empresas en la misma base, y migró un monolito a servicios.",
          ["Python", "FastAPI", "Postgres"],
          ["Celery en producción"],
        ]
      : score >= 4
        ? [
            "Tiene buena base de backend con Python, pero casi no ha trabajado con sistemas multiempresa ni con colas de tareas.",
            ["Python"],
            ["Multiempresa", "Celery"],
          ]
        : [
            "Su experiencia es sobre todo de frontend con React; el puesto pide backend con Python.",
            ["React"],
            ["Python", "FastAPI"],
          ];
  return { score, razonamiento, fortalezas, brechas, siguientePaso: siguientePaso(score) };
}

/** Las primeras `evaluadas` aplicaciones ya pasaron por la IA, de más a menos encaje. */
function conEvaluaciones(aplicados: Aplicado[], evaluadas: number): Aplicado[] {
  return aplicados.map((a, i) =>
    i < evaluadas
      ? {
          ...a,
          estado: "evaluated",
          evaluacion: evaluacionDeEjemplo(Math.round((9.4 - i * 0.15) * 10) / 10),
        }
      : a,
  );
}

/**
 * De los evaluados con menos de 7, que no cuentan en la decisión del día del
 * cockpit, una persona preseleccionó a 9, entrevistó a 1 y le hizo oferta a 2: el
 * mismo embudo que muestra el cockpit.
 */
function movidosAMano(aplicados: Aplicado[]): Aplicado[] {
  const movidos: ApplicationStatus[] = [
    ...Array.from({ length: 9 }, () => "shortlisted" as const),
    "interviewed",
    "offered",
    "offered",
  ];
  return aplicados.map((a, i) => ({ ...a, estado: movidos[i - 17] ?? a.estado }));
}

interface Registro {
  vacante: VacanteDeLaEmpresa;
  aplicados: Aplicado[];
  gancho: GanchoDelPipeline | null;
  /** Cómo va la evaluación con IA (plan con IA). */
  evaluaciones?: ResumenDeEvaluaciones;
}

interface Estado {
  sesion: SesionEmpresa;
  limite: number | null;
  maxAplicaciones: number | null;
  registros: Registro[];
  interes: OrigenDelInteres[];
  /** Las vacantes cuyas postulaciones se abrieron, en orden. */
  vistas: string[];
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
    moderacion: "publicada",
    motivos: [],
    ...extra,
  };
}

function estadoGratis(): Estado {
  return {
    sesion: {
      usuario: { nombre: "Mariana", iniciales: "MV" },
      empresa: { nombre: "Andes Logística" },
      plan: "Bolsa de empleo · gratis",
      modulos: ["career-site"],
      publicaParaClientes: false,
    },
    // Andes Logística tiene 80 personas: 4 vacantes activas (la regla es de `domain/plan.py`).
    limite: limiteDeVacantes(80),
    maxAplicaciones: LIMITES_DEL_PLAN.gratis.aplicacionesPorVacante,
    interes: [],
    vistas: [],
    registros: [
      {
        vacante: vacante("coordinador-de-almacen", "Coordinador de almacén", 6, 47),
        // 21 en Aplicados, 9 Revisados, 5 Preseleccionados, 3 En entrevista, 1 Con
        // oferta, 1 Contratado y 7 Descartados.
        aplicados: conEtapas(
          aplicadosDeEjemplo("coordinador-de-almacen", 47, 6),
          "AARADARPAA RAADRAPARA AAPDRARDEA DAPRAEARDA EAPDOAC",
        ),
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
        // Casi cerrada: 1 Contratado, 1 que se retiró y 30 Descartados.
        aplicados: conEtapas(
          aplicadosDeEjemplo("analista-de-inventarios", 50, 40),
          "ADARDDRADD DRDDADPDDR DDADDPDRDD DEDDADDRDD DPDXDEDACD",
        ),
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
        // Recién publicada: casi todos esperan su primera revisión.
        aplicados: conEtapas(aplicadosDeEjemplo("chofer-repartidor", 12, 1), "AARAADARAP RA"),
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
      publicaParaClientes: false,
    },
    limite: null,
    maxAplicaciones: LIMITES_DEL_PLAN.ia.aplicacionesPorVacante,
    interes: [],
    vistas: [],
    registros: [
      {
        vacante: vacante("senior-software-engineer", "Senior Software Engineer", 9, 84, {
          modalidad: "remote",
          ubicacion: "Remoto · LATAM",
          cupoCompleto: false,
        }),
        aplicados: movidosAMano(
          conEvaluaciones(aplicadosDeEjemplo("senior-software-engineer", 84, 9), 41),
        ),
        gancho: null,
        evaluaciones: {
          aplicaciones: 84,
          evaluadas: 41,
          enEspera: 40,
          sinEvaluar: 1,
          ilegibles: 2,
          sinIa: 0,
        },
      },
    ],
  };
}

/**
 * El cockpit de Grupo Cobalto: su única vacante con las 84 aplicaciones del pipeline de
 * ejemplo, de las que la IA evaluó 41. Los tres mejores son los mismos que ahí.
 */
function resumenDelCockpit(): ResumenCockpit {
  const vacante = { id: "senior-software-engineer", titulo: "Senior Software Engineer" };
  const { razonamiento } = evaluacionDeEjemplo(9);
  return {
    decision: { tipo: "entrevistar", vacante, listos: 17, scores: [9.4, 9.3, 9.1] },
    decisionesPendientes: 2,
    candidatosEnProceso: { total: 84, nuevos24h: 8 },
    vacantesPublicadas: { total: 1, nuevas7d: 0 },
    evaluaciones24h: { total: 27, porcentajeSinError: 96 },
    enEspera: { total: 40, topeAlcanzado: false },
    cvsDelMes: { evaluados: 41, tope: 1000, porcentajeDelTope: 4 },
    vacante,
    mejoresEvaluados: {
      total: 41,
      filas: [
        { id: `${vacante.id}-1`, candidato: "María Fernanda Ramírez", score: 9.4 },
        { id: `${vacante.id}-2`, candidato: "José Luis Herrera", score: 9.3 },
        { id: `${vacante.id}-3`, candidato: "Ana Sofía Villarreal", score: 9.1 },
      ].map((f) => ({ ...f, razonamiento, siguientePaso: siguientePaso(f.score) })),
    },
    embudo: { applied: 84, evaluated: 41, shortlisted: 12, interviewed: 3, offered: 2 },
    registro: [
      { id: "run-3", en: haceMinutos(12), vacante: vacante.titulo, score: 8.5 },
      { id: "run-2", en: haceMinutos(47), vacante: vacante.titulo, score: 6.1 },
      { id: "run-1", en: haceMinutos(95), vacante: vacante.titulo, score: null },
    ].map((e) => ({ ...e, agente: "cv-evaluator", aplazada: e.score === null })),
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

/** Para los tests: las vacantes cuyas postulaciones se abrieron, en orden. */
export const postulacionesVistasDelEjemplo = (): readonly string[] => [...estado.vistas];

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
        // Sin hr-engine que la modere: en el ejemplo se publica al instante.
        moderacion: "publicada",
        motivos: [],
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
    const { vacante: v } = registro;
    const conIa = estado.sesion.modulos.includes("cockpit");
    return {
      vacante: {
        id: v.id,
        titulo: v.titulo,
        publicadaEn: v.publicadaEn,
        aplicaciones: v.aplicaciones,
        moderacion: v.moderacion,
        motivos: v.motivos,
      },
      maxAplicaciones: estado.maxAplicaciones,
      aplicados: registro.aplicados,
      gancho: registro.gancho,
      evaluaciones: conIa
        ? (registro.evaluaciones ?? {
            aplicaciones: v.aplicaciones,
            evaluadas: 0,
            enEspera: v.aplicaciones,
            sinEvaluar: 0,
            ilegibles: 0,
            sinIa: 0,
          })
        : null,
    };
  },

  async obtenerResumenCockpit() {
    return estado.sesion.modulos.includes("cockpit") ? resumenDelCockpit() : null;
  },

  /** Como la base (0021): solo se mueve lo que existe. La fecha y el motivo no se muestran. */
  async moverDeEtapa(aplicacionId, etapa) {
    const registro = estado.registros.find((r) => r.aplicados.some((a) => a.id === aplicacionId));
    if (!registro) throw new Error("la aplicación no es de la empresa o ya no existe");
    registro.aplicados = registro.aplicados.map((a) =>
      a.id === aplicacionId ? { ...a, estado: etapa } : a,
    );
  },

  /**
   * Como la base (0015, 0021): lo que evaluó la IA no se descarta sin un motivo, y
   * un motivo escrito mide de 10 a 500 caracteres. Sin IA, el motivo es opcional.
   */
  async descartar(aplicacionId, motivo) {
    for (const registro of estado.registros) {
      const aplicado = registro.aplicados.find((a) => a.id === aplicacionId);
      if (!aplicado) continue;
      const largo = motivo.trim().length;
      if ((aplicado.evaluacion && largo === 0) || (largo > 0 && (largo < 10 || largo > 500))) {
        return { ok: false, motivo: "sin-motivo" };
      }
      registro.aplicados = registro.aplicados.map((a) =>
        a.id === aplicacionId ? { ...a, estado: "rejected" } : a,
      );
    }
    return { ok: true };
  },

  /** El ejemplo no tiene archivos que bajar. */
  async solicitarDescargaDeCvs() {
    return { url: null, motivo: "ejemplo" };
  },

  async registrarInteres(origen) {
    estado.interes.push(origen);
  },

  async marcarPostulacionesVistas(vacanteId) {
    estado.vistas.push(vacanteId);
  },

  async entrar() {
    return { ok: true };
  },

  async verificarCodigo() {
    return { ok: true };
  },

  async salir() {},

  // El área de admin necesita el hr-engine: con datos de ejemplo no hay sesión que mandarle.
  async tokenDeAcceso() {
    return null;
  },

  alCambiarLaSesion() {
    return () => {};
  },
};
