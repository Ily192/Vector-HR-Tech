import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    // Asegura que la carpeta de salida sea 'dist'
    outDir: 'dist', 
  }
});
