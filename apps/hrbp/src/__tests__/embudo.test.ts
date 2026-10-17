import { describe, expect, it } from "vitest";

import { anchoRelativo } from "../cockpit/embudo";

describe("anchoRelativo", () => {
  it("escala cada etapa contra la más grande", () => {
    expect(anchoRelativo(84, [84, 42])).toBe(100);
    expect(anchoRelativo(42, [84, 42])).toBe(50);
  });

  it("devuelve 0 sin dividir entre cero cuando no hay conteos", () => {
    expect(anchoRelativo(0, [0, 0])).toBe(0);
    expect(anchoRelativo(0, [])).toBe(0);
  });
});
