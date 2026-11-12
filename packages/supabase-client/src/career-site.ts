import { createClient } from "@supabase/supabase-js";

import { getRequiredEnv } from "./env";
import type { Database } from "./types/database";

/**
 * Cliente del career site con el rol `career_site` (migración 0017), en lugar de la
 * service_role. Ese rol solo lee el `id` y el `empresa_id` de las vacantes abiertas,
 * sube CVs al bucket `cvs` y borra uno recién subido si trae su ruta en la cabecera
 * `x-cv-ruta`. Si la clave se filtra, no da acceso a nada más.
 *
 * La clave es un JWT firmado con el JWT_SECRET del Supabase autoalojado
 * (`infra/vps/scripts/generar_secretos.py`). Va en `Authorization` mediante la
 * opción `accessToken` de supabase-js, y la anon en `apikey`, porque el gateway solo
 * deja pasar la anon o la service_role como `apikey`. PostgREST y Storage toman el
 * rol del JWT.
 *
 * Solo en código de servidor: lanza si se importa desde el navegador.
 */
type CareerSiteClient = ReturnType<typeof createClient<Database>>;

export interface OpcionesDelCareerSite {
  /** Cabeceras extra en todas las peticiones de este cliente (p. ej. `x-cv-ruta`). */
  cabeceras?: Record<string, string>;
}

export function createCareerSiteClient(opciones: OpcionesDelCareerSite = {}): CareerSiteClient {
  if (typeof window !== "undefined") {
    throw new Error(
      "createCareerSiteClient() llamado desde código browser — esto filtraría la clave del career site. Usa createPublicClient() en su lugar.",
    );
  }
  const clave = getRequiredEnv("SUPABASE_CAREER_SITE_KEY");
  return createClient<Database>(
    getRequiredEnv("SUPABASE_URL"),
    getRequiredEnv("SUPABASE_ANON_KEY"),
    {
      accessToken: async () => clave,
      ...(opciones.cabeceras ? { global: { headers: opciones.cabeceras } } : {}),
    },
  );
}
