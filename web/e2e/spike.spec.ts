import { expect, test } from "@playwright/test";

// SwiftShader draws every splat pass on the CPU; a smaller canvas keeps the frame rate usable.
test.use({ viewport: { width: 720, height: 450 } });

// The outline pass is the difference between a frame with the extra passes and one without,
// so the shade pass's own dark pixels can never pass for ink.
test("spike S1: outlines only on the imagined half", async ({ page }) => {
  test.setTimeout(240_000);
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/spike.html?pass=final");
  await page.waitForSelector("html[data-ready='1']", { timeout: 60_000 });

  const settle = async () => {
    const f0 = await page.evaluate(() => (window as any).__spike.frame());
    await page.waitForFunction((f) => (window as any).__spike.frame() >= f + 3, f0, { timeout: 120_000 });
  };
  await settle();
  const withOutline = await page.screenshot();
  await page.evaluate(() => (window as any).__spike.setPasses(false));
  await settle();
  const without = await page.screenshot();
  const planeX = await page.evaluate(() => (window as any).__spike.planeScreenX() as number);

  const counts = await page.evaluate(async ({ a, b, planeX }) => {
    const decode = async (b64: string) => {
      const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
      const c = new OffscreenCanvas(bmp.width, bmp.height);
      const ctx = c.getContext("2d")!;
      ctx.drawImage(bmp, 0, 0);
      return ctx.getImageData(0, 0, bmp.width, bmp.height);
    };
    const A = await decode(a), B = await decode(b);
    // Skip a band either side of the plane: the 3 px coastline lives there by design.
    const band = 12;
    let left = 0, right = 0;
    for (let y = 0; y < A.height; y++) {
      for (let x = 0; x < A.width; x++) {
        const i = (y * A.width + x) * 4;
        const d = Math.abs(A.data[i] - B.data[i]) + Math.abs(A.data[i + 1] - B.data[i + 1]) + Math.abs(A.data[i + 2] - B.data[i + 2]);
        if (d < 24) continue;
        if (x < planeX - band) left++;
        else if (x > planeX + band) right++;
      }
    }
    return { left, right };
  }, { a: withOutline.toString("base64"), b: without.toString("base64"), planeX });

  test.info().annotations.push({ type: "outline pixels", description: `left ${counts.left}, right ${counts.right}` });
  expect(counts.left).toBe(0);
  expect(counts.right).toBeGreaterThan(100);
  expect(errors).toEqual([]);
});
