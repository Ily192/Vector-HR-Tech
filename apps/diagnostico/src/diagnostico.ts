/**
 * El diagnóstico gratuito: las preguntas y el cálculo, sin React ni red.
 *
 * El cálculo es deliberadamente simple y se le explica entero al prospecto: las horas
 * por semana las pone él, y lo único nuestro son los porcentajes recuperables de cada
 * etapa (PORCENTAJE_RECUPERABLE), que son supuestos conservadores para dimensionar, no
 * resultados medidos en clientes.
 */

export type Etapa = "Digitalizar" | "Optimizar" | "Automatizar";

export interface Proceso {
  id: string;
  nombre: string;
  /** Lo que se le pregunta: las horas de todo el equipo, no de una persona. */
  pregunta: string;
}

export const PROCESOS: readonly Proceso[] = [
  {
    id: "reclutamiento",
    nombre: "Reclutamiento y filtro de CVs",
    pregunta: "publicar vacantes, leer CVs y agendar entrevistas",
  },
  {
    id: "altas",
    nombre: "Altas, onboarding y expedientes",
    pregunta: "dar de alta a la gente nueva, pedir documentos y armar expedientes",
  },
  {
    id: "asistencia",
    nombre: "Asistencia, incidencias y prenómina",
    pregunta: "revisar asistencias, faltas e incidencias antes de la nómina",
  },
  {
    id: "solicitudes",
    nombre: "Solicitudes internas",
    pregunta: "atender vacaciones, permisos, constancias y dudas del equipo",
  },
  {
    id: "comercial",
    nombre: "Seguimiento comercial y cotizaciones",
    pregunta: "dar seguimiento a prospectos, armar cotizaciones y perseguir respuestas",
  },
  {
    id: "reportes",
    nombre: "Reportes y captura entre sistemas",
    pregunta: "pasar datos de un lado a otro y armar reportes",
  },
];

/** Rangos de horas por semana; el valor es el punto medio que entra al cálculo. */
export const RANGOS_HORAS = [
  { valor: 0.5, etiqueta: "Menos de 1 h" },
  { valor: 2, etiqueta: "1 a 3 h" },
  { valor: 4.5, etiqueta: "3 a 6 h" },
  { valor: 8, etiqueta: "6 a 10 h" },
  { valor: 15, etiqueta: "10 a 20 h" },
  { valor: 25, etiqueta: "Más de 20 h" },
] as const;

/**
 * Qué parte de las horas de un proceso se puede recuperar según la etapa en la que
 * está. Supuestos conservadores de Vector HR Tech, a la vista del prospecto.
 */
export const PORCENTAJE_RECUPERABLE: Record<Etapa, number> = {
  Digitalizar: 0.2,
  Optimizar: 0.3,
  Automatizar: 0.5,
};

export const QUE_SIGNIFICA: Record<Etapa, string> = {
  Digitalizar:
    "Hoy vive en papel, en chats sueltos o en hojas de cálculo. El primer paso es sacarlo a un registro único donde todos vean lo mismo.",
  Optimizar:
    "Ya está en un sistema, pero cada quien lo hace a su manera. Conviene definir los pasos, quitar esperas y dobles capturas.",
  Automatizar:
    "Está en un sistema y con pasos definidos: un agente de IA puede ejecutarlo de principio a fin, con tus reglas y aprobaciones.",
};

/** Semanas promedio por mes (52 / 12). */
export const SEMANAS_POR_MES = 52 / 12;

export type Pregunta =
  | {
      tipo: "una";
      id: string;
      titulo: string;
      ayuda?: string;
      opciones: readonly { valor: string; etiqueta: string }[];
    }
  | {
      tipo: "varias";
      id: string;
      titulo: string;
      ayuda?: string;
      opciones: readonly { valor: string; etiqueta: string }[];
    };

const opcionesDeProcesos = PROCESOS.map((p) => ({ valor: p.id, etiqueta: p.nombre }));

