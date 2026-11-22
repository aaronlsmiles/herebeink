import { resolve } from "node:path";
import { defineConfig } from "vitest/config";
import { filmSceneServer } from "./vite/film-scene.ts";
import { frameDump } from "./vite/frame-dump.ts";

export default defineConfig({
  plugins: [frameDump(resolve(import.meta.dirname, "..")), filmSceneServer(resolve(import.meta.dirname, ".."))],
  // Minifying strips the MIT notices from three.js and Spark; this ships them beside the page instead.
  build: { license: { fileName: "third-party-licences.md" } },
  test: { environment: "node", include: ["src/**/*.test.ts", "vite/**/*.test.ts"] },
});
