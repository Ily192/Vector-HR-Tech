import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SiteFooter } from "../components/site-footer";
import { SiteHeader } from "../components/site-header";

vi.mock("next/link", async () => ({ default: (await import("../test/mocks-next")).LinkFalso }));

describe("career-site · encabezado y pie comunes", () => {
  it("el encabezado lleva el wordmark al inicio", () => {
    render(<SiteHeader />);
    expect(screen.getByRole("link", { name: /Vortex Empleos, inicio/i })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByLabelText("VORTEX OPS")).toBeInTheDocument();
  });

  it("el encabezado solo navega para candidatos, sin CTA de venta", () => {
    render(<SiteHeader />);
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(nav.querySelector('a[href="/vacantes"]')).not.toBeNull();
    expect(nav.querySelector('a[href="/#como-aplicar"]')).not.toBeNull();
    expect(screen.queryByText(/Agendar demo/i)).toBeNull();
  });

  it("el pie dice de quién es el servicio y el año en curso", () => {
    render(<SiteFooter />);
    const year = new Date().getFullYear().toString();
    expect(screen.getByText(new RegExp(`${year}.*Vector HR Tech`))).toBeInTheDocument();
  });

  it("la única puerta para empresas es su panel", () => {
    render(<SiteFooter />);
    expect(screen.getByRole("link", { name: /Entra a tu panel/i })).toHaveAttribute(
      "href",
      "https://vortex-hrbp.vercel.app",
    );
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});
