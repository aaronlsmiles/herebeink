// Ladder mode (Part 2) on the synthetic ladder fixture: opt-in, one rung in memory at a time, coverage numbers only,
// the red pen as colour, and the walk left as it was. Screenshots for the record land in docs/viewer/.
import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { settle, watchErrors } from "./helpers.ts";

test.describe.configure({ timeout: 300_000 });

const DOCS = resolve(import.meta.dirname, "../../docs/viewer");

async function openLadder(page: Page, qs: string) {
  await page.goto(`/?${qs}`);
  await page.waitForFunction(() => document.documentElement.dataset.ladderReady !== undefined, undefined, { timeout: 180_000 });
  await settle(page);
}

async function stepTo(page: Page, id: string, how: "step" | "chart" = "step") {
  if (how === "step") await page.locator(`.ladder-step[data-rung='${id}']`).click();
  else await page.locator(`.ladder-chart [data-rung='${id}']`).click();
  await page.waitForFunction((r) => document.documentElement.dataset.ladderReady === r, id, { timeout: 180_000 });
  await settle(page);
}

/** The names of the splat meshes in the scene: a rung's are "<rung>-seen" and so on, Part 1's its file keys. */
const meshNames = (page: Page) => page.evaluate(() => {
  const names: string[] = [];
  (window as any).__hbi.viewer.scene.traverse((o: any) => { if (o.packedSplats && o.layers.mask & 1) names.push(o.name); });
  return names.sort();
});

/**
 * Pixels the red pen drew: clearly red strokes, in both schemes' reds; or, with `wash`, the paler red the map's
 * paper takes (only ever compared with the same view with the pen off, since a brown floor is warm too).
 */
const redPixels = (page: Page, wash = false) => page.screenshot({ style: ".bar, .ladder, .map-legend { visibility: hidden !important; }" }).then((png) => page.evaluate(async ({ b64, wash }) => {
  const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
  const c = new OffscreenCanvas(bmp.width, bmp.height);
  const ctx = c.getContext("2d")!;
  ctx.drawImage(bmp, 0, 0);
  const d = ctx.getImageData(0, 0, bmp.width, bmp.height).data;
  let n = 0;
  for (let i = 0; i < d.length; i += 4) {
    const [r, g, b] = [d[i], d[i + 1], d[i + 2]];
    if (wash ? r - g > 18 && r - b > 22 : r > 150 && r - g > 70 && r - b > 70) n++;
  }
  return n;
}, { b64: png.toString("base64"), wash }));

/** Every word a reader or a screen reader gets from the page, attributes and SVG titles included. */
const allText = (page: Page) => page.evaluate(() => {
  const bits = [document.body.innerText];
  document.querySelectorAll("[aria-label], [title], title, figcaption, dd, dt").forEach((e) => {
    bits.push(e.getAttribute("aria-label") ?? "", e.getAttribute("title") ?? "", e.textContent ?? "");
  });
  return bits.join("\n");
});

test("the walk stays the default: no panel until asked, and the Ladder switch is there once the ladder is", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await page.waitForSelector("html[data-ready='1']", { timeout: 180_000 });
  await page.evaluate(() => (window as any).__hbi.chrome.hideIntro());
  await expect(page.locator(".ladder")).toBeHidden();
  await expect(page.locator("[data-control='ladder']")).toHaveAttribute("aria-pressed", "false");
  expect(await meshNames(page)).toEqual(["imagined", "measured", "overlap"]);
  expect(errors).toEqual([]);
});

