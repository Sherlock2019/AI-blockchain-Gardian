import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server only answers to localhost and IP addresses unless told
// otherwise. To reach it through a hostname (for example an EC2 public DNS
// name), list the hostnames in ALLOWED_HOSTS, comma-separated, or set it to "all".
const allowed = (process.env.ALLOWED_HOSTS ?? "").split(",").map((h) => h.trim()).filter(Boolean);
const allowedHosts = allowed.includes("all") ? true : allowed;

// The dashboard calls /api on its own origin; the dev server forwards it.
// That is why it works unchanged behind any hostname or public address.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts,
    proxy: {
      "/api": process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
    },
  },
});
