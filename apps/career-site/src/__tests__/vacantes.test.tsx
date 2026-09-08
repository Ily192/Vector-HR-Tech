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
 * Renderiza silenciando el `console.error` que React emite al propagar el throw
 * de `notFound()` — el error esperado se afirma con `toThrow`, no con el log.
 */
function renderEsperandoError(ui: React.ReactElement) {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});
  try {
    return render(ui);
  } finally {
    spy.mockRestore();
  }
}

describe("career-site · /vacantes", () => {
  it("declara el título de la página para el <head>", () => {
    expect(metadata).toEqual({ title: "Vacantes abiertas" });
  });

  it("renderiza el encabezado del listado", () => {
    render(<VacantesPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: /Vacantes abiertas/i }),
    ).toBeInTheDocument();
  });

  it("lista una card por vacante, cada una enlazando a su detalle", () => {
    render(<VacantesPage />);

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

  it("muestra seniority, ubicación y modalidad de cada vacante", () => {
    render(<VacantesPage />);

    const card = screen.getByRole("link", { name: /Senior Software Engineer/i });
    const scoped = within(card);
    expect(scoped.getByText(/senior/)).toBeInTheDocument();
    expect(scoped.getByText(/Remote · LATAM/)).toBeInTheDocument();
    expect(scoped.getByText(/remote/)).toBeInTheDocument();
    expect(scoped.getByText(/Open/)).toBeInTheDocument();
  });

  it("cada vacante muestra su resumen", () => {
    render(<VacantesPage />);
    expect(
      screen.getByText(/Liderar arquitectura de servicios Python\/FastAPI/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Acompañar líderes de tecnología/)).toBeInTheDocument();
  });
});

describe("career-site · /vacantes/[slug]", () => {
  it("renderiza el detalle de una vacante existente", () => {
    render(<VacanteDetail params={{ slug: "senior-software-engineer" }} />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Senior Software Engineer" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Sobre el rol/i })).toBeInTheDocument();
    expect(screen.getByText(/FastAPI, SQLAlchemy 2 async, Celery, Supabase/)).toBeInTheDocument();
    expect(notFound).not.toHaveBeenCalled();
  });

  it("muestra badges de estado, modalidad y ubicación", () => {
    render(<VacanteDetail params={{ slug: "hr-business-partner" }} />);

    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByText("hybrid")).toBeInTheDocument();
    expect(screen.getByText("CDMX · Híbrido")).toBeInTheDocument();
  });

  it("ofrece el CTA de aplicar deshabilitado (upload llega en cycle 1)", () => {
    render(<VacanteDetail params={{ slug: "senior-software-engineer" }} />);

    const cta = screen.getByRole("button", { name: /Subir CV/i });
    expect(cta).toBeDisabled();
  });

  it("incluye el link de vuelta al listado", () => {
    render(<VacanteDetail params={{ slug: "senior-software-engineer" }} />);
    expect(screen.getByRole("link", { name: /Volver a vacantes/i })).toHaveAttribute(
      "href",
      "/vacantes",
    );
  });

  it("llama a notFound() cuando el slug no existe", () => {
    // React reintenta el render al capturar el throw: solo verificamos que se invocó.
    expect(() => renderEsperandoError(<VacanteDetail params={{ slug: "no-existe" }} />)).toThrow(
      "NEXT_NOT_FOUND",
    );
    expect(notFound).toHaveBeenCalled();
  });

  it("no confunde slugs parecidos — el lookup es case-sensitive", () => {
    expect(() =>
      renderEsperandoError(<VacanteDetail params={{ slug: "Senior-Software-Engineer" }} />),
    ).toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
  });
});
