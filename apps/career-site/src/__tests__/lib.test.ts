import { describe, expect, it } from "vitest";

import { leerFiltros, urlConFiltros } from "../lib/filtros";

describe("filtros en la URL", () => {
  it("lee los filtros válidos y descarta vacíos e inválidos", () => {
    expect(
      leerFiltros({ q: " almacén ", ubicacion: "", modalidad: "hybrid", salario: "1" }),
    ).toEqual({ q: "almacén", ubicacion: undefined, modalidad: "hybrid", conSalario: true });
    expect(leerFiltros({ modalidad: "marte", salario: "0" })).toEqual({
      q: undefined,
      ubicacion: undefined,
      modalidad: undefined,
      conSalario: undefined,
    });
  });

  it("toma el primer valor si un parámetro llega repetido", () => {
    expect(leerFiltros({ q: ["data", "ventas"] }).q).toBe("data");
  });

  it("escribe la URL sin parámetros vacíos y es la inversa de leerFiltros", () => {
    expect(urlConFiltros({})).toBe("/vacantes");
    const url = urlConFiltros({ q: "data", modalidad: "remote", conSalario: true });
    expect(url).toBe("/vacantes?q=data&modalidad=remote&salario=1");
    const params = Object.fromEntries(new URL(url, "https://x").searchParams);
    expect(leerFiltros(params)).toEqual({
      q: "data",
      ubicacion: undefined,
      modalidad: "remote",
      conSalario: true,
    });
  });
});
