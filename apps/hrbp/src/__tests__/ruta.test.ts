import { describe, expect, it } from "vitest";

import { resolverRuta } from "../navegacion/ruta";

describe("resolverRuta", () => {
  it.each([
    ["/", { pantalla: "inicio" }],
    // Con la sesión abierta, la página del código del alta es el inicio.
    ["/verificar", { pantalla: "inicio" }],
    ["/verificar/x", { pantalla: "no-encontrada" }],
    ["/vacantes", { pantalla: "mis-vacantes" }],
    ["/vacantes/", { pantalla: "mis-vacantes" }],
    ["/vacantes/nueva", { pantalla: "crear-empleo" }],
    [
      "/vacantes/coordinador-de-almacen",
      { pantalla: "pipeline", vacanteId: "coordinador-de-almacen" },
    ],
    ["/vacantes/a%C3%B1o", { pantalla: "pipeline", vacanteId: "año" }],
    ["/vacantes/x/y", { pantalla: "no-encontrada" }],
    ["/configuracion", { pantalla: "no-encontrada" }],
  ])("%s", (url, esperada) => {
    expect(resolverRuta(url)).toEqual(esperada);
  });
});
