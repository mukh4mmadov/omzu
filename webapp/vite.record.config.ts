import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  publicDir: "public-record",
  build: {
    outDir: "../web/dist-record",
    emptyOutDir: true,
    rolldownOptions: { input: { index: "record.html" } },
  },
});
