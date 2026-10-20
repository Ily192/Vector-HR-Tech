import { describe, expect, it } from "vitest";

import {
  detalleDelRegistro,
  textoDeLaDecision,
  variacionDeCandidatos,
  variacionDeEnEspera,
  variacionDeEvaluaciones,
  variacionDeVacantes,
} from "../cockpit/textos";

const vacante = { id: "v1", titulo: "Chofer repartidor" };

describe("textoDeLaDecision", () => {
  it("con más listos que scores, dice que son los mejores", () => {
    expect(
      textoDeLaDecision({ tipo: "entrevistar", vacante, listos: 17, scores: [9.4, 9.3, 9.1] }),
    ).toEqual({
      titulo: "17 candidatos listos para entrevista en Chofer repartidor",
      detalle:
        "Los 3 mejores: 9.4, 9.3 y 9.1. Lo sugiere la IA, que evaluó sin ver nombres; la decisión es tuya.",
    });
  });

  it("en singular y con todos los scores", () => {
    expect(textoDeLaDecision({ tipo: "entrevistar", vacante, listos: 1, scores: [7] })).toEqual({
      titulo: "Un candidato listo para entrevista en Chofer repartidor",
      detalle: "Score 7.0. Lo sugiere la IA, que evaluó sin ver nombres; la decisión es tuya.",
    });
    expect(
      textoDeLaDecision({ tipo: "entrevistar", vacante, listos: 2, scores: [8.9, 8.5] }).detalle,
    ).toMatch(/^Scores 8\.9 y 8\.5\./);
  });

  it("lo que hay que revisar a mano dice por qué la IA no lo evaluó", () => {
    expect(
      textoDeLaDecision({ tipo: "revisar", vacante, sinEvaluar: 1, ilegibles: 2, sinIa: 1 }),
    ).toEqual({
      titulo: "4 aplicaciones por revisar a mano en Chofer repartidor",
      detalle:
        "La IA no las evaluó: una no se pudo evaluar, 2 CVs no se pudieron leer y un candidato pidió no ser evaluado con IA.",
    });
    expect(
      textoDeLaDecision({ tipo: "revisar", vacante, sinEvaluar: 0, ilegibles: 0, sinIa: 1 }),
    ).toEqual({
      titulo: "Una aplicación por revisar a mano en Chofer repartidor",
      detalle: "La IA no la evaluó: un candidato pidió no ser evaluado con IA.",
    });
  });
});

describe("variaciones de los indicadores", () => {
  it("dicen lo nuevo, o que no hubo", () => {
    expect(variacionDeCandidatos(34)).toBe("+34 en 24 h");
    expect(variacionDeCandidatos(0)).toBe("ninguno nuevo en 24 h");
    expect(variacionDeVacantes(2)).toBe("+2 en 7 días");
    expect(variacionDeVacantes(0)).toBe("ninguna nueva en 7 días");
    expect(variacionDeEvaluaciones(98)).toBe("98 % sin error");
    expect(variacionDeEvaluaciones(null)).toBe("sin evaluaciones");
  });

  it("lo que espera con el tope del mes alcanzado espera al mes siguiente", () => {
    expect(variacionDeEnEspera({ total: 3, topeAlcanzado: false })).toBe("se evalúan solas");
    expect(variacionDeEnEspera({ total: 3, topeAlcanzado: true })).toBe(
      "esperan al próximo mes: llegaste al tope",
    );
    expect(variacionDeEnEspera({ total: 0, topeAlcanzado: true })).toBe("nada en espera");
  });
});

describe("detalleDelRegistro", () => {
  const entrada = {
    id: "r1",
    en: "2026-10-20T14:42:00+00:00",
    agente: "cv-evaluator",
    vacante: "Chofer repartidor",
    score: 8.5,
    aplazada: false,
  };

  it("lleva la vacante, el score y la sugerencia, sin el nombre del candidato", () => {
    expect(detalleDelRegistro(entrada)).toBe("Chofer repartidor · 8.5 · Entrevista");
    expect(detalleDelRegistro({ ...entrada, score: 5 })).toBe(
      "Chofer repartidor · 5.0 · Psicométrico",
    );
  });

  it("dice cuándo no se pudo evaluar y cuándo ya no hay score", () => {
    expect(detalleDelRegistro({ ...entrada, aplazada: true })).toBe(
      "Chofer repartidor · no se pudo evaluar",
    );
    expect(detalleDelRegistro({ ...entrada, score: null })).toBe("Chofer repartidor · evaluada");
    expect(detalleDelRegistro({ ...entrada, vacante: null, score: null })).toBe(
      "Ejecución terminada",
    );
  });
});
