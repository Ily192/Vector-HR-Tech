import { ETAPAS_DEL_PIPELINE, ETAPAS_DE_SALIDA } from "@fluveai/types/reglas";
import { describe, expect, it } from "vitest";

import {
  BARRA_DE_ETAPA,
  TODAS_LAS_ETAPAS,
  contarPorEtapa,
  deLaEtapa,
  salidasVisibles,
} from "../pipeline/etapas";

const aplicados = [
  { id: "1", estado: "applied" },
  { id: "2", estado: "shortlisted" },
  { id: "3", estado: "applied" },
  { id: "4", estado: "hired" },
  { id: "5", estado: "rejected" },
] as const;

describe("etapas del pipeline de una vacante", () => {
  it("se muestran todas, primero el pipeline y después el cierre", () => {
    expect(TODAS_LAS_ETAPAS).toEqual([...ETAPAS_DEL_PIPELINE, ...ETAPAS_DE_SALIDA]);
    expect(Object.keys(BARRA_DE_ETAPA)).toEqual([...ETAPAS_DEL_PIPELINE]);
  });

  it("cuenta a cada uno en la etapa en que está, con 0 en las vacías", () => {
    expect(contarPorEtapa(aplicados)).toEqual({
      applied: 2,
      evaluated: 0,
      shortlisted: 1,
      interviewed: 0,
      offered: 0,
      hired: 1,
      rejected: 1,
      withdrawn: 0,
    });
    expect(Object.values(contarPorEtapa([])).every((n) => n === 0)).toBe(true);
  });

  it("filtra por etapa sin cambiar el orden; sin etapa, todos", () => {
    expect(deLaEtapa(aplicados, "applied").map((a) => a.id)).toEqual(["1", "3"]);
    expect(deLaEtapa(aplicados, "offered")).toEqual([]);
    expect(deLaEtapa(aplicados, null)).toEqual(aplicados);
    expect(deLaEtapa(aplicados, null)).not.toBe(aplicados);
  });

  it("muestra «Se retiraron» solo si alguien se retiró", () => {
    const retirado = { id: "6", estado: "withdrawn" } as const;
    expect(salidasVisibles(contarPorEtapa(aplicados))).toEqual(["hired", "rejected"]);
    expect(salidasVisibles(contarPorEtapa([...aplicados, retirado]))).toEqual([
      "hired",
      "rejected",
      "withdrawn",
    ]);
  });
});
