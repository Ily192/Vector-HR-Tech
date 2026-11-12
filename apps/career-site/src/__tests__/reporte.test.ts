// @vitest-environment node
import { describe, expect, it } from "vitest";

import { type PuertosDeReporte, procesarReporte } from "../lib/reporte";

function formulario(campos: Record<string, string> = {}): FormData {
  const datos = new FormData();
  for (const [clave, valor] of Object.entries({ motivo: "dinero", ...campos })) {
    datos.set(clave, valor);
  }
  return datos;
}

function conPuertos(cambios: Partial<PuertosDeReporte> = {}) {
  const enviados: { slug: string; motivo: string }[] = [];
  const puertos: PuertosDeReporte = {
    verificarHumano: async () => true,
    reportar: async (slug, motivo) => {
      enviados.push({ slug, motivo });
      return "recibido";
    },
    ...cambios,
  };
  return { puertos, enviados };
}

describe("reportar una vacante (ADR-022)", () => {
  it("manda el motivo con su texto y el detalle limpio", async () => {
    const { puertos, enviados } = conPuertos();
    const r = await procesarReporte(
      "analista",
      formulario({ detalle: "  Me pidieron   $500\n por el curso " }),
      puertos,
    );
    expect(r).toEqual({ estado: "ok" });
    expect(enviados).toEqual([
      { slug: "analista", motivo: "Pide dinero, un curso o un kit: Me pidieron $500 por el curso" },
    ]);
  });

  it("sin detalle manda solo el motivo", async () => {
    const { puertos, enviados } = conPuertos();
    await procesarReporte("analista", formulario({ motivo: "falsa" }), puertos);
    expect(enviados[0]?.motivo).toBe("Parece falsa o engañosa");
  });

  it("el detalle se recorta y el motivo cabe en la base (300)", async () => {
    const { puertos, enviados } = conPuertos();
    await procesarReporte("analista", formulario({ detalle: "x".repeat(500) }), puertos);
    expect(enviados[0]?.motivo.length).toBeLessThanOrEqual(300);
  });

  it("un motivo que no está en la lista no llega a la base", async () => {
    const { puertos, enviados } = conPuertos();
    const r = await procesarReporte("analista", formulario({ motivo: "toString" }), puertos);
    expect(r.estado).toBe("error");
    expect(enviados).toEqual([]);
  });

  it("al bot del campo trampa se le dice que sí sin reportar", async () => {
    const { puertos, enviados } = conPuertos();
    expect(await procesarReporte("analista", formulario({ sitio_web: "x" }), puertos)).toEqual({
      estado: "ok",
    });
    expect(enviados).toEqual([]);
  });

  it("sin pasar Turnstile no se reporta", async () => {
    const { puertos, enviados } = conPuertos({ verificarHumano: async () => false });
    const r = await procesarReporte("analista", formulario(), puertos);
    expect(r).toMatchObject({ estado: "error", mensaje: expect.stringMatching(/robot/) });
    expect(enviados).toEqual([]);
  });

  it.each([
    ["no-disponible", /ya no está publicada/],
    ["limite", /varios reportes hoy/],
  ] as const)("si la base responde %s, lo dice", async (respuesta, mensaje) => {
    const { puertos } = conPuertos({ reportar: async () => respuesta });
    const r = await procesarReporte("analista", formulario(), puertos);
    expect(r).toMatchObject({ estado: "error", mensaje: expect.stringMatching(mensaje) });
  });

  it("cuando el reporte la oculta, a quien reporta solo se le agradece", async () => {
    const { puertos } = conPuertos({ reportar: async () => "oculta" });
    expect(await procesarReporte("analista", formulario(), puertos)).toEqual({ estado: "ok" });
  });
});
