import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { PREGUNTAS } from "./diagnostico";
import { leerOrigen } from "./envio";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

/** Responde todo: la primera opción en las de una, y "reclutamiento" marcado en las de varias. */
async function responderTodo(usuario: ReturnType<typeof userEvent.setup>) {
  await usuario.click(screen.getByRole("button", { name: /empezar el diagnóstico/i }));
  for (const pregunta of PREGUNTAS) {
    expect(screen.getByText(pregunta.titulo)).toBeInTheDocument();
    if (pregunta.tipo === "una") {
      // En las de horas, la más alta, para que el top 3 sea predecible.
      const etiqueta = pregunta.id.startsWith("horas.")
        ? (pregunta.opciones.at(-1)?.etiqueta ?? "")
        : (pregunta.opciones[0]?.etiqueta ?? "");
      await usuario.click(screen.getByRole("button", { name: etiqueta }));
    } else {
      await usuario.click(screen.getByLabelText("Reclutamiento y filtro de CVs"));
      await usuario.click(screen.getByRole("button", { name: /siguiente/i }));
    }
  }
}

describe("el diagnóstico", () => {
  it("pide los datos antes del detalle y los manda con el origen de la campaña", async () => {
    window.history.replaceState(
      null,
      "",
      "/?utm_source=linkedin&utm_medium=social&utm_campaign=lanzamiento",
    );
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);
    const usuario = userEvent.setup();
    render(<App />);

    await responderTodo(usuario);

    // El top 3 se ve, pero sin horas hasta dejar los datos.
    expect(screen.getByText(/3 procesos que conviene atacar primero/i)).toBeInTheDocument();
    expect(screen.queryByText("Recuperables")).not.toBeInTheDocument();
    const enviar = screen.getByRole("button", { name: /ver mi diagnóstico completo/i });
    expect(enviar).toBeDisabled();

    await usuario.type(screen.getByLabelText("Tu nombre"), "Ana Pérez");
    await usuario.type(screen.getByLabelText("Empresa"), "Acme");
    await usuario.type(screen.getByLabelText("Correo de trabajo"), "Ana@Acme.mx");
    await usuario.click(screen.getByLabelText(/no quiero que me contacten/i));
    await usuario.click(enviar);

    expect(await screen.findByRole("heading", { name: "Cómo lo calculamos" })).toBeInTheDocument();
    expect(screen.getByText("Automatizar")).toBeInTheDocument();

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/diagnostico");
    const cuerpo = JSON.parse(String(init.body));
    expect(cuerpo).toMatchObject({
      p_nombre: "Ana Pérez",
      p_empresa: "Acme",
      p_correo: "ana@acme.mx",
      p_origen: "linkedin",
      p_utm_medium: "social",
      p_utm_campaign: "lanzamiento",
      p_turnstile_token: null,
      p_sin_fines_comerciales: true,
    });
    expect(cuerpo.p_resultado.procesos[0].id).toBe("reclutamiento");
    expect(cuerpo.p_horas_recuperables_mes).toBe(cuerpo.p_resultado.horasRecuperablesMes);
  });

  it("si no se pudo guardar, lo dice y no enseña el detalle", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 400 })));
    const usuario = userEvent.setup();
    render(<App />);

    await responderTodo(usuario);
    await usuario.type(screen.getByLabelText("Tu nombre"), "Ana");
    await usuario.type(screen.getByLabelText("Empresa"), "Acme");
    await usuario.type(screen.getByLabelText("Correo de trabajo"), "ana@acme.mx");
    await usuario.click(screen.getByRole("button", { name: /ver mi diagnóstico completo/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no pudimos guardar/i);
    expect(screen.queryByRole("heading", { name: "Cómo lo calculamos" })).not.toBeInTheDocument();
  });

  it("con el freno de la base (429) explica que ya hubo varios", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 429 })));
    const usuario = userEvent.setup();
    render(<App />);

    await responderTodo(usuario);
    await usuario.type(screen.getByLabelText("Tu nombre"), "Ana");
    await usuario.type(screen.getByLabelText("Empresa"), "Acme");
    await usuario.type(screen.getByLabelText("Correo de trabajo"), "ana@acme.mx");
    await usuario.click(screen.getByRole("button", { name: /ver mi diagnóstico completo/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/ya recibimos varios/i);
  });

  it("no deja enviar con un correo mal escrito", async () => {
    const usuario = userEvent.setup();
    render(<App />);
    await responderTodo(usuario);
    await usuario.type(screen.getByLabelText("Tu nombre"), "Ana");
    await usuario.type(screen.getByLabelText("Empresa"), "Acme");
    await usuario.type(screen.getByLabelText("Correo de trabajo"), "ana@acme");
    expect(screen.getByText("Revisa el correo.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ver mi diagnóstico completo/i })).toBeDisabled();
  });
});

describe("el origen", () => {
  it("sin utm queda vacío y recorta los largos", () => {
    expect(leerOrigen("")).toEqual({ origen: null, utmMedium: null, utmCampaign: null });
    expect(leerOrigen(`?utm_source=${"x".repeat(100)}`).origen).toHaveLength(64);
  });
});
