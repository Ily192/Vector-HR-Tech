import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { port: 3001 },
  build: {
    sourcemap: true,
    target: "es2022",
    rollupOptions: {
      // El bundle principal sale como `entrada-*.js` para que size-limit mida solo a
      // él: un paquete cuyo módulo es `index.js` (client-zip) también salía `index-*.js`.
      output: { entryFileNames: "assets/entrada-[hash].js" },
    },
  },
});
