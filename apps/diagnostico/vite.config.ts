import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En el VPS, Caddy reenvía /api/diagnostico a la RPC de Supabase con la clave anon
// (infra/vps/caddy/Caddyfile). En desarrollo hace lo mismo este proxy, contra el
// Supabase local de la CLI.
const supabaseLocal = process.env.SUPABASE_LOCAL_URL ?? "http://127.0.0.1:54321";
const claveAnonLocal = process.env.SUPABASE_LOCAL_ANON_KEY ?? "";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3004,
    proxy: {
      "/api/diagnostico": {
        target: supabaseLocal,
        changeOrigin: true,
        rewrite: () => "/rest/v1/rpc/registrar_diagnostico",
        headers: { apikey: claveAnonLocal, Authorization: `Bearer ${claveAnonLocal}` },
      },
    },
  },
  build: {
    sourcemap: true,
    target: "es2022",
  },
});
