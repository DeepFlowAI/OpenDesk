import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  // Product tsconfig uses jsx: preserve; prototypes compile JSX with the automatic runtime instead.
  oxc: {
    jsx: { runtime: "automatic" },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("../", import.meta.url)),
    },
  },
  css: {
    postcss: fileURLToPath(new URL("../", import.meta.url)),
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
