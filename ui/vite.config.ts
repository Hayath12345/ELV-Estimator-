import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built to static files loaded by pywebview (relative paths, no CDN, works offline).
export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 1500, assetsInlineLimit: 0 },
  server: { port: 5173 },
})
