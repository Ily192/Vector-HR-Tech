/**
 * Cálculos de presentación del pipeline de una vacante. No son reglas de negocio:
 * agrupan a los aplicados que ya llegaron por la etapa en que están. Qué etapas hay
 * y su orden vienen de `@fluveai/types/reglas`; quién puede mover a quién lo decide
 * la base (0004 y 0021, ADR-024).
 */
import type { ApplicationStatus } from "@fluveai/types/hr";
import {
  ETAPAS_DEL_PIPELINE,
  ETAPAS_DE_SALIDA,
  type EtapaDelPipeline,
} from "@fluveai/types/reglas";

/** La barra de cada etapa: del interés (aqua) a la decisión (flame), como en el tablero B. */
export const BARRA_DE_ETAPA: Record<EtapaDelPipeline, string> = {
  applied: "bg-aqua-100",
  evaluated: "bg-aqua-300",
  shortlisted: "bg-aqua-600",
  interviewed: "bg-flame-400",
  offered: "bg-flame-500",
};

/** Todas las etapas, en el orden en que se muestran: el pipeline y después el cierre. */
export const TODAS_LAS_ETAPAS: readonly ApplicationStatus[] = [
  ...ETAPAS_DEL_PIPELINE,
  ...ETAPAS_DE_SALIDA,
];

/** Cuántos aplicados hay en cada etapa, con 0 en las vacías. */
export function contarPorEtapa(
  aplicados: readonly { estado: ApplicationStatus }[],
): Record<ApplicationStatus, number> {
  const conteo = Object.fromEntries(TODAS_LAS_ETAPAS.map((e) => [e, 0])) as Record<
    ApplicationStatus,
    number
  >;
  for (const a of aplicados) conteo[a.estado] += 1;
  return conteo;
}

/** Los de una etapa, en el mismo orden; con `null`, todos. */
export function deLaEtapa<T extends { estado: ApplicationStatus }>(
  aplicados: readonly T[],
  etapa: ApplicationStatus | null,
): T[] {
  return etapa === null ? [...aplicados] : aplicados.filter((a) => a.estado === etapa);
}

/** Cómo se cierra, tal como se muestra: "Se retiraron" solo si alguien se retiró. */
export function salidasVisibles(
  conteo: Record<ApplicationStatus, number>,
): readonly ApplicationStatus[] {
  return ETAPAS_DE_SALIDA.filter((e) => e !== "withdrawn" || conteo[e] > 0);
}
