import { render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it } from "vitest";

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../card";

describe("Card", () => {
  it("renderiza la composición completa con su contenido", () => {
    render(
      <Card data-testid="card">
        <CardHeader data-testid="header">
          <CardTitle>Velocidad</CardTitle>
          <CardDescription>Agentes autónomos que procesan candidatos en minutos.</CardDescription>
        </CardHeader>
        <CardContent data-testid="content">Sourcing 24/7</CardContent>
        <CardFooter data-testid="footer">Ver más</CardFooter>
      </Card>,
    );

    expect(screen.getByTestId("card")).toBeInTheDocument();
    expect(screen.getByTestId("header")).toBeInTheDocument();
    expect(screen.getByTestId("content")).toHaveTextContent("Sourcing 24/7");
    expect(screen.getByTestId("footer")).toHaveTextContent("Ver más");
    expect(
      screen.getByText("Agentes autónomos que procesan candidatos en minutos."),
    ).toBeInTheDocument();
  });

  it("CardTitle es un heading de nivel 3 — accesible por rol", () => {
    render(<CardTitle>Inteligencia</CardTitle>);
    const heading = screen.getByRole("heading", { level: 3, name: "Inteligencia" });
    expect(heading.tagName).toBe("H3");
    expect(heading).toHaveClass("font-display");
  });

  it("CardDescription renderiza un <p> con estilo mutado", () => {
    render(<CardDescription data-testid="desc">Texto secundario</CardDescription>);
    const desc = screen.getByTestId("desc");
    expect(desc.tagName).toBe("P");
    expect(desc).toHaveClass("text-muted-foreground");
  });

  it("Card lleva las clases de superficie (borde, radio, sombra)", () => {
    render(<Card data-testid="card">contenido</Card>);
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("rounded-lg");
    expect(card).toHaveClass("border");
    expect(card).toHaveClass("bg-card");
    expect(card).toHaveClass("shadow-sm");
  });

  it("CardFooter distribuye su contenido en fila", () => {
    render(<CardFooter data-testid="footer">pie</CardFooter>);
    const footer = screen.getByTestId("footer");
    expect(footer).toHaveClass("flex");
    expect(footer).toHaveClass("items-center");
    expect(footer).toHaveClass("justify-between");
  });

  it("cada subcomponente fusiona className sin perder las clases base", () => {
    render(
      <Card data-testid="card" className="mb-6">
        <CardHeader data-testid="header" className="pb-3">
          <CardTitle className="text-xl">Título</CardTitle>
        </CardHeader>
      </Card>,
    );
    expect(screen.getByTestId("card")).toHaveClass("mb-6", "rounded-lg");
    const header = screen.getByTestId("header");
    expect(header).toHaveClass("pb-3", "flex");
    // p-6 sobrevive porque pb-3 solo pisa el padding-bottom.
    expect(header).toHaveClass("p-6");
    const title = screen.getByRole("heading", { level: 3 });
    expect(title).toHaveClass("text-xl");
    expect(title).not.toHaveClass("text-2xl");
  });

  it("propaga refs en Card y CardTitle", () => {
    const cardRef = React.createRef<HTMLDivElement>();
    const titleRef = React.createRef<HTMLHeadingElement>();
    render(
      <Card ref={cardRef}>
        <CardTitle ref={titleRef}>Con ref</CardTitle>
      </Card>,
    );
    expect(cardRef.current).toBeInstanceOf(HTMLDivElement);
    expect(titleRef.current).toBeInstanceOf(HTMLHeadingElement);
  });

  it("todos los subcomponentes exponen displayName", () => {
    expect(Card.displayName).toBe("Card");
    expect(CardHeader.displayName).toBe("CardHeader");
    expect(CardTitle.displayName).toBe("CardTitle");
    expect(CardDescription.displayName).toBe("CardDescription");
    expect(CardContent.displayName).toBe("CardContent");
    expect(CardFooter.displayName).toBe("CardFooter");
  });
});
