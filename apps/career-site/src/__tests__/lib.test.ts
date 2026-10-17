import { describe, expect, it } from "vitest";

import { leerFiltros, urlConFiltros } from "../lib/filtros";
import { esNueva, formatearSalario, haceCuanto, iniciales } from "../lib/formato";

const AHORA = new Date("2026-10-16T18:00:00Z");

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

describe("formato de la vacante", () => {
  it("formatea el rango en la moneda de la vacante, o null si no se publica", () => {
    expect(formatearSalario({ salario_min: 22000, salario_max: 28000, moneda: "MXN" })).toBe(
      "$22,000 – $28,000",
    );
    expect(formatearSalario({ salario_min: 13500, salario_max: 13500, moneda: "MXN" })).toBe(
      "$13,500",
    );
    expect(formatearSalario({ salario_min: null, salario_max: null, moneda: null })).toBeNull();
  });

  it("dice hace cuánto se publicó", () => {
    expect(haceCuanto("2026-10-16T09:00:00Z", AHORA)).toBe("Hoy");
    expect(haceCuanto("2026-10-15T09:00:00Z", AHORA)).toBe("Ayer");
    expect(haceCuanto("2026-10-13T09:00:00Z", AHORA)).toBe("Hace 3 días");
    expect(haceCuanto("2026-10-08T09:00:00Z", AHORA)).toBe("Hace 1 semana");
    expect(haceCuanto("2026-09-25T09:00:00Z", AHORA)).toBe("Hace 3 semanas");
  });

  it("marca como nueva una vacante de menos de 3 días", () => {
    expect(esNueva("2026-10-14T19:00:00Z", AHORA)).toBe(true);
    expect(esNueva("2026-10-13T17:00:00Z", AHORA)).toBe(false);
  });

  it("saca dos iniciales del nombre de la empresa", () => {
    expect(iniciales("Andes Logística")).toBe("AL");
    expect(iniciales("Cobalto")).toBe("CO");
  });
});
