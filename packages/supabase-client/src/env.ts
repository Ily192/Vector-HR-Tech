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

const ALIASES: Record<string, readonly string[]> = {
  SUPABASE_URL: ["SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL", "VITE_SUPABASE_URL"],
  SUPABASE_ANON_KEY: [
    "SUPABASE_ANON_KEY",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "VITE_SUPABASE_ANON_KEY",
  ],
  SUPABASE_SERVICE_ROLE_KEY: ["SUPABASE_SERVICE_ROLE_KEY"],
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
