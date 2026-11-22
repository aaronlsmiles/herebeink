// Dumps the film walk's frames as PNGs into film/frames/ (gitignored) by opening the viewer's
// film page in Chromium on the real GPU (ANGLE's Metal backend, macOS) and waiting for its done signal.
// Usage: node tools/film-dump.mjs [--w 1920] [--h 1080] [--set name] [--sw] [--scene <url>] [--from N] [--frames N] [--keep] [--timeout <minutes>]
//        [--export <dir> --shot <name>] [--ink off]
// It starts the Vite dev server on :5299 if nothing answers there (the /frame endpoint lives in it).
// --export serves a local export folder (relative to the repo) at /film-scene/ and --shot picks a camera path from
// film/paths.json (web/vite/film-scene.ts), so a film can be cut from a corrected path without touching published media.
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");
const framesRoot = resolve(webRoot, "../film/frames");

const argv = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : fallback;
};
const width = Number(opt("w", 1920));
const height = Number(opt("h", 1080));
const set = opt("set", null);
const exportDir = opt("export", null);
const shot = opt("shot", null);
const sceneUrl = exportDir ? `/film-scene/scene.json?shot=${encodeURIComponent(shot ?? "walk")}` : opt("scene", null);
const ink = opt("ink", null);
const from = opt("from", null);
const frames = opt("frames", null);
const timeoutMs = Number(opt("timeout", 60)) * 60_000;
const software = argv.includes("--sw");
const keep = argv.includes("--keep");
const port = 5299;
const base = process.env.VIEWER_URL ?? `http://localhost:${port}/`;

async function reachable() {
  try { return (await fetch(base)).ok; } catch { return false; }
}

let server = null;
if (!(await reachable())) {
  const env = exportDir ? { ...process.env, HBI_FILM_EXPORT: exportDir } : process.env;
  // Vite itself, not npx: killing npx at the end would leave Vite holding the port.
  server = spawn(process.execPath, [resolve(webRoot, "node_modules/vite/bin/vite.js"), "--port", String(port), "--strictPort"], { cwd: webRoot, stdio: "ignore", env });
  for (let i = 0; i < 60 && !(await reachable()); i++) await new Promise((r) => setTimeout(r, 500));
  if (!(await reachable())) { server.kill(); console.error("The dev server did not start."); process.exit(1); }
}

if (exportDir && !(await fetch(new URL(sceneUrl, base)).then((r) => r.ok, () => false))) {
  console.error(`${sceneUrl} does not answer: a server already on :${port} was started without HBI_FILM_EXPORT, or the shot is not in film/paths.json.`);
  server?.kill();
  process.exit(1);
}

const dir = set ? resolve(framesRoot, set) : framesRoot;
mkdirSync(dir, { recursive: true });
if (!keep) for (const f of readdirSync(dir)) if (/^\d{5}\.png$/.test(f)) rmSync(resolve(dir, f));

const args = software
  ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
  : ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"];
const browser = await chromium.launch({ args });
let failed = false;
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1, colorScheme: "light" });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  const qs = new URLSearchParams({ path: "film", dump: "1", w: String(width), h: String(height) });
  if (set) qs.set("set", set);
  if (sceneUrl) qs.set("scene", sceneUrl);
  if (ink) qs.set("ink", ink);
  if (from !== null) qs.set("from", from);
  if (frames !== null) qs.set("frames", frames);
  await page.goto(`${base}?${qs}`);
  const t0 = Date.now();
  let shown = -1;
  for (;;) {
    const s = await page.evaluate(() => {
      const d = document.documentElement.dataset;
      return { done: Number(d.filmDone ?? 0), total: Number(d.filmFrames ?? 0), complete: d.filmComplete === "1", error: d.filmError ?? null };
    });
    if (s.error) { console.error(`film mode failed: ${s.error}`); failed = true; break; }
    if (s.total > 0 && Math.floor((s.done / s.total) * 10) !== shown) {
      shown = Math.floor((s.done / s.total) * 10);
      console.log(`${s.done}/${s.total} frames`);
    }
    if (s.complete) { console.log(`done: ${s.done} frames, ${width}x${height}, in ${((Date.now() - t0) / 1000).toFixed(0)} s -> ${dir}`); break; }
    if (Date.now() - t0 > timeoutMs) { console.error("timed out"); failed = true; break; }
    await new Promise((r) => setTimeout(r, 500));
  }
  const renderer = await page.evaluate(() => {
    const gl = document.querySelector("canvas")?.getContext("webgl2");
    const ext = gl?.getExtension("WEBGL_debug_renderer_info");
    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : "unknown";
  }).catch(() => "unknown");
  console.log(`renderer: ${renderer}`);
  if (errors.length) { console.error("console errors:", errors); failed = true; }
} finally {
  await browser.close();
  server?.kill();
}
process.exit(failed ? 1 : 0);
