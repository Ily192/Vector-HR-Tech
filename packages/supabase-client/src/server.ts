import { createServerClient as createSupabaseServerClient } from "@supabase/ssr";
import { getRequiredEnv } from "./env";
import type { Database } from "./types/database";

/**
 * Adapter mínimo de cookies para que el caller pase su propia integración.
 * En Next.js App Router viene de `next/headers` → `cookies()`. En cualquier otro
 * framework con cookie store similar también funciona.
 */
export interface CookieAdapter {
  get: (name: string) => { value: string } | undefined;
  set?: (name: string, value: string, options?: Record<string, unknown>) => void;
  remove?: (name: string, options?: Record<string, unknown>) => void;
}

/**
 * Cliente Supabase para Server Components / API Routes de Next.js. Lee la sesión
 * desde cookies, aplica RLS con el JWT del usuario. NO usa service role.
 */
type ServerClient = ReturnType<typeof createSupabaseServerClient<Database>>;

export function createServerClient(cookies: CookieAdapter): ServerClient {
  return createSupabaseServerClient<Database>(
    getRequiredEnv("SUPABASE_URL"),
    getRequiredEnv("SUPABASE_ANON_KEY"),
    {
      cookies: {
        get: (name: string) => cookies.get(name)?.value,
        set: (name: string, value: string, options?: Record<string, unknown>) => {
          cookies.set?.(name, value, options);
        },
        remove: (name: string, options?: Record<string, unknown>) => {
          cookies.remove?.(name, options);
        },
      },
    },
  );
}
