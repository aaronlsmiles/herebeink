// Layout of the chrome: nothing the page says is cut off or covered at the sizes people open it at.
import { expect, type Page, test } from "@playwright/test";
import { openViewer, watchErrors } from "./helpers.ts";

test.describe.configure({ timeout: 300_000 });

const LOADING = "The room is here; the rest is on its way.";

test("the first-screen card shows all its words, without scrolling, at the common laptop sizes", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await page.waitForSelector("html[data-ready='1']", { timeout: 180_000 });
  // The longest status line the card shows while the room arrives.
  await page.evaluate((t) => (window as any).__hbi.chrome.setStatus(t), LOADING);
  for (const [width, height] of [[1440, 900], [1366, 768], [1280, 800], [1280, 720], [1100, 900]] as const) {
    await page.setViewportSize({ width, height });
    const m = await page.evaluate(() => {
      const i = document.querySelector<HTMLElement>(".intro")!;
      return { scroll: i.scrollHeight, client: i.clientHeight, top: i.getBoundingClientRect().top };
    });
    expect(m.scroll, `${width} x ${height}`).toBeLessThanOrEqual(m.client);
    expect(m.top, `${width} x ${height}`).toBeGreaterThanOrEqual(0);
  }
  expect(errors).toEqual([]);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, colorScheme: "light" });

  // "Walk in" shows the touch controls; the helper only hides the first screen.
  const walkIn = (page: Page, qs: string) => openViewer(page, qs).then(() => page.evaluate(() => (window as any).__hbi.viewer.walk.engage()));

  test("the tilt switch leaves the map's key the foot of the sheet, and comes back with the room", async ({ page }) => {
    const errors = watchErrors(page);
    await walkIn(page, "");
    const gyro = page.locator("button[data-control='gyro']");
    await expect(gyro).toBeVisible();
    await page.locator("[data-control='map']").click();
    await expect(page.locator(".map-legend")).toBeVisible();
    await expect(gyro).toBeHidden();
    await page.locator("[data-control='map']").click();
    await expect(gyro).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("with the plain-words notes open, the column stops above the tilt switch's note, and above the key on the map", async ({ page }) => {
    await walkIn(page, "plain=1");
    await page.locator(".pw-fold:not([open]) summary").click();
    const bottoms = () => page.evaluate(() => {
      const top = (s: string) => document.querySelector(s)!.getBoundingClientRect().top;
      const stack = document.querySelector(".pw-stack")!.getBoundingClientRect();
      return { stackBottom: stack.bottom, note: top(".touch-ui .pw-note"), gyro: top(".gyro-button"), key: document.querySelector(".map-legend")!.getBoundingClientRect().top };
    });
    const walking = await bottoms();
    expect(walking.stackBottom).toBeLessThanOrEqual(walking.note);
    expect(walking.stackBottom).toBeLessThanOrEqual(walking.gyro);
    await page.locator("[data-control='map']").click();
    await expect(page.locator(".map-legend")).toBeVisible();
    const mapped = await bottoms();
    expect(mapped.stackBottom).toBeLessThanOrEqual(mapped.key);
  });
});
