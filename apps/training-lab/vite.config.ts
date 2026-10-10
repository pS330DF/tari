import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./", // loaded from file:// inside Electron
  server: { fs: { allow: [resolve(__dirname, "../..")] } },
  build: { target: "es2022", assetsInlineLimit: 0 },
  test: { include: ["test/**/*.test.ts"], environment: "node" },
} as never);
