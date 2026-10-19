import { ETIQUETA_MODALIDAD, ETIQUETA_SENIORITY } from "@vortex/types/etiquetas";
import type { VacantePublica } from "@vortex/types/hr";
import Link from "next/link";

import { esNueva, formatearSalario, haceCuanto, iniciales } from "../lib/formato";

/**
 * Tarjeta de una vacante en el listado. Lo primero que se lee es el puesto, la
 * empresa, dónde y cuánto: es lo que decide si alguien abre la vacante.
 */
export function TarjetaVacante({ vacante: v, ahora }: { vacante: VacantePublica; ahora?: Date }) {
  const salario = formatearSalario(v);
  return (
    <Link
      href={`/vacantes/${v.slug}`}
      data-vacante={v.slug}
      className="group flex flex-col gap-2.5 rounded-[20px] border border-mist-200 bg-white p-[22px] text-ink-900 transition-[box-shadow,border-color] duration-normal hover:border-aqua-500 hover:shadow-lift"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-aqua-50 text-sm font-black text-aqua-700"
        >
          {iniciales(v.empresa_nombre)}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[19px] font-extrabold leading-tight">{v.title}</h3>
          <p className="text-sm font-semibold text-mist-700">{v.empresa_nombre}</p>
        </div>
        {v.cupo_completo ? (
          <span className="shrink-0 rounded-full bg-mist-100 px-2.5 py-0.5 text-xs font-bold text-mist-700">
            Cupo completo
          </span>
        ) : (
          esNueva(v.created_at, ahora) && (
            <span className="shrink-0 rounded-full bg-aqua-50 px-2.5 py-0.5 text-xs font-bold text-aqua-700">
              Nueva
            </span>
          )
        )}
      </div>
      <p className="flex flex-wrap gap-x-3.5 gap-y-1 text-sm font-semibold text-mist-600">
        {v.location && <span>{v.location}</span>}
        <span>{ETIQUETA_MODALIDAD[v.modality]}</span>
        {v.seniority && <span>{ETIQUETA_SENIORITY[v.seniority]}</span>}
      </p>
      {salario ? (
        <p className="text-base font-extrabold tabular-nums">
          {salario}{" "}
          <span className="text-[13px] font-semibold text-mist-600">{v.moneda} / mes</span>
        </p>
      ) : (
        <p className="text-[14.5px] font-bold text-mist-600">Salario a convenir</p>
      )}
      <p className="mt-auto flex items-center justify-between border-t border-mist-150 pt-2.5 text-[13px] text-mist-600">
        <span>{haceCuanto(v.created_at, ahora)}</span>
        <span className="font-bold text-aqua-700 group-hover:underline">Ver vacante →</span>
      </p>
    </Link>
  );
}
