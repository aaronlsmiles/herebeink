import { type Page, test } from "@playwright/test";

/** A measured number: kept on the test's report and printed, so the list reporter shows it. */
export function note(type: string, description: string) {
  test.info().annotations.push({ type, description });
  console.log(`  [${type}] ${description}`);
}

/** Collects console errors and page errors; a test ends with `expect(errors).toEqual([])`. */
export function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

export async function openViewer(page: Page, qs: string) {
  await page.goto(`/?${qs}`);
  await page.waitForSelector("html[data-ready='1']", { timeout: 180_000 });
  // As "Walk in" does, minus the pointer lock: the intro goes, the control bar appears.
  await page.evaluate(() => (window as any).__hbi.chrome.hideIntro());
  await settle(page);
}

/**
 * Spark generates, sorts and refines its level of detail asynchronously, so wait a few frames after
 * any change, then until the sorts and the detail cut have stayed settled for a second with frames
 * drawn throughout (while the loop runs): a screenshot taken while the cut is still coarse differs everywhere from one
 * taken after it.
 */
export async function settle(page: Page, frames = 4) {
  // A quiet period left by an earlier call would let this one return on its first poll.
  await page.evaluate(() => { (window as any).__quiet = null; });
  const f0 = await page.evaluate(() => (window as any).__hbi.frame() as number);
  await page.waitForFunction((f) => (window as any).__hbi.frame() >= f, f0 + frames, { timeout: 180_000 });
  await page.waitForFunction(() => {
    const w = window as any;
    const frame = w.__hbi.frame() as number;
    if (!w.__hbi.viewer.settled) { w.__quiet = null; return false; }
    w.__quiet ??= { since: performance.now(), frame };
    // The flag is true for a moment between a detail cut landing and the next frame's generate asking
    // for another, so a quiet window only counts if frames were drawn inside it. A test that has
    // stopped the loop draws none, so for it the quiet second is all there is to wait for.
    const framesDrawn = frame - w.__quiet.frame >= 2 || !w.__hbi.viewer.running;
    return performance.now() - w.__quiet.since > 1000 && framesDrawn;
  }, undefined, { timeout: 180_000, polling: 100 });
}

export async function setParts(page: Page, parts: { outline?: boolean; hatch?: boolean; grain?: boolean }) {
  await page.evaluate((p) => (window as any).__hbi.setParts(p), parts);
  await settle(page, 2);
}

/** A screenshot as RGBA bytes, decoded in the page so the tooling needs no image library. */
export async function shot(page: Page): Promise<{ width: number; height: number; data: number[] }> {
  // The control bar's labels change with the switches; only the canvas is under test.
  const png = await page.screenshot({ style: ".bar { visibility: hidden !important; }" });
  return page.evaluate(async (b64) => {
    const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = c.getContext("2d")!;
    ctx.drawImage(bmp, 0, 0);
    const d = ctx.getImageData(0, 0, bmp.width, bmp.height);
    return { width: d.width, height: d.height, data: Array.from(d.data) };
  }, png.toString("base64"));
}

export type Region = "measured" | "imagined" | "other";

/**
 * Classifies every screenshot pixel by the flag target: measured where the coverage-weighted flag
 * is near 0 and no pixel within `margin` screenshot pixels is anything else; imagined where it is
 * near 1 (with the same margin). Lines are drawn on the imagined side of a boundary and spread a
 * pixel either way, so the margin keeps the test about regions, not about where a boundary falls.
 * With `pure`, measured means no imagined splat contributes at all (flag exactly 0): a pixel with a
 * few percent of imagined splats behind it is shaded differently by the ink and filter modes
 * whatever the ink pass does, so a comparison between those modes must leave such pixels out.
 */
export async function regions(page: Page, width: number, height: number, margin: number, pure = false): Promise<Region[]> {
  return page.evaluate(({ width, height, margin, pure }) => {
    const f = (window as any).__hbi.readFlag() as { width: number; height: number; rgba: number[] };
    const cls = new Uint8Array(width * height);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        // The target's rows run bottom-up.
        const fx = Math.min(f.width - 1, Math.floor((x / width) * f.width));
        const fy = Math.min(f.height - 1, Math.floor(((height - 1 - y) / height) * f.height));
        const i = (fy * f.width + fx) * 4;
        const a = f.rgba[i + 3];
        const v = a > 0 ? f.rgba[i] / a : 0;
        cls[y * width + x] = a < 200 ? 0 : (pure ? v === 0 : v < 0.05) ? 1 : v > 0.95 ? 2 : 0;
      }
    }
    const out: string[] = new Array(width * height);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const c = cls[y * width + x];
        let same = c !== 0;
        for (let dy = -margin; same && dy <= margin; dy++) {
          for (let dx = -margin; same && dx <= margin; dx++) {
            const xx = x + dx, yy = y + dy;
            if (xx < 0 || yy < 0 || xx >= width || yy >= height) continue;
            if (cls[yy * width + xx] !== c) same = false;
          }
        }
        out[y * width + x] = !same ? "other" : c === 1 ? "measured" : "imagined";
      }
    }
    return out;
  }, { width, height, margin, pure }) as Promise<Region[]>;
}

