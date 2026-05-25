import { createBrowserClient as createSupabaseBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { getRequiredEnv } from "./env";
import type { Database } from "./types/database";

/**
 * Cliente Supabase para componentes de browser (career-site páginas públicas,
 * hrbp SPA). Usa la anon key — RLS se aplica del lado del Postgres con el
 * JWT que Supabase Auth pone en cookies/localStorage.
 *
 * Idempotente: llamadas múltiples devuelven el mismo singleton para evitar
 * múltiples conexiones realtime.
 */
let _client: SupabaseClient<Database> | null = null;

export function createBrowserClient(): SupabaseClient<Database> {
  if (_client) return _client;
  _client = createSupabaseBrowserClient<Database>(
    getRequiredEnv("SUPABASE_URL"),
    getRequiredEnv("SUPABASE_ANON_KEY"),
  );
  return _client;
}
