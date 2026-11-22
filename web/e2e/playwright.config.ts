import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  reporter: [["list"]],
  webServer: { command: "npx vite --port 5299 --strictPort", port: 5299, reuseExistingServer: true, cwd: ".." },
  use: {
    baseURL: "http://localhost:5299",
    viewport: { width: 1440, height: 900 },
    // Headless Chromium has no GPU by default; SwiftShader gives a software WebGL2 context that Spark needs.
    launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] },
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
