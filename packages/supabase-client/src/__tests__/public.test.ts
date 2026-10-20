import { afterEach, describe, expect, it, vi } from "vitest";

import { createPublicClient } from "../public";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("createPublicClient", () => {
  it("se arma con la URL y la clave publishable", () => {
    vi.stubEnv("SUPABASE_URL", "https://proyecto-test.supabase.co");
    vi.stubEnv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_de_prueba");
    expect(createPublicClient().from).toBeTypeOf("function");
  });

  it("sin configuración lanza, nombrando lo que falta", () => {
    for (const nombre of ["SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL", "VITE_SUPABASE_URL"]) {
      vi.stubEnv(nombre, undefined);
    }
    expect(() => createPublicClient()).toThrow(/Missing required env: SUPABASE_URL/);
  });
});
