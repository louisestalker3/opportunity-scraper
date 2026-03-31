import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

const apiPort = process.env.APP_API_PORT ?? "9000";
const frontendPort = parseInt(process.env.APP_FRONTEND_PORT ?? "9001", 10);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: frontendPort,
    proxy: {
      "/api": {
        target: `http://localhost:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
});
