import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge, badgeVariants } from "../badge";

describe("Badge", () => {
  it("renderiza un <span> con su contenido", () => {
    render(<Badge data-testid="badge">Open</Badge>);
    const badge = screen.getByTestId("badge");
    expect(badge).toHaveTextContent("Open");
    expect(badge.tagName).toBe("SPAN");
  });

  it("usa la variante default (cian dark) cuando no se especifica", () => {
    render(<Badge data-testid="badge">Default</Badge>);
    expect(screen.getByTestId("badge")).toHaveClass("bg-vector-cian-dark-500");
  });

  it.each([
    ["default", "bg-vector-cian-dark-500"],
    ["ai", "bg-vector-cian-electric-500"],
    ["manual", "bg-neutral-100"],
    ["success", "bg-success-50"],
    ["warning", "bg-warning-50"],
    ["danger", "bg-danger-50"],
    ["outline", "border-border"],
  ] as const)("la variante %s aplica su clase distintiva", (variant, expectedClass) => {
    render(
      <Badge data-testid="badge" variant={variant}>
        Badge
      </Badge>,
    );
    expect(screen.getByTestId("badge")).toHaveClass(expectedClass);
  });

  it("mantiene siempre las clases estructurales de la píldora", () => {
    render(<Badge data-testid="badge">Pill</Badge>);
    const badge = screen.getByTestId("badge");
    expect(badge).toHaveClass("inline-flex");
    expect(badge).toHaveClass("rounded-full");
    expect(badge).toHaveClass("text-xs");
  });

  it("fusiona className y deja que gane sobre la variante", () => {
    render(
      <Badge data-testid="badge" variant="ai" className="bg-black">
        Custom
      </Badge>,
    );
    const badge = screen.getByTestId("badge");
    expect(badge).toHaveClass("bg-black");
    expect(badge).not.toHaveClass("bg-vector-cian-electric-500");
  });

  it("propaga atributos HTML arbitrarios", () => {
    render(
      <Badge
        data-testid="badge"
        id="estado-vacante"
        title="Estado de la vacante"
        aria-live="polite"
      >
        Open
      </Badge>,
    );
    const badge = screen.getByTestId("badge");
    expect(badge).toHaveAttribute("id", "estado-vacante");
    expect(badge).toHaveAttribute("title", "Estado de la vacante");
    expect(badge).toHaveAttribute("aria-live", "polite");
  });

  it("admite nodos hijos (icono + texto), como en el hero del career-site", () => {
    render(
      <Badge data-testid="badge" variant="ai">
        <svg role="img" aria-label="chispa" />
        Powered by agentic AI
      </Badge>,
    );
    expect(screen.getByTestId("badge")).toHaveTextContent("Powered by agentic AI");
    expect(screen.getByRole("img", { name: "chispa" })).toBeInTheDocument();
  });
});

describe("badgeVariants", () => {
  it("expone las clases sin necesidad de renderizar el componente", () => {
    expect(badgeVariants({ variant: "success" })).toContain("bg-success-50");
    expect(badgeVariants()).toContain("bg-vector-cian-dark-500");
  });
});
