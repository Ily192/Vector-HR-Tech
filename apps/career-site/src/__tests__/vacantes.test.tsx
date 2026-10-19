import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VacanteDetail, { generateMetadata } from "../app/vacantes/[slug]/page";
import VacantesPage, { metadata } from "../app/vacantes/page";

vi.mock("next/link", async () => ({ default: (await import("../test/mocks-next")).LinkFalso }));
vi.mock("next/form", async () => ({ default: (await import("../test/mocks-next")).FormFalso }));

// `vi.hoisted` es necesario porque la factory de `vi.mock` se evalúa antes que el
// cuerpo del módulo de test.
const { notFound } = vi.hoisted(() => ({
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
}));

beforeEach(() => {
  notFound.mockClear();
});

/** Las páginas son Server Components async: se invocan y se renderiza lo que resuelven. */
const listado = (params: Record<string, string> = {}) =>
  VacantesPage({ searchParams: Promise.resolve(params) });
const detalle = (slug: string) => VacanteDetail({ params: Promise.resolve({ slug }) });

describe("career-site · /vacantes", () => {
  it("declara el título de la página para el <head>", () => {
    expect(metadata).toEqual({ title: "Vacantes abiertas" });
  });

  it("lista todas las vacantes, cada una enlazando a su detalle", async () => {
    render(await listado());
    expect(screen.getByRole("heading", { level: 1, name: /Vacantes abiertas/i })).toBeVisible();
    const tarjetas = document.querySelectorAll("[data-vacante]");
    expect(tarjetas).toHaveLength(5);
    for (const t of tarjetas) expect(t.getAttribute("href")).toMatch(/^\/vacantes\/[a-z0-9-]+$/);
    expect(screen.getByText("5 vacantes")).toBeInTheDocument();
  });

  it("la tarjeta muestra empresa, ubicación, modalidad, nivel y salario en español", async () => {
    render(await listado());
    const card = within(
      document.querySelector('[data-vacante="coordinador-de-almacen"]') as HTMLElement,
    );
    expect(card.getByText("Andes Logística")).toBeInTheDocument();
    expect(card.getByText("Monterrey, NL")).toBeInTheDocument();
    expect(card.getByText("Híbrido")).toBeInTheDocument();
    expect(card.getByText("Semi-senior")).toBeInTheDocument();
    expect(card.getByText(/\$22,000 – \$28,000/)).toBeInTheDocument();
  });

  it("si la empresa no publica salario, dice 'Salario a convenir'", async () => {
    render(await listado());
    const card = within(
      document.querySelector('[data-vacante="hr-business-partner"]') as HTMLElement,
    );
    expect(card.getByText("Salario a convenir")).toBeInTheDocument();
  });

  it("marca la vacante que llegó al tope de aplicaciones como 'Cupo completo'", async () => {
    render(await listado());
    const llena = within(document.querySelector('[data-vacante="data-analyst"]') as HTMLElement);
    expect(llena.getByText("Cupo completo")).toBeInTheDocument();
    const abierta = document.querySelector(
      '[data-vacante="senior-software-engineer"]',
    ) as HTMLElement;
    expect(within(abierta).queryByText("Cupo completo")).toBeNull();
  });

  it("filtra por palabra clave sin distinguir acentos ni mayúsculas", async () => {
    render(await listado({ q: "ALMACEN" }));
    expect(document.querySelectorAll("[data-vacante]")).toHaveLength(1);
    expect(screen.getByText("1 vacante")).toBeInTheDocument();
  });

  it("filtra por modalidad y marca el filtro activo", async () => {
    render(await listado({ modalidad: "remote" }));
    expect(document.querySelectorAll("[data-vacante]")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Remoto" })).toHaveAttribute("aria-current", "true");
  });

  it("ignora una modalidad inválida en la URL en vez de fallar", async () => {
    render(await listado({ modalidad: "marte" }));
    expect(document.querySelectorAll("[data-vacante]")).toHaveLength(5);
  });

  it("sin resultados, lo dice y ofrece volver a ver todas", async () => {
    render(await listado({ q: "astronauta" }));
    expect(screen.getByRole("heading", { name: /No hay vacantes/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver todas las vacantes" })).toHaveAttribute(
      "href",
      "/vacantes",
    );
  });
});

describe("career-site · /vacantes/[slug]", () => {
  it("renderiza el detalle con empresa, salario y descripción", async () => {
    render(await detalle("coordinador-de-almacen"));
    expect(
      screen.getByRole("heading", { level: 1, name: "Coordinador de almacén" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Andes Logística")).toBeInTheDocument();
    expect(screen.getByText(/\$22,000 – \$28,000/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Sobre el rol/i })).toBeInTheDocument();
    expect(notFound).not.toHaveBeenCalled();
  });

  it("muestra estado, modalidad, ubicación y nivel con etiquetas en español", async () => {
    render(await detalle("hr-business-partner"));
    expect(screen.getByText("Abierta")).toBeInTheDocument();
    expect(screen.getByText("Híbrido")).toBeInTheDocument();
    expect(screen.getByText("CDMX")).toBeInTheDocument();
    expect(screen.getByText("Semi-senior")).toBeInTheDocument();
    expect(screen.getByText("Salario a convenir")).toBeInTheDocument();
  });

  it("titula la pestaña con puesto y empresa", async () => {
    expect(await generateMetadata({ params: Promise.resolve({ slug: "data-analyst" }) })).toEqual({
      title: "Data Analyst · Grupo Cobalto",
    });
  });

  it("ofrece el CTA de aplicar deshabilitado (la subida de CV llega después)", async () => {
    render(await detalle("senior-software-engineer"));
    expect(screen.getByRole("button", { name: /Subir CV/i })).toBeDisabled();
  });

  it("con el cupo completo no ofrece aplicar y lo explica", async () => {
    render(await detalle("data-analyst"));
    expect(screen.getByText("Esta vacante ya no recibe aplicaciones.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Subir CV/i })).toBeNull();
  });

  it("incluye el link de vuelta al listado", async () => {
    render(await detalle("senior-software-engineer"));
    expect(screen.getByRole("link", { name: /Volver a vacantes/i })).toHaveAttribute(
      "href",
      "/vacantes",
    );
  });

  it("llama a notFound() cuando el slug no existe, y el lookup es exacto", async () => {
    await expect(detalle("no-existe")).rejects.toThrow("NEXT_NOT_FOUND");
    await expect(detalle("Data-Analyst")).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalledTimes(2);
  });
});
