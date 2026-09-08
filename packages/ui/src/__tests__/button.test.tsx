import { render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { Button, buttonVariants } from "../button";

describe("Button", () => {
  it("renderiza un <button> con su contenido", () => {
    render(<Button>Ver vacantes</Button>);
    const button = screen.getByRole("button", { name: "Ver vacantes" });
    expect(button).toBeInTheDocument();
    expect(button.tagName).toBe("BUTTON");
  });

  it('aplica type="button" por defecto — evita submits accidentales dentro de forms', () => {
    render(<Button>Enviar</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("respeta un type explícito", () => {
    render(<Button type="submit">Enviar</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
  });

  it("usa la variante y el tamaño por defecto (naranja Vortex, h-10)", () => {
    render(<Button>CTA</Button>);
    const button = screen.getByRole("button");
    expect(button).toHaveClass("bg-vector-orange-500");
    expect(button).toHaveClass("h-10");
  });

  it.each([
    ["default", "bg-vector-orange-500"],
    ["secondary", "border-vector-cian-electric-500"],
    ["ghost", "hover:bg-vector-cian-dark-500/5"],
    ["destructive", "bg-danger-500"],
    ["link", "underline-offset-4"],
  ] as const)("la variante %s aplica su clase distintiva", (variant, expectedClass) => {
    render(<Button variant={variant}>Botón</Button>);
    expect(screen.getByRole("button")).toHaveClass(expectedClass);
  });

  it.each([
    ["sm", "h-9"],
    ["default", "h-10"],
    ["lg", "h-12"],
    ["icon", "w-10"],
  ] as const)("el tamaño %s aplica su clase de altura", (size, expectedClass) => {
    render(<Button size={size}>Botón</Button>);
    expect(screen.getByRole("button")).toHaveClass(expectedClass);
  });

  describe("asChild", () => {
    it("delega el render al hijo (Slot) manteniendo las clases del botón", () => {
      render(
        <Button asChild variant="secondary" size="lg">
          <a href="/vacantes">Ver vacantes</a>
        </Button>,
      );

      const link = screen.getByRole("link", { name: "Ver vacantes" });
      expect(link.tagName).toBe("A");
      expect(link).toHaveAttribute("href", "/vacantes");
      expect(link).toHaveClass("h-12");
      expect(link).toHaveClass("border-vector-cian-electric-500");
      // No debe existir ningún <button> envolviendo al link.
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    it('no inyecta type="button" en un elemento que no es <button>', () => {
      render(
        <Button asChild>
          <a href="/contacto">Contacto</a>
        </Button>,
      );
      expect(screen.getByRole("link")).not.toHaveAttribute("type");
    });
  });

  it("fusiona className del consumidor y deja que gane sobre la clase por defecto", () => {
    render(<Button className="h-20 bg-black">Custom</Button>);
    const button = screen.getByRole("button");
    expect(button).toHaveClass("h-20");
    expect(button).toHaveClass("bg-black");
    // tailwind-merge elimina las clases en conflicto.
    expect(button).not.toHaveClass("h-10");
    expect(button).not.toHaveClass("bg-vector-orange-500");
  });

  it("dispara onClick y lo bloquea cuando está disabled", async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Click</Button>);

    screen.getByRole("button").click();
    expect(onClick).toHaveBeenCalledTimes(1);

    rerender(
      <Button onClick={onClick} disabled>
        Click
      </Button>,
    );
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    button.click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("propaga la ref al nodo DOM", () => {
    const ref = React.createRef<HTMLButtonElement>();
    render(<Button ref={ref}>Con ref</Button>);
    expect(ref.current).toBeInstanceOf(HTMLButtonElement);
    expect(ref.current?.textContent).toBe("Con ref");
  });

  it("expone displayName para debugging en React DevTools", () => {
    expect(Button.displayName).toBe("Button");
  });
});

describe("buttonVariants", () => {
  it("es usable de forma standalone para estilar links externos", () => {
    const classes = buttonVariants({ variant: "link", size: "sm" });
    expect(classes).toContain("underline-offset-4");
    expect(classes).toContain("h-9");
  });

  it("devuelve los defaults cuando no recibe argumentos", () => {
    const classes = buttonVariants();
    expect(classes).toContain("bg-vector-orange-500");
    expect(classes).toContain("h-10");
  });
});
