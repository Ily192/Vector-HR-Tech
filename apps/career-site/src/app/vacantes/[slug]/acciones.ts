"use server";

import { headers } from "next/headers";

import { procesarAplicacion } from "../../../lib/aplicacion";
import { puertosDeSupabase } from "../../../lib/aplicacion-supabase";
import { supabaseConfigurado } from "../../../lib/supabase";
import type { ResultadoDeAplicar } from "../../../lib/tipos-de-aplicacion";

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
  const ip = (await headers()).get("x-forwarded-for")?.split(",")[0]?.trim() || null;
  return procesarAplicacion(slug, formulario, puertosDeSupabase(ip));
}
