import { render, screen } from "@testing-library/react";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { SiteFooter } from "../components/site-footer";
import { SiteHeader } from "../components/site-header";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.PropsWithChildren<{ href: string }>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("career-site · encabezado y pie comunes", () => {
  it("el encabezado lleva el wordmark Vortex al inicio", () => {
    render(<SiteHeader />);
    expect(screen.getByRole("link", { name: /Vortex Ops, inicio/i })).toHaveAttribute("href", "/");
    expect(screen.getByLabelText("VORTEX OPS")).toBeInTheDocument();
  });

  it("el encabezado navega a vacantes y contacto, con un único CTA", () => {
    render(<SiteHeader />);
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(nav.querySelector('a[href="/vacantes"]')).not.toBeNull();
    expect(nav.querySelector('a[href="/contacto"]')).not.toBeNull();
    expect(screen.getByRole("link", { name: "Agendar demo" })).toHaveAttribute("href", "/contacto");
  });

  it("el pie muestra el wordmark Vector y el año en curso", () => {
    render(<SiteFooter />);
    expect(screen.getByLabelText("VECTOR HR TECH")).toBeInTheDocument();
    const year = new Date().getFullYear().toString();
    expect(screen.getByText(new RegExp(`${year}\\s+Vector HR Tech`))).toBeInTheDocument();
  });

  it("el pie ofrece el email de contacto como mailto", () => {
    render(<SiteFooter />);
    expect(screen.getByRole("link", { name: "hola@vectorhr.tech" })).toHaveAttribute(
      "href",
      "mailto:hola@vectorhr.tech",
    );
  });
});
