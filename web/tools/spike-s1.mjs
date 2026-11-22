// Spike S1 measurements: screenshots, outline width, silhouette softness and pass cost.
// Needs the dev server on :5299 (npm run dev -- --port 5299) and the sample splat.
// Usage: node tools/spike-s1.mjs [shots|width|soft|cost|all] [--sw]
// By default Chromium runs headless on the real GPU through ANGLE's Metal backend (macOS);
// --sw falls back to SwiftShader, whose numbers say nothing about real cost.
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const shotsDir = resolve(here, "../../docs/spike-s1");
const base = process.env.SPIKE_URL ?? "http://localhost:5299/spike.html";
const what = process.argv[2] ?? "all";
const sw = process.argv.includes("--sw");
const args = sw
  ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
  : ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"];

const browser = await chromium.launch({ args });
const results = {};

async function open(qs, dpr = 1) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: dpr, colorScheme: "light" });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${base}?${qs}`);
  await page.waitForSelector("html[data-ready='1']", { timeout: 90_000 });
  const f0 = await page.evaluate(() => window.__spike.frame());
  await page.waitForFunction((f) => window.__spike.frame() >= f + 10, f0);
  return { page, errors };
}

async function rendererName(page) {
  return page.evaluate(() => {
    const gl = window.__spike.renderer.getContext();
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : "unknown";
  });
}

// Ink summed across the line: horizontal and vertical crossings of a straight band of width w
// at any angle satisfy 1/w² = 1/w_h² + 1/w_v².
async function lineWidth(page, png, paperHex, inkHex) {
  return page.evaluate(async ({ b64, paperHex, inkHex }) => {
    const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = c.getContext("2d");
    ctx.drawImage(bmp, 0, 0);
    const { data, width: W, height: H } = ctx.getImageData(0, 0, bmp.width, bmp.height);
    const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    const P = hex(paperHex), K = hex(inkHex);
    const f = new Float32Array(W * H);
    for (let i = 0; i < W * H; i++) {
      let t = 0;
      for (let k = 0; k < 3; k++) t += (P[k] - data[i * 4 + k]) / (P[k] - K[k]);
      f[i] = Math.min(1, Math.max(0, t / 3));
    }
    const on = (x, y) => x >= 0 && y >= 0 && x < W && y < H && f[y * W + x] > 0.04;
    const samples = [];
    for (let y = 2; y < H - 2; y += 3) {
      let x = 0;
      while (x < W) {
        if (!on(x, y)) { x++; continue; }
        let x1 = x, wh = 0, mx = 0;
        while (on(x1, y)) { wh += f[y * W + x1]; mx += x1 * f[y * W + x1]; x1++; }
        const xc = Math.round(mx / wh);
        let y0 = y, wv = 0;
        while (on(xc, y0 - 1)) y0--;
        let y1 = y0;
        while (on(xc, y1)) { wv += f[y1 * W + xc]; y1++; }
        if (x1 - x < 60 && y1 - y0 < 60 && wh > 0.3 && wv > 0.3) samples.push(1 / Math.sqrt(1 / (wh * wh) + 1 / (wv * wv)));
        x = x1;
      }
    }
    samples.sort((a, b) => a - b);
    const q = (p) => samples[Math.round(p * (samples.length - 1))];
    return { n: samples.length, median: q(0.5), p25: q(0.25), p75: q(0.75) };
  }, { b64: png.toString("base64"), paperHex, inkHex });
}

const PAPER = "#f4efe4", INK = "#1c1a17";
const POSE = "angle=40&elev=20";

if (what === "shots" || what === "all") {
  mkdirSync(shotsDir, { recursive: true });
  for (const v of ["final", "shade", "depth", "normal", "flag", "edges"]) {
    const { page, errors } = await open(`pass=${v}&${POSE}`);
    await page.screenshot({ path: resolve(shotsDir, `${v}.png`) });
    if (errors.length) results[`errors_${v}`] = errors;
    await page.close();
  }
  for (const a of [10, 45, 80]) {
    const { page } = await open(`pass=final&angle=${a}&elev=20`);
    await page.screenshot({ path: resolve(shotsDir, `orbit-${a}.png`) });
    await page.close();
  }
  // √8 against √4 at the same pose, the shade pass beside the edges it yields, cropped to the wing.
  const crops = {};
  for (const sd of ["8", "4"]) {
    for (const v of ["shade", "edges"]) {
      const { page } = await open(`pass=${v}&stddev=${sd}&angle=40&elev=20&dist=1.6`);
      crops[`${v}${sd}`] = (await page.screenshot({ clip: { x: 520, y: 150, width: 400, height: 600 } })).toString("base64");
      await page.close();
    }
  }
  const { page } = await open(`pass=shade`);
  const sideBySide = await page.evaluate(async (crops) => {
    const order = ["shade8", "shade4", "edges8", "edges4"];
    const bmps = await Promise.all(order.map(async (k) => createImageBitmap(await (await fetch(`data:image/png;base64,${crops[k]}`)).blob())));
    const c = new OffscreenCanvas(1600 + 30, 600);
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#f4efe4";
    ctx.fillRect(0, 0, c.width, c.height);
    bmps.forEach((b, i) => ctx.drawImage(b, i * 410, 0));
    ctx.fillStyle = "#1c1a17";
    ctx.font = "16px ui-monospace, monospace";
    ["shade √8", "shade √4", "edges √8", "edges √4"].forEach((t, i) => ctx.fillText(t, i * 410 + 12, 24));
    const blob = await c.convertToBlob({ type: "image/png" });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(s);
  }, crops);
  writeFileSync(resolve(shotsDir, "stddev-8-vs-4.png"), Buffer.from(sideBySide, "base64"));
  await page.close();
}

if (what === "width" || what === "all") {
  const rows = [];
  const cases = [];
  for (const dpr of [1, 2]) for (const dist of [2, 4]) cases.push({ dpr, qs: `pass=edges&coast=0&${POSE}&dist=${dist}`, label: `dpr${dpr} dist${dist}` });
  for (const a of [10, 45, 80]) cases.push({ dpr: 1, qs: `pass=edges&coast=0&angle=${a}&elev=20`, label: `dpr1 orbit ${a}°` });
  for (const dist of [2, 4]) cases.push({ dpr: 2, qs: `pass=edges&coast=0&${POSE}&dist=${dist}&gscale=0.5`, label: `dpr2 dist${dist} data at half resolution` });
  for (const c of cases) {
    const { page } = await open(c.qs, c.dpr);
    const png = await page.screenshot();
    const w = await lineWidth(page, png, PAPER, INK);
    rows.push({ case: c.label, cssPx: +(w.median / c.dpr).toFixed(2), devicePx: +w.median.toFixed(2), iqrDevice: [+w.p25.toFixed(2), +w.p75.toFixed(2)], samples: w.n });
    await page.close();
  }
  // The coastline should read 3 CSS px; measured in the flag-coloured debug view would mix colours,
  // so measure the edges view with the coastline on and only near the plane.
  results.width = rows;
}

if (what === "soft" || what === "all") {
  const rows = [];
  for (const sd of ["8", "4"]) for (const dist of [1.6, 3]) {
    const { page } = await open(`pass=edges&stddev=${sd}&${POSE}&dist=${dist}`);
    rows.push({ stddev: `√${sd}`, dist, ...(await page.evaluate(() => window.__spike.coverageRamp())) });
    await page.close();
  }
  results.softness = rows;
}

if (what === "cost" || what === "all") {
  const rows = [];
  const med = (xs) => { const s = [...xs].sort((a, b) => a - b); return +s[s.length >> 1].toFixed(3); };
  // Primary clock: batches of back-to-back passes between forced syncs (window.__spike.bench).
  for (const dpr of process.env.SKIP_BENCH ? [] : [1, 2, 3]) {
    for (const dilate of ["sep", "brute"]) {
      const { page } = await open(`pass=final&dilate=${dilate}`, dpr);
      if (!results.gpu) results.gpu = await rendererName(page);
      const runs = [];
      for (let k = 0; k < 7; k++) runs.push(await page.evaluate(() => window.__spike.bench(40)));
      const row = { dpr, dilate };
      for (const p of ["empty", "shade", "gbuf", "flag", "post"]) row[p] = med(runs.map((r) => r[p]));
      row.secondPass = +(row.gbuf + row.flag + row.post).toFixed(3);
      rows.push(row);
      await page.close();
    }
  }
  results.bench = rows;
  // Frame throughput with vsync and the frame-rate cap off, the states interleaved in one page
  // (1.5 s each, eight cycles) so thermal drift on a fanless machine hits every state alike.
  // Mean frame time is window length over frames drawn: what a frame actually pays, pipeline
  // stalls included, which the isolated batches above cannot see.
  const fast = await chromium.launch({ args: [...args, "--disable-gpu-vsync", "--disable-frame-rate-limit"] });
  const tp = {};
  const tpCases = [];
  for (const dpr of [1, 2, 3]) for (const dilate of ["sep", "brute"]) tpCases.push({ dpr, dilate, gscale: 1 });
  tpCases.push({ dpr: 2, dilate: "sep", gscale: 0.5 }, { dpr: 3, dilate: "sep", gscale: 0.5 }, { dpr: 3, dilate: "sep", gscale: 1 / 3 });
  for (const { dpr, dilate, gscale } of tpCases.filter((c) => !process.env.TP_ONLY_SCALED || c.gscale < 1)) {
    {
      const page = await fast.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: dpr, colorScheme: "light" });
      await page.goto(`${base}?pass=final&orbit=1&dilate=${dilate}&gscale=${gscale}`);
      await page.waitForSelector("html[data-ready='1']", { timeout: 90_000 });
      await page.waitForTimeout(1500);
      const states = { off: [false, false], splats: [true, false], full: [true, true] };
      const r = { off: [], splats: [], full: [] };
      for (let c = 0; c < 8; c++) {
        for (const [name, [passes, post]] of Object.entries(states)) {
          await page.evaluate(([a, b]) => { window.__spike.setPasses(a); window.__spike.setPost(b); }, [passes, post]);
          await page.waitForTimeout(300);
          const a = await page.evaluate(() => [window.__spike.frame(), performance.now()]);
          await page.waitForTimeout(1500);
          const b = await page.evaluate(() => [window.__spike.frame(), performance.now()]);
          r[name].push((b[1] - a[1]) / (b[0] - a[0]));
        }
        process.stderr.write(`dpr${dpr} ${dilate} gscale ${gscale.toFixed(2)} cycle ${c}\n`);
      }
      const med = (xs) => { const v = [...xs].sort((a, b) => a - b); return +(0.5 * (v[3] + v[4])).toFixed(2); };
      const pairs = (a, b) => med(r[a].map((x, i) => x - r[b][i]));
      tp[`dpr${dpr} ${dilate}${gscale < 1 ? ` data ×${gscale.toFixed(2)}` : ""}`] = {
        offMs: med(r.off), splatsMs: med(r.splats), fullMs: med(r.full),
        splatPassesCost: pairs("splats", "off"), postCost: pairs("full", "splats"), secondPassCost: pairs("full", "off"),
      };
      await page.close();
    }
  }
  await fast.close();
  results.throughput = tp;
}

console.log(JSON.stringify(results, null, 1));
await browser.close();
