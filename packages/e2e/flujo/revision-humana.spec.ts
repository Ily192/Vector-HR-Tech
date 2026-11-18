import { type Page, expect, test } from "@playwright/test";

import { codigoDelCorreo } from "./apoyo/correo";
import { entorno } from "./apoyo/entorno";

/**
 * La revisión humana desde panel/admin (ADR-022, enmienda del 2026-11-17): una empresa
 * sin verificar (correo de un proveedor gratuito) publica su primera vacante, que queda
 * en revisión y fuera del career site; el admin entra a /admin con su código y la
 * aprueba, y sale en el career site. Después publica otra que manda a WhatsApp, el admin
 * la rechaza con un motivo y la empresa lo ve en su panel.
 *
 * Corre contra el stack del VPS (pruebas/probar_en_local.sh): necesita el alta desde la
 * web, Mailpit para los códigos, el beat que modera cada minuto y el hr-engine como API
 * con ADMIN_CORREOS. En local, contra `pnpm db:start`, se salta.
 */
const e = entorno();

test.skip(
  !e.alta || !e.mailpit || !e.admin,
  "Necesita E2E_ALTA_URL, E2E_ALTA_SECRETO, E2E_MAILPIT_URL y E2E_ADMIN_CORREO (pruebas/probar_en_local.sh).",
);

/** Dos barridos de la moderación (uno por minuto), con margen. */
const ESPERA_DEL_BEAT = 3 * 60_000;

/** Escribe el código que llegó a `correo` después de `desde` y entra. */
async function entrarConCodigo(pagina: Page, correo: string, desde: number) {
  const codigo = await codigoDelCorreo(correo, desde);
  await pagina.getByLabel("Código de 6 dígitos").fill(codigo);
  await pagina.getByRole("button", { name: "Entrar" }).click();
  await expect(pagina.getByRole("button", { name: "Salir" })).toBeVisible();
}

/** Publica desde "Crear empleo" y devuelve el id de la vacante. */
async function publicar(pagina: Page, titulo: string, descripcion: string): Promise<string> {
  await pagina.goto(`${e.panel}/vacantes/nueva`);
  const formulario = pagina.getByRole("form", { name: "Datos de la vacante" });
  await formulario.getByLabel("Puesto").fill(titulo);
  await formulario.getByLabel("Ubicación").fill("Guadalajara, Jal.");
  await formulario.getByLabel("Descripción").fill(descripcion);
  await formulario.getByRole("button", { name: "Publicar en el career site" }).click();
  await pagina.waitForURL(/\/vacantes\/[0-9a-f-]{36}$/);
  return pagina.url().split("/").at(-1) as string;
}

/** En "Mis vacantes", hasta que el beat la modere y quede en `estado`. */
async function esperarModeracion(pagina: Page, vacanteId: string, estado: string) {
  const fila = pagina.locator(`li[data-vacante="${vacanteId}"]`);
  await expect(async () => {
    await pagina.goto(`${e.panel}/vacantes`);
    await expect(fila.getByText(estado, { exact: true })).toBeVisible({ timeout: 3_000 });
  }).toPass({ timeout: ESPERA_DEL_BEAT, intervals: [5_000, 10_000, 15_000] });
  return fila;
}

/** Las vacantes con `titulo` en la búsqueda del career site. */
async function enElCareerSite(pagina: Page, marca: string, titulo: string) {
  await pagina.goto(`${e.careerSite}/vacantes?q=${encodeURIComponent(marca)}`);
  return pagina.locator("[data-vacante]").filter({ hasText: titulo }).count();
}

