"use client";

import { Button } from "@vortex/ui";
import { Flag } from "lucide-react";
import Script from "next/script";
import { useActionState } from "react";

import {
  MAX_DETALLE_DEL_REPORTE,
  MOTIVOS_DE_REPORTE,
  type ResultadoDeReportar,
} from "../lib/tipos-de-reporte";

type Accion = (
  anterior: ResultadoDeReportar | null,
  formulario: FormData,
) => Promise<ResultadoDeReportar>;

/**
 * "Reportar vacante" (ADR-022): un motivo y, si quiere, un detalle corto. Vector HR
 * lo revisa; con dos personas distintas la vacante se oculta mientras tanto. La
 * validación de verdad es del servidor (`lib/reporte.ts`) y de la base.
 */
export function ReportarVacante({
  accion,
  sitekey,
}: {
  accion: Accion;
  /** La site key de Turnstile; sin ella el widget no se pinta. */
  sitekey: string | null;
}) {
  const [resultado, enviar, enviando] = useActionState(accion, null);

  return (
    <details className="rounded-xl border border-mist-200 bg-white px-4 py-3 text-sm">
      <summary className="inline-flex cursor-pointer items-center gap-2 font-bold text-mist-700">
        <Flag aria-hidden="true" className="h-4 w-4" /> Reportar vacante
      </summary>
      {resultado?.estado === "ok" ? (
        <output className="mt-3 block text-mist-700">
          Gracias. Vector HR revisa los reportes y, si hace falta, retira la vacante.
        </output>
      ) : (
        <form action={enviar} aria-label="Reportar la vacante" className="mt-3 flex flex-col gap-3">
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1 font-bold text-ink-900">¿Qué pasa con esta vacante?</legend>
            {Object.entries(MOTIVOS_DE_REPORTE).map(([valor, texto]) => (
              <label key={valor} className="flex items-center gap-2 text-mist-700">
                <input type="radio" name="motivo" value={valor} required />
                {texto}
              </label>
            ))}
          </fieldset>
          <label className="block font-bold text-ink-900">
            Cuéntanos más <span className="font-normal text-mist-600">(opcional)</span>
            <textarea
              name="detalle"
              rows={2}
              maxLength={MAX_DETALLE_DEL_REPORTE}
              className="mt-1.5 block w-full rounded-xl border-[1.5px] border-mist-200 px-3 py-2 font-normal"
            />
          </label>
          {/* Campo trampa: una persona no lo ve ni lo llena. */}
          <input
            type="text"
            name="sitio_web"
            tabIndex={-1}
            autoComplete="off"
            aria-hidden="true"
            className="hidden"
          />
          {sitekey && (
            <>
              <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer />
              <div className="cf-turnstile" data-sitekey={sitekey} data-language="es" />
            </>
          )}
          {resultado?.estado === "error" && (
            <p role="alert" className="font-semibold text-red-600">
              {resultado.mensaje}
            </p>
          )}
          <Button type="submit" variant="secondary" size="sm" disabled={enviando}>
            {enviando ? "Enviando…" : "Enviar reporte"}
          </Button>
        </form>
      )}
    </details>
  );
}
