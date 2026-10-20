import { createClient } from "@supabase/supabase-js";

import { getRequiredEnv } from "./env";
import type { Database } from "./types/database";

/**
 * Cliente con la clave pública (anon o publishable) y sin sesión: no guarda
 * cookies ni refresca tokens. Sirve para lo que cualquiera puede hacer, del lado
 * del servidor o del navegador: leer la vista `vacantes_publicas` y llamar a las
 * RPC que `anon` puede ejecutar, como `aplicar_a_vacante`. RLS decide el resto.
 */
type PublicClient = ReturnType<typeof createClient<Database>>;

export function createPublicClient(): PublicClient {
  return createClient<Database>(
    getRequiredEnv("SUPABASE_URL"),
    getRequiredEnv("SUPABASE_ANON_KEY"),
    {
      auth: { persistSession: false, autoRefreshToken: false },
    },
  );
}
