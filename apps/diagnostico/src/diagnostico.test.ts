import { describe, expect, it } from "vitest";

import {
  PREGUNTAS,
  PROCESOS,
  type Respuestas,
  SEMANAS_POR_MES,
  calcular,
  estaRespondida,
  etapaDe,
} from "./diagnostico";

function respuestasCon(horas: Record<string, number>, extra: Respuestas = {}): Respuestas {
  const r: Respuestas = { en_sistema: [], pasos_definidos: [], ...extra };
  for (const p of PROCESOS) r[`horas.${p.id}`] = String(horas[p.id] ?? 0.5);
  return r;
}

describe("el cuestionario", () => {
  it("tiene entre 8 y 12 preguntas, con ids únicos", () => {
    expect(PREGUNTAS.length).toBeGreaterThanOrEqual(8);
    expect(PREGUNTAS.length).toBeLessThanOrEqual(12);
    expect(new Set(PREGUNTAS.map((p) => p.id)).size).toBe(PREGUNTAS.length);
  });

  it("una pregunta de varias opciones sin nada marcado cuenta como respondida", () => {
    const varias = PREGUNTAS.find((p) => p.tipo === "varias");
    if (!varias) throw new Error("falta una pregunta de varias opciones");
    expect(estaRespondida(varias, {})).toBe(false);
    expect(estaRespondida(varias, { [varias.id]: [] })).toBe(true);
  });
});

describe("la etapa de cada proceso", () => {
  it("fuera de un sistema se digitaliza, sin pasos se optimiza y con pasos se automatiza", () => {
    expect(etapaDe(false, true)).toBe("Digitalizar");
    expect(etapaDe(true, false)).toBe("Optimizar");
    expect(etapaDe(true, true)).toBe("Automatizar");
  });
});

describe("el cálculo", () => {
  it("multiplica las horas por semana por el porcentaje de la etapa y las semanas del mes", () => {
    const r = calcular(
      respuestasCon(
        { reclutamiento: 15 },
        { en_sistema: ["reclutamiento"], pasos_definidos: ["reclutamiento"] },
      ),
    );
    const primero = r.procesos[0];
    expect(primero?.id).toBe("reclutamiento");
    expect(primero?.etapa).toBe("Automatizar");
    // 15 h × 50 % × 4.33 = 32.5 h al mes.
    expect(primero?.horasRecuperablesMes).toBe(Math.round(15 * 0.5 * SEMANAS_POR_MES * 2) / 2);
  });

  it("ordena de mayor a menor y suma solo el top 3", () => {
    const r = calcular(
      respuestasCon({ reclutamiento: 2, altas: 25, asistencia: 8, solicitudes: 15, reportes: 4.5 }),
    );
    expect(r.procesos.map((p) => p.id).slice(0, 3)).toEqual(["altas", "solicitudes", "asistencia"]);
    const top = r.procesos.slice(0, 3).reduce((s, p) => s + p.horasRecuperablesMes, 0);
    expect(r.horasRecuperablesMes).toBeCloseTo(top, 5);
    expect(r.horasRecuperablesAnio).toBe(Math.round(r.horasRecuperablesMes * 12));
  });

  it("con empates respeta el orden de las preguntas, para que el top sea estable", () => {
    const r = calcular(respuestasCon({}));
    expect(r.procesos.map((p) => p.id)).toEqual(PROCESOS.map((p) => p.id));
  });

  it("no se rompe con respuestas faltantes o raras", () => {
    const r = calcular({ "horas.altas": "no-es-numero" });
    expect(r.horasRecuperablesMes).toBe(0);
    expect(r.procesos).toHaveLength(PROCESOS.length);
  });
});
