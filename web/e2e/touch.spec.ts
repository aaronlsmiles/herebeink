import { type CDPSession, expect, type Page, test } from "@playwright/test";
import { pointInPolygon } from "../src/geometry.ts";
import { note, openViewer, settle, watchErrors } from "./helpers.ts";

// An iPhone 15 Pro's viewport at DPR 1: the touch logic does not depend on pixel density, and
// SwiftShader would take minutes a frame at 1179 x 2556.
test.use({ viewport: { width: 393, height: 852 }, hasTouch: true, isMobile: true, colorScheme: "light" });
test.describe.configure({ timeout: 300_000 });

type Pt = { x: number; y: number; id: number };
const send = (cdp: CDPSession, type: "touchStart" | "touchMove" | "touchEnd", pts: Pt[]) =>
  cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts });

/** Opens the viewer the way a phone visitor does, then freezes the loop so steps have exact dt. */
async function openOnPhone(page: Page, qs = "walk=touch") {
  await openViewer(page, qs);
  await page.evaluate(() => {
    const v = (window as any).__hbi.viewer;
    v.walk.engage();
    v.stop();
  });
}
const pose = (page: Page) => page.evaluate(() => {
  const p = (window as any).__hbi.viewer.walk.pose();
  return { x: p.position.x as number, y: p.position.y as number, z: p.position.z as number, yaw: p.yaw as number, pitch: p.pitch as number };
});
const step = (page: Page, n: number, dt: number) => page.evaluate(([n, dt]) => { for (let i = 0; i < n; i++) (window as any).__hbi.viewer.step(dt); }, [n, dt] as const);

test("a coarse pointer gets the touch walk, ?walk=desktop overrides it, and the console stays clean", async ({ page }) => {
  const errors = watchErrors(page);
  await openViewer(page, "");
  expect(await page.evaluate(() => (window as any).__hbi.viewer.walkMode)).toBe("touch");
  await expect(page.locator(".intro .hint")).toContainText("left thumb");
  await page.goto("/?walk=desktop");
  await page.waitForSelector("html[data-ready='1']", { timeout: 180_000 });
  expect(await page.evaluate(() => (window as any).__hbi.viewer.walkMode)).toBe("desktop");
  expect(errors).toEqual([]);
});

test("the left thumb walks the way the view faces, at a speed that scales with the push and caps at 1.4 m/s", async ({ page }) => {
  await openOnPhone(page);
  const cdp = await page.context().newCDPSession(page);
  const p0 = await pose(page);
  // Facing +x at the start pose: forward is +x. Full push: the thumb a ring radius above where it landed.
  await send(cdp, "touchStart", [{ x: 100, y: 600, id: 1 }]);
  await send(cdp, "touchMove", [{ x: 100, y: 600 - 56, id: 1 }]);
  await step(page, 5, 0.1);
  const full = await pose(page);
  await send(cdp, "touchEnd", []);
  const run = Math.hypot(full.x - p0.x, full.z - p0.z);
  note("full push", `${run.toFixed(3)} m in 0.5 s of steps`);
  expect(full.x - p0.x).toBeGreaterThan(0);
  expect(Math.abs(full.z - p0.z)).toBeLessThan(0.05);
  expect(run).toBeCloseTo(1.4 * 0.5, 2);
  expect(full.y).toBeCloseTo(p0.y, 6);

  // Half way between the dead zone and the ring: about half the speed.
  await send(cdp, "touchStart", [{ x: 100, y: 600, id: 2 }]);
  await send(cdp, "touchMove", [{ x: 100, y: 600 - 32, id: 2 }]);
  await step(page, 5, 0.1);
  const half = await pose(page);
  await send(cdp, "touchEnd", []);
  expect(Math.hypot(half.x - full.x, half.z - full.z)).toBeCloseTo(0.5 * 1.4 * 0.5, 2);

  // Released: standing still.
  await step(page, 2, 0.1);
  const still = await pose(page);
  expect(still.x).toBeCloseTo(half.x, 9);
});

test("walking never leaves the walkable area, and a ring dropped at the bottom edge stays clear of the gesture bar", async ({ page }) => {
  await openOnPhone(page);
  const cdp = await page.context().newCDPSession(page);
  const polys = await page.evaluate(async () => (await (await fetch("/fixture/scene.json")).json()).walkable.polygons as [number, number][][]);
  // The thumb lands in the very bottom corner of the left half.
  await send(cdp, "touchStart", [{ x: 40, y: 848, id: 1 }]);
  const ring = await page.locator(".joy-ring").boundingBox();
  expect(ring).not.toBeNull();
  expect(ring!.y + ring!.height).toBeLessThanOrEqual(852 - 16);
  expect(ring!.x).toBeGreaterThanOrEqual(0);
  // Push hard to the left of the view (towards -z, the room's near wall) in big steps.
  await send(cdp, "touchMove", [{ x: 40 - 200, y: 848 - 40, id: 1 }]);
  for (let i = 0; i < 6; i++) {
    await step(page, 1, 1.0);
    const p = await pose(page);
    expect(pointInPolygon([p.x, p.z], polys[0])).toBe(true);
  }
  const end = await pose(page);
  note("wall", `ended at x ${end.x.toFixed(3)}, z ${end.z.toFixed(3)}`);
  expect(Math.abs(end.z)).toBeGreaterThan(1.5);
  expect(Math.abs(end.z)).toBeLessThanOrEqual(1.7);
  await send(cdp, "touchEnd", []);
});

