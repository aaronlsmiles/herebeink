import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { filmScene, filmSceneHandler } from "./film-scene.ts";

const key = (t: number, x: number) => ({ t, position: [x, 1.6, 0], yawDeg: 0, pitchDeg: 0 });

let dir: string;
let pathFile: string;
let server: Server;
let base: string;

beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "film-scene-"));
  writeFileSync(join(dir, "scene.json"), JSON.stringify({ schemaVersion: 1, start: { yawDeg: 3 }, filmPath: [key(0, 0), key(1, 9)] }));
  writeFileSync(join(dir, "imagined.spz"), "splats");
  pathFile = join(dir, "paths.json");
  writeFileSync(pathFile, JSON.stringify({ shots: { walk: { filmPath: [key(0, 1), key(2, 2)] }, hook: { filmPath: [key(0, 5), key(1, 6)] }, bad: { filmPath: [key(0, 1)] } } }));
  server = createServer(filmSceneHandler(dir, pathFile));
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterAll(() => {
  server.close();
  rmSync(dir, { recursive: true, force: true });
});

describe("filmScene", () => {
  it("swaps the filmPath for the shot's and leaves everything else as exported", () => {
    const s = JSON.parse(filmScene(dir, pathFile, "hook"));
    expect(s.filmPath).toEqual([key(0, 5), key(1, 6)]);
    expect(s.start).toEqual({ yawDeg: 3 });
    expect(s.schemaVersion).toBe(1);
  });
  it("refuses a missing shot or a path of one key", () => {
    expect(() => filmScene(dir, pathFile, "nope")).toThrow();
    expect(() => filmScene(dir, pathFile, "bad")).toThrow();
  });
});

describe("filmSceneHandler", () => {
  it("serves scene.json with the walk shot by default, and other files as they are", async () => {
    const s = await (await fetch(`${base}/scene.json`)).json();
    expect(s.filmPath).toEqual([key(0, 1), key(2, 2)]);
    expect(await (await fetch(`${base}/imagined.spz`)).text()).toBe("splats");
  });
  it("picks a shot by query", async () => {
    const s = await (await fetch(`${base}/scene.json?shot=hook`)).json();
    expect(s.filmPath[0].position[0]).toBe(5);
  });
  it("serves only plain scene file names", async () => {
    for (const p of ["/..%2Fsecret.spz", "/.env", "/a/b.spz", "/x.png"]) {
      expect((await fetch(`${base}${p}`)).status, p).not.toBe(200);
    }
  });
  it("is read-only", async () => {
    expect((await fetch(`${base}/scene.json`, { method: "POST", body: "x" })).status).toBe(405);
  });
});
