import { readFile } from "node:fs/promises";

import { type Page, expect, test } from "@playwright/test";

import { nombresEnElZip, pdf } from "./apoyo/archivos";
import { enlaceDelCorreo } from "./apoyo/correo";
import { entorno } from "./apoyo/entorno";
import { barrer, darDeAlta } from "./apoyo/hr-engine";
import { enlaceParaEntrar } from "./apoyo/supabase";

/**
 * El plan gratis de punta a punta (MVP, ADR-019): Vector HR da de alta a una
 * empresa, la empresa acepta la invitación y publica una vacante con 4 skills,
 * 7 candidatos aplican desde el career site, el worker cuenta las menciones y la
 * empresa ve el gancho, baja el .zip y elimina la vacante.
 */

const SKILLS = ["Excel", "Inventarios", "Montacargas", "Inglés"];

/** Para que cada CV pase de las 100 letras que el worker pide para leerlo. */
const RELLENO = [
  "Experiencia coordinando equipos de trabajo en centros de distribucion,",
  "con enfoque en seguridad, orden y cumplimiento de metas diarias del turno.",
];

type Candidato = { nombre: string; cv: string | null; sinIa?: true };

/**
 * El gancho cuenta de 5 en 5 (0009), así que son 5 CVs legibles: el lote es
 * exacto. "La mayoría" es más de la mitad: 3 de las 4 skills.
 */
const CANDIDATOS: Candidato[] = [
  { nombre: "Ana Paz", cv: "Excel avanzado, control de inventarios, montacargas e ingles" }, // 4
  { nombre: "José Ruiz", cv: "Excel intermedio, inventarios ciclicos y operacion de montacargas" }, // 3
  { nombre: "Lucía Gómez", cv: "Reportes en Excel y nivel de ingles conversacional" }, // 2
  { nombre: "Pedro Sánchez", cv: "Excel, inventarios, montacargas e ingles avanzado" }, // 4
  { nombre: "Rosa Díaz", cv: "Operadora de montacargas certificada" }, // 1
  { nombre: "Carla Núñez", cv: null }, // escaneado: ilegible
  { nombre: "Iván Torres", cv: "Excel, inventarios, montacargas e ingles", sinIa: true }, // no se compara
];

const sinAcentos = (texto: string) => texto.normalize("NFD").replace(/\p{Diacritic}/gu, "");

/** Con las claves de prueba de Turnstile el token llega solo, pero tarda un momento. */
async function esperarTurnstile(pagina: Page) {
  if ((await pagina.locator(".cf-turnstile").count()) === 0) return;
  await expect(pagina.locator('input[name="cf-turnstile-response"]')).not.toHaveValue("", {
    timeout: 30_000,
  });
}