/**
 * Pixels that are measured by any reading: covered by at least half and weighted below half
 * towards the imagined files, so partly transparent measured surfaces with imagined splats behind
 * them count too. A pixel within `band` screenshot pixels of one that is not measured is left out;
 * the band exists only because the flag target and the screenshot meet at different resolutions
 * when devicePixelRatio is above 1, so at 1 it is 0 and every pixel is held to it.
 */
export async function measuredPixels(page: Page, width: number, height: number, band: number): Promise<boolean[]> {
  return page.evaluate(({ width, height, band }) => {
    const f = (window as any).__hbi.readFlag() as { width: number; height: number; rgba: number[] };
    const at = (x: number, y: number) => {
      const fx = Math.min(f.width - 1, Math.floor((x / width) * f.width));
      const fy = Math.min(f.height - 1, Math.floor(((height - 1 - y) / height) * f.height));
      const i = (fy * f.width + fx) * 4;
      const a = f.rgba[i + 3];
      return { covered: a >= 128, flag: a > 0 ? f.rgba[i] / a : 0, any: a > 0 };
    };
    const out: boolean[] = new Array(width * height);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const p = at(x, y);
        let ok = p.covered && p.flag < 0.5;
        for (let dy = -band; ok && dy <= band; dy++) {
          for (let dx = -band; ok && dx <= band; dx++) {
            const xx = x + dx, yy = y + dy;
            if (xx < 0 || yy < 0 || xx >= width || yy >= height) continue;
            const q = at(xx, yy);
            if (q.any && q.flag >= 0.5) ok = false;
          }
        }
        out[y * width + x] = ok;
      }
    }
    return out;
  }, { width, height, band });
}

/** The share of pixels that differ from the paper colour by at least `tol` (summed over the channels): how much of a frame is drawn at all. */
export function paintedShare(img: { data: number[] }, paperHex: string, tol = 24) {
  const [pr, pg, pb] = [1, 3, 5].map((i) => parseInt(paperHex.slice(i, i + 2), 16));
  let n = 0;
  const total = img.data.length / 4;
  for (let i = 0; i < total; i++) {
    if (Math.abs(img.data[i * 4] - pr) + Math.abs(img.data[i * 4 + 1] - pg) + Math.abs(img.data[i * 4 + 2] - pb) >= tol) n++;
  }
  return n / total;
}

export function diffCount(a: { data: number[] }, b: { data: number[] }, where: (i: number) => boolean, tol = 24) {
  let n = 0;
  for (let i = 0; i < a.data.length / 4; i++) {
    if (!where(i)) continue;
    const d = Math.abs(a.data[i * 4] - b.data[i * 4]) + Math.abs(a.data[i * 4 + 1] - b.data[i * 4 + 1]) + Math.abs(a.data[i * 4 + 2] - b.data[i * 4 + 2]);
    if (d >= tol) n++;
  }
  return n;
}

/**
 * Line width in device pixels from a screenshot of ink on paper (spike S1's method): ink summed
 * across the line horizontally (w_h) and vertically (w_v) at each crossing, w = 1/sqrt(1/w_h² + 1/w_v²),
 * which holds for a straight band at any angle. Returns the median over crossings.
 * Splat outlines break into dashes and dots where the splats are sparse, and a dash shorter than
 * its own width reads as a thin line by this formula; so only crossings whose run along one axis
 * is at least `minRun` device pixels count (lines at least that long, unless near 45°).
 */
