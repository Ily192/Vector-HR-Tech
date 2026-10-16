/**
 * Datos del cockpit: qué necesita la pantalla y de dónde los saca.
 *
 * La pantalla no calcula ningún indicador. Conteos, ventanas de tiempo y
 * porcentajes los devolverá un caso de uso del hr-engine (pendiente) que agrega
 * runs, costos y aplicaciones por tenant; `ResumenCockpit` es la forma de esa
 * respuesta. Mientras no exista, `obtenerResumenCockpit()` devuelve un ejemplo
 * fijo, y es lo único que habrá que cambiar para leer el real.
 */
import type { EtapaDelPipeline } from "@vortex/types/reglas";

/** Un indicador ya calculado: el número y su variación, tal como se muestran. */
export interface Indicador {
  valor: number | string;
  variacion: string;
}

/** Quién está usando el cockpit. Saldrá de la sesión de Supabase (ADR-015). */
export interface SesionCockpit {
  nombre: string;
  iniciales: string;
  empresa: string;
}

export interface ResumenCockpit {
  sesion: SesionCockpit;
  vacantesActivas: Indicador;
  candidatosEnPipeline: Indicador;
  runsDeAgentes24h: Indicador;
  costoIaHoyUsd: Indicador;
  /** Vacante que se muestra en el embudo y su conteo por etapa. */
  pipeline: { vacante: string; conteos: Record<EtapaDelPipeline, number> };
}

const RESUMEN_DE_EJEMPLO: ResumenCockpit = {
  sesion: { nombre: "Ilyra", iniciales: "IR", empresa: "Vector HR" },
  vacantesActivas: { valor: 8, variacion: "+2 esta semana" },
  candidatosEnPipeline: { valor: 142, variacion: "+34 hoy" },
  runsDeAgentes24h: { valor: 327, variacion: "98% éxito" },
  costoIaHoyUsd: { valor: "$1.42", variacion: "12% del tope mensual" },
  pipeline: {
    vacante: "Senior Software Engineer",
    conteos: { applied: 84, evaluated: 41, shortlisted: 12, interviewed: 3, offered: 2 },
  },
};

/** Resumen del cockpit para la empresa de la sesión. Hoy: datos de ejemplo. */
export function obtenerResumenCockpit(): ResumenCockpit {
  return RESUMEN_DE_EJEMPLO;
}

/** `true` mientras el resumen sea de ejemplo; la pantalla lo avisa. */
export const ES_DE_EJEMPLO = true;
