import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";

test("splat loads and the canvas is not blank", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/smoke.html");
  await page.waitForSelector("html[data-ready='1']", { timeout: 30_000 });
  await page.waitForTimeout(500);

  mkdirSync("shots", { recursive: true });
  const png = await page.screenshot({ path: "shots/smoke-1440.png" });

  // Decode in the browser to avoid an image dependency in the test tooling.
  const distinct = await page.evaluate(async (b64) => {
    const blob = await (await fetch(`data:image/png;base64,${b64}`)).blob();
    const bmp = await createImageBitmap(blob);
    const w = Math.floor(bmp.width / 2), h = Math.floor(bmp.height / 2);
    const c = new OffscreenCanvas(w, h);
    const ctx = c.getContext("2d")!;
    ctx.drawImage(bmp, bmp.width / 4, bmp.height / 4, w, h, 0, 0, w, h);
    const d = ctx.getImageData(0, 0, w, h).data;
    const seen = new Set<number>();
    for (let i = 0; i < d.length; i += 4) seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
    return seen.size;
  }, png.toString("base64"));

  expect(distinct).toBeGreaterThan(1);
  expect(errors).toEqual([]);
});
