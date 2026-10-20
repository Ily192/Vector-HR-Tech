import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Con Supabase configurado: las vacantes salen de `vacantes_publicas` y el detalle
 * trae el formulario. El cliente de Supabase se sustituye por uno en memoria.
 */

const FILAS = [
  {
    id: "00000000-0000-4000-8000-0000000000b1",
    slug: "analista-de-datos-k3f9",
    title: "Analista de datos",
    jd: "SQL y Python para tableros de operación.",
    seniority: "semi-senior",
    modality: "remote",
    location: "Monterrey, NL",
    created_at: "2026-10-19T15:00:00+00:00",
    empresa_nombre: "Siete",
    empresa_slug: "siete",
    salario_min: null,
    salario_max: null,
    moneda: null,
    cupo_completo: false,
  },
];

const estado = vi.hoisted(() => ({
  error: null as { message: string } | null,
  slug: null as string | null,
}));

vi.mock("../lib/supabase", () => ({ supabaseConfigurado: () => true }));
vi.mock("@vortex/supabase-client", () => {
  const consulta = {
    select: () => consulta,
    order: () => consulta,
    eq: (_columna: string, valor: string) => {
      estado.slug = valor;
      return consulta;
    },
    limit: async () => ({
      data: estado.error ? null : FILAS.filter((f) => !estado.slug || f.slug === estado.slug),
      error: estado.error,
    }),
  };
  return {
    createPublicClient: () => ({ from: () => consulta }),
    createServiceRoleClient: () => ({}),
    getOptionalEnv: () => "configurada",
  };
});
vi.mock("next/link", async () => ({ default: (await import("../test/mocks-next")).LinkFalso }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));
vi.mock("next/script", () => ({ default: () => null }));

beforeEach(() => {
  estado.error = null;
  estado.slug = null;
});

describe("career-site con Supabase", () => {
  it("lee vacantes_publicas, normaliza la fecha y filtra sin acentos", async () => {
    const { listarVacantes } = await import("../lib/vacantes");
    const vacantes = await listarVacantes({ q: "ANALISTA" });
    expect(vacantes.map((v) => v.slug)).toEqual(["analista-de-datos-k3f9"]);
    expect(vacantes[0]?.created_at).toBe("2026-10-19T15:00:00.000Z");
    expect(await listarVacantes({ q: "ventas" })).toEqual([]);
  });

  it("busca el detalle por slug", async () => {
    const { obtenerVacante } = await import("../lib/vacantes");
    expect((await obtenerVacante("analista-de-datos-k3f9"))?.empresa_nombre).toBe("Siete");
    expect(await obtenerVacante("no-existe")).toBeNull();
  });

  it("si Supabase falla, lo dice en vez de mostrar el sitio vacío", async () => {
    estado.error = { message: "connection refused" };
    const { listarVacantes } = await import("../lib/vacantes");
    await expect(listarVacantes()).rejects.toThrow(/connection refused/);
  });

  it("el detalle trae el formulario de aplicación", async () => {
    const { default: VacanteDetail } = await import("../app/vacantes/[slug]/page");
    render(await VacanteDetail({ params: Promise.resolve({ slug: "analista-de-datos-k3f9" }) }));
    expect(screen.getByRole("form", { name: "Aplicar a la vacante" })).toBeInTheDocument();
    expect(screen.getByText(/Envía tu CV a Siete/)).toBeInTheDocument();
  });
});
