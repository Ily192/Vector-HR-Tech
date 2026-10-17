/**
 * Datos del cockpit (plan con servicios de IA): qué necesita la pantalla y de
 * dónde los saca.
 *
 * La pantalla no calcula ningún indicador. Conteos, ventanas de tiempo,
 * porcentajes y el siguiente paso de cada candidato los devolverá un caso de uso
 * del hr-engine (pendiente) que agrega runs, costos y aplicaciones por tenant;
 * `ResumenCockpit` es la forma de esa respuesta. Mientras no exista,
 * `obtenerResumenCockpit()` devuelve un ejemplo fijo, y es lo único que habrá
 * que cambiar para leer el real.
 */
import type { EtapaDelPipeline } from "@vortex/types/reglas";

import type { Evaluado } from "../datos/tipos";

/** Un indicador ya calculado: el número y su variación, tal como se muestran. */
export interface Indicador {
  valor: number | string;
  variacion: string;
}

/** Lo más urgente del día, elegido por el backend. */
export interface DecisionDelDia {
  posicion: number;
  total: number;
  titulo: string;
  detalle: string;
}

export interface EntradaDelRegistro {
  hora: string;
  agente: string;
  detalle: string;
  /** Costo en USD, o `null` si la ejecución quedó en espera. */
  costoUsd: number | null;
}

export interface ResumenCockpit {
  decision: DecisionDelDia;
  candidatosEnProceso: Indicador;
  vacantesPublicadas: Indicador;
  evaluacionesIa24h: Indicador;
  enEsperaDelModelo: Indicador;
  gastoIaDelMes: { usd: number; porcentajeDelTope: number };
  mejoresEvaluados: { vacante: string; total: number; filas: Evaluado[] };
  /** Vacante que se muestra en el embudo y su conteo por etapa. */
  pipeline: { vacante: string; conteos: Record<EtapaDelPipeline, number> };
  registro: EntradaDelRegistro[];
}

const RESUMEN_DE_EJEMPLO: ResumenCockpit = {
  decision: {
    posicion: 1,
    total: 3,
    titulo: "3 candidatas listas para entrevista en Senior Software Engineer",
    detalle:
      "Scores 8.9, 8.5 y 8.2, evaluadas a ciegas. El siguiente paso lo fija la política de la vacante, no el modelo.",
  },
  candidatosEnProceso: { valor: 142, variacion: "+34 hoy" },
  vacantesPublicadas: { valor: 8, variacion: "+2 esta semana" },
  evaluacionesIa24h: { valor: 327, variacion: "98 % sin error" },
  enEsperaDelModelo: { valor: 2, variacion: "se reintentan solas" },
  gastoIaDelMes: { usd: 18.4, porcentajeDelTope: 31 },
  mejoresEvaluados: {
    vacante: "Senior Software Engineer",
    total: 41,
    filas: [
      {
        candidato: "#455",
        score: 8.9,
        razonamiento: "Arquitectura multi-tenant y Postgres avanzado",
        siguientePaso: "entrevista",
      },
      {
        candidato: "#482",
        score: 8.5,
        razonamiento: "Python y FastAPI; le falta Celery",
        siguientePaso: "entrevista",
      },
      {
        candidato: "#477",
        score: 6.1,
        razonamiento: "Buen backend, sin experiencia en SaaS",
        siguientePaso: "psicometrico",
      },
    ],
  },
  pipeline: {
    vacante: "Senior Software Engineer",
    conteos: { applied: 84, evaluated: 41, shortlisted: 12, interviewed: 3, offered: 2 },
  },
  registro: [
    {
      hora: "08:42",
      agente: "cv-evaluator",
      detalle: "Candidata #482 · 8.5 · entrevista",
      costoUsd: 0.0003,
    },
    {
      hora: "07:15",
      agente: "sourcer",
      detalle: "12 perfiles para HR Business Partner",
      costoUsd: 0.041,
    },
    {
      hora: "06:58",
      agente: "cv-evaluator",
      detalle: "2 evaluaciones aplazadas: sin modelo disponible",
      costoUsd: null,
    },
  ],
};

/** Resumen del cockpit para la empresa de la sesión. Hoy: datos de ejemplo. */
export async function obtenerResumenCockpit(): Promise<ResumenCockpit> {
  return RESUMEN_DE_EJEMPLO;
}