test("plan gratis: alta, publicar, aplicar, gancho, .zip y eliminar", async ({ page, browser }) => {
  const e = entorno();
  const marca = Date.now().toString(36);
  const empresa = `Distribuidora Norte ${marca}`;
  const titulo = `Analista de inventarios ${marca}`;
  test.info().annotations.push({ type: "marca", description: marca });

  const correo = await test.step("Vector HR da de alta a la empresa", async () => {
    if (e.remoto) return e.correo as string;
    const correoNuevo = `rh.${marca}@correo.test`;
    await darDeAlta(empresa, correoNuevo, "Mariana López");
    return correoNuevo;
  });

  await test.step("la empresa entra al panel con su invitación", async () => {
    const enlace = e.remoto ? await enlaceParaEntrar(correo) : await enlaceDelCorreo(correo);
    await page.goto(enlace);
    await page.waitForURL(`${e.panel}/**`);
    await expect(page.getByRole("button", { name: "Salir" })).toBeVisible();
  });

  const vacanteId = await test.step("publica una vacante con 4 skills", async () => {
    await page.goto(`${e.panel}/vacantes/nueva`);
    const formulario = page.getByRole("form", { name: "Datos de la vacante" });
    await formulario.getByLabel("Puesto").fill(titulo);
    await formulario.getByLabel("Ubicación").fill("Monterrey, NL");
    const skill = formulario.getByLabel("Agregar skill");
    for (const s of SKILLS) {
      await skill.fill(s);
      await skill.press("Enter");
    }
    await expect(formulario.getByRole("button", { name: /^Quitar / })).toHaveCount(SKILLS.length);
    await formulario
      .getByLabel("Descripción")
      .fill("Controlarás el inventario del almacén y los conteos cíclicos con el equipo de turno.");
    await formulario.getByRole("button", { name: "Publicar en el career site" }).click();
    await page.waitForURL(/\/vacantes\/[0-9a-f-]{36}$/);
    await expect(page.getByText("La vacante ya está en el career site.")).toBeVisible();
    return page.url().split("/").at(-1) as string;
  });

  const candidatos = await browser.newContext();
  const candidato = await candidatos.newPage();

  const urlDeLaVacante =
    await test.step("un candidato la encuentra en el career site", async () => {
      await candidato.goto(`${e.careerSite}/vacantes?q=${encodeURIComponent(marca)}`);
      await candidato.locator("[data-vacante]").filter({ hasText: titulo }).click();
      await candidato.waitForURL(/\/vacantes\/[^/?]+$/);
      await expect(candidato.getByRole("heading", { level: 1 })).toHaveText(titulo);
      return candidato.url();
    });

  await test.step(`aplican ${CANDIDATOS.length} candidatos con su CV`, async () => {
    for (const c of CANDIDATOS) {
      await candidato.goto(urlDeLaVacante);
      const formulario = candidato.getByRole("form", { name: "Aplicar a la vacante" });
      const plano = sinAcentos(c.nombre);
      await formulario.getByLabel("Nombre completo").fill(c.nombre);
      await formulario
        .getByLabel("Correo")
        .fill(`${plano.toLowerCase().replace(/\s+/g, ".")}.${marca}@correo.test`);
      await formulario.getByLabel("Tu CV").setInputFiles({
        name: `CV ${plano}.pdf`,
        mimeType: "application/pdf",
        buffer: c.cv === null ? pdf() : pdf(`Nombre: ${plano}`, c.cv, ...RELLENO),
      });
      if (c.sinIa) {
        await formulario.getByLabel("Evaluar mi CV sin procesos automatizados").check();
      }
      await formulario.getByLabel("Leí y acepto el aviso de privacidad").check();
      await esperarTurnstile(candidato);
      await formulario.getByRole("button", { name: "Enviar mi aplicación" }).click();
      await expect(candidato.getByText("Listo, recibimos tu aplicación.")).toBeVisible();
    }
  });

  const gancho = page.getByRole("region", { name: "Coincidencia de skills" });

  await test.step("el worker cuenta las menciones de las skills", async () => {
    if (!e.remoto) {
      const resultado = await barrer();
      test
        .info()
        .annotations.push({ type: "barrido", description: resultado.split("\n").at(-1) ?? "" });
    }
    // En un despliegue el beat barre cada minuto: se recarga hasta que aparezca.
    await expect(async () => {
      await page.goto(`${e.panel}/vacantes/${vacanteId}`);
      await expect(gancho).toContainText("Revisamos 5 de tus CVs", { timeout: 5_000 });
    }).toPass({ timeout: e.remoto ? 4 * 60_000 : 30_000, intervals: [2_000, 15_000] });
  });

  await test.step("la empresa ve el gancho sin IA", async () => {
    await expect(gancho).toContainText(
      `Revisamos 5 de tus CVs contra las ${SKILLS.length} skills de la vacante.`,
    );
    await expect(gancho).toContainText("Un CV no se pudo leer (escaneado o protegido).");
    const cifra = (texto: string) => gancho.locator("p", { hasText: texto }).locator("b");
    await expect(cifra("mencionan la mayoría de tus skills")).toHaveText("3");
    await expect(cifra("las mencionan todas")).toHaveText("2");
  });

  await test.step("baja el .zip con todos los CVs en orden de llegada", async () => {
    const [descarga] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: `Descargar los ${CANDIDATOS.length} CVs (.zip)` }).click(),
    ]);
    const zip = await readFile(await descarga.path());
    expect(nombresEnElZip(zip)).toEqual(
      CANDIDATOS.map((c, i) => `${String(i + 1).padStart(2, "0")} - ${c.nombre}.pdf`),
    );
  });

  await test.step("elimina la vacante y sale del career site", async () => {
    await page.goto(`${e.panel}/vacantes`);
    const fila = page.locator(`li[data-vacante="${vacanteId}"]`);
    await fila.getByRole("button", { name: "Eliminar" }).click();
    await fila
      .getByRole("alertdialog", { name: `Eliminar ${titulo}` })
      .getByRole("button", { name: "Sí, eliminar" })
      .click();
    await expect(fila).toHaveCount(0);
    const respuesta = await candidato.goto(urlDeLaVacante);
    expect(respuesta?.status()).toBe(404);
  });

  await candidatos.close();
});
