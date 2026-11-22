import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 480, height: 300 }, colorScheme: "light" });
test.describe.configure({ timeout: 240_000 });

async function lose(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.waitForFunction(() => (window as any).__hbi !== undefined, undefined, { timeout: 60_000 });
  await page.waitForFunction(() => document.documentElement.dataset.firstSplats !== undefined, undefined, { timeout: 120_000 });
  return page.evaluate(() => {
    const v = (window as any).__hbi.viewer;
    const canvas = v.renderer.domElement as HTMLCanvasElement;
    const ext = v.renderer.getContext().getExtension("WEBGL_lose_context");
    let prevented = false;
    canvas.addEventListener("webglcontextlost", (e) => { prevented = e.defaultPrevented; });
    ext.loseContext();
    (window as any).__restore = () => ext.restoreContext();
    return new Promise<{ prevented: boolean }>((ok) => setTimeout(() => ok({ prevented }), 500));
  });
}

test("a lost WebGL context stops the loop and tells the visitor to reload", async ({ page }) => {
  const lost = await lose(page);
  // The page's own listener runs before this test's, so the event is already handled by then.
  expect(lost.prevented).toBe(true);
  await expect(page.locator("html[data-fatal='1']")).toHaveCount(1);
  await expect(page.locator(".intro.fatal")).toContainText("Reload the page");
  const before = await page.evaluate(() => (window as any).__hbi.frame() as number);
  await page.waitForTimeout(800);
  expect(await page.evaluate(() => (window as any).__hbi.frame() as number)).toBe(before);
});

test("a restored context reloads the page", async ({ page }) => {
  await lose(page);
  const navigated = page.waitForEvent("load", { timeout: 60_000 });
  await page.evaluate(() => (window as any).__restore());
  await navigated;
});
