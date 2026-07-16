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
      // main: explorer SPA · public: server-rendered pages (tokens + theme
      // toggle) · alert-detail: progressive area map on the detail page ·
      // home: homepage active-alerts map + time/severity filtering
      input: {
        main: "src/main.ts",
        public: "src/public.ts",
        "alert-detail": "src/alert-detail.ts",
        home: "src/home.ts",
      },
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
    setupFiles: ["./vitest.setup.ts"],
  },
});
