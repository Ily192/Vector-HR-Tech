import { describe, expect, it } from "vitest";

import { esNueva, formatearSalario, haceCuanto, iniciales } from "../formato";

const AHORA = new Date("2026-10-16T18:00:00Z");

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

  it("no repite el código de la moneda, que las pantallas ya ponen al lado", () => {
    expect(formatearSalario({ salario_min: 1500, salario_max: 2000, moneda: "USD" })).toBe(
      "$1,500 – $2,000",
    );
    // es-MX no tiene símbolo para el bolívar y escribiría "VES 22,000". `Intl`
    // separa símbolo y cifra con un espacio que no se parte.
    const sinCorte = String.fromCharCode(0xa0);
    expect(formatearSalario({ salario_min: 22000, salario_max: 28000, moneda: "VES" })).toBe(
      `Bs.${sinCorte}22,000 – Bs.${sinCorte}28,000`,
    );
    // Una moneda sin símbolo conocido queda solo con la cifra.
    expect(formatearSalario({ salario_min: 900, salario_max: null, moneda: "CHF" })).toBe("900");
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
