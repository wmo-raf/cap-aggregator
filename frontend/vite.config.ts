/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// Served by Django: dev via the Vite dev server (django-vite dev_mode),
// prod as hashed bundles collected from src/capaggregator/static/frontend/.
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  base: "/static/frontend/",
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    manifest: true,
    outDir: "../src/capaggregator/static/frontend",
    emptyOutDir: true,
    rollupOptions: {
      input: "src/main.ts",
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    cors: true,
  },
  test: {
    environment: "jsdom",
    globals: false,
  },
});
