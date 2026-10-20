import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { SinAccesoAlPanel } from "../datos/tipos";
import { Entrar, ErrorDeSesion } from "../pantallas/entrar";

function montar(contenido: ReactNode) {
  const cliente = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={cliente}>{contenido}</QueryClientProvider>);
}

describe("entrar al panel", () => {
  it("pide el enlace y responde igual tenga o no cuenta el correo", async () => {
    montar(<Entrar />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Entra a tu panel");

    fireEvent.change(screen.getByLabelText("Correo de trabajo"), {
      target: { value: " mariana@andes.mx " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Mandarme el enlace" }));

    await screen.findByRole("heading", { level: 1, name: "Revisa tu correo" });
    expect(screen.getByRole("status")).toHaveTextContent(
      "Si mariana@andes.mx tiene una cuenta en Vortex Ops, te llegó un enlace",
    );

    fireEvent.click(screen.getByRole("button", { name: "Usar otro correo" }));
    expect(await screen.findByLabelText("Correo de trabajo")).toBeInTheDocument();
  });

  it("una cuenta sin acceso ve a quién escribir y solo puede salir", () => {
    montar(<ErrorDeSesion error={new SinAccesoAlPanel()} reintentar={() => {}} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Tu cuenta no tiene acceso",
    );
    expect(screen.getByRole("link", { name: "hola@vectorhr.tech" })).toHaveAttribute(
      "href",
      "mailto:hola@vectorhr.tech",
    );
    expect(screen.queryByRole("button", { name: "Reintentar" })).toBeNull();
    expect(screen.getByRole("button", { name: "Salir" })).toBeInTheDocument();
  });

  it("si falla la red, deja reintentar", () => {
    const reintentar = vi.fn();
    montar(<ErrorDeSesion error={new Error("Failed to fetch")} reintentar={reintentar} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "No pudimos abrir tu panel",
    );
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(reintentar).toHaveBeenCalledOnce();
  });
});
