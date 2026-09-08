import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createServiceRoleClient } from "../service-role";

const SERVICE_KEY = "sbp_test_service_role_key_no_real";

beforeEach(() => {
  vi.stubEnv("SUPABASE_URL", "https://proyecto-test.supabase.co");
  vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("createServiceRoleClient — defensa anti-browser", () => {
  it("lanza si `window` está definido (evita filtrar la service_role key)", () => {
    vi.stubGlobal("window", { document: {} });

    expect(() => createServiceRoleClient()).toThrow(
      /createServiceRoleClient\(\) llamado desde código browser/,
    );
  });

  it("el mensaje de error redirige al cliente correcto", () => {
    vi.stubGlobal("window", {});
    try {
      createServiceRoleClient();
      expect.unreachable("debería haber lanzado");
    } catch (error) {
      expect((error as Error).message).toContain("service_role key");
      expect((error as Error).message).toContain("createBrowserClient()");
    }
  });

  it("la guarda corre ANTES de leer el entorno — no filtra qué env falta al browser", () => {
    vi.stubEnv("SUPABASE_URL", undefined);
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", undefined);
    vi.stubGlobal("window", {});

    expect(() => createServiceRoleClient()).toThrow(/llamado desde código browser/);
    expect(() => createServiceRoleClient()).not.toThrow(/Missing required env/);
  });

  it("nunca incluye el valor de la key en el mensaje de error", () => {
    vi.stubGlobal("window", {});
    try {
      createServiceRoleClient();
      expect.unreachable("debería haber lanzado");
    } catch (error) {
      expect((error as Error).message).not.toContain(SERVICE_KEY);
    }
  });
});

describe("createServiceRoleClient — entorno servidor", () => {
  it("construye un cliente Supabase cuando no hay window", () => {
    expect(typeof globalThis.window).toBe("undefined");

    const client = createServiceRoleClient();

    expect(client).toBeDefined();
    expect(typeof client.from).toBe("function");
    expect(client.auth).toBeDefined();
  });

  it("devuelve instancias nuevas en cada llamada (no es singleton, a diferencia del browser client)", () => {
    expect(createServiceRoleClient()).not.toBe(createServiceRoleClient());
  });

  it("desactiva autoRefreshToken y persistSession — no hay sesión de usuario que mantener", () => {
    const client = createServiceRoleClient() as unknown as {
      auth: { autoRefreshToken?: boolean; persistSession?: boolean };
    };
    expect(client.auth.autoRefreshToken).toBe(false);
    expect(client.auth.persistSession).toBe(false);
  });

  it("lanza si falta SUPABASE_SERVICE_ROLE_KEY", () => {
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", undefined);
    expect(() => createServiceRoleClient()).toThrow(
      /Missing required env: SUPABASE_SERVICE_ROLE_KEY/,
    );
  });

  it("lanza si falta SUPABASE_URL", () => {
    vi.stubEnv("SUPABASE_URL", undefined);
    expect(() => createServiceRoleClient()).toThrow(/Missing required env: SUPABASE_URL/);
  });

  it("no acepta la service role key vía NEXT_PUBLIC_ (sería una fuga al bundle público)", () => {
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", undefined);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY", "leaked-key");

    expect(() => createServiceRoleClient()).toThrow(
      /Missing required env: SUPABASE_SERVICE_ROLE_KEY/,
    );
  });
});
