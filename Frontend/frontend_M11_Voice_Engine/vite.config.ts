import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * M11 — Voice & Conversation Engine, on its reserved port 5211 (PORTS.txt).
 *
 * This repo holds one module, so this is the app. Platform_Shell mounts the
 * same `src/routes.tsx`, so what you fix here is what students get.
 *
 * The voice check plays M06's interviewers, so `/v1/interviews` goes to M06
 * here exactly as the shell routes it — the more specific entry first, because
 * Vite tries proxies in order.
 */
const API_TARGET = process.env.VITE_API_BASE ?? "http://127.0.0.1:8111";
const M06_TARGET = process.env.M06_BASE_URL ?? "http://127.0.0.1:8106";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    // @ai/core ships TypeScript source rather than a build, so Vite must
    // transform it instead of pre-bundling it as an opaque dependency.
    exclude: ["@ai/core"],
  },
  server: {
    port: 5211,
    proxy: {
      "/v1/interviews": { target: M06_TARGET, changeOrigin: true },
      "/v1": { target: API_TARGET, changeOrigin: true },
      "/health": { target: API_TARGET, changeOrigin: true },
      "/status": { target: API_TARGET, changeOrigin: true },
    },
  },
  preview: { port: 5211 },
});
