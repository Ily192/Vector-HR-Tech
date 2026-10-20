import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FormularioDeAplicacion } from "../components/formulario-de-aplicacion";
import type { ResultadoDeAplicar } from "../lib/tipos-de-aplicacion";

vi.mock("next/script", () => ({ default: () => null }));

function montar(
  responder: () => ResultadoDeAplicar = () => ({ estado: "ok" }),
  sitekey: string | null = null,
  conIa = false,
) {
  const accion = vi.fn(async (_anterior: ResultadoDeAplicar | null, _datos: FormData) =>
    responder(),
  );
  render(
    <FormularioDeAplicacion
      accion={accion}
      empresa="Andes Logística"
      conIa={conIa}
      sitekey={sitekey}
    />,
  );
  return accion;
}

async function enviar() {
  await act(async () => {
    fireEvent.submit(screen.getByRole("form", { name: "Aplicar a la vacante" }));
  });
}

describe("FormularioDeAplicacion", () => {
  it("pide nombre, correo y CV, y ofrece la oposición y el aviso de privacidad", () => {
    montar();
    expect(screen.getByLabelText("Nombre completo")).toBeRequired();
    expect(screen.getByLabelText("Correo")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText(/Tu CV/)).toHaveAttribute(
      "accept",
      expect.stringContaining(".pdf"),
    );
    expect(screen.getByLabelText("Evaluar mi CV sin procesos automatizados")).not.toBeChecked();
    expect(screen.getByLabelText("Leí y acepto el aviso de privacidad")).toBeRequired();
    expect(screen.getByText("Aviso de privacidad")).toBeInTheDocument();
  });

  it("sin IA, el aviso dice que solo se cuentan menciones y que no decide nada", () => {
    montar();
    expect(screen.getByText(/solo un conteo de cuántos CVs las mencionan/)).toBeInTheDocument();
    expect(screen.queryByText(/Un sistema de IA compara tu CV/)).toBeNull();
  });

  it("con IA, el aviso dice que la IA no descarta y que se puede pedir revisión humana", () => {
    montar(undefined, null, true);
    const aviso = screen.getByText(/Un sistema de IA compara tu CV/);
    expect(aviso).toHaveTextContent("sin recibir tu nombre ni tus datos de contacto");
    expect(aviso).toHaveTextContent("La IA no descarta a nadie: decide una persona de Andes");
    expect(aviso).toHaveTextContent("pedir que lo revise una persona");
    expect(screen.queryByText(/solo un conteo/)).toBeNull();
  });

  it("el campo trampa no se ve ni se alcanza con el teclado", () => {
    montar();
    const trampa = document.querySelector('input[name="sitio_web"]') as HTMLInputElement;
    expect(trampa).toHaveAttribute("tabindex", "-1");
    expect(trampa.closest('[aria-hidden="true"]')).not.toBeNull();
  });

  it("pinta Turnstile solo si hay site key", () => {
    montar();
    expect(document.querySelector(".cf-turnstile")).toBeNull();
    cleanup();
    montar(undefined, "1x00000000000000000000AA");
    expect(document.querySelector(".cf-turnstile")).toHaveAttribute(
      "data-sitekey",
      "1x00000000000000000000AA",
    );
  });

  it("al enviarse bien, confirma que el CV llegó a la empresa", async () => {
    const accion = montar();
    fireEvent.change(screen.getByLabelText("Nombre completo"), { target: { value: "Ana Pérez" } });
    await enviar();
    expect(accion).toHaveBeenCalledOnce();
    expect((accion.mock.calls[0]?.[1] as FormData).get("nombre")).toBe("Ana Pérez");
    expect(screen.getByRole("status")).toHaveTextContent("Listo, recibimos tu aplicación.");
    expect(screen.getByRole("status")).toHaveTextContent("Andes Logística");
  });

  it("muestra el error general y el de cada campo", async () => {
    montar(() => ({
      estado: "error",
      mensaje: "Revisa los datos marcados.",
      campos: { correo: "Revisa tu correo.", cv: "Tu CV pesa más de 4 MB." },
    }));
    await enviar();
    expect(screen.getByRole("alert")).toHaveTextContent("Revisa los datos marcados.");
    expect(screen.getByLabelText("Correo")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Tu CV pesa más de 4 MB.")).toBeInTheDocument();
    expect(screen.getByLabelText("Nombre completo")).not.toHaveAttribute("aria-invalid");
  });
});
