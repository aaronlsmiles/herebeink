import { expect, test } from "@playwright/test";
import { centrePhases, diffCount, inkArea, measuredPixels, note, lineWidth, openViewer, regions, setParts, settle, shot, watchErrors } from "./helpers.ts";

// SwiftShader draws every splat pass on the CPU: small canvases keep these runs to minutes.
test.use({ viewport: { width: 720, height: 450 }, colorScheme: "light" });
// The DPR 3 page and the ink-switch test took 4.6 and 4.7 minutes of the old five on a loaded machine:
// settle() now waits for drawn frames, and a software-rendered frame at DPR 3 takes seconds.
test.describe.configure({ timeout: 600_000 });

const PAPER = "#f4efe4", INK = "#1c1a17";
// In the room, looking through the doorway at the imagined hallway: both halves in view.
const ACROSS = "pose=1.0,1.6,0,-90,-10";
// Standing short of the doorway, looking down at where the measured floor ends.
const FLOOR_LINE = "pose=1.7,1.6,0,-90,-38";
// A 4G profile: 9 Mbit/s down, 1.5 Mbit/s up, 85 ms round trip.
const FOUR_G = { offline: false, latency: 85, downloadThroughput: (9e6 / 8), uploadThroughput: (1.5e6 / 8) };

test("loads the fixture, shows the first splats quickly on 4G, and keeps the console clean", async ({ page }) => {
  const errors = watchErrors(page);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", FOUR_G);
  await page.goto("/");
  await page.waitForFunction(() => document.documentElement.dataset.firstSplats !== undefined, undefined, { timeout: 120_000 });
  const t = await page.evaluate(() => {
    const preview = performance.getEntriesByType("resource").find((e) => e.name.endsWith("/measured-preview.spz")) as PerformanceResourceTiming;
    return {
      fetch: Number(document.documentElement.dataset.sceneFetch),
      previewIn: preview.responseEnd,
      first: Number(document.documentElement.dataset.firstSplats),
    };
  });
  // Network: scene.json, then the preview beside coastline.json. Then decoding and a frame, which
  // SwiftShader draws on the CPU, so the end-to-end bound here is looser than the 2 s criterion;
  // tools/viewer-measure.mjs times the same thing on the real GPU. The JS bundle is left out:
  // the dev server serves it unbundled.
  const network = t.previewIn - t.fetch;
  const toSplats = t.first - t.fetch;
  note("first splats", `preview in ${network.toFixed(0)} ms, splats on screen ${toSplats.toFixed(0)} ms after the scene request (SwiftShader, 4G profile)`);
  expect(network).toBeLessThan(1000);
  expect(toSplats).toBeLessThan(4000);

  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await page.waitForSelector("html[data-ready='1']", { timeout: 180_000 });
  await expect(page.locator(".intro h1")).toHaveText("Here Be Ink");
  await expect(page.locator(".intro .statement")).toContainText("The pen line on the floor is where one ends and the other begins.");
  await expect(page.locator(".intro .credit")).toHaveText("The imagined half was generated with Marble by World Labs, through its World API.");
  await expect(page.locator(".intro .device")).toContainText("Android phones are not supported yet");
  const hud = await page.evaluate(() => (window as any).__hbi.hud());
  expect(hud.splatsLoaded).toBe(185121 + 5779 + 22426);
  expect(errors).toEqual([]);
});

// The spike's crossing method reads a clean contour well; the fixture's outlines break into
// dashes where its splats are sparse, which biases that estimate low as the dashes get more
// device pixels. So: the crossing width at DPR 1, and at DPR 2 and 3 the ink area per CSS pixel
// against DPR 1's at the same pose. Lines drawn at a fixed device width would give area ∝ DPR;
// lines at a fixed CSS width give area ∝ DPR², so the ratio is 1.
test("outlines measure 2 CSS px at devicePixelRatio 1, 2 and 3", async ({ browser }) => {
  const rows: { dpr: number; crossingCss: number; crossings: number; areaPerCss2: number }[] = [];
  for (const dpr of [1, 2, 3]) {
    const page = await browser.newPage({ viewport: { width: 720, height: 450 }, deviceScaleFactor: dpr, colorScheme: "light" });
    const errors = watchErrors(page);
    await openViewer(page, `${ACROSS}&debug=edges&coast=off`);
    const w = await lineWidth(page, PAPER, INK, 3 * 2 * dpr);
    const area = await inkArea(page, PAPER, INK);
    rows.push({ dpr, crossingCss: w.median / dpr, crossings: w.n, areaPerCss2: area / (dpr * dpr) });
    expect(errors).toEqual([]);
    await page.close();
  }
  for (const r of rows) {
    note(`dpr ${r.dpr}`, `crossing median ${r.crossingCss.toFixed(2)} CSS px (${r.crossings} crossings); ink ${r.areaPerCss2.toFixed(0)} per CSS px² (${(r.areaPerCss2 / rows[0].areaPerCss2).toFixed(3)} of DPR 1)`);
  }
  expect(rows[0].crossings).toBeGreaterThan(20);
  expect(rows[0].crossingCss).toBeGreaterThan(1.6);
  expect(rows[0].crossingCss).toBeLessThan(2.4);
  expect(rows[0].areaPerCss2).toBeGreaterThan(200);
  for (const r of rows.slice(1)) expect(Math.abs(r.areaPerCss2 / rows[0].areaPerCss2 - 1)).toBeLessThan(0.03);
});

