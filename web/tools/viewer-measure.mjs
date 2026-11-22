// Viewer measurements on the fixture: the five screenshots for docs/viewer/, frame time with and
// without the ink pass at DPR 2, and the splat counts. Real GPU (ANGLE's Metal backend, macOS).
// Needs the dev server on :5299 (npm run dev -- --port 5299).
// Usage: node tools/viewer-measure.mjs [shots|cost|all]
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, "../../docs/viewer");
const base = process.env.VIEWER_URL ?? "http://localhost:5299/";
const what = process.argv[2] ?? "all";
const gpu = ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"];
const results = {};

// The poses, in scene.json's convention: x, y, z, yaw (0 looks along -z, -90 along +x), pitch.
export const POSES = {
  room: null, // scene.json's start pose
  across: "1.7,1.6,0,-90,-38",
  back: "2.6,1.6,2.5,8,-12",
};

async function open(browser, qs, { dpr = 1, hideIntro = true } = {}) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: dpr, colorScheme: "light" });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${base}?${qs}`);
  await page.waitForSelector("html[data-ready='1']", { timeout: 120_000 });
  if (hideIntro) await page.evaluate(() => { document.querySelector(".intro").hidden = true; document.querySelector(".bar").hidden = false; });
  const f0 = await page.evaluate(() => window.__hbi.frame());
  await page.waitForFunction((f) => window.__hbi.frame() >= f + 20, f0);
  return { page, errors };
}

if (what === "shots" || what === "all") {
  mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ args: gpu });
  const shots = [
    ["01-room.png", ""],
    ["02-across.png", `pose=${POSES.across}`],
    ["03-ink-looking-back.png", `pose=${POSES.back}`],
    ["04-map.png", "map=1"],
    ["05-filter-looking-back.png", `pose=${POSES.back}&ink=off`],
  ];
  for (const [file, qs] of shots) {
    const { page, errors } = await open(browser, qs);
    await page.screenshot({ path: resolve(outDir, file) });
    if (errors.length) results[`errors ${file}`] = errors;
    await page.close();
  }
  const { page } = await open(browser, "", { hideIntro: false });
  await page.screenshot({ path: resolve(outDir, "00-first-screen.png") });
  results.renderer = await page.evaluate(() => {
    const gl = window.__hbi.viewer.renderer.getContext();
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : "unknown";
  });
  results.hud = await page.evaluate(() => window.__hbi.hud());
  await page.close();
  await browser.close();
}

if (what === "cost" || what === "all") {
  // Frame throughput with vsync and the frame-rate cap off, the camera turning 0.25° a frame so
  // Spark regenerates and re-sorts as it would while walking. The two states alternate in one
  // page (1.5 s each after a 0.3 s settle, eight cycles), as in spike S1, so thermal drift on a
  // fanless machine hits both alike; the cost is the median of the paired differences.
  const browser = await chromium.launch({ args: [...gpu, "--disable-gpu-vsync", "--disable-frame-rate-limit"] });
  const rows = {};
  for (const [label, qs, dpr] of [["dpr2 back", `pose=${POSES.back}`, 2], ["dpr2 across", `pose=${POSES.across}`, 2], ["dpr1 back", `pose=${POSES.back}`, 1]]) {
    const { page } = await open(browser, qs, { dpr });
    await page.evaluate(() => {
      const v = window.__hbi.viewer;
      const start = v.walk.pose().yaw;
      let n = 0;
      v.beforeFrame = () => { n++; v.walk.setPose({ position: v.walk.pose().position, yaw: start + Math.sin(n * 0.004) * 0.6, pitch: v.walk.pose().pitch }); };
    });
    const r = { off: [], on: [] };
    for (let c = 0; c < 8; c++) {
      for (const state of ["off", "on"]) {
        await page.evaluate((on) => { window.__hbi.viewer.inkPassesOn = on; }, state === "on");
        await page.waitForTimeout(300);
        const a = await page.evaluate(() => [window.__hbi.frame(), performance.now()]);
        await page.waitForTimeout(1500);
        const b = await page.evaluate(() => [window.__hbi.frame(), performance.now()]);
        r[state].push((b[1] - a[1]) / (b[0] - a[0]));
      }
      process.stderr.write(`${label} cycle ${c}\n`);
    }
    const med = (xs) => { const v = [...xs].sort((x, y) => x - y); return +(0.5 * (v[3] + v[4])).toFixed(2); };
    rows[label] = {
      shadeOnlyMs: med(r.off),
      withInkMs: med(r.on),
      inkPassCostMs: med(r.on.map((x, i) => x - r.off[i])),
      hud: await page.evaluate(() => { const h = window.__hbi.hud(); return { splatsRendered: h.splatsRendered, splatsLoaded: h.splatsLoaded, dataScale: h.dataScale, dataPassPx: h.dataPassPx, canvasPx: h.canvasPx, lod: h.lod }; }),
      dataPassSplats: await page.evaluate(() => window.__hbi.viewer.data.activeSplats),
    };
    await page.close();
  }
  results.cost = rows;
  await browser.close();
}

const json = JSON.stringify(results, null, 1);
console.log(json);
if (what === "all") writeFileSync(resolve(outDir, "numbers.json"), `${json}\n`);