test("?ladder= opens straight onto a rung and never fetches the walk's splat files", async ({ page }) => {
  const errors = watchErrors(page);
  const fetched: string[] = [];
  page.on("request", (r) => fetched.push(new URL(r.url()).pathname));
  await openLadder(page, "ladder=R4");
  expect(fetched.filter((p) => p.startsWith("/fixture/") && p.endsWith(".spz"))).toEqual([]);
  expect(fetched.filter((p) => p.startsWith("/fixture-ladder/") && p.endsWith(".spz")).sort()).toEqual(
    ["/fixture-ladder/R4/imagined.spz", "/fixture-ladder/R4/seen.spz", "/fixture-ladder/R4/wrong.spz"]);
  await expect(page.locator(".ladder")).toBeVisible();
  await expect(page.locator(".ladder-step[data-rung='R4']")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ladder-readout")).toContainText("31% of the view from this spot");
  expect(await meshNames(page)).toEqual(["R4-imagined", "R4-seen", "R4-wrong"]);
  // The visitor stands at the camera point, facing the first photo (the door, along +x).
  const pose = await page.evaluate(() => { const p = (window as any).__hbi.viewer.walk.pose(); return { x: p.position.x, z: p.position.z, yaw: p.yaw }; });
  expect(pose.x).toBeCloseTo(0, 5);
  expect(pose.z).toBeCloseTo(0, 5);
  expect(pose.yaw).toBeCloseTo(-Math.PI / 2, 5);
  expect(errors).toEqual([]);
});

test("stepping keeps one rung in memory, follows the address, and reaches the extra points from the chart", async ({ page }) => {
  const errors = watchErrors(page);
  await openLadder(page, "ladder=1");
  expect(await meshNames(page)).toEqual(["R1-imagined", "R1-seen", "R1-wrong"]);
  for (const id of ["R2", "R8", "P"]) {
    await stepTo(page, id);
    expect(await meshNames(page)).toEqual([`${id}-imagined`, `${id}-seen`, `${id}-wrong`]);
    expect(new URL(page.url()).searchParams.get("ladder")).toBe(id);
  }
  await stepTo(page, "R4b", "chart");
  expect(await meshNames(page)).toEqual(["R4b-imagined", "R4b-seen", "R4b-wrong"]);
  await expect(page.locator(".ladder-step[data-rung='R4']")).toHaveAttribute("aria-pressed", "mixed");
  // The keyboard walks the scale bar like a slider.
  await page.locator(".ladder-step[data-rung='R1']").focus();
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(() => document.documentElement.dataset.ladderReady === "R2", undefined, { timeout: 180_000 });
  expect(errors).toEqual([]);
});

test("a rung that was not placed shows its frames and says so, with no splats and no point", async ({ page }) => {
  const errors = watchErrors(page);
  await openLadder(page, "ladder=R4r");
  expect(await meshNames(page)).toEqual([]);
  await expect(page.locator(".ladder-now")).toContainText("Not placed");
  await expect(page.locator(".ladder-chart [data-rung='R4r']")).toHaveCount(0);
  await expect(page.locator(".ladder-figure figcaption")).toContainText("Not placed, so not plotted: 4 photos, reconstruction mode.");
  expect(errors).toEqual([]);
});

test("the red pen draws the wrong file in red, and only while it is on", async ({ page }) => {
  const errors = watchErrors(page);
  await openLadder(page, "ladder=R1");
  const off = await redPixels(page);
  await page.locator("[data-control='redpen']").click();
  await settle(page);
  const on = await redPixels(page);
  expect(new URL(page.url()).searchParams.get("redpen")).toBe("1");
  expect(off).toBeLessThan(50);
  expect(on).toBeGreaterThan(2000);
  // The map shows it too, as a wash on the paper.
  await page.locator("[data-control='map']").click();
  await settle(page);
  const mapOn = await redPixels(page, true);
  await page.locator("[data-control='redpen']").click();
  await settle(page);
  const mapOff = await redPixels(page, true);
  expect(mapOn - mapOff).toBeGreaterThan(2000);
  await page.locator("[data-control='redpen']").click();
  await settle(page);
  await expect(page.locator(".ladder-map-key")).toBeVisible();
  await expect(page.locator(".map-legend:not(.ladder-map-key)")).toBeHidden();
  expect(errors).toEqual([]);
});

test("no right or wrong figure anywhere on the page, the HUD included (stance A)", async ({ page }) => {
  const errors = watchErrors(page);
  await openLadder(page, "ladder=R4&redpen=1&hud=1&plain=1");
  for (const id of ["R4", "P"]) {
    if (id !== "R4") await stepTo(page, id);
    await page.waitForTimeout(600);
    const text = await allText(page);
    const judging = /\b(right|wrong|correct|incorrect|accura\w*|error|mistakes?|complete\w*)\b/i;
    const lines = text.split(/\n|(?<=[.;])\s/).filter((l) => /\d/.test(l) && judging.test(l));
    expect(lines).toEqual([]);
    // The HUD shows the splats drawn in all, never a count per class, which a reader could divide.
    const hud = await page.locator(".hud pre").textContent();
    expect(hud).not.toMatch(/seen|imagined|wrong/i);
  }
  expect(errors).toEqual([]);
});

test("leaving the ladder brings the walk back as it was", async ({ page }) => {
  const errors = watchErrors(page);
  await openLadder(page, "ladder=R2&redpen=1");
  await page.locator("[data-control='ladder']").click();
  await page.waitForFunction(() => (window as any).__hbi.viewer.world.fullyLoaded, undefined, { timeout: 180_000 });
  await settle(page);
  expect(await meshNames(page)).toEqual(["imagined", "measured", "overlap"]);
  await expect(page.locator(".ladder")).toBeHidden();
  expect(new URL(page.url()).search).toBe("");
  expect(await redPixels(page)).toBeLessThan(50);
  expect(await page.evaluate(() => (window as any).__hbi.viewer.redPen)).toBe(false);
  expect(errors).toEqual([]);
});

for (const [width, height, label] of [[1440, 900, "1440"], [390, 844, "390"]] as const) {
  for (const scheme of ["light", "dark"] as const) {
    test.describe(`at ${label} px, ${scheme}`, () => {
      test.use({ viewport: { width, height }, colorScheme: scheme, ...(width < 500 ? { hasTouch: true, isMobile: true } : {}) });

      test("the panel fits, nothing is cut off, and the console is clean", async ({ page }) => {
        const errors = watchErrors(page);
        await openLadder(page, "ladder=R4&redpen=1");
        if (width < 500) await page.evaluate(() => (window as any).__hbi.viewer.walk.engage());
        const box = await page.locator(".ladder").boundingBox();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width);
        expect(box!.y).toBeGreaterThanOrEqual(0);
        expect(box!.y + box!.height).toBeLessThanOrEqual(height);
        // The page never scrolls sideways, and the steps' labels are whole.
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        for (const b of await page.locator(".ladder-step .name").all()) {
          expect(await b.evaluate((e) => e.scrollWidth <= e.clientWidth + 1)).toBe(true);
        }
        if (width < 500) {
          const gyro = await page.locator(".gyro-button").boundingBox();
          expect(gyro!.y + gyro!.height).toBeLessThanOrEqual(box!.y);
        }
        await settle(page);
        await page.screenshot({ path: `${DOCS}/ladder-${label}-${scheme}.png` });
        await page.locator("[data-control='map']").click();
        await settle(page);
        await page.screenshot({ path: `${DOCS}/ladder-${label}-${scheme}-map.png` });
        expect(errors).toEqual([]);
      });
    });
  }
}
