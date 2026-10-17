import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Home from "../app/page";

vi.mock("next/link", async () => ({ default: (await import("../test/mocks-next")).LinkFalso }));
vi.mock("next/form", async () => ({ default: (await import("../test/mocks-next")).FormFalso }));

describe("career-site · inicio para candidatos", () => {
  it("el titular habla al candidato, no vende a empresas", async () => {
    render(await Home());
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent("Tu siguiente trabajo");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("no tiene CTAs comerciales (ADR-017)", async () => {
    render(await Home());
    expect(screen.queryByText(/Agendar/i)).toBeNull();
    expect(screen.queryByText(/Hablar con Vector HR/i)).toBeNull();
    expect(document.querySelector('a[href="/contacto"]')).toBeNull();
  });

  it("el buscador envía puesto y ubicación a /vacantes por GET", async () => {
    render(await Home());
    // Landmark nativo <search>; jsdom aún no le asigna el rol, así que se busca por etiqueta.
    const form = document.querySelector('search[aria-label="Buscar vacantes"] form') as HTMLElement;
    expect(form).toHaveAttribute("action", "/vacantes");
    expect(within(form).getByPlaceholderText("Puesto o palabra clave")).toHaveAttribute(
      "name",
      "q",
    );
    expect(within(form).getByPlaceholderText("Ciudad o «remoto»")).toHaveAttribute(
      "name",
      "ubicacion",
    );
  });

  it("cuenta vacantes y empresas a partir de la capa de datos", async () => {
    render(await Home());
    expect(screen.getByText("5 vacantes · 4 empresas en LATAM")).toBeInTheDocument();
  });

  it("muestra las vacantes recientes como tarjetas que llevan a su detalle", async () => {
    render(await Home());
    const tarjetas = document.querySelectorAll("[data-vacante]");
    expect(tarjetas).toHaveLength(5);
    expect(tarjetas[0]).toHaveAttribute("href", "/vacantes/coordinador-de-almacen");
  });

  it("explica cómo se aplica en tres pasos, enlazable desde la cabecera", async () => {
    render(await Home());
    const seccion = document.getElementById("como-aplicar") as HTMLElement;
    expect(within(seccion).getAllByRole("heading", { level: 3 })).toHaveLength(3);
  });
});
