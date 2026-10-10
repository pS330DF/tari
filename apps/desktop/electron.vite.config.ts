import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import type { Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Strict CSP for production builds (dev uses a header from the main process because the
// Vite dev server needs inline scripts for React refresh).
const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; " +
  "media-src 'self' blob: mediastream: tari-e2e:; font-src 'self' data:; " +
  "connect-src 'self' ws://127.0.0.1:* http://127.0.0.1:* tari-e2e:; worker-src 'self' blob:";

function cspPlugin(): Plugin {
  return {
    name: "tari-csp",
    apply: "build",
    transformIndexHtml(html) {
      return html.replace("<head>", `<head>\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`);
    },
  };
}

// Workspace packages ship TypeScript sources, so they are bundled rather than externalized.
const workspace = ["@tari/shared-types", "@tari/telemetry", "@tari/overlay-components"];

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin({ exclude: workspace })],
    build: { rollupOptions: { input: { index: resolve(__dirname, "src/main/index.ts") } } },
  },
  preload: {
    plugins: [externalizeDepsPlugin({ exclude: workspace })],
    build: { rollupOptions: { input: { index: resolve(__dirname, "src/preload/index.ts") } } },
  },
  renderer: {
    root: resolve(__dirname, "src/renderer"),
    plugins: [react(), tailwindcss(), cspPlugin()],
    worker: { format: "es" },
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, "src/renderer/index.html"),
          companion: resolve(__dirname, "src/renderer/companion.html"),
        },
      },
    },
  },
});
