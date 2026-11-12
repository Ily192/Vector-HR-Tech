import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createCareerSiteClient } from "../career-site";

const ANON = "clave-anon-de-prueba";
const CAREER = "header.clave-career-site-de-prueba.firma";

let pedidas: { url: string; cabeceras: Headers }[] = [];

beforeEach(() => {
  pedidas = [];
  vi.stubEnv("SUPABASE_URL", "https://api.prueba.invalid");
  vi.stubEnv("SUPABASE_ANON_KEY", ANON);
  vi.stubEnv("SUPABASE_CAREER_SITE_KEY", CAREER);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
      pedidas.push({ url: String(entrada), cabeceras: new Headers(init?.headers) });
      return new Response("[]", { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("createCareerSiteClient", () => {
  it("manda la anon en apikey (la que deja pasar el gateway) y su JWT en Authorization", async () => {
    await createCareerSiteClient().from("vacantes").select("id, empresa_id").eq("slug", "x");
    expect(pedidas).toHaveLength(1);
    expect(pedidas[0]?.url).toContain("/rest/v1/vacantes");
    expect(pedidas[0]?.cabeceras.get("apikey")).toBe(ANON);
    expect(pedidas[0]?.cabeceras.get("authorization")).toBe(`Bearer ${CAREER}`);
  });

  it("Storage también entra con su JWT, y las cabeceras extra llegan (x-cv-ruta)", async () => {
    const ruta = "11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222.pdf";
    await createCareerSiteClient({ cabeceras: { "x-cv-ruta": ruta } })
      .storage.from("cvs")
      .remove([ruta]);
    expect(pedidas).toHaveLength(1);
    expect(pedidas[0]?.url).toContain("/storage/v1/object/cvs");
    expect(pedidas[0]?.cabeceras.get("authorization")).toBe(`Bearer ${CAREER}`);
    expect(pedidas[0]?.cabeceras.get("x-cv-ruta")).toBe(ruta);
  });

  it("nunca usa la service_role aunque esté en el entorno", async () => {
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "la-service-role");
    await createCareerSiteClient().from("vacantes").select("id");
    const cabeceras = [...(pedidas[0]?.cabeceras.values() ?? [])].join(" ");
    expect(cabeceras).not.toContain("la-service-role");
  });

  it("sin la clave lanza, nombrando la variable y sin caer en otra clave", () => {
    vi.stubEnv("SUPABASE_CAREER_SITE_KEY", undefined);
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "la-service-role");
    expect(() => createCareerSiteClient()).toThrow(
      /Missing required env: SUPABASE_CAREER_SITE_KEY/,
    );
  });

  it("lanza desde el navegador antes de leer el entorno", () => {
    vi.stubGlobal("window", {});
    expect(() => createCareerSiteClient()).toThrow(/llamado desde código browser/);
    expect(() => createCareerSiteClient()).not.toThrow(/Missing required env/);
  });
});
