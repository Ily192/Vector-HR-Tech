import { describe, expect, it } from "vitest";

import { manifiestoDe, resolverRuta } from "../navegacion/ruta";

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
    ["/admin", { pantalla: "admin" }],
    ["/admin/", { pantalla: "admin" }],
    ["/admin/cola", { pantalla: "no-encontrada" }],
  ])("%s", (url, esperada) => {
    expect(resolverRuta(url)).toEqual(esperada);
  });
});

describe("manifiestoDe", () => {
  it.each([
    ["/admin", "/admin.webmanifest"],
    ["/", "/manifest.webmanifest"],
    ["/vacantes/nueva", "/manifest.webmanifest"],
  ])("%s → %s", (url, manifiesto) => {
    expect(manifiestoDe(url)).toBe(manifiesto);
  });
});