test("revisión humana: el admin aprueba y rechaza desde panel/admin", async ({ page, browser }) => {
  test.setTimeout(12 * 60_000);
  const alta = e.alta as { url: string; secreto: string };
  const correoAdmin = e.admin as string;
  const marca = Date.now().toString(36);
  // Un proveedor gratuito nunca da la insignia (ADR-022): su primera vacante va a revisión.
  // En el stack de prueba todo correo va a Mailpit.
  const correo = `rh.delta.${marca}@gmail.com`;
  const empresa = `Servicios Delta ${marca}`;
  const aprobada = `Auxiliar contable ${marca}`;
  const rechazada = `Promotor de tienda ${marca}`;
  const motivo = "Pide escribir por WhatsApp: deja que apliquen en la bolsa de empleo.";
  test.info().annotations.push({ type: "marca", description: marca });

  await test.step("una empresa sin verificar se registra en la web y entra con su código", async () => {
    const desde = Date.now();
    const respuesta = await fetch(alta.url, {
      method: "POST",
      headers: { Authorization: `Bearer ${alta.secreto}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        lead_id: `e2e-revision-${marca}`,
        nombre: "Rocío Méndez",
        correo,
        publica_para: "propia",
        empresa,
        cargo: "Dueña",
        web_empresa: "https://serviciosdelta.test",
        linkedin: null,
        verificacion: "revision",
        pais: "mx",
        tamano: "1-15",
        sector: "servicios",
        contrataciones_mes: "1-2",
        puestos: ["administrativos"],
        origen: "e2e",
        utm_medium: null,
        utm_campaign: null,
        ip: "198.51.100.47",
      }),
    });
    expect(respuesta.status).toBe(200);
    const { verificar_url } = (await respuesta.json()) as { verificar_url: string };
    await page.goto(verificar_url);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Escribe tu código");
    await entrarConCodigo(page, correo, desde);
  });

  const primera = await test.step("su primera vacante queda en revisión", async () => {
    const id = await publicar(
      page,
      aprobada,
      "Registrarás facturas de proveedores y prepararás los cierres mensuales con el equipo de contabilidad.",
    );
    await esperarModeracion(page, id, "En revisión");
    return id;
  });

  const candidatos = await browser.newPage();
  await test.step("y no sale en el career site", async () => {
    expect(await enElCareerSite(candidatos, marca, aprobada)).toBe(0);
  });

  const contextoAdmin = await browser.newContext();
  // Las métricas de la web son de otro repo (vectorhrtech.com): aquí no se llaman.
  await contextoAdmin.route("https://vectorhrtech.com/**", (ruta) => ruta.abort());
  const admin = await contextoAdmin.newPage();

  await test.step("el admin abre /admin, entra con su código y ve el tablero", async () => {
    await admin.goto(`${e.panel}/admin`);
    await expect(admin.getByRole("heading", { level: 1 })).toHaveText("Entra a tu panel");
    const desde = Date.now();
    await admin.getByLabel("Correo de trabajo").fill(correoAdmin);
    await admin.getByRole("button", { name: "Mandarme el código" }).click();
    await expect(admin.getByRole("heading", { level: 1 })).toHaveText("Escribe tu código");
    await entrarConCodigo(admin, correoAdmin, desde);
    // Sigue en /admin después de entrar.
    await expect(admin.getByRole("heading", { level: 1 })).toHaveText("La plataforma hoy");
    expect(new URL(admin.url()).pathname).toBe("/admin");
    await expect(admin.getByRole("region", { name: "Panel" }).getByText("Empresas")).toBeVisible();
    await expect(admin.getByText(/No pudimos leer las métricas de la web/)).toBeVisible();
    await expect(admin.locator('link[rel="manifest"]')).toHaveAttribute(
      "href",
      "/admin.webmanifest",
    );
  });

  await test.step("aprueba la vacante y sale en el career site", async () => {
    const tarjeta = admin.getByRole("article", { name: aprobada });
    await expect(tarjeta).toContainText(empresa);
    await expect(tarjeta.getByText("Sin verificar")).toBeVisible();
    await tarjeta.getByRole("button", { name: "Aprobar" }).click();
    await expect(admin.getByRole("status")).toContainText(`Aprobaste «${aprobada}»`);
    await expect(tarjeta).toHaveCount(0);
    await expect(async () => {
      expect(await enElCareerSite(candidatos, marca, aprobada)).toBe(1);
    }).toPass({ timeout: 60_000, intervals: [2_000, 5_000] });
    // En "Mis vacantes" una publicada no lleva insignia.
    await page.goto(`${e.panel}/vacantes`);
    await expect(page.locator(`li[data-vacante="${primera}"]`)).not.toContainText("En revisión");
  });

  const segunda = await test.step("otra vacante que manda a WhatsApp va a revisión", async () => {
    const id = await publicar(
      page,
      rechazada,
      "Atenderás a los clientes en la tienda. Interesados, escríbenos por WhatsApp al 55 1234 5678.",
    );
    await esperarModeracion(page, id, "En revisión");
    return id;
  });

  await test.step("el admin la rechaza con un motivo", async () => {
    await admin.reload();
    const tarjeta = admin.getByRole("article", { name: rechazada });
    await expect(tarjeta).toContainText("WhatsApp");
    await tarjeta.getByRole("button", { name: "Rechazar" }).click();
    const formulario = admin.getByRole("form", { name: `Rechazar ${rechazada}` });
    await formulario.getByLabel("Motivo del rechazo (la empresa lo ve en su panel)").fill(motivo);
    await formulario.getByRole("button", { name: "Rechazar vacante" }).click();
    await expect(admin.getByRole("status")).toContainText(`Rechazaste «${rechazada}»`);
    await expect(tarjeta).toHaveCount(0);
  });

  await test.step("la empresa ve el rechazo y el motivo en su panel", async () => {
    const fila = await esperarModeracion(page, segunda, "Rechazada");
    await expect(fila).toContainText(`Qué corregir: ${motivo}`);
    expect(await enElCareerSite(candidatos, marca, rechazada)).toBe(0);
  });

  await contextoAdmin.close();
  await candidatos.close();
});
