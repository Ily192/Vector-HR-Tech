import { createClient } from "@supabase/supabase-js";

import { getRequiredEnv } from "./env";
import type { Database } from "./types/database";

/**
 * Cliente Supabase con la **service role key** — bypasea RLS. Solo usar en
 * código de servidor (Route Handlers, scripts admin, workers Python no — esos
 * usan asyncpg directo). Nunca exponer al browser.
 *
 * Patrón defensivo: tira si por accidente se importa desde un módulo cliente.
 */
type ServiceRoleClient = ReturnType<typeof createClient<Database>>;

export function createServiceRoleClient(): ServiceRoleClient {
  if (typeof window !== "undefined") {
    throw new Error(
      "createServiceRoleClient() llamado desde código browser — esto filtraría la service_role key. Usa createBrowserClient() en su lugar.",
    );
  }
  return createClient<Database>(
    getRequiredEnv("SUPABASE_URL"),
    getRequiredEnv("SUPABASE_SERVICE_ROLE_KEY"),
    {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
      },
    },
  );
}
