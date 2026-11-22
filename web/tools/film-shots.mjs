// Page shots for the film: the parts of the page a frame dump cannot hold (the first screen, the map
// with its key), and quick looks at a pose while choosing a camera path. Chromium on the real GPU.
// Usage:
//   node tools/film-shots.mjs --export pipeline/work/export/v2 [--edl ../film/edl.json] [--only a,b] [--aspect 16x9|9x16]
//   node tools/film-shots.mjs --export pipeline/work/export/v2 --pose x,y,z,yaw,pitch [--query ink=off] [--name look] [--w 1280 --h 720]
// Shots from the edit list go to film/frames/stills/<aspect>/<name>.png; a --pose look to film/frames/looks/<name>.png.
// Like film-dump.mjs it starts the dev server on :5299 if nothing answers there.
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");
const repoRoot = resolve(webRoot, "..");
const framesRoot = resolve(repoRoot, "film/frames");

const argv = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : fallback;
};
const exportDir = opt("export", null);
const aspect = opt("aspect", "16x9");
const port = 5299;
const base = process.env.VIEWER_URL ?? `http://localhost:${port}/`;
const sceneUrl = exportDir ? "/film-scene/scene.json" : opt("scene", null);

async function ok(url) {
  try { return (await fetch(url)).ok; } catch { return false; }
}

let server = null;
if (!(await ok(base))) {
  const env = exportDir ? { ...process.env, HBI_FILM_EXPORT: exportDir } : process.env;
  // Vite itself, not npx: killing npx at the end would leave Vite holding the port.
  server = spawn(process.execPath, [resolve(webRoot, "node_modules/vite/bin/vite.js"), "--port", String(port), "--strictPort"], { cwd: webRoot, stdio: "ignore", env });
  for (let i = 0; i < 60 && !(await ok(base)); i++) await new Promise((r) => setTimeout(r, 500));
  if (!(await ok(base))) { server.kill(); console.error("The dev server did not start."); process.exit(1); }
}
if (sceneUrl && !(await ok(new URL(sceneUrl, base)))) {
  console.error(`${sceneUrl} does not answer: a server already on :${port} was started without HBI_FILM_EXPORT.`);
  server?.kill();
  process.exit(1);
}

let shots;
if (opt("pose", null)) {
  const [w, h] = [Number(opt("w", 1280)), Number(opt("h", 720))];
  shots = [{ name: opt("name", "look"), pose: opt("pose"), query: opt("query", ""), intro: false, w, h, dir: resolve(framesRoot, "looks") }];
} else {
  const edl = JSON.parse(readFileSync(resolve(webRoot, opt("edl", "../film/edl.json")), "utf8"));
  const only = opt("only", null)?.split(",");
  const { page: size, scale } = edl.aspects[aspect];
  shots = Object.entries(edl.shots)
    .filter(([name]) => !only || only.includes(name))
    .map(([name, s]) => ({ name, ...s, w: size[0], h: size[1], scale, dir: resolve(framesRoot, "stills", aspect) }));
}

const browser = await chromium.launch({ args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] });
let failed = false;
try {
  for (const s of shots) {
    mkdirSync(s.dir, { recursive: true });
    const page = await browser.newPage({ viewport: { width: s.w, height: s.h }, deviceScaleFactor: s.scale ?? 1, colorScheme: "light" });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    const qs = new URLSearchParams(s.query ?? "");
    if (sceneUrl) qs.set("scene", s.walk ? `${sceneUrl}?shot=${encodeURIComponent(s.walk.shot)}` : sceneUrl);
    if (s.pose) qs.set("pose", s.pose);
    await page.goto(`${base}?${qs}`);
    await page.waitForFunction(() => document.documentElement.dataset.ready === "1", null, { timeout: 180_000 });
    // The page keeps drawing; this gives the sort and the level-of-detail cut time to settle on the pose.
    await page.waitForTimeout(s.settleMs ?? 2500);
    if (s.intro === false) {
      await page.evaluate(() => {
        const hbi = window.__hbi;
        hbi.chrome.hideIntro();
        if (!hbi.params.map) hbi.chrome.bar.hidden = true;
      });
      await page.waitForTimeout(600);
    }
    if (s.walk) {
      // The visitor's dot follows a shot's camera path across the map, one page shot per film frame.
      const seqDir = resolve(s.dir, s.name);
      rmSync(seqDir, { recursive: true, force: true });
      mkdirSync(seqDir, { recursive: true });
      await page.evaluate(async () => {
        const { FilmPath } = await import("/src/film.ts");
        window.__filmPath = new FilmPath(window.__hbi.viewer.sceneContract.filmPath);
      });
      const { from, to, every } = s.walk;
      let k = 0;
      for (let n = from; n < to; n += every, k++) {
        await page.evaluate(async (frame) => {
          const p = window.__filmPath.frame(frame);
          window.__hbi.viewer.walk.setPose({ position: { x: p.position[0], y: p.position[1], z: p.position[2] }, yaw: p.yaw, pitch: p.pitch });
          for (let i = 0; i < 2; i++) await new Promise((r) => requestAnimationFrame(r));
        }, n);
        await page.screenshot({ path: resolve(seqDir, `${String(k).padStart(5, "0")}.png`) });
      }
      console.log(`${s.name} -> ${seqDir} (${k} frames)`);
    } else {
      const file = resolve(s.dir, `${s.name}.png`);
      await page.screenshot({ path: file });
      console.log(`${s.name} -> ${file}`);
    }
    if (errors.length) { console.error(`${s.name}: console errors`, errors); failed = true; }
    await page.close();
  }
} finally {
  await browser.close();
  server?.kill();
}
process.exit(failed ? 1 : 0);
