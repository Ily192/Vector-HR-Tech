// @vitest-environment node
// La lógica corre en el servidor: con el `File` de Node 22, que sí tiene `arrayBuffer()`.
// El de jsdom no lo implementa.
import { describe, expect, it } from "vitest";

import { type PuertosDeAplicacion, formatoDeCv, procesarAplicacion } from "../lib/aplicacion";
import { MAX_BYTES_DEL_CV } from "../lib/tipos-de-aplicacion";

const PDF = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34]); // %PDF-1.4
const ZIP = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x14, 0x00]);
const DOC = new Uint8Array([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1]);

function formulario(campos: Record<string, string | File> = {}): FormData {
  const datos = new FormData();
  const base: Record<string, string | File> = {
    nombre: "Ana Pérez",
    correo: "ana@example.test",
    acepta: "on",
    cv: new File([PDF], "cv-ana.pdf", { type: "application/pdf" }),
  };
  for (const [clave, valor] of Object.entries({ ...base, ...campos })) datos.set(clave, valor);
  return datos;
}

function conPuertos(cambios: Partial<PuertosDeAplicacion> = {}) {
  const registro = {
    subidas: [] as { ruta: string; contentType: string }[],
    borradas: [] as string[],
    aplicadas: [] as Parameters<PuertosDeAplicacion["aplicar"]>[0][],
  };
  const puertos: PuertosDeAplicacion = {
    vacante: async () => ({ id: "vac-1", empresaId: "emp-1" }),
    verificarHumano: async () => true,
    subirCv: async (ruta, _contenido, contentType) => {
      registro.subidas.push({ ruta, contentType });
    },
    borrarCv: async (ruta) => {
      registro.borradas.push(ruta);
    },
    aplicar: async (datos) => {
      registro.aplicadas.push(datos);
      return "ok";
    },
    nuevoId: () => "id-1",
    ...cambios,
  };
  return { puertos, registro };
}

describe("formatoDeCv", () => {
  it("reconoce el PDF por sus primeros bytes", () => {
    expect(formatoDeCv(PDF, "lo-que-sea.bin")).toBe("pdf");
  });

  it("un .zip solo cuenta como Word si se llama .docx", () => {
    expect(formatoDeCv(ZIP, "Mi CV.DOCX")).toBe("docx");
    expect(formatoDeCv(ZIP, "fotos.zip")).toBeNull();
  });

  it("el .doc antiguo no se acepta: el worker no lo puede leer", () => {
    expect(formatoDeCv(DOC, "cv.doc")).toBeNull();
    expect(formatoDeCv(new TextEncoder().encode("hola"), "cv.pdf")).toBeNull();
  });
});

describe("procesarAplicacion", () => {
  it("sube el CV a la carpeta de la empresa y registra la aplicación", async () => {
    const { puertos, registro } = conPuertos();
    expect(await procesarAplicacion("analista", formulario(), puertos)).toEqual({ estado: "ok" });
    expect(registro.subidas).toEqual([{ ruta: "emp-1/id-1.pdf", contentType: "application/pdf" }]);
    expect(registro.aplicadas).toEqual([
      {
        vacanteId: "vac-1",
        nombre: "Ana Pérez",
        correo: "ana@example.test",
        rutaDelCv: "emp-1/id-1.pdf",
        titular: null,
        linkedin: null,
        sinIa: false,
      },
    ]);
    expect(registro.borradas).toEqual([]);
  });

  it("lleva la oposición del candidato y los campos opcionales", async () => {
    const { puertos, registro } = conPuertos();
    await procesarAplicacion(
      "analista",
      formulario({
        sin_ia: "on",
        titular: "  Analista de datos ",
        linkedin: "https://www.linkedin.com/in/ana",
        cv: new File([ZIP], "CV Ana.docx"),
      }),
      puertos,
    );
    expect(registro.aplicadas[0]).toMatchObject({
      sinIa: true,
      titular: "Analista de datos",
      linkedin: "https://www.linkedin.com/in/ana",
      rutaDelCv: "emp-1/id-1.docx",
    });
    expect(registro.subidas[0]?.contentType).toContain("wordprocessingml");
  });

  it("al bot que llena el campo trampa se le dice que sí, sin tocar nada", async () => {
    const { puertos, registro } = conPuertos();
    const resultado = await procesarAplicacion(
      "analista",
      formulario({ sitio_web: "https://spam.test" }),
      puertos,
    );
    expect(resultado).toEqual({ estado: "ok" });
    expect(registro.subidas).toEqual([]);
    expect(registro.aplicadas).toEqual([]);
  });

  it("sin pasar Turnstile no se sube nada", async () => {
    const { puertos, registro } = conPuertos({ verificarHumano: async () => false });
    const resultado = await procesarAplicacion("analista", formulario(), puertos);
    expect(resultado).toMatchObject({ estado: "error", mensaje: expect.stringMatching(/robot/) });
    expect(registro.subidas).toEqual([]);
  });

  it("marca cada campo que no pasa la validación", async () => {
    const { puertos, registro } = conPuertos();
    const resultado = await procesarAplicacion(
      "analista",
      formulario({ nombre: "A", correo: "no-es-correo", linkedin: "linkedin", acepta: "" }),
      puertos,
    );
    expect(resultado).toMatchObject({
      estado: "error",
      campos: {
        nombre: expect.any(String),
        correo: expect.any(String),
        linkedin: expect.any(String),
        acepta: expect.stringMatching(/aviso de privacidad/),
      },
    });
    expect(registro.subidas).toEqual([]);
  });

  it.each([
    ["sin CV", new File([], "vacio.pdf"), /Adjunta tu CV/],
    ["de más de 4 MB", new File([new Uint8Array(MAX_BYTES_DEL_CV + 1)], "cv.pdf"), /4 MB/],
    ["en otro formato", new File([DOC], "cv.doc"), /PDF o Word/],
  ])("rechaza un CV %s", async (_caso, cv, mensaje) => {
    const { puertos, registro } = conPuertos();
    const resultado = await procesarAplicacion("analista", formulario({ cv }), puertos);
    expect(resultado).toMatchObject({
      estado: "error",
      campos: { cv: expect.stringMatching(mensaje) },
    });
    expect(registro.subidas).toEqual([]);
  });

  it("si la vacante ya no está abierta, lo dice antes de subir nada", async () => {
    const { puertos, registro } = conPuertos({ vacante: async () => null });
    const resultado = await procesarAplicacion("analista", formulario(), puertos);
    expect(resultado).toMatchObject({
      estado: "error",
      mensaje: expect.stringMatching(/ya no está/),
    });
    expect(registro.subidas).toEqual([]);
  });

  it("si la vacante llegó a su tope, borra el CV que subió y lo explica", async () => {
    const { puertos, registro } = conPuertos({ aplicar: async () => "sin-cupo" });
    const resultado = await procesarAplicacion("analista", formulario(), puertos);
    expect(resultado).toMatchObject({ estado: "error", mensaje: expect.stringMatching(/máximo/) });
    expect(registro.borradas).toEqual(["emp-1/id-1.pdf"]);
  });

  it("si registrar falla del todo, el CV tampoco se queda en el bucket", async () => {
    const { puertos, registro } = conPuertos({
      aplicar: async () => {
        throw new Error("la base no responde");
      },
    });
    await expect(procesarAplicacion("analista", formulario(), puertos)).rejects.toThrow(
      "la base no responde",
    );
    expect(registro.borradas).toEqual(["emp-1/id-1.pdf"]);
  });
});