export async function lineWidth(page: Page, paperHex: string, inkHex: string, minRun = 0) {
  const png = await page.screenshot();
  return page.evaluate(async ({ b64, paperHex, inkHex, minRun }) => {
    const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = c.getContext("2d")!;
    ctx.drawImage(bmp, 0, 0);
    const { data, width: W, height: H } = ctx.getImageData(0, 0, bmp.width, bmp.height);
    const hex = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    const P = hex(paperHex), K = hex(inkHex);
    const f = new Float32Array(W * H);
    for (let i = 0; i < W * H; i++) {
      let t = 0;
      for (let k = 0; k < 3; k++) t += (P[k] - data[i * 4 + k]) / (P[k] - K[k]);
      f[i] = Math.min(1, Math.max(0, t / 3));
    }
    const on = (x: number, y: number) => x >= 0 && y >= 0 && x < W && y < H && f[y * W + x] > 0.04;
    const samples: number[] = [];
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
        if (x1 - x < 60 && y1 - y0 < 60 && wh > 0.3 && wv > 0.3 && Math.max(wh, wv) >= minRun) samples.push(1 / Math.sqrt(1 / (wh * wh) + 1 / (wv * wv)));
        x = x1;
      }
    }
    samples.sort((a, b) => a - b);
    const q = (p: number) => samples[Math.round(p * (samples.length - 1))];
    return { n: samples.length, median: q(0.5), p25: q(0.25), p75: q(0.75) };
  }, { b64: png.toString("base64"), paperHex, inkHex, minRun });
}

/** Total ink in a screenshot of ink on paper, in device pixels' worth of full ink. */
export async function inkArea(page: Page, paperHex: string, inkHex: string) {
  const png = await page.screenshot({ style: ".bar { visibility: hidden !important; }" });
  return page.evaluate(async ({ b64, paperHex, inkHex }) => {
    const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = c.getContext("2d")!;
    ctx.drawImage(bmp, 0, 0);
    const { data } = ctx.getImageData(0, 0, bmp.width, bmp.height);
    const hex = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    const P = hex(paperHex), K = hex(inkHex);
    let sum = 0;
    for (let i = 0; i < data.length; i += 4) {
      let t = 0;
      for (let k = 0; k < 3; k++) t += (P[k] - data[i + k]) / (P[k] - K[k]);
      sum += Math.min(1, Math.max(0, t / 3));
    }
    return sum;
  }, { b64: png.toString("base64"), paperHex, inkHex });
}

/**
 * Where thin lines sit between pixels. For every short run of ink in a row or column of a
 * screenshot of ink on paper, the fractional part of the run's ink-weighted centre goes into one of
 * `bins` bins. A line placed on the pixel grid has its centre at the same few phases everywhere, so
 * one bin takes most runs; a line placed to a fraction of a pixel spreads them across all of them.
 * Returns the runs counted and the largest bin's share.
 */
export async function centrePhases(page: Page, paperHex: string, inkHex: string, bins = 10) {
  const png = await page.screenshot({ style: ".bar { visibility: hidden !important; }" });
  return page.evaluate(async ({ b64, paperHex, inkHex, bins }) => {
    const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = c.getContext("2d")!;
    ctx.drawImage(bmp, 0, 0);
    const { data, width: W, height: H } = ctx.getImageData(0, 0, bmp.width, bmp.height);
    const hex = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    const P = hex(paperHex), K = hex(inkHex);
    const f = new Float32Array(W * H);
    for (let i = 0; i < W * H; i++) {
      let t = 0;
      for (let k = 0; k < 3; k++) t += (P[k] - data[i * 4 + k]) / (P[k] - K[k]);
      f[i] = Math.min(1, Math.max(0, t / 3));
    }
    const counts = new Array(bins).fill(0);
    let n = 0;
    const scan = (len: number, lines: number, at: (line: number, i: number) => number) => {
      for (let line = 0; line < lines; line++) {
        let i = 0;
        while (i < len) {
          if (at(line, i) <= 0.04) { i++; continue; }
          let j = i, sum = 0, moment = 0;
          while (j < len && at(line, j) > 0.04) { sum += at(line, j); moment += j * at(line, j); j++; }
          // Short runs across a line; long ones run along it, where the centre means nothing.
          if (j - i >= 2 && j - i <= 10 && sum >= 1.2 && sum <= 12) {
            const phase = (moment / sum) % 1;
            counts[Math.min(bins - 1, Math.floor(phase * bins))]++;
            n++;
          }
          i = j;
        }
      }
    };
    scan(W, H, (y, x) => f[y * W + x]);
    scan(H, W, (x, y) => f[y * W + x]);
    return { n, maxShare: Math.max(...counts) / Math.max(1, n), counts };
  }, { b64: png.toString("base64"), paperHex, inkHex, bins });
}
