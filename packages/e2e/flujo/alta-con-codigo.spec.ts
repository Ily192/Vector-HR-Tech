import { expect, test } from "@playwright/test";

import { codigoDelCorreo } from "./apoyo/correo";
import { entorno } from "./apoyo/entorno";
import { empresasLlamadas } from "./apoyo/supabase";

/**
 * El alta desde vectorhrtech.com/publicar-vacantes (ADR-017, enmienda del 2026-11-12):
 * la web llama al hr-engine de servidor a servidor, la empresa queda creada y la persona
 * entra a su panel con el código de 6 dígitos que le llega al correo. Después sale y
 * vuelve a entrar con otro código, sin enlaces ni contraseñas.
 *
 * Corre contra el stack del VPS (pruebas/probar_en_local.sh), que trae el endpoint y
 * Mailpit. En local, contra `pnpm db:start`, se salta: ahí el hr-engine no corre como API.
 */
const e = entorno();

test.skip(
  !e.alta || !e.mailpit,
  "Necesita E2E_ALTA_URL, E2E_ALTA_SECRETO y E2E_MAILPIT_URL (pruebas/probar_en_local.sh).",
);

test("alta desde la web: el registro da el panel y se entra con un código", async ({ page }) => {
  const alta = e.alta as { url: string; secreto: string };
  const marca = Date.now().toString(36);
  const correo = `rh.${marca}@alta.test`;
  const empresa = `Textiles del Sur ${marca}`;
  const registro = {
    lead_id: `e2e-${marca}`,
    nombre: "Lucía Prieto",
    correo,
    publica_para: "propia",
    empresa,
    cargo: "Coordinadora de RH",
    web_empresa: "https://textilesdelsur.test",
    linkedin: null,
    verificacion: "dominio",
    pais: "ve",
    tamano: "16-50",
    sector: "industria",
    contrataciones_mes: "3-5",
    puestos: ["operativos"],
    origen: "e2e",
    utm_medium: null,
    utm_campaign: null,
    ip: "198.51.100.23",
  };
  const registrar = (cuerpo: object) =>
    fetch(alta.url, {
      method: "POST",
      headers: { Authorization: `Bearer ${alta.secreto}`, "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });

  const desde = Date.now();
  const verificarUrl = await test.step("la web registra la empresa", async () => {
    const respuesta = await registrar(registro);
    expect(respuesta.status).toBe(200);
    const cuerpo = (await respuesta.json()) as { estado: string; verificar_url: string };
    expect(cuerpo).toEqual({
      estado: "codigo_enviado",
      verificar_url: `${e.panel}/verificar#correo=${encodeURIComponent(correo)}`,
    });

    // La web reintenta con el mismo lead: la misma respuesta y ninguna empresa de más.
    const reintento = await registrar(registro);
    expect(reintento.status).toBe(200);
    expect(await reintento.json()).toEqual(cuerpo);
    expect(await empresasLlamadas(empresa)).toBe(1);
    return cuerpo.verificar_url;
  });

  await test.step("escribe el código del correo y entra a su panel", async () => {
    const codigo = await codigoDelCorreo(correo, desde);
    await page.goto(verificarUrl);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Escribe tu código");
    // El correo iba en el fragmento: la página lo lee y lo quita de la URL.
    await expect.poll(() => new URL(page.url()).hash).toBe("");
    await page.getByLabel("Código de 6 dígitos").fill(codigo);
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page.getByRole("button", { name: "Salir" })).toBeVisible();
    await expect(page.getByText(empresa).first()).toBeVisible();
    await expect.poll(() => new URL(page.url()).pathname).toBe("/");
  });

  await test.step("sale y vuelve a entrar con otro código", async () => {
    await page.getByRole("button", { name: "Salir" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Entra a tu panel");
    const otraVez = Date.now();
    await page.getByLabel("Correo de trabajo").fill(correo);
    await page.getByRole("button", { name: "Mandarme el código" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Escribe tu código");
    const codigo = await codigoDelCorreo(correo, otraVez);
    await page.getByLabel("Código de 6 dígitos").fill(codigo);
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page.getByRole("button", { name: "Salir" })).toBeVisible();
  });
  // Va al final: le manda otro código a la misma cuenta, y Auth no manda dos en un minuto.
  await test.step("un registro nuevo con el mismo correo no crea otra empresa", async () => {
    const respuesta = await registrar({ ...registro, lead_id: `e2e-${marca}-2` });
    expect(respuesta.status).toBe(200);
    expect(await empresasLlamadas(empresa)).toBe(1);
  });
});
