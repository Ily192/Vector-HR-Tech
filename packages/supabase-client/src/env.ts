/**
 * Lectura de variables de entorno con fallback Next.js (NEXT_PUBLIC_*) y Vite
 * (VITE_*) para que el mismo package sirva a `apps/career-site` y `apps/hrbp`.
 *
 * Si llamas desde código de servidor, también acepta nombres sin prefijo.
 */

type EnvBag = Record<string, string | undefined>;

function readEnv(name: string): string | undefined {
  // Node / Next.js server runtime
  if (typeof process !== "undefined" && process.env) {
    const fromNode = (process.env as EnvBag)[name];
    if (fromNode) return fromNode;
  }
  // Vite browser bundle
  // biome-ignore lint/suspicious/noExplicitAny: import.meta.env shape is build-tool dependent
  const importMeta = typeof import.meta !== "undefined" ? (import.meta as any) : undefined;
  if (importMeta?.env) {
    const fromVite = (importMeta.env as EnvBag)[name];
    if (fromVite) return fromVite;
  }
  return undefined;
}

/**
 * Las claves nuevas de Supabase reemplazan a las legadas, que se retiran a fines
 * de 2026: la `publishable` (sb_publishable_…) hace de anon y la `secret`
 * (sb_secret_…) de service role. Se aceptan los dos nombres. La secreta nunca con
 * prefijo NEXT_PUBLIC_ ni VITE_: eso la metería en el bundle del navegador.
 */
const ALIASES: Record<string, readonly string[]> = {
  SUPABASE_URL: ["SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL", "VITE_SUPABASE_URL"],
  SUPABASE_ANON_KEY: [
    "SUPABASE_ANON_KEY",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "VITE_SUPABASE_ANON_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    "VITE_SUPABASE_PUBLISHABLE_KEY",
  ],
  SUPABASE_SERVICE_ROLE_KEY: ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"],
};

export function getOptionalEnv(canonical: keyof typeof ALIASES): string | undefined {
  for (const name of ALIASES[canonical] ?? [canonical]) {
    const value = readEnv(name);
    if (value) return value;
  }
  return undefined;
}

export function getRequiredEnv(canonical: keyof typeof ALIASES): string {
  const value = getOptionalEnv(canonical);
  if (!value) {
    throw new Error(
      `Missing required env: ${canonical}. Set one of: ${ALIASES[canonical]?.join(", ")}`,
    );
  }
  return value;
}
