import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { ETIQUETA_ESTADO_APLICACION } from "../etiquetas";
import { ApplicationStatusSchema } from "../hr";
import { ETAPAS_DEL_PIPELINE, UMBRALES_SIGUIENTE_PASO, siguientePaso } from "../reglas";

// El mismo fichero lo valida el hr-engine contra `app/domain/siguiente_paso.py`
// (services/hr-engine/tests/unit/test_contrato_siguiente_paso.py).
const contrato = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../contracts/siguiente-paso.json", import.meta.url)),
    "utf8",
  ),
) as {
  umbrales: { psicometrico: number; entrevista: number };
  casos: { score: number; paso: string }[];
};

describe("contrato siguiente-paso (TS ↔ Python)", () => {
  it("usa los mismos umbrales que el backend", () => {
    expect(UMBRALES_SIGUIENTE_PASO).toEqual(contrato.umbrales);
  });

  it.each(contrato.casos.map((c) => [c.score, c.paso] as const))("score %d → %s", (score, paso) => {
    expect(siguientePaso(score)).toBe(paso);
  });
});

describe("ETAPAS_DEL_PIPELINE", () => {
  it("son estados de aplicación válidos, en el orden del embudo", () => {
    for (const etapa of ETAPAS_DEL_PIPELINE) {
      expect(ApplicationStatusSchema.safeParse(etapa).success).toBe(true);
    }
    expect(ETAPAS_DEL_PIPELINE.map((e) => ETIQUETA_ESTADO_APLICACION[e])).toEqual([
      "Aplicados",
      "Evaluados",
      "Shortlist",
      "Entrevista",
      "Oferta",
    ]);
  });
});
