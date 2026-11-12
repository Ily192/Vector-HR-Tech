"use server";

import { headers } from "next/headers";

import { procesarAplicacion } from "../../../lib/aplicacion";
import { puertosDeSupabase } from "../../../lib/aplicacion-supabase";
import { procesarReporte } from "../../../lib/reporte";
import { puertosDeReporte } from "../../../lib/reporte-supabase";
import { supabaseConfigurado } from "../../../lib/supabase";
import type { ResultadoDeAplicar } from "../../../lib/tipos-de-aplicacion";
import type { ResultadoDeReportar } from "../../../lib/tipos-de-reporte";

async function ipDelVisitante(): Promise<string | null> {
  return (await headers()).get("x-forwarded-for")?.split(",")[0]?.trim() || null;
}

/**
 * Server Action del formulario de aplicación. Solo traduce: la lógica está en
 * `lib/aplicacion.ts` y los adaptadores en `lib/aplicacion-supabase.ts`. Next la
 * protege contra CSRF comparando el `Origin` con el host (guía de Server Actions).
 */
export async function aplicarAVacante(
  slug: string,
  _anterior: ResultadoDeAplicar | null,
  formulario: FormData,
): Promise<ResultadoDeAplicar> {
  if (!supabaseConfigurado()) {
    return {
      estado: "error",
      mensaje: "Las aplicaciones se abren cuando el sitio se conecte a la base de datos.",
    };
  }
  return procesarAplicacion(slug, formulario, puertosDeSupabase(await ipDelVisitante()));
}

/**
 * "Reportar vacante" (ADR-022). Con dos personas distintas la base la oculta y la
 * pasa a revisión de Vector HR; la lógica está en `lib/reporte.ts`.
 */
export async function reportarVacante(
  slug: string,
  _anterior: ResultadoDeReportar | null,
  formulario: FormData,
): Promise<ResultadoDeReportar> {
  if (!supabaseConfigurado()) {
    return { estado: "error", mensaje: "Los reportes se abren cuando el sitio se conecte." };
  }
  return procesarReporte(slug, formulario, puertosDeReporte(await ipDelVisitante()));
}
