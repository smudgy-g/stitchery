import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  // Same origin as in production, so sign-in cookies work the same way
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
