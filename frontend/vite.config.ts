/// <reference types="vitest/config" />
import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@shared": path.resolve(__dirname, "../shared"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          forms: ["react-hook-form", "zod", "@hookform/resolvers"],
        },
      },
    },
  },
  server: {
    port: 5173,
    fs: { allow: [".."] },
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