// Up close a pen line must not stair-step. A line drawn on the pixel grid puts its ink centre at one
// or two fixed sub-pixel positions (six runs in ten at one of ten phases, measured); a line placed to
// a fraction of a pixel spreads them. The room's far wall has long near-straight outlines.
for (const dpr of [1, 2]) {
  test(`outline edges are anti-aliased at devicePixelRatio ${dpr}: line centres fall at every sub-pixel phase`, async ({ browser }) => {
    const page = await browser.newPage({ viewport: { width: 720, height: 450 }, deviceScaleFactor: dpr, colorScheme: "light" });
    const errors = watchErrors(page);
    await openViewer(page, `${FLOOR_LINE}&debug=edges&coast=off`);
    const r = await centrePhases(page, PAPER, INK);
    note(`phases dpr ${dpr}`, `${r.n} runs, largest of ten phase bins ${(r.maxShare * 100).toFixed(1)} %`);
    expect(r.n).toBeGreaterThan(150);
    expect(r.maxShare).toBeLessThan(0.3);
    expect(errors).toEqual([]);
    await page.close();
  });
}

test("outlines fall on the imagined region and never on the measured one", async ({ page }) => {
  const errors = watchErrors(page);
  await openViewer(page, `${ACROSS}&coast=off`);
  await setParts(page, { hatch: false, grain: false, outline: true });
  const withLines = await shot(page);
  await setParts(page, { outline: false });
  const without = await shot(page);
  const reg = await regions(page, withLines.width, withLines.height, 4);
  const measured = await measuredPixels(page, withLines.width, withLines.height, 0);
  const onImagined = diffCount(withLines, without, (i) => reg[i] === "imagined");
  const onMeasured = diffCount(withLines, without, (i) => measured[i], 1);
  const measuredPx = measured.filter(Boolean).length;
  const imaginedPx = reg.filter((r) => r === "imagined").length;
  note("outline pixels", `imagined ${onImagined} of ${imaginedPx}, measured ${onMeasured} of ${measuredPx}`);
  expect(measuredPx).toBeGreaterThan(10_000);
  expect(imaginedPx).toBeGreaterThan(10_000);
  expect(onImagined).toBeGreaterThan(100);
  expect(onMeasured).toBe(0);
  expect(errors).toEqual([]);
});

test("with outlines, hatching and grain all on, no measured pixel differs from the same frame without them", async ({ page }) => {
  const errors = watchErrors(page);
  await openViewer(page, `${ACROSS}&coast=off`);
  const inked = await shot(page);
  await setParts(page, { outline: false, hatch: false, grain: false });
  const plain = await shot(page);
  const measured = await measuredPixels(page, inked.width, inked.height, 0);
  const measuredPx = measured.filter(Boolean).length;
  // Any difference at all: grain is four percent of the ink, well under diffCount's default step.
  const bled = diffCount(inked, plain, (i) => measured[i], 1);
  const onImagined = diffCount(inked, plain, (i) => !measured[i], 24);
  note("ink on measured pixels", `${bled} of ${measuredPx} measured pixels differ with hatching, grain and outlines on; ${onImagined} others do`);
  expect(measuredPx).toBeGreaterThan(10_000);
  expect(onImagined).toBeGreaterThan(1000);
  expect(bled).toBe(0);
  expect(errors).toEqual([]);
});

// The flag target is half the canvas's resolution here and the ink is stretched up from it, so this
// is where a value pulled across a border by bilinear filtering would show.
test("on a retina screen too, no measured pixel differs from the frame without hatching, grain and outlines", async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 360, height: 225 }, deviceScaleFactor: 2, colorScheme: "light" });
  const errors = watchErrors(page);
  await openViewer(page, `${ACROSS}&coast=off`);
  const inked = await shot(page);
  await setParts(page, { outline: false, hatch: false, grain: false });
  const plain = await shot(page);
  const measured = await measuredPixels(page, inked.width, inked.height, 0);
  const measuredPx = measured.filter(Boolean).length;
  const bled = diffCount(inked, plain, (i) => measured[i], 1);
  const onOthers = diffCount(inked, plain, (i) => !measured[i], 24);
  note("ink on measured pixels, dpr 2", `${bled} of ${measuredPx} measured pixels differ; ${onOthers} others do`);
  expect(inked.width).toBe(720);
  expect(measuredPx).toBeGreaterThan(10_000);
  expect(onOthers).toBeGreaterThan(500);
  expect(bled).toBe(0);
  expect(errors).toEqual([]);
  await page.close();
});

