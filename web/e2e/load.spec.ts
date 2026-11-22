import { expect, test } from "@playwright/test";
import { watchErrors } from "./helpers.ts";

test.use({ viewport: { width: 480, height: 300 }, colorScheme: "light" });
test.describe.configure({ timeout: 300_000 });

// What a visitor sees while the files arrive. Spark answers a level-of-detail request on a worker,
// so a file that has just been added has no cut for a few frames, and a far-off view of it is the
// tree's coarse root. The state each frame is about to draw is sampled from the first frame on:
// the sampler is hung on the test hook the moment the page assigns it.
test("while the world loads, a file is drawn only once its detail cut is in all three renderers, and the room never drops out", async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() => {
    const w = window as any;
    const log = { frames: 0, noCut: [] as string[], roomMissing: 0, sawPreview: false, sawFull: false };
    w.__loadLog = log;
    let hook: any;
    Object.defineProperty(w, "__hbi", {
      configurable: true,
      get: () => hook,
      set: (h) => {
        hook = h;
        const v = h.viewer;
        v.beforeFrame = () => {
          log.frames++;
          const meshes = v.world.meshes as Map<string, any>;
          const preview = meshes.has("measuredPreview");
          const full = meshes.has("measured");
          log.sawPreview ||= preview;
          log.sawFull ||= full;
          if (log.sawPreview && !preview && !full) log.roomMissing++;
          for (const [key, world] of meshes) {
            if (key === "measuredPreview") continue;
            const mesh = world.mesh;
            const t = v.twins.get(mesh);
            const cut = v.spark.lodInstances.has(mesh) && v.data.gbufSpark.lodInstances.has(t.gbuf) && v.data.flagSpark.lodInstances.has(t.flag);
            if (!cut && !log.noCut.includes(key)) log.noCut.push(key);
          }
        };
      },
    });
  });
  await page.goto("/");
  await page.waitForSelector("html[data-ready='1']", { timeout: 240_000 });
  const log = await page.evaluate(() => (window as any).__loadLog);
  expect(log.sawPreview).toBe(true);
  expect(log.sawFull).toBe(true);
  expect(log.frames).toBeGreaterThan(3);
  expect(log.noCut).toEqual([]);
  expect(log.roomMissing).toBe(0);
  expect(errors).toEqual([]);
});
