import { describe, expect, it } from "vitest";

import { cn } from "../utils";

describe("cn", () => {
  it("concatena clases sueltas", () => {
    expect(cn("px-4", "py-2")).toBe("px-4 py-2");
  });

  it("resuelve conflictos de Tailwind quedándose con la última", () => {
    expect(cn("px-4", "px-8")).toBe("px-8");
    expect(cn("bg-red-500", "bg-blue-500")).toBe("bg-blue-500");
    expect(cn("h-10", "h-20")).toBe("h-20");
  });

  it("no colapsa clases de propiedades distintas", () => {
    expect(cn("px-4", "py-2", "text-sm")).toBe("px-4 py-2 text-sm");
  });

  it("ignora valores falsy (patrón de clases condicionales)", () => {
    expect(cn("base", false && "oculto", null, undefined, "")).toBe("base");
  });

  it("acepta objetos y arrays al estilo clsx", () => {
    expect(cn(["flex", "items-center"], { hidden: false, "gap-2": true })).toBe(
      "flex items-center gap-2",
    );
  });

  it("respeta variantes (hover:, dark:) como grupos independientes", () => {
    expect(cn("bg-white hover:bg-black", "hover:bg-gray-500")).toBe("bg-white hover:bg-gray-500");
    expect(cn("text-black dark:text-white")).toBe("text-black dark:text-white");
  });

  it("devuelve cadena vacía sin argumentos", () => {
    expect(cn()).toBe("");
  });
});
