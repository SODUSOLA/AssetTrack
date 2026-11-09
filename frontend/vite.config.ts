/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

// The app is served at /app/ by the API container, and by `npm run dev` at the same path, so
// links and the router behave identically in both. /api is proxied to the backend in dev, which
// keeps the refresh-token cookie (SameSite=Strict) on one origin without any CORS setup.
export default defineConfig({
  base: "/app/",
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.API_URL ?? "http://localhost:8000" } },
  },
  build: {
    // The API serves this folder (backend/app/static); the Docker build copies it into the image.
    outDir: "../backend/app/static",
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: { modules: { classNameStrategy: "non-scoped" } },
    env: { VITE_API_BASE: "http://localhost:3000" },
    restoreMocks: true,
    // Pages load on demand, and this runs on busy laptops as well as CI.
    testTimeout: 20_000,
  },
});
