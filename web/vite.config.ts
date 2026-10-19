import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev: the Python server runs on :8000; in production both are served from the same origin
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
