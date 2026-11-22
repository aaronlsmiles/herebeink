import { expect, test } from "@playwright/test";
import { watchErrors } from "./helpers.ts";

test.describe.configure({ timeout: 120_000 });

// Spark's splat size limits are in the pixels of the renderer that draws, so a data pass at a
// fraction of the canvas's resolution must carry that fraction of the limit: only then is a splat
// cut at the same size on screen in the flag and G-buffer passes as in the picture.
for (const dpr of [2, 3]) {
  test(`at devicePixelRatio ${dpr} the data passes cut splats at the size the picture does`, async ({ browser }) => {
    const page = await browser.newPage({ viewport: { width: 360, height: 225 }, deviceScaleFactor: dpr, colorScheme: "light" });
    const errors = watchErrors(page);
    await page.goto("/");
    await page.waitForFunction(() => (window as any).__hbi !== undefined, undefined, { timeout: 60_000 });
    const onScreen = () => page.evaluate(() => {
      const v = (window as any).__hbi.viewer;
      const buffer = v.renderer.domElement.width as number;
      const cap = (s: any, target: any) => ({ min: s.minPixelRadius * (buffer / target.width), max: s.maxPixelRadius * (buffer / target.width) });
      return {
        picture: { min: v.spark.minPixelRadius as number, max: v.spark.maxPixelRadius as number },
        gbuf: cap(v.data.gbufSpark, v.data.gbufTarget),
        flag: cap(v.data.flagSpark, v.data.flagTarget),
        dataScale: v.data.gbufTarget.width / buffer,
      };
    });
    const first = await onScreen();
    expect(first.dataScale).toBeCloseTo(1 / dpr, 2);
    expect(first.gbuf).toEqual(first.picture);
    expect(first.flag).toEqual(first.picture);

    // A new budget (a headset session, say) changes the data scale: the limits follow it.
    await page.evaluate(() => {
      const v = (window as any).__hbi.viewer;
      v.setBudget({ ...v.budget, dataScale: 0.25 });
    });
    const after = await onScreen();
    expect(after.dataScale).toBeCloseTo(0.25, 2);
    expect(after.gbuf).toEqual(after.picture);
    expect(after.flag).toEqual(after.picture);
    expect(errors).toEqual([]);
    await page.close();
  });
}
