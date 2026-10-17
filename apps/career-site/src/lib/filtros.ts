/**
 * Filtros de búsqueda del career-site: cómo se leen de la URL y cómo se escriben
 * en ella. Viajan en la URL (`?q=&ubicacion=&modalidad=&salario=1`) para que una
 * búsqueda se pueda compartir y funcione sin JavaScript.
 */
import { type Modality, ModalitySchema } from "@vortex/types/hr";
import type { Route } from "next";

export interface FiltrosVacantes {
  q?: string | undefined;
  ubicacion?: string | undefined;
  modalidad?: Modality | undefined;
  /** Solo vacantes que publican salario. */
  conSalario?: boolean | undefined;
}

type SearchParams = Record<string, string | string[] | undefined>;

const primero = (valor: string | string[] | undefined) =>
  (Array.isArray(valor) ? valor[0] : valor)?.trim() || undefined;

/** Lee los filtros de `searchParams`. Lo que no es válido se ignora, no falla. */
export function leerFiltros(params: SearchParams): FiltrosVacantes {
  const modalidad = ModalitySchema.safeParse(primero(params.modalidad));
  return {
    q: primero(params.q),
    ubicacion: primero(params.ubicacion),
    modalidad: modalidad.success ? modalidad.data : undefined,
    conSalario: primero(params.salario) === "1" || undefined,
  };
}

/** URL de `/vacantes` con estos filtros, sin parámetros vacíos. */
export function urlConFiltros(filtros: FiltrosVacantes): Route {
  const params = new URLSearchParams();
  if (filtros.q) params.set("q", filtros.q);
  if (filtros.ubicacion) params.set("ubicacion", filtros.ubicacion);
  if (filtros.modalidad) params.set("modalidad", filtros.modalidad);
  if (filtros.conSalario) params.set("salario", "1");
  const query = params.toString();
  return (query ? `/vacantes?${query}` : "/vacantes") as Route;
}
