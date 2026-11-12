import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SinAccesoAlPanel } from "../datos/tipos";
import { Entrar, ErrorDeSesion } from "../pantallas/entrar";

// Lo que responde Auth, sin red: cada test decide.
const panel = vi.hoisted(() => ({
  entrar: vi.fn(),
  verificarCodigo: vi.fn(),
}));
vi.mock("../datos/panel", async (original) => ({
  ...(await original<typeof import("../datos/panel")>()),
  ...panel,
}));

function montar(contenido: ReactNode) {
  const cliente = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={cliente}>{contenido}</QueryClientProvider>);
}

const codigo = () => screen.getByLabelText("Código de 6 dígitos");

beforeEach(() => {
  panel.entrar.mockReset().mockResolvedValue({ ok: true });
  panel.verificarCodigo.mockReset().mockResolvedValue({ ok: true });
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("entrar al panel con un código", () => {
  it("pide el código, responde igual tenga o no cuenta el correo y entra con él", async () => {
    montar(<Entrar />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Entra a tu panel");
    expect(screen.getByLabelText("VECTOR HR TECH")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Regístrate gratis" })).toHaveAttribute(
      "href",
      "https://vectorhrtech.com/publicar-vacantes",
    );

    fireEvent.change(screen.getByLabelText("Correo de trabajo"), {
      target: { value: " mariana@andes.mx " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Mandarme el código" }));

    await screen.findByRole("heading", { level: 1, name: "Escribe tu código" });
    expect(String(panel.entrar.mock.calls[0]?.[0]).trim()).toBe("mariana@andes.mx");
    expect(
      screen.getByText(/tiene una cuenta en el panel de Vector HR Tech, te llegó un código/),
    ).toHaveTextContent("Si mariana@andes.mx tiene una cuenta");

    const entrar = screen.getByRole("button", { name: "Entrar" });
    expect(entrar).toBeDisabled();
    fireEvent.change(codigo(), { target: { value: "12a 34-56789" } });
    expect(codigo()).toHaveValue("123456");
    expect(codigo()).toHaveAttribute("autocomplete", "one-time-code");
    expect(codigo()).toHaveAttribute("inputmode", "numeric");
    fireEvent.click(entrar);

    await vi.waitFor(() =>
      expect(panel.verificarCodigo).toHaveBeenCalledWith("mariana@andes.mx", "123456"),
    );
  });

  it("si el código no sirve lo dice, y deja pedir otro pasado el minuto", async () => {
    panel.verificarCodigo.mockResolvedValue({ ok: false, motivo: "codigo-invalido" });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    montar(<Entrar />);
    fireEvent.change(screen.getByLabelText("Correo de trabajo"), {
      target: { value: "mariana@andes.mx" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Mandarme el código" }));
    await screen.findByRole("heading", { level: 1, name: "Escribe tu código" });

    fireEvent.change(codigo(), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El código no es correcto o ya venció",
    );

    const reenviar = screen.getByRole("button", { name: /^Reenviar código \(\d+ s\)$/ });
    expect(reenviar).toBeDisabled();
    for (let s = 0; s < 61; s++) {
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    }
    fireEvent.click(screen.getByRole("button", { name: "Reenviar código" }));
    expect(await screen.findByText("Te mandamos otro código.")).toBeInTheDocument();
    expect(panel.entrar).toHaveBeenCalledTimes(2);
    expect(codigo()).toHaveValue("");
  });

  it("deja volver a escribir el correo", async () => {
    montar(<Entrar />);
    fireEvent.change(screen.getByLabelText("Correo de trabajo"), {
      target: { value: "mariana@andes.mx" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Mandarme el código" }));
    await screen.findByRole("heading", { level: 1, name: "Escribe tu código" });
    fireEvent.click(screen.getByRole("button", { name: "Usar otro correo" }));
    expect(screen.getByLabelText("Correo de trabajo")).toHaveValue("mariana@andes.mx");
  });

  it("si Auth pide esperar, lo dice", async () => {
    panel.entrar.mockResolvedValue({ ok: false, motivo: "demasiados-intentos" });
    montar(<Entrar />);
    fireEvent.change(screen.getByLabelText("Correo de trabajo"), {
      target: { value: "mariana@andes.mx" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Mandarme el código" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Espera un minuto");
  });
});

describe("/verificar, al volver del registro en la web", () => {
  it("lee el correo del fragmento, lo quita de la URL y pide el código que ya salió", async () => {
    window.history.replaceState(null, "", "/verificar#correo=ana%2Brh%40andes.mx");
    vi.resetModules();
    const { Entrar: EntrarDelRegistro } = await import("../pantallas/entrar");
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/verificar");

    montar(<EntrarDelRegistro />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Escribe tu código");
    expect(screen.getByText(/para entrar a tu panel/)).toHaveTextContent(
      "Te mandamos un código de 6 dígitos a ana+rh@andes.mx",
    );
    // El código lo mandó el alta: el panel no pide otro.
    expect(panel.entrar).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /^Reenviar código \(\d+ s\)$/ })).toBeDisabled();

    fireEvent.change(codigo(), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await vi.waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(panel.verificarCodigo).toHaveBeenCalledWith("ana+rh@andes.mx", "654321");
  });
});

describe("errores de sesión", () => {
  it("una cuenta sin acceso ve a quién escribir y solo puede salir", () => {
    montar(<ErrorDeSesion error={new SinAccesoAlPanel()} reintentar={() => {}} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Tu cuenta no tiene acceso",
    );
    expect(screen.getByRole("link", { name: "hola@vectorhrtech.com" })).toHaveAttribute(
      "href",
      "mailto:hola@vectorhrtech.com",
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
