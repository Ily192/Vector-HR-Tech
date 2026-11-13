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
  {
    id: "00000000-0000-4000-8000-0000000000b2",
    slug: "ejecutivo-de-ventas-p2x7",
    title: "Ejecutivo de ventas",
    jd: "Ventas consultivas a pymes.",
    seniority: "junior",
    modality: "onsite",
    location: "Caracas",
    created_at: "2026-10-18T15:00:00+00:00",
    empresa_nombre: "Recluta con Ana",
    empresa_slug: "recluta-con-ana",
    salario_min: null,
    salario_max: null,
    moneda: null,
    cupo_completo: false,
    evalua_con_ia: false,
    empresa_verificada: false,
    publicada_por: "Ana Ruiz",
    linkedin_de_quien_publica: "https://www.linkedin.com/in/ana-ruiz",
  },
];

const estado = vi.hoisted(() => ({
  error: null as { message: string } | null,
  slug: null as string | null,
}));

vi.mock("../lib/supabase", () => ({ supabaseConfigurado: () => true }));
vi.mock("@fluveai/supabase-client", () => {
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
    createCareerSiteClient: () => ({}),
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
    // Sin las columnas de 0019, la insignia y quien publica salen vacías.
    expect(vacantes[0]?.empresa_verificada).toBe(false);
    expect(vacantes[0]?.publicada_por).toBeNull();
    expect(vacantes[0]?.created_at).toBe("2026-10-19T15:00:00.000Z");
    expect(await listarVacantes({ q: "enfermería" })).toEqual([]);
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
    // Y el botón de reporte, con su aviso (ADR-022).
    expect(screen.getByRole("form", { name: "Reportar la vacante" })).toBeInTheDocument();
    expect(
      screen.getByText("Vector HR nunca te pedirá dinero para postularte."),
    ).toBeInTheDocument();
  });

  it("la de un reclutador independiente sale a su nombre, con su LinkedIn y sin insignia", async () => {
    const { default: VacanteDetail } = await import("../app/vacantes/[slug]/page");
    render(await VacanteDetail({ params: Promise.resolve({ slug: "ejecutivo-de-ventas-p2x7" }) }));
    expect(
      screen.getByText(/Publicada por Ana Ruiz, reclutador\(a\) independiente/),
    ).toBeInTheDocument();
    const enlace = screen.getByRole("link", { name: "LinkedIn" });
    expect(enlace).toHaveAttribute("href", "https://www.linkedin.com/in/ana-ruiz");
    expect(enlace).toHaveAttribute("rel", "nofollow noopener noreferrer");
    expect(screen.queryByText("Empresa verificada")).toBeNull();
  });
});
