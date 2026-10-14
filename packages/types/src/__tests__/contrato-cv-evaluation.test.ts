import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { CvEvaluationSchema } from "../hr";

// El mismo fichero lo valida el hr-engine contra Pydantic
// (services/hr-engine/tests/unit/test_contrato_cv_evaluation.py).
const contrato = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../contracts/cv-evaluation.json", import.meta.url)),
    "utf8",
  ),
) as {
  campos: string[];
  validos: Record<string, unknown>[];
  invalidos: { motivo: string; cambio?: Record<string, unknown>; quitar?: string }[];
};

describe("contrato cv-evaluation (Zod ↔ Pydantic)", () => {
  it("tiene exactamente los campos del contrato", () => {
    expect(Object.keys(CvEvaluationSchema.shape).sort()).toEqual([...contrato.campos].sort());
  });

  it.each(contrato.validos.map((v, i) => [i, v] as const))(
    "acepta el ejemplo válido %i",
    (_i, v) => {
      expect(CvEvaluationSchema.safeParse(v).success).toBe(true);
    },
  );

  it.each(contrato.invalidos.map((c) => [c.motivo, c] as const))("rechaza: %s", (_m, caso) => {
    const dato: Record<string, unknown> = { ...contrato.validos[0], ...caso.cambio };
    if (caso.quitar) delete dato[caso.quitar];
    expect(CvEvaluationSchema.strict().safeParse(dato).success).toBe(false);
  });
});
