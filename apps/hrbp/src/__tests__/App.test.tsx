import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "../App";

describe("hrbp · App (cockpit)", () => {
  it("renderiza la barra superior con el wordmark y el indicador Live", () => {
    render(<App />);

    expect(screen.getByLabelText("VORTEX OPS")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ilyra · Vector HR/ })).toBeInTheDocument();
  });

  it("saluda al usuario en el encabezado principal", () => {
    render(<App />);

    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent("Hola, Ilyra");
    expect(screen.getByText(/Cockpit HRBP/)).toBeInTheDocument();
  });

  it("expone el CTA para crear una vacante", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "+ Nueva vacante" })).toBeInTheDocument();
  });

  it("renderiza los cuatro KPIs con su valor y su delta", () => {
    render(<App />);

    const kpis: Array<[string, string, string]> = [
      ["Vacantes activas", "8", "+2 esta semana"],
      ["Candidatos en pipeline", "142", "+34 hoy"],
      ["Runs de agentes (24h)", "327", "98% éxito"],
      ["Costo IA hoy (USD)", "$1.42", "12% del cap"],
    ];

    for (const [label, value, delta] of kpis) {
      expect(screen.getByText(label)).toBeInTheDocument();
      expect(screen.getByText(value)).toBeInTheDocument();
      expect(screen.getByText(delta)).toBeInTheDocument();
    }
  });

  it("renderiza el kanban de pipeline con sus cinco etapas y conteos", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: /Pipeline · Senior Software Engineer/ }),
    ).toBeInTheDocument();

    const etapas: Array<[string, string]> = [
      ["Aplicados", "84"],
      ["Evaluados", "41"],
      ["Shortlist", "12"],
      ["Entrevista", "3"],
      ["Oferta", "2"],
    ];

    for (const [etapa, count] of etapas) {
      const label = screen.getByText(etapa);
      const column = label.closest("div.rounded-lg");
      expect(column, `columna de ${etapa}`).not.toBeNull();
      expect(within(column as HTMLElement).getByText(count)).toBeInTheDocument();
    }
  });

  it("marca el pipeline como mock hasta que cycle 1 lo conecte al hr-engine", () => {
    render(<App />);
    expect(screen.getByText(/Mock — el cycle 1 conecta esto a hr-engine/)).toBeInTheDocument();
  });

  it("todos los botones del cockpit son type=button (no submits accidentales)", () => {
    render(<App />);
    for (const button of screen.getAllByRole("button")) {
      expect(button).toHaveAttribute("type", "button");
    }
  });

  it("usa un único <h1> en la vista", () => {
    render(<App />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
