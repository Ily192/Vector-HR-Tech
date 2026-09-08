import { render, screen, within } from "@testing-library/react";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";

import Home from "../app/page";

// `next/link` necesita el router de Next; en jsdom lo sustituimos por un <a> real.
vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.PropsWithChildren<{ href: string }>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("career-site · Home", () => {
  it("renderiza el hero con el claim de marca", () => {
    render(<Home />);

    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent("Hackeando la rutina");
    expect(h1).toHaveTextContent("liberando el talento");
  });

  it("muestra el wordmark Vortex en el hero y el Vector en el footer", () => {
    render(<Home />);
    expect(screen.getByLabelText("VORTEX OPS")).toBeInTheDocument();
    expect(screen.getByLabelText("VECTOR HR TECH")).toBeInTheDocument();
  });

  it("marca la propuesta como agentic con el badge de IA", () => {
    render(<Home />);
    expect(screen.getByText(/Powered by agentic AI/i)).toBeInTheDocument();
  });

  it("expone los dos CTAs del hero apuntando a rutas reales", () => {
    render(<Home />);

    expect(screen.getByRole("link", { name: /Ver vacantes abiertas/i })).toHaveAttribute(
      "href",
      "/vacantes",
    );
    expect(screen.getByRole("link", { name: /Hablar con Vector HR/i })).toHaveAttribute(
      "href",
      "/contacto",
    );
  });

  it("renderiza los tres pilares con sus bullets", () => {
    render(<Home />);

    for (const pilar of ["Velocidad", "Inteligencia", "Control"]) {
      expect(screen.getByRole("heading", { level: 3, name: pilar })).toBeInTheDocument();
    }

    expect(screen.getByText(/Sourcing 24\/7/)).toBeInTheDocument();
    expect(screen.getByText(/Skills versionadas con evals/)).toBeInTheDocument();
    expect(screen.getByText(/RLS Postgres nativo/)).toBeInTheDocument();
  });

  it("el pilar Velocidad lista exactamente sus tres capacidades", () => {
    render(<Home />);

    const velocidad = screen.getByRole("heading", { level: 3, name: "Velocidad" });
    const card = velocidad.closest("div.rounded-lg");
    expect(card).not.toBeNull();
    const items = within(card as HTMLElement).getAllByRole("listitem");
    expect(items).toHaveLength(3);
  });

  it("el footer muestra el año en curso", () => {
    render(<Home />);
    const year = new Date().getFullYear().toString();
    expect(screen.getByText(new RegExp(`${year}\\s+Vector HR Tech`))).toBeInTheDocument();
  });

  it("usa un único <h1> — jerarquía correcta para SEO", () => {
    render(<Home />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