test("the ink switch and ?ink=off draw no outlines or hatching and leave the measured half's pixels unchanged", async ({ page }) => {
  const errors = watchErrors(page);
  await openViewer(page, ACROSS);
  const ink = await shot(page);
  const reg = await regions(page, ink.width, ink.height, 4, true);

  // The switch, as a visitor uses it; it also writes ?ink=off into the address.
  await page.locator("[data-control='ink']").click({ force: true });
  await settle(page);
  await expect(page.locator("[data-control='ink']")).toHaveText("Imagined half: filter");
  expect(new URL(page.url()).searchParams.get("ink")).toBe("off");
  const off = await shot(page);
  // Under ?ink=off the ink parts are forced off: switching them off again changes nothing.
  await setParts(page, { outline: false, hatch: false, grain: false });
  expect(diffCount(off, await shot(page), () => true)).toBe(0);

  const measuredChanged = diffCount(ink, off, (i) => reg[i] === "measured");
  const imaginedChanged = diffCount(ink, off, (i) => reg[i] === "imagined");
  note("ink vs filter", `measured pixels changed ${measuredChanged}, imagined pixels changed ${imaginedChanged}`);
  expect(measuredChanged).toBe(0);
  expect(imaginedChanged).toBeGreaterThan(1000);

  // A fresh load with ?ink=off draws the same frame as the switch did.
  await openViewer(page, `${ACROSS}&ink=off`);
  await expect(page.locator("[data-control='ink']")).toHaveText("Imagined half: filter");
  expect(diffCount(off, await shot(page), () => true)).toBe(0);
  expect(errors).toEqual([]);
});

test("?coast=off hides the floor line, the screen-space coastline and the pen-line sentence", async ({ page }) => {
  const errors = watchErrors(page);
  await openViewer(page, `${FLOOR_LINE}&coast=off`);
  await expect(page.locator(".pen-line-sentence")).toHaveCount(0);
  await expect(page.locator(".intro .statement")).not.toContainText("pen line");
  await expect(page.locator(".intro .statement")).toContainText("The drawing is what the model made up beyond it.");
  await setParts(page, { outline: false, hatch: false, grain: false });
  const state = await page.evaluate(() => {
    const v = (window as any).__hbi.viewer;
    return { floor: v.coast.floor.visible, map: v.coast.map.visible };
  });
  expect(state).toEqual({ floor: false, map: false });
  const hidden = await shot(page);
  await page.evaluate(() => (window as any).__hbi.viewer.setCoast(true));
  await settle(page);
  const shown = await shot(page);
  const linePixels = diffCount(hidden, shown, () => true);
  note("coastline pixels", `${linePixels} pixels drawn when the coastlines come back`);
  expect(linePixels).toBeGreaterThan(200);
  await page.evaluate(() => (window as any).__hbi.viewer.setCoast(false));
  await settle(page);
  expect(diffCount(hidden, await shot(page), () => true)).toBe(0);
  expect(errors).toEqual([]);
});

test("the map opens and closes with M and with its button", async ({ page }) => {
  const errors = watchErrors(page);
  await openViewer(page, "");
  const walkView = await shot(page);
  await page.locator("body").press("KeyM");
  await settle(page);
  await expect(page.locator(".map")).toBeVisible();
  await expect(page.locator(".map-legend")).toContainText("15 cm");
  await expect(page.locator(".map-legend")).toContainText("50 cm");
  await expect(page.locator("[data-control='map']")).toHaveAttribute("aria-pressed", "true");
  const mapView = await shot(page);
  expect(diffCount(walkView, mapView, () => true)).toBeGreaterThan(50_000);
  await page.locator("[data-control='map']").click({ force: true });
  await settle(page);
  await expect(page.locator(".map")).toBeHidden();
  await expect(page.locator("[data-control='map']")).toHaveAttribute("aria-pressed", "false");
  expect(errors).toEqual([]);
});

test("a broken scene.json gets a readable message, not a blank page", async ({ page }) => {
  // Matched on the path alone: a glob would also catch the page URL, whose query names the file.
  await page.route((url) => url.pathname === "/broken/scene.json", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ schemaVersion: 1 }) }));
  await page.goto("/?scene=/broken/scene.json");
  await expect(page.locator("html[data-fatal='1']")).toHaveCount(1);
  await expect(page.locator(".intro.fatal")).toContainText("The world did not arrive");
  await expect(page.locator(".intro.fatal")).toContainText("splats: missing");
});
