import { expect, test } from "@playwright/test";

/**
 * Smoke E2E del career-site para candidatos (ADR-017).
 *
 * Cubre el camino crítico del candidato: inicio → búsqueda → listado filtrado →
 * detalle de una vacante. Todos los tests llevan `@smoke` para que
 * `pnpm e2e:smoke` (que filtra por ese tag) sea un subconjunto ejecutable en cada PR.
 */

test.describe("career-site @smoke", () => {
  test("el inicio carga para candidatos, sin CTAs de venta @smoke", async ({ page }) => {
    const response = await page.goto("/");
    expect(response?.status()).toBeLessThan(400);

    await expect(page).toHaveTitle(/Vortex Empleos/i);
    await expect(page.getByLabel("VORTEX OPS").first()).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Tu siguiente trabajo/i);
    await expect(page.getByRole("search", { name: "Buscar vacantes" })).toBeVisible();
    await expect(page.getByText(/Agendar/i)).toHaveCount(0);

    const tarjetas = page.locator("[data-vacante]");
    await expect(tarjetas.first()).toBeVisible();
  });

  test("buscar desde el inicio lleva al listado filtrado @smoke", async ({ page }) => {
    await page.goto("/");
    await page.getByPlaceholder("Puesto o palabra clave").fill("almacen");
    await page.getByRole("button", { name: "Buscar" }).click();

    await page.waitForURL(/\/vacantes\?q=almacen/);
    await expect(page.getByRole("heading", { level: 1, name: /Vacantes abiertas/i })).toBeVisible();
    await expect(page.locator("[data-vacante]")).toHaveCount(1);
    await expect(page.getByText("1 vacante", { exact: true })).toBeVisible();
  });

  test("los filtros rápidos cambian la URL y el resultado @smoke", async ({ page }) => {
    await page.goto("/vacantes");
    const total = await page.locator("[data-vacante]").count();
    await page.getByRole("link", { name: "Remoto", exact: true }).click();
    await page.waitForURL(/modalidad=remote/);
    const remotas = await page.locator("[data-vacante]").count();
    expect(remotas).toBeGreaterThan(0);
    expect(remotas).toBeLessThan(total);
  });

  test("el detalle de una vacante muestra empresa, JD y CTA de aplicar @smoke", async ({
    page,
  }) => {
    await page.goto("/vacantes");

    const primera = page.locator("[data-vacante]").first();
    const titulo = (await primera.getByRole("heading").first().textContent())?.trim();
    expect(titulo).toBeTruthy();

    await primera.click();
    await page.waitForURL(/\/vacantes\/[^/?]+$/);

    await expect(page.getByRole("heading", { level: 1 })).toHaveText(titulo as string);
    await expect(page.getByRole("heading", { name: /Sobre el rol/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^Aplicar$/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Subir CV/i })).toBeDisabled();

    await page.getByRole("link", { name: /Volver a vacantes/i }).click();
    await page.waitForURL("**/vacantes");
  });

  test("una vacante inexistente devuelve 404 @smoke", async ({ page }) => {
    const response = await page.goto("/vacantes/no-existe-esta-vacante");
    expect(response?.status()).toBe(404);
  });

  test("la antigua página comercial /contacto redirige al inicio @smoke", async ({ page }) => {
    await page.goto("/contacto");
    await page.waitForURL((url) => url.pathname === "/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Tu siguiente trabajo/i);
  });
});
