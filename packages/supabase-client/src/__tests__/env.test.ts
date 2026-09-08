import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getOptionalEnv, getRequiredEnv } from "../env";

/** Todos los nombres que `env.ts` conoce, en todas sus variantes. */
const TODOS_LOS_ALIAS = [
  "SUPABASE_URL",
  "NEXT_PUBLIC_SUPABASE_URL",
  "VITE_SUPABASE_URL",
  "SUPABASE_ANON_KEY",
  "NEXT_PUBLIC_SUPABASE_ANON_KEY",
  "VITE_SUPABASE_ANON_KEY",
  "SUPABASE_SERVICE_ROLE_KEY",
  "NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY",
  "VITE_SUPABASE_SERVICE_ROLE_KEY",
] as const;

beforeEach(() => {
  // Partimos siempre de un entorno limpio: `vi.stubEnv(name, undefined)` borra la
  // variable tanto de `process.env` como de `import.meta.env`.
  for (const name of TODOS_LOS_ALIAS) {
    vi.stubEnv(name, undefined);
  }
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getOptionalEnv", () => {
  it("lee el nombre canónico sin prefijo (runtime servidor)", () => {
    vi.stubEnv("SUPABASE_URL", "https://raw.supabase.co");
    expect(getOptionalEnv("SUPABASE_URL")).toBe("https://raw.supabase.co");
  });

  it("cae al alias NEXT_PUBLIC_ (bundle de Next.js)", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://next.supabase.co");
    expect(getOptionalEnv("SUPABASE_URL")).toBe("https://next.supabase.co");
  });

  it("cae al alias VITE_ (bundle de Vite)", () => {
    vi.stubEnv("VITE_SUPABASE_URL", "https://vite.supabase.co");
    expect(getOptionalEnv("SUPABASE_URL")).toBe("https://vite.supabase.co");
  });

  it("respeta la precedencia raw > NEXT_PUBLIC_ > VITE_", () => {
    vi.stubEnv("VITE_SUPABASE_URL", "https://vite.supabase.co");
    expect(getOptionalEnv("SUPABASE_URL")).toBe("https://vite.supabase.co");

    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://next.supabase.co");
    expect(getOptionalEnv("SUPABASE_URL")).toBe("https://next.supabase.co");

    vi.stubEnv("SUPABASE_URL", "https://raw.supabase.co");
    expect(getOptionalEnv("SUPABASE_URL")).toBe("https://raw.supabase.co");
  });

  it("resuelve la anon key por sus tres alias", () => {
    vi.stubEnv("VITE_SUPABASE_ANON_KEY", "anon-vite");
    expect(getOptionalEnv("SUPABASE_ANON_KEY")).toBe("anon-vite");

    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-next");
    expect(getOptionalEnv("SUPABASE_ANON_KEY")).toBe("anon-next");

    vi.stubEnv("SUPABASE_ANON_KEY", "anon-raw");
    expect(getOptionalEnv("SUPABASE_ANON_KEY")).toBe("anon-raw");
  });

  it("devuelve undefined cuando ninguna variante está definida", () => {
    expect(getOptionalEnv("SUPABASE_URL")).toBeUndefined();
    expect(getOptionalEnv("SUPABASE_ANON_KEY")).toBeUndefined();
    expect(getOptionalEnv("SUPABASE_SERVICE_ROLE_KEY")).toBeUndefined();
  });

  it("trata la cadena vacía como ausente (no propaga config rota)", () => {
    vi.stubEnv("SUPABASE_URL", "");
    expect(getOptionalEnv("SUPABASE_URL")).toBeUndefined();
  });

  it("una cadena vacía en el alias más prioritario no bloquea al siguiente", () => {
    vi.stubEnv("SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://next.supabase.co");
    expect(getOptionalEnv("SUPABASE_URL")).toBe("https://next.supabase.co");
  });
});

describe("getOptionalEnv — service role key", () => {
  it("SOLO acepta el nombre sin prefijo: exponerla como NEXT_PUBLIC_/VITE_ la filtraría al browser", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY", "service-next");
    vi.stubEnv("VITE_SUPABASE_SERVICE_ROLE_KEY", "service-vite");
    expect(getOptionalEnv("SUPABASE_SERVICE_ROLE_KEY")).toBeUndefined();

    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "service-raw");
    expect(getOptionalEnv("SUPABASE_SERVICE_ROLE_KEY")).toBe("service-raw");
  });
});

describe("getRequiredEnv", () => {
  it("devuelve el valor cuando existe", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-123");
    expect(getRequiredEnv("SUPABASE_ANON_KEY")).toBe("anon-123");
  });

  it("lanza cuando falta, nombrando la variable canónica", () => {
    expect(() => getRequiredEnv("SUPABASE_URL")).toThrow(/Missing required env: SUPABASE_URL/);
  });

  it("el mensaje de error lista todos los alias aceptados", () => {
    try {
      getRequiredEnv("SUPABASE_ANON_KEY");
      expect.unreachable("debería haber lanzado");
    } catch (error) {
      const message = (error as Error).message;
      expect(message).toContain("SUPABASE_ANON_KEY");
      expect(message).toContain("NEXT_PUBLIC_SUPABASE_ANON_KEY");
      expect(message).toContain("VITE_SUPABASE_ANON_KEY");
    }
  });

  it("lanza también para la service role key ausente", () => {
    expect(() => getRequiredEnv("SUPABASE_SERVICE_ROLE_KEY")).toThrow(
      /Missing required env: SUPABASE_SERVICE_ROLE_KEY/,
    );
  });

  it("lanza si el valor es cadena vacía", () => {
    vi.stubEnv("SUPABASE_ANON_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "");
    vi.stubEnv("VITE_SUPABASE_ANON_KEY", "");
    expect(() => getRequiredEnv("SUPABASE_ANON_KEY")).toThrow(/Missing required env/);
  });
});
