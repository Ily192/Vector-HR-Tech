/**
 * El career site lee Supabase si tiene su URL y su clave pública. Sin ellas
 * (en local sin `pnpm db:start`, en los tests, en una preview sin variables) usa
 * los datos de ejemplo y no recibe aplicaciones.
 */
import "server-only";

import { getOptionalEnv } from "@vortex/supabase-client";

export function supabaseConfigurado(): boolean {
  return Boolean(getOptionalEnv("SUPABASE_URL") && getOptionalEnv("SUPABASE_ANON_KEY"));
}
