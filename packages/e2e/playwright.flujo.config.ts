import { defineConfig, devices } from "@playwright/test";

import { entorno } from "./flujo/apoyo/entorno";

/**
 * El flujo completo del plan gratis (`flujo/`), aparte del smoke (`playwright.config.ts`),
 * que corre contra los datos de ejemplo.
 *
 * En local levanta el career site y el panel con `pnpm dev` apuntando al Supabase de
 * `pnpm db:start`, o usa los que ya estén corriendo. Con `E2E_REMOTO=1` no levanta
 * nada y va contra las URLs del despliegue. Detalles en el README del paquete.
 */
const e = entorno();

export default defineConfig({
  testDir: "./flujo",
  outputDir: "./test-results/flujo",
  // Un solo test, en orden: cada paso deja lo que necesita el siguiente.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  // `next dev` compila cada ruta la primera vez, y en un despliegue el beat barre cada minuto.
  timeout: 6 * 60_000,
  expect: { timeout: 20_000 },
  reporter: [["html", { open: "never", outputFolder: "playwright-report/flujo" }], ["list"]],
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  ...(e.remoto
    ? {}
    : {
        webServer: [
          {
            command: "pnpm --filter @vortex/career-site dev",
            url: e.careerSite,
            reuseExistingServer: true,
            timeout: 180_000,
            env: {
              SUPABASE_URL: e.supabaseUrl,
              SUPABASE_PUBLISHABLE_KEY: e.clavePublica,
              SUPABASE_SECRET_KEY: e.claveSecreta,
              NEXT_PUBLIC_PANEL_EMPRESAS_URL: e.panel,
            },
          },
          {
            command: "pnpm --filter @vortex/hrbp dev",
            url: e.panel,
            reuseExistingServer: true,
            timeout: 120_000,
            env: {
              VITE_SUPABASE_URL: e.supabaseUrl,
              VITE_SUPABASE_PUBLISHABLE_KEY: e.clavePublica,
            },
          },
        ],
      }),
});
