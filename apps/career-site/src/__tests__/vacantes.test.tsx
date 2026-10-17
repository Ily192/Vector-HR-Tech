import { render, screen, within } from "@testing-library/react";
import type * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VacanteDetail from "../app/vacantes/[slug]/page";
import VacantesPage, { metadata } from "../app/vacantes/page";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.PropsWithChildren<{ href: string }>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

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

/**
 * El detalle es un Server Component async (`params` llega como Promise), así que
 * se invoca como función y se renderiza el JSX que resuelve.
 */
function detalle(slug: string) {
  return VacanteDetail({ params: Promise.resolve({ slug }) });
}

describe("career-site · /vacantes", () => {
  it("declara el título de la página para el <head>", () => {
    expect(metadata).toEqual({ title: "Vacantes abiertas" });
  });

  it("renderiza el encabezado del listado", async () => {
    render(await VacantesPage());
    expect(
      screen.getByRole("heading", { level: 1, name: /Vacantes abiertas/i }),
    ).toBeInTheDocument();
  });

  it("lista una card por vacante, cada una enlazando a su detalle", async () => {
    render(await VacantesPage());

    const links = screen.getAllByRole("link");
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link.getAttribute("href")).toMatch(/^\/vacantes\/[a-z0-9-]+$/);
    }

    expect(screen.getByRole("link", { name: /Senior Software Engineer/i })).toHaveAttribute(
      "href",
      "/vacantes/senior-software-engineer",
    );
    expect(screen.getByRole("link", { name: /HR Business Partner/i })).toHaveAttribute(
      "href",
      "/vacantes/hr-business-partner",
    );
  });

  it("muestra seniority, ubicación y modalidad con sus etiquetas en español", async () => {
    render(await VacantesPage());

    const card = screen.getByRole("link", { name: /Senior Software Engineer/i });
    const scoped = within(card);
    expect(scoped.getByText("Senior")).toBeInTheDocument();
    expect(scoped.getByText("LATAM")).toBeInTheDocument();
    expect(scoped.getByText("Remoto")).toBeInTheDocument();
    expect(scoped.getByText("Abierta")).toBeInTheDocument();
  });

  it("cada vacante muestra el inicio de su descripción", async () => {
    render(await VacantesPage());
    expect(screen.getByText(/Liderarás el diseño e implementación/)).toBeInTheDocument();
    expect(screen.getByText(/Serás el puente entre los líderes técnicos/)).toBeInTheDocument();
  });

  it("cuenta las vacantes que devuelve la capa de datos", async () => {
    render(await VacantesPage());
    expect(screen.getByText("2 vacantes abiertas")).toBeInTheDocument();
  });
});

describe("career-site · /vacantes/[slug]", () => {
  it("renderiza el detalle de una vacante existente", async () => {
    render(await detalle("senior-software-engineer"));

    expect(
      screen.getByRole("heading", { level: 1, name: "Senior Software Engineer" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Sobre el rol/i })).toBeInTheDocument();
    expect(screen.getByText(/FastAPI, SQLAlchemy 2 async, Celery, Supabase/)).toBeInTheDocument();
    expect(notFound).not.toHaveBeenCalled();
  });

  it("muestra badges de estado, modalidad y ubicación", async () => {
    render(await detalle("hr-business-partner"));

    expect(screen.getByText("Abierta")).toBeInTheDocument();
    expect(screen.getByText("Híbrido")).toBeInTheDocument();
    expect(screen.getByText("CDMX")).toBeInTheDocument();
  });

  it("ofrece el CTA de aplicar deshabilitado (upload llega en cycle 1)", async () => {
    render(await detalle("senior-software-engineer"));

    const cta = screen.getByRole("button", { name: /Subir CV/i });
    expect(cta).toBeDisabled();
  });

  it("incluye el link de vuelta al listado", async () => {
    render(await detalle("senior-software-engineer"));
    expect(screen.getByRole("link", { name: /Volver a vacantes/i })).toHaveAttribute(
      "href",
      "/vacantes",
    );
  });

  it("llama a notFound() cuando el slug no existe", async () => {
    await expect(detalle("no-existe")).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalledTimes(1);
  });

  it("no confunde slugs parecidos — el lookup es case-sensitive", async () => {
    await expect(detalle("Senior-Software-Engineer")).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalledTimes(1);
  });
});
