import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  AvisoDeModeracion,
  AvisoDeReclutador,
  InsigniaDeModeracion,
  sinAplicaciones,
} from "../pantallas/moderacion";

const COBRO = {
  regla: "pago",
  senal: "Le pide al candidato pagar, depositar o comprar algo.",
  gravedad: "alta" as const,
  cita: "Debes pagar el kit",
  corregir: "Quita cualquier cobro al candidato.",
};

describe("la moderación en el panel (ADR-022)", () => {
  it("una publicada no lleva insignia ni aviso", () => {
    const { container } = render(
      <>
        <InsigniaDeModeracion moderacion="publicada" />
        <AvisoDeModeracion moderacion="publicada" motivos={[]} />
      </>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it.each([
    ["pendiente", "Revisando"],
    ["en_revision", "En revisión"],
    ["rechazada", "Rechazada"],
    ["oculta", "Oculta por reportes"],
  ] as const)("la insignia de %s dice «%s»", (moderacion, texto) => {
    render(<InsigniaDeModeracion moderacion={moderacion} />);
    expect(screen.getByText(texto)).toBeInTheDocument();
  });

  it("una rechazada dice qué corregir y cita la frase", () => {
    render(<AvisoDeModeracion moderacion="rechazada" motivos={[COBRO]} />);
    const aviso = screen.getByRole("status");
    expect(aviso).toHaveTextContent("No la publicamos.");
    expect(aviso).toHaveTextContent("«Debes pagar el kit»");
    expect(aviso).toHaveTextContent("Qué corregir: Quita cualquier cobro al candidato.");
  });

  it("en revisión explica por qué, sin «qué corregir»", () => {
    render(
      <AvisoDeModeracion
        moderacion="en_revision"
        motivos={[
          {
            regla: "primera_vacante",
            senal: "La primera vacante de una empresa sin verificar la revisa Vector HR.",
            gravedad: "baja",
            cita: null,
            corregir: null,
          },
        ]}
      />,
    );
    const aviso = screen.getByRole("status");
    expect(aviso).toHaveTextContent("Una persona de Vector HR la revisa");
    expect(aviso).toHaveTextContent("La primera vacante de una empresa sin verificar");
    expect(aviso).not.toHaveTextContent("Qué corregir");
  });

  it("al reclutador le avisa que todas se revisan", () => {
    render(<AvisoDeReclutador />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Vector HR revisa cada vacante antes de publicarla",
    );
  });

  it("la lista vacía de aplicados dice si ya está en el career site", () => {
    expect(sinAplicaciones("publicada")).toContain("ya está en el career site");
    expect(sinAplicaciones("pendiente")).toContain("aún no está en el career site");
  });
});
