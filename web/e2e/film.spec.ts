import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { note, watchErrors } from "./helpers.ts";

// Frames go to film/frames/<set>/ at the repo root (gitignored); the sets here are removed after.
const FRAMES = resolve(import.meta.dirname, "../../film/frames");
const sets = ["e2e-a", "e2e-b", "e2e-c"];
test.beforeEach(() => { for (const s of sets) rmSync(resolve(FRAMES, s), { recursive: true, force: true }); });
test.afterAll(() => { for (const s of sets) rmSync(resolve(FRAMES, s), { recursive: true, force: true }); });

test.describe.configure({ timeout: 900_000 });
// SwiftShader draws every splat pass on the CPU: a small canvas keeps a dump to minutes.
const W = 320, H = 180;
// Four to four and a half seconds in: the camera is moving between the first two keys.
const RANGE = "from=96&frames=12";

async function dump(page: Page, set: string, extra = "") {
  const errors = watchErrors(page);
  await page.goto(`/?path=film&dump=1&w=${W}&h=${H}&set=${set}&${RANGE}${extra}`);
  await page.waitForSelector("html[data-film-complete='1'], html[data-film-error]", { timeout: 800_000, state: "attached" });
  const d = await page.evaluate(() => ({ error: document.documentElement.dataset.filmError ?? null, done: document.documentElement.dataset.filmDone, frames: document.documentElement.dataset.filmFrames }));
  expect(d.error).toBeNull();
  expect(errors).toEqual([]);
  return d;
}

const files = (set: string) => readdirSync(resolve(FRAMES, set)).sort();
const sha = (set: string, f: string) => createHash("sha256").update(readFileSync(resolve(FRAMES, set, f))).digest("hex");

function pngSize(set: string, f: string) {
  const b = readFileSync(resolve(FRAMES, set, f));
  return { signature: b.subarray(0, 8).toString("hex"), width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
}

test("two dumps of the same frames are identical, byte for byte, and the frames are the film's own numbers at the canvas size asked for", async ({ browser }) => {
  const a = await dump(await browser.newPage({ viewport: { width: 1280, height: 720 } }), "e2e-a");
  const b = await dump(await browser.newPage({ viewport: { width: 800, height: 600 } }), "e2e-b");
  expect(a).toMatchObject({ done: "12", frames: "12" });
  expect(b).toMatchObject({ done: "12", frames: "12" });

  const names = files("e2e-a");
  expect(names).toEqual(Array.from({ length: 12 }, (_, i) => `${String(96 + i).padStart(5, "0")}.png`));
  expect(files("e2e-b")).toEqual(names);
  // The canvas size is the one asked for, not the window's.
  for (const f of names) expect(pngSize("e2e-a", f)).toEqual({ signature: "89504e470d0a1a0a", width: W, height: H });

  const same = names.filter((f) => sha("e2e-a", f) === sha("e2e-b", f));
  note("determinism", `${same.length} of ${names.length} frames byte-identical across two runs (SwiftShader, ${W}x${H}, different window sizes)`);
  expect(same).toEqual(names);

  // The camera is moving: consecutive frames differ, and nothing is a blank canvas.
  const hashes = new Set(names.map((f) => sha("e2e-a", f)));
  expect(hashes.size).toBe(names.length);
  // The first frame must be the full-detail picture, not the level-of-detail tree's coarse root (a
  // far-off view shows one giant splat until the worker answers: about half the bytes of a real frame).
  const sizes = names.map((f) => readFileSync(resolve(FRAMES, "e2e-a", f)).length);
  const median = [...sizes].sort((x, y) => x - y)[Math.floor(sizes.length / 2)];
  expect(sizes[0]).toBeGreaterThan(median * 0.85);
  for (const size of sizes) expect(size).toBeGreaterThan(2000);
});

test("film mode hides the chrome, and the frame endpoint refuses what is not a plain frame", async ({ page, request }) => {
  await page.goto(`/?path=film&w=${W}&h=${H}&from=0&frames=1`);
  await page.waitForSelector("html[data-film-complete='1']", { timeout: 300_000, state: "attached" });
  for (const sel of [".intro", ".bar", ".hud", ".map"]) {
    for (const el of await page.locator(sel).all()) await expect(el).toBeHidden();
  }
  // From the page's own origin and as a PNG, so what is refused here is the name, not the sender.
  const own = { Origin: new URL(page.url()).origin, "Content-Type": "image/png" };
  for (const [q, status] of [["n=../../../escape", 400], ["n=1&set=..", 400], ["n=1&set=A/b", 400], ["n=", 400], ["", 400]] as const) {
    expect((await request.post(`/frame?${q}`, { data: "x", headers: own })).status(), q).toBe(status);
  }
  // A well-formed frame from anywhere else, or not as a PNG, is refused too, and nothing is written.
  expect((await request.post("/frame?n=7&set=e2e-a", { data: "x", headers: { ...own, Origin: "https://elsewhere.example" } })).status()).toBe(403);
  expect((await request.post("/frame?n=7&set=e2e-a", { data: "x", headers: { "Content-Type": "image/png" } })).status()).toBe(403);
  expect((await request.post("/frame?n=7&set=e2e-a", { data: "x", headers: { ...own, "Content-Type": "text/plain" } })).status()).toBe(415);
  expect(existsSync(resolve(FRAMES, "e2e-a/00007.png"))).toBe(false);
  expect((await request.get("/frame?n=1")).status()).toBe(405);
  expect(existsSync(resolve(FRAMES, "../escape.png"))).toBe(false);
});
