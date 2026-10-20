import { createBrowserClient as createSupabaseBrowserClient } from "@supabase/ssr";
import { getRequiredEnv } from "./env";
import type { Database } from "./types/database";

/**
 * Cliente Supabase para componentes de browser de una app con SSR: guarda la
 * sesión en cookies y usa el flujo PKCE. Usa la anon key — RLS se aplica del
 * lado del Postgres con el JWT de Supabase Auth.
 *
 * El panel (hrbp) no lo usa: es una SPA y los enlaces de invitación vuelven con
 * los tokens en el hash (flujo implícito), que un cliente PKCE rechaza. Crea el
 * suyo en `apps/hrbp/src/datos/panel-supabase.ts`.
 *
 * Idempotente: llamadas múltiples devuelven el mismo singleton para evitar
 * múltiples conexiones realtime.
 */
// El tipo se infiere del factory: anotarlo a mano como `SupabaseClient<Database>`
// chocaba con la aridad de genericos que expone @supabase/ssr.
type BrowserClient = ReturnType<typeof createSupabaseBrowserClient<Database>>;

let _client: BrowserClient | null = null;

export function createBrowserClient(): BrowserClient {
  if (_client) return _client;
  _client = createSupabaseBrowserClient<Database>(
    getRequiredEnv("SUPABASE_URL"),
    getRequiredEnv("SUPABASE_ANON_KEY"),
  );
  return _client;
}
