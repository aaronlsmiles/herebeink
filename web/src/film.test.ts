import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { pointInPolygon } from "./geometry.ts";
import type { FilmKey } from "./contract.ts";
import { FilmPath, tangents, unwrapDegrees } from "./film.ts";

const deg = (r: number) => (r * 180) / Math.PI;
// The fixture's own path: out through the doorway, hold, turn, walk back.
const FIXTURE: FilmKey[] = [
  { t: 0, position: [0, 1.6, 0], yawDeg: -90.021, pitchDeg: 0 },
  { t: 4, position: [1.2, 1.6, 0], yawDeg: -90.021, pitchDeg: -8 },
  { t: 8, position: [3.2, 1.6, 0.001], yawDeg: -90.021, pitchDeg: -8 },
  { t: 11, position: [3.2, 1.6, 0.001], yawDeg: 89.979, pitchDeg: 0 },
  { t: 15, position: [1.2, 1.6, 0], yawDeg: 89.979, pitchDeg: 0 },
];

describe("unwrapDegrees", () => {
  it("takes the short way round", () => {
    expect(unwrapDegrees([170, -170, -150])).toEqual([170, 190, 210]);
    expect(unwrapDegrees([-170, 170])).toEqual([-170, -190]);
    expect(unwrapDegrees([10, 20])).toEqual([10, 20]);
  });
});

describe("tangents", () => {
  it("is Catmull-Rom for steady motion and zero at the ends", () => {
    expect(tangents([0, 1, 2], [0, 1, 2])).toEqual([0, 1, 0]);
  });
  it("holds still at a reversal or a pause, so a held position cannot overshoot", () => {
    expect(tangents([0, 1, 2], [0, 1, 0])[1]).toBe(0);
    expect(tangents([0, 1, 2, 3], [0, 1, 1, 2])).toEqual([0, 0, 0, 0]);
  });
});

describe("FilmPath", () => {
  const path = new FilmPath(FIXTURE);
  it("passes through every key and counts frames at the frame rate", () => {
    for (const k of FIXTURE) {
      const p = path.at(k.t);
      expect(p.position[0]).toBeCloseTo(k.position[0], 9);
      expect(p.position[2]).toBeCloseTo(k.position[2], 9);
      expect(p.pitch).toBeCloseTo((k.pitchDeg * Math.PI) / 180, 9);
    }
    expect(path.duration).toBe(15);
    expect(path.frameCount(24)).toBe(361);
    expect(path.frameCount(1)).toBe(16);
  });
  it("eases in and out: it barely moves in the first and last frames", () => {
    const a = path.frame(0).position[0], b = path.frame(1).position[0];
    expect(b - a).toBeLessThan(0.01);
    const c = path.frame(359).position[0], d = path.frame(360).position[0];
    expect(Math.abs(d - c)).toBeLessThan(0.01);
  });
  it("never leaves the span of its keys: the hold at the far end does not overshoot the wall", () => {
    for (let n = 0; n <= 360; n++) {
      const [x, , z] = path.frame(n).position;
      expect(x).toBeLessThanOrEqual(3.2 + 1e-9);
      expect(x).toBeGreaterThanOrEqual(0 - 1e-9);
      expect(Math.abs(z)).toBeLessThan(0.01);
    }
  });
  it("is smooth: no frame step jumps and the speed changes gradually", () => {
    let prev = path.frame(0).position;
    let prevStep = 0;
    for (let n = 1; n <= 360; n++) {
      const p = path.frame(n).position;
      const step = Math.hypot(p[0] - prev[0], p[2] - prev[2]);
      expect(step).toBeLessThan(0.1);
      expect(Math.abs(step - prevStep)).toBeLessThan(0.02);
      prev = p;
      prevStep = step;
    }
  });
  it("turns through 180 degrees in one direction between the keys, never the long way twice", () => {
    let prevYaw = path.frame(192).yaw;
    let total = 0;
    for (let n = 193; n <= 264; n++) {
      const y = path.frame(n).yaw;
      total += y - prevYaw;
      prevYaw = y;
    }
    expect(Math.abs(deg(total))).toBeCloseTo(180, 0);
    // A turn from 170 to -170 degrees is 20, not 340.
    const wrap = new FilmPath([{ t: 0, position: [0, 0, 0], yawDeg: 170, pitchDeg: 0 }, { t: 2, position: [0, 0, 0], yawDeg: -170, pitchDeg: 0 }]);
    expect(Math.abs(deg(wrap.at(1).yaw) - 180)).toBeLessThan(1);
  });
  it("gives the same pose for the same frame every time", () => {
    expect(new FilmPath(FIXTURE).frame(137)).toEqual(path.frame(137));
  });
  it("sorts keys, drops repeated times and refuses a single key", () => {
    const shuffled = new FilmPath([FIXTURE[3], FIXTURE[0], FIXTURE[1], FIXTURE[1], FIXTURE[4], FIXTURE[2]]);
    expect(shuffled.frame(100)).toEqual(path.frame(100));
    expect(() => new FilmPath([FIXTURE[0], FIXTURE[0]])).toThrow();
  });
});

describe("the fixture's own film path", () => {
  const scene = JSON.parse(readFileSync(new URL("../public/fixture/scene.json", import.meta.url), "utf8"));
  it("stays inside the walkable area for every frame, with a centimetre to spare for the edge", () => {
    const path = new FilmPath(scene.filmPath);
    const poly = scene.walkable.polygons[0] as [number, number][];
    for (let n = 0; n < path.frameCount(); n++) {
      const [x, , z] = path.frame(n).position;
      // The far end of the path sits on the polygon's edge, where even-odd may fall either side.
      const inside = pointInPolygon([x, z], poly) || pointInPolygon([x - 0.01, z], poly);
      expect(inside, `frame ${n} at ${x.toFixed(3)}, ${z.toFixed(3)}`).toBe(true);
    }
  });
});
