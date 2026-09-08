import { defineConfig, devices } from "@playwright/test";

/**
 * Config Playwright de Vortex Ops.
 *
 * - `BASE_URL` definido  → se testea contra ese deploy (preview de Vercel, staging…)
 *   y Playwright NO levanta ningún servidor.
 * - `BASE_URL` sin definir → default `http://localhost:3000` y Playwright arranca
 *   el career-site con `next start` (el bundle lo produce `turbo run build`, del que
 *   dependen las tareas `e2e` / `e2e:smoke`).
 */
const DEFAULT_BASE_URL = "http://localhost:3000";
const externalBaseUrl = process.env.BASE_URL;
const baseURL = externalBaseUrl ?? DEFAULT_BASE_URL;
const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  // En CI serializamos (un solo `next start`); en local dejamos que Playwright decida.
  ...(isCI ? { workers: 1 } : {}),
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: isCI
    ? [["github"], ["html", { open: "never" }], ["list"]]
    : [["html", { open: "never" }], ["list"]],
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Solo levantamos servidor cuando no apuntamos a un entorno ya desplegado.
  ...(externalBaseUrl
    ? {}
    : {
        webServer: {
          command: "pnpm --filter @vortex/career-site start",
          url: DEFAULT_BASE_URL,
          reuseExistingServer: !isCI,
          timeout: 120_000,
          stdout: "pipe" as const,
          stderr: "pipe" as const,
        },
      }),
});
