import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { ETIQUETA_ESTADO_APLICACION } from "../etiquetas";
import { ApplicationStatusSchema } from "../hr";
import {
  ETAPAS_DEL_PIPELINE,
  LIMITES_DEL_PLAN,
  UMBRALES_SIGUIENTE_PASO,
  VENTANA_DE_PUBLICACIONES_DIAS,
  limiteDeVacantes,
  siguientePaso,
} from "../reglas";

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

// El mismo fichero lo validan el dominio (tests/unit/test_contrato_limites_plan.py) y
// la copia en SQL de las migraciones 0008 y 0010 (tests/security/test_plan_gratis.py).
const limites = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../contracts/limites-plan.json", import.meta.url)),
    "utf8",
  ),
) as {
  max_aplicaciones_gratis: number;
  ventana_de_publicaciones_dias: number;
  planes: Record<
    "gratis" | "ia",
    { incluye_ia: boolean; modulos: string[]; etapas_visibles: string[]; con_limites: boolean }
  >;
  casos_limite_de_vacantes: { tamano: number | null; ajuste: number | null; limite: number }[];
};

describe("contrato limites-plan (TS ↔ Python ↔ SQL)", () => {
  it("usa el mismo tope de aplicaciones del plan gratis", () => {
    expect(LIMITES_DEL_PLAN.gratis.aplicacionesPorVacante).toBe(limites.max_aplicaciones_gratis);
    expect(LIMITES_DEL_PLAN.ia.aplicacionesPorVacante).toBeNull();
  });

  it("cuenta las publicaciones en la misma ventana", () => {
    expect(VENTANA_DE_PUBLICACIONES_DIAS).toBe(limites.ventana_de_publicaciones_dias);
  });

  it.each(["gratis", "ia"] as const)("el plan %s abre los mismos módulos y etapas", (plan) => {
    expect(LIMITES_DEL_PLAN[plan].modulos).toEqual(limites.planes[plan].modulos);
    expect(LIMITES_DEL_PLAN[plan].etapasVisibles).toEqual(limites.planes[plan].etapas_visibles);
    expect(LIMITES_DEL_PLAN[plan].incluyeIa).toBe(limites.planes[plan].incluye_ia);
  });

  it.each(limites.casos_limite_de_vacantes.map((c) => [c.tamano, c.ajuste, c.limite] as const))(
    "tamaño %s, ajuste %s → %d vacantes",
    (tamano, ajuste, limite) => {
      expect(limiteDeVacantes(tamano, ajuste)).toBe(limite);
    },
  );
});
