import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    // Sin Turnstile en los tests, aunque haya un .env.local con la clave.
    env: { VITE_TURNSTILE_SITE_KEY: "" },
  },
});
