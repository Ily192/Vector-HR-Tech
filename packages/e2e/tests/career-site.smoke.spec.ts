import { expect, test } from "@playwright/test";

/**
 * Smoke E2E del career-site público.
 *
 * Cubre el camino crítico del candidato: landing → listado de vacantes →
 * detalle de una vacante → contacto. Todos los tests llevan `@smoke` para que
 * `pnpm e2e:smoke` (que filtra por ese tag) sea un subconjunto ejecutable en cada PR.
 */

test.describe("career-site @smoke", () => {
  test("la home carga y muestra el hero @smoke", async ({ page }) => {
    const response = await page.goto("/");
    expect(response?.status()).toBeLessThan(400);

    await expect(page).toHaveTitle(/Vortex Ops/i);

    // Wordmark del hero — el componente expone aria-label "VORTEX OPS".
    await expect(page.getByLabel("VORTEX OPS").first()).toBeVisible();

    const hero = page.getByRole("heading", { level: 1 });
    await expect(hero).toBeVisible();
    await expect(hero).toContainText(/Hackeando la rutina/i);
    await expect(hero).toContainText(/liberando el talento/i);

    // Los dos CTAs del hero apuntan a las rutas reales.
    await expect(page.getByRole("link", { name: /Ver vacantes abiertas/i })).toHaveAttribute(
      "href",
      "/vacantes",
    );
    await expect(page.getByRole("link", { name: /Hablar con Vector HR/i })).toHaveAttribute(
      "href",
      "/contacto",
    );

    // Los tres pilares se renderizan.
    for (const pilar of ["Velocidad", "Inteligencia", "Control"]) {
      await expect(page.getByRole("heading", { name: pilar, exact: true })).toBeVisible();
    }
  });

  test("desde la home se navega al listado de vacantes @smoke", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /Ver vacantes abiertas/i }).click();

    await page.waitForURL("**/vacantes");
    await expect(page.getByRole("heading", { level: 1, name: /Vacantes abiertas/i })).toBeVisible();

    // Cada vacante es un link a su detalle; debe haber al menos una.
    const vacantes = page.locator('a[href^="/vacantes/"]');
    await expect(vacantes.first()).toBeVisible();
    expect(await vacantes.count()).toBeGreaterThan(0);
  });

  test("el detalle de una vacante muestra JD y CTA de aplicar @smoke", async ({ page }) => {
    await page.goto("/vacantes");

    const primeraVacante = page.locator('a[href^="/vacantes/"]').first();
    const titulo = (await primeraVacante.getByRole("heading").first().textContent())?.trim();
    expect(titulo).toBeTruthy();

    await primeraVacante.click();
    await page.waitForURL(/\/vacantes\/[^/]+$/);

    await expect(page.getByRole("heading", { level: 1 })).toHaveText(titulo as string);
    await expect(page.getByRole("heading", { name: /Sobre el rol/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^Aplicar$/i })).toBeVisible();

    // El botón de subir CV existe pero todavía está deshabilitado (feature de cycle 1).
    await expect(page.getByRole("button", { name: /Subir CV/i })).toBeDisabled();

    // Y se puede volver al listado.
    await page.getByRole("link", { name: /Volver a vacantes/i }).click();
    await page.waitForURL("**/vacantes");
    await expect(page.getByRole("heading", { level: 1, name: /Vacantes abiertas/i })).toBeVisible();
  });

  test("una vacante inexistente devuelve 404 @smoke", async ({ page }) => {
    const response = await page.goto("/vacantes/no-existe-esta-vacante");
    expect(response?.status()).toBe(404);
  });

  test("la página de contacto carga con sus canales @smoke", async ({ page }) => {
    const response = await page.goto("/contacto");
    expect(response?.status()).toBeLessThan(400);

    await expect(
      page.getByRole("heading", { level: 1, name: /Hablemos de tu operación/i }),
    ).toBeVisible();

    // Canal email: link mailto real.
    const email = page.locator('a[href^="mailto:"]').first();
    await expect(email).toBeVisible();

    // Canal LinkedIn.
    await expect(page.locator('a[href*="linkedin.com"]').first()).toBeVisible();

    // Cross-link de vuelta a vacantes.
    await expect(page.getByRole("link", { name: /Ver vacantes abiertas/i })).toHaveAttribute(
      "href",
      "/vacantes",
    );
  });
});
