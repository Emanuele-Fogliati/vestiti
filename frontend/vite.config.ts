import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8000 and Vite proxies /api to it, so cookies stay
// first-party. In docker, nginx does the same proxying.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.API_URL ?? "http://localhost:8000", changeOrigin: false } },
  },
  test: { environment: "node" },
});