export const PREGUNTAS: readonly Pregunta[] = [
  {
    tipo: "una",
    id: "equipo",
    titulo: "¿Cuántas personas trabajan en tu empresa?",
    opciones: [
      { valor: "1-10", etiqueta: "1 a 10" },
      { valor: "11-50", etiqueta: "11 a 50" },
      { valor: "51-200", etiqueta: "51 a 200" },
      { valor: "201+", etiqueta: "Más de 200" },
    ],
  },
  ...PROCESOS.map(
    (p): Pregunta => ({
      tipo: "una",
      id: `horas.${p.id}`,
      titulo: `¿Cuántas horas a la semana se van en ${p.pregunta}?`,
      ayuda: "Suma las de todo el equipo, no solo las tuyas.",
      opciones: RANGOS_HORAS.map((r) => ({ valor: String(r.valor), etiqueta: r.etiqueta })),
    }),
  ),
  {
    tipo: "varias",
    id: "en_sistema",
    titulo: "¿Cuáles de estos procesos ya viven en un sistema?",
    ayuda:
      "Un software o plataforma donde queda el registro. Papel, WhatsApp suelto o Excel no cuentan.",
    opciones: opcionesDeProcesos,
  },
  {
    tipo: "varias",
    id: "pasos_definidos",
    titulo: "¿Cuáles tienen pasos definidos que todos siguen igual?",
    ayuda: "Aunque no estén escritos: si cualquiera lo haría de la misma forma, cuenta.",
    opciones: opcionesDeProcesos,
  },
  {
    tipo: "una",
    id: "canal",
    titulo: "¿Por dónde te piden las cosas tu equipo y tus clientes?",
    opciones: [
      { valor: "whatsapp", etiqueta: "WhatsApp" },
      { valor: "correo", etiqueta: "Correo" },
      { valor: "chat", etiqueta: "Teams, Slack o Google Chat" },
      { valor: "presencial", etiqueta: "En persona o por teléfono" },
    ],
  },
  {
    tipo: "una",
    id: "objetivo",
    titulo: "¿Qué te gustaría lograr primero?",
    opciones: [
      { valor: "tiempo", etiqueta: "Recuperar tiempo del equipo" },
      { valor: "errores", etiqueta: "Menos errores y retrabajo" },
      { valor: "visibilidad", etiqueta: "Ver en qué va cada proceso" },
      { valor: "crecer", etiqueta: "Crecer sin contratar al mismo ritmo" },
    ],
  },
];

/** Respuesta de una pregunta "una": el valor; de una "varias": la lista de valores. */
export type Respuestas = Record<string, string | string[]>;

export interface ProcesoEvaluado {
  id: string;
  nombre: string;
  horasSemana: number;
  etapa: Etapa;
  horasRecuperablesMes: number;
}

export interface Resultado {
  version: 1;
  /** De mayor a menor; los tres primeros son el top que se recomienda. */
  procesos: ProcesoEvaluado[];
  /** La suma del top 3: lo que se ataca primero. */
  horasRecuperablesMes: number;
  horasRecuperablesAnio: number;
}

export const TOP = 3;

export function estaRespondida(pregunta: Pregunta, respuestas: Respuestas): boolean {
  const valor = respuestas[pregunta.id];
  // Una "varias" sin nada marcado es una respuesta válida: ninguno.
  if (pregunta.tipo === "varias") return Array.isArray(valor);
  return typeof valor === "string" && valor !== "";
}

export function etapaDe(enSistema: boolean, pasosDefinidos: boolean): Etapa {
  if (!enSistema) return "Digitalizar";
  return pasosDefinidos ? "Automatizar" : "Optimizar";
}

/** Redondea a media hora: más precisión sería fingir una exactitud que no hay. */
function aMediaHora(horas: number): number {
  return Math.round(horas * 2) / 2;
}

function lista(respuestas: Respuestas, id: string): string[] {
  const valor = respuestas[id];
  return Array.isArray(valor) ? valor : [];
}

export function calcular(respuestas: Respuestas): Resultado {
  const enSistema = new Set(lista(respuestas, "en_sistema"));
  const pasosDefinidos = new Set(lista(respuestas, "pasos_definidos"));

  const procesos = PROCESOS.map((p, orden) => {
    const horasSemana = Number(respuestas[`horas.${p.id}`] ?? 0) || 0;
    const etapa = etapaDe(enSistema.has(p.id), pasosDefinidos.has(p.id));
    const horasRecuperablesMes = aMediaHora(
      horasSemana * PORCENTAJE_RECUPERABLE[etapa] * SEMANAS_POR_MES,
    );
    return {
      orden,
      evaluado: { id: p.id, nombre: p.nombre, horasSemana, etapa, horasRecuperablesMes },
    };
  })
    // Empates: primero el que más horas consume y luego el orden de las preguntas, para
    // que el mismo cuestionario dé siempre el mismo top.
    .sort(
      (a, b) =>
        b.evaluado.horasRecuperablesMes - a.evaluado.horasRecuperablesMes ||
        b.evaluado.horasSemana - a.evaluado.horasSemana ||
        a.orden - b.orden,
    )
    .map((x) => x.evaluado);

  const horasRecuperablesMes = aMediaHora(
    procesos.slice(0, TOP).reduce((suma, p) => suma + p.horasRecuperablesMes, 0),
  );
  return {
    version: 1,
    procesos,
    horasRecuperablesMes,
    horasRecuperablesAnio: Math.round(horasRecuperablesMes * 12),
  };
}

export function formatoHoras(horas: number): string {
  return `${horas.toLocaleString("es-MX", { maximumFractionDigits: 1 })} h`;
}
