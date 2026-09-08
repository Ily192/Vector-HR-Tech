import { render, screen } from "@testing-library/react";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";

import ContactoPage, { metadata } from "../app/contacto/page";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.PropsWithChildren<{ href: string }>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("career-site · /contacto", () => {
  it("declara título y descripción para SEO", () => {
    expect(metadata.title).toBe("Hablar con Vector HR");
    expect(metadata.description).toMatch(/Vortex Ops/);
  });

  it("renderiza el encabezado principal", () => {
    render(<ContactoPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: /Hablemos de tu operación/i }),
    ).toBeInTheDocument();
  });

  it("ofrece el canal de email como enlace mailto con asunto precargado", () => {
    render(<ContactoPage />);

    const email = screen.getByRole("link", { name: /@/ });
    const href = email.getAttribute("href") ?? "";
    expect(href.startsWith("mailto:")).toBe(true);
    expect(href).toContain("subject=");
    expect(decodeURIComponent(href)).toContain("Quiero conocer Vortex Ops");
  });

  it("usa el email por defecto cuando no hay NEXT_PUBLIC_CONTACT_EMAIL", () => {
    render(<ContactoPage />);
    expect(screen.getByText("hola@vectorhr.tech")).toBeInTheDocument();
  });

  it("ofrece el canal LinkedIn apuntando a la company page", () => {
    render(<ContactoPage />);

    const linkedin = screen.getByRole("link", { name: "/company/vector-hr-tech" });
    expect(linkedin).toHaveAttribute("href", "https://www.linkedin.com/company/vector-hr-tech");
    expect(linkedin).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("promete respuesta en 24 h con un badge", () => {
    render(<ContactoPage />);
    expect(screen.getByText(/Respuesta en 24 h/i)).toBeInTheDocument();
  });

  it("cross-linkea a vacantes para quien busca trabajo, no una demo", () => {
    render(<ContactoPage />);

    expect(
      screen.getByRole("heading", { name: /¿Buscas trabajo, no una demo\?/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ver vacantes abiertas/i })).toHaveAttribute(
      "href",
      "/vacantes",
    );
  });

  it("incluye el link de vuelta al inicio y el wordmark Vector", () => {
    render(<ContactoPage />);

    expect(screen.getByRole("link", { name: /Volver al inicio/i })).toHaveAttribute("href", "/");
    expect(screen.getByLabelText("VECTOR HR TECH")).toBeInTheDocument();
  });
});
