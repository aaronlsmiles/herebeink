import { expect, test } from "@playwright/test";
import { inkArea, note, openViewer, paintedShare, settle, shot, watchErrors } from "./helpers.ts";

// No headset in CI: ?xr=mock stands in for one, which checks the button logic and the switch to the
// headset configuration. The session itself, the controllers and the per-eye picture need a Quest.
test.use({ viewport: { width: 720, height: 450 }, colorScheme: "light" });
test.describe.configure({ timeout: 300_000 });
// A headset frame of the room is mostly photograph; a blank one is all paper.
const PAINTED_MIN = 0.5;

const state = (page: import("@playwright/test").Page) => page.evaluate(() => {
  const v = (window as any).__hbi.viewer;
  const cam = v.camera.getWorldPosition(new (v.camera.position.constructor)());
  return {
    active: v.xrActive as boolean,
    deviceClass: v.hudNumbers().lod.deviceClass as string,
    splatBudget: v.hudNumbers().lod.splatBudget as number,
    preUpdate: v.spark.preUpdate as boolean,
    maxStdDev: v.spark.maxStdDev as number,
    dataVisible: [v.data.gbufSpark.visible, v.data.flagSpark.visible] as boolean[],
    floorLine: v.coast.floor.visible as boolean,
    cam: [cam.x, cam.y, cam.z],
    inRig: v.camera.parent === v.rig,
  };
});

test("no headset, no button: the page is unchanged for desktop and phone", async ({ page }) => {
  await openViewer(page, "");
  await expect(page.locator("[data-control='xr']")).toHaveCount(0);
  await expect(page.locator(".xr-note")).toHaveCount(0);
});

test("with a headset in view the button appears, the headset budget and Spark settings apply, and leaving puts everything back", async ({ page }) => {
  const errors = watchErrors(page);
  await openViewer(page, "xr=mock&pose=1.0,1.6,0,-90,0");
  const button = page.locator("button[data-control='xr']");
  await expect(button).toBeVisible();
  await expect(button).toHaveText("Enter VR");
  await expect(button).toHaveAttribute("aria-pressed", "false");
  const before = await state(page);
  expect(before).toMatchObject({ active: false, deviceClass: "desktop", splatBudget: 1_500_000, preUpdate: true, dataVisible: [true, true], inRig: false });

  // The About text carries the outline caveat for headsets.
  await page.evaluate(() => (window as any).__hbi.chrome.showIntro());
  await expect(page.locator(".intro .xr-note")).toContainText("outlines are drawn on screens, not yet in the headset");
  await page.evaluate(() => (window as any).__hbi.chrome.hideIntro());

  await button.click();
  await expect(button).toHaveText("Exit VR");
  await expect(button).toHaveAttribute("aria-pressed", "true");
  await settle(page, 3);
  const inXr = await state(page);
  expect(inXr.active).toBe(true);
  expect(inXr.deviceClass).toBe("xr");
  expect(inXr.splatBudget).toBe(500_000);
  expect(inXr.preUpdate).toBe(false);
  expect(inXr.maxStdDev).toBeCloseTo(Math.sqrt(5), 9);
  expect(inXr.dataVisible).toEqual([false, false]);
  expect(inXr.floorLine).toBe(true);
  expect(inXr.inRig).toBe(true);
  // The stand-in camera sits where the walk put the rig, at eye height.
  expect(inXr.cam[0]).toBeCloseTo(1.0, 3);
  expect(inXr.cam[1]).toBeCloseTo(1.6, 3);
  expect(inXr.cam[2]).toBeCloseTo(0, 3);

  await button.click();
  await expect(button).toHaveText("Enter VR");
  await settle(page, 3);
  const after = await state(page);
  expect(after).toMatchObject({ active: false, deviceClass: "desktop", splatBudget: 1_500_000, preUpdate: true, dataVisible: [true, true], inRig: false });
  expect(after.maxStdDev).toBeCloseTo(Math.sqrt(8), 9);
  expect(errors).toEqual([]);
});

test("the headset configuration honours ?lod= for its splat budget", async ({ page }) => {
  await openViewer(page, "xr=mock&lod=300000");
  await page.locator("button[data-control='xr']").click();
  await settle(page, 2);
  expect((await state(page)).splatBudget).toBe(300_000);
});

test("in the headset configuration the screen-space ink is gone and the picture is still the room", async ({ page }) => {
  // Looking through the doorway at the imagined hallway, where outlines and hatching would be.
  await openViewer(page, "xr=mock&coast=off&pose=1.0,1.6,0,-90,-10");
  const ink = await inkArea(page, "#f4efe4", "#1c1a17");
  await page.locator("button[data-control='xr']").click();
  await settle(page, 4);
  const inXr = await inkArea(page, "#f4efe4", "#1c1a17");
  note("ink area", `${ink.toFixed(0)} on screen, ${inXr.toFixed(0)} in the headset configuration`);
  expect(inXr).toBeLessThan(ink * 0.7);
  // Not blank: the photograph is still drawn, so most of the frame is something other than paper.
  const painted = paintedShare(await shot(page), "#f4efe4");
  note("painted", `${(painted * 100).toFixed(1)} % of the frame is not paper in the headset configuration`);
  expect(painted).toBeGreaterThan(PAINTED_MIN);
});

test("entering the headset configuration closes the map and its button says so", async ({ page }) => {
  await openViewer(page, "xr=mock");
  const map = page.locator("[data-control='map']");
  await map.click({ force: true });
  await expect(map).toHaveAttribute("aria-pressed", "true");
  await page.locator("button[data-control='xr']").click();
  await settle(page, 2);
  await expect(page.locator(".map")).toBeHidden();
  await expect(map).toHaveAttribute("aria-pressed", "false");
});
