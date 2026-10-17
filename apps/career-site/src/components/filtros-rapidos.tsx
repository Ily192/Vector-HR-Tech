import { ETIQUETA_MODALIDAD } from "@vortex/types/etiquetas";
import type { Modality } from "@vortex/types/hr";
import Link from "next/link";

import { type FiltrosVacantes, urlConFiltros } from "../lib/filtros";

const MODALIDADES: Modality[] = ["remote", "hybrid", "onsite"];

const chip = (activo: boolean) =>
  `inline-flex min-h-10 shrink-0 items-center rounded-full border-[1.5px] px-4 text-sm font-bold transition-colors ${
    activo
      ? "border-ink-900 bg-ink-900 text-white"
      : "border-mist-200 bg-white text-ink-900 hover:border-ink-300"
  }`;

/**
 * Filtros de un toque: modalidad y "con salario". Son enlaces, no estado: cada
 * uno lleva a la URL con el filtro puesto o quitado, y conserva la búsqueda.
 */
export function FiltrosRapidos({ filtros }: { filtros: FiltrosVacantes }) {
  const sinModalidad = { ...filtros, modalidad: undefined };
  return (
    <nav aria-label="Filtros" className="flex gap-2 overflow-x-auto pb-1">
      <Link
        href={urlConFiltros(sinModalidad)}
        className={chip(!filtros.modalidad)}
        aria-current={!filtros.modalidad ? "true" : undefined}
      >
        Todas
      </Link>
      {MODALIDADES.map((m) => {
        const activo = filtros.modalidad === m;
        return (
          <Link
            key={m}
            href={urlConFiltros(activo ? sinModalidad : { ...filtros, modalidad: m })}
            className={chip(activo)}
            aria-current={activo ? "true" : undefined}
          >
            {ETIQUETA_MODALIDAD[m]}
          </Link>
        );
      })}
      <Link
        href={urlConFiltros({ ...filtros, conSalario: !filtros.conSalario || undefined })}
        className={chip(!!filtros.conSalario)}
        aria-current={filtros.conSalario ? "true" : undefined}
      >
        Con salario
      </Link>
    </nav>
  );
}
