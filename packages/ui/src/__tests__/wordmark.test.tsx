import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Wordmark } from "../wordmark";

describe("Wordmark", () => {
  it("por defecto renderiza la marca Vortex (VORTEX + OPS)", () => {
    render(<Wordmark />);
    const wordmark = screen.getByLabelText("VORTEX OPS");
    expect(wordmark).toBeInTheDocument();
    expect(wordmark).toHaveTextContent("VORTEX");
    expect(wordmark).toHaveTextContent("OPS");
  });

  it('con brand="vector" renderiza VECTOR + HR TECH', () => {
    render(<Wordmark brand="vector" />);
    const wordmark = screen.getByLabelText("VECTOR HR TECH");
    expect(wordmark).toHaveTextContent("VECTOR");
    expect(wordmark).toHaveTextContent("HR TECH");
  });

  it("el aria-label describe la marca completa para lectores de pantalla", () => {
    const { rerender } = render(<Wordmark brand="vortex" />);
    expect(screen.getByLabelText("VORTEX OPS")).toBeInTheDocument();

    rerender(<Wordmark brand="vector" />);
    expect(screen.getByLabelText("VECTOR HR TECH")).toBeInTheDocument();
    expect(screen.queryByLabelText("VORTEX OPS")).not.toBeInTheDocument();
  });

  it("usa cian electric como acento en Vortex y naranja en Vector", () => {
    const { rerender } = render(<Wordmark brand="vortex" />);
    const acentoVortex = screen.getByLabelText("VORTEX OPS").querySelector("span:last-of-type");
    expect(acentoVortex).toHaveClass("text-vector-cian-electric-500");

    rerender(<Wordmark brand="vector" />);
    const acentoVector = screen.getByLabelText("VECTOR HR TECH").querySelector("span:last-of-type");
    expect(acentoVector).toHaveClass("text-vector-orange-500");
  });

  it("el acento va en Lato bold itálica (font-body italic font-bold)", () => {
    render(<Wordmark />);
    const acento = screen.getByLabelText("VORTEX OPS").querySelector("span:last-of-type");
    expect(acento).toHaveClass("font-body", "italic", "font-bold");
  });

  it.each([
    ["sm", "text-lg"],
    ["md", "text-2xl"],
    ["lg", "text-4xl"],
    ["xl", "text-6xl"],
  ] as const)('size="%s" mapea a %s', (size, expectedClass) => {
    render(<Wordmark size={size} />);
    expect(screen.getByLabelText("VORTEX OPS")).toHaveClass(expectedClass);
  });

  it("por defecto usa el tamaño md", () => {
    render(<Wordmark />);
    expect(screen.getByLabelText("VORTEX OPS")).toHaveClass("text-2xl");
  });

  it("mantiene la tipografía display en negra y el tracking apretado", () => {
    render(<Wordmark />);
    const wordmark = screen.getByLabelText("VORTEX OPS");
    expect(wordmark).toHaveClass("font-display", "font-black", "tracking-tighter");
  });

  it("fusiona className del consumidor pisando el tamaño", () => {
    render(<Wordmark className="text-8xl opacity-50" />);
    const wordmark = screen.getByLabelText("VORTEX OPS");
    expect(wordmark).toHaveClass("text-8xl", "opacity-50");
    expect(wordmark).not.toHaveClass("text-2xl");
  });

  it("propaga atributos HTML arbitrarios al contenedor", () => {
    render(<Wordmark id="logo-header" data-testid="wordmark" />);
    expect(screen.getByTestId("wordmark")).toHaveAttribute("id", "logo-header");
  });
});