test("dragging on the right looks, and a thumb on each side does both at once", async ({ page }) => {
  await openOnPhone(page);
  const cdp = await page.context().newCDPSession(page);
  const p0 = await pose(page);
  await send(cdp, "touchStart", [{ x: 300, y: 400, id: 1 }]);
  await send(cdp, "touchMove", [{ x: 400 - 1, y: 350, id: 1 }]);
  await send(cdp, "touchEnd", []);
  const d = await pose(page);
  // 99 px right turns the view right (yaw falls); 50 px up looks up.
  expect(d.yaw - p0.yaw).toBeCloseTo(-99 * 0.0045, 3);
  expect(d.pitch - p0.pitch).toBeCloseTo(50 * 0.0045, 3);
  expect(d.x).toBeCloseTo(p0.x, 9);

  const before = await pose(page);
  await send(cdp, "touchStart", [{ x: 100, y: 600, id: 1 }]);
  await send(cdp, "touchStart", [{ x: 100, y: 600, id: 1 }, { x: 300, y: 400, id: 2 }]);
  await send(cdp, "touchMove", [{ x: 100, y: 544, id: 1 }, { x: 250, y: 400, id: 2 }]);
  await step(page, 3, 0.1);
  await send(cdp, "touchEnd", []);
  const after = await pose(page);
  expect(after.yaw - before.yaw).toBeGreaterThan(0.2);
  expect(Math.hypot(after.x - before.x, after.z - before.z)).toBeGreaterThan(0.3);
});

test("tilt looks only after the opt-in tap, follows the phone, and drag keeps working", async ({ page }) => {
  await page.addInitScript(() => { (DeviceOrientationEvent as any).requestPermission = async () => "granted"; });
  const errors = watchErrors(page);
  await openOnPhone(page);
  const button = page.locator("button[data-control='gyro']");
  await expect(button).toBeVisible();
  await expect(button).toHaveText("Look by tilting the phone");
  const fire = (alpha: number, beta: number, gamma: number) =>
    page.evaluate(([a, b, g]) => window.dispatchEvent(new DeviceOrientationEvent("deviceorientation", { alpha: a, beta: b, gamma: g })), [alpha, beta, gamma] as const);

  const p0 = await pose(page);
  await fire(10, 90, 0);
  expect((await pose(page)).yaw).toBe(p0.yaw); // not opted in: ignored
  await button.tap();
  await expect(button).toHaveAttribute("aria-pressed", "true");
  await fire(10, 90, 0);
  await fire(40, 120, 0);
  const g = await pose(page);
  // alpha +30 degrees turns the view left by 30; beta +30 looks up by 30.
  expect(g.yaw - p0.yaw).toBeCloseTo(Math.PI / 6, 4);
  expect(g.pitch - p0.pitch).toBeCloseTo(Math.PI / 6, 4);
  // Drag still adds to it.
  const cdp = await page.context().newCDPSession(page);
  await send(cdp, "touchStart", [{ x: 300, y: 400, id: 1 }]);
  await send(cdp, "touchMove", [{ x: 300 + 20, y: 400, id: 1 }]);
  await send(cdp, "touchEnd", []);
  expect((await pose(page)).yaw).toBeCloseTo(g.yaw - 20 * 0.0045, 4);
  await button.tap();
  await expect(button).toHaveAttribute("aria-pressed", "false");
  expect(errors).toEqual([]);
});

test("a refused or missing tilt sensor is handled quietly and drag-look keeps working", async ({ page, browser }) => {
  await page.addInitScript(() => { (DeviceOrientationEvent as any).requestPermission = async () => "denied"; });
  const errors = watchErrors(page);
  await openOnPhone(page);
  const button = page.locator("button[data-control='gyro']");
  await button.tap();
  await expect(button).toBeDisabled();
  await expect(button).toContainText("drag to look");
  const cdp = await page.context().newCDPSession(page);
  const p0 = await pose(page);
  await send(cdp, "touchStart", [{ x: 300, y: 400, id: 1 }]);
  await send(cdp, "touchMove", [{ x: 340, y: 400, id: 1 }]);
  await send(cdp, "touchEnd", []);
  expect((await pose(page)).yaw).toBeLessThan(p0.yaw);
  expect(errors).toEqual([]);

  const ctx = await browser.newContext({ viewport: { width: 393, height: 852 }, hasTouch: true, isMobile: true });
  const bare = await ctx.newPage();
  await bare.addInitScript(() => Object.defineProperty(window, "DeviceOrientationEvent", { value: undefined, configurable: true }));
  const bareErrors = watchErrors(bare);
  await openOnPhone(bare);
  await bare.locator("button[data-control='gyro']").tap();
  await expect(bare.locator("button[data-control='gyro']")).toBeDisabled();
  expect(bareErrors).toEqual([]);
  await ctx.close();
  await settle(page, 0);
});
