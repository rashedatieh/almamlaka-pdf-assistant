import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The build output (dist/) is served by the FastAPI service as static files: one Cloud Run
// service, no CDN, no external assets (CSP default-src 'self'; ADR-0001 D23).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { proxy: { "/api": "http://127.0.0.1:8000", "/sources": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", sourcemap: false, assetsInlineLimit: 0 },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});
