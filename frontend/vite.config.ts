import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the React app talks to the FastAPI server started with `uvicorn app.main:app` (port 8000).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  preview: { port: 4173, proxy: { "/api": "http://127.0.0.1:8000" } },
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
