import { expect, test } from "@playwright/test";
import { settle } from "./helpers.ts";

// settle() on a stand-in for the viewer's test hook, so these checks need no WebGL: `settled` and
// whether frames are being drawn are set by the test.
async function standIn(page: import("@playwright/test").Page) {
  await page.setContent("<html><body></body></html>");
  await page.evaluate(() => {
    const w = window as any;
    w.__state = { frames: 0, settled: true, drawing: true, running: true };
    w.__hbi = { frame: () => w.__state.frames, viewer: { get settled() { return w.__state.settled; }, get running() { return w.__state.running; } } };
    setInterval(() => { if (w.__state.drawing) w.__state.frames++; }, 16);
  });
}

test.describe.configure({ timeout: 60_000 });

test("settle() does not reuse the quiet period an earlier call left behind", async ({ page }) => {
  await standIn(page);
  await settle(page);
  // Long enough ago that a stale timestamp would pass the one-second test on the very next poll.
  await page.waitForTimeout(1500);
  const t0 = Date.now();
  await settle(page);
  expect(Date.now() - t0).toBeGreaterThanOrEqual(950);
});

test("settle() needs frames drawn inside the quiet window, not just a settled flag", async ({ page }) => {
  await standIn(page);
  // The flag is true but nothing is drawn for 2 s, as between a detail cut landing and the next frame.
  await page.evaluate(() => { (window as any).__state.drawing = false; setTimeout(() => { (window as any).__state.drawing = true; }, 2000); });
  const t0 = Date.now();
  await settle(page, 0);
  expect(Date.now() - t0).toBeGreaterThanOrEqual(1900);
});

test("settle() starts the quiet period again when the viewer stops being settled", async ({ page }) => {
  await standIn(page);
  await page.evaluate(() => {
    const s = (window as any).__state;
    s.settled = false;
    setTimeout(() => { s.settled = true; }, 1500);
  });
  const t0 = Date.now();
  await settle(page);
  expect(Date.now() - t0).toBeGreaterThanOrEqual(2400);
});

test("settle() with the loop stopped waits for the quiet second alone, since no frame can be drawn", async ({ page }) => {
  await standIn(page);
  await page.evaluate(() => { const s = (window as any).__state; s.running = false; s.drawing = false; });
  const t0 = Date.now();
  await settle(page, 0);
  const took = Date.now() - t0;
  expect(took).toBeGreaterThanOrEqual(950);
  expect(took).toBeLessThan(5000);
});
