import { describe, expect, it } from "vitest";
import { lineView, NEAR_LINE_M, Trail, type LineView } from "./trail.ts";

// The published scene's coastline and door (media v2): one stretch across the doorway at x = 1.9.
const COAST: [number, number][][] = [[[1.9, -0.15], [1.9, 0.0125], [1.9, 0.2125], [1.9, 0.45]]];
const OUTWARD: [number, number] = [0.987221, 0.159355];
const deg = (d: number) => (d * Math.PI) / 180;
/** Half the horizontal field of view at 1440 × 900 with the viewer's 70° vertical one. */
const HALF_H = Math.atan((1440 / 900) * Math.tan(deg(35)));
const TOWARDS = deg(-99.169);
const BACK = deg(80.831);
const view = (x: number, z: number, yaw: number) => lineView([x, z], yaw, HALF_H, COAST, OUTWARD);

describe("lineView", () => {
  it("at the start pose: 1.9 m off, on the room's side, the doorway ahead and in view", () => {
    const v = view(0, 0, TOWARDS);
    expect(v.distM).toBeCloseTo(1.9, 2);
    expect(v).toMatchObject({ past: false, inView: true, lineAhead: true });
    expect(v.facing).toBeGreaterThan(0.99);
  });
  it("a step past the line is the drawn side", () => {
    expect(view(2.0, 0.15, TOWARDS).past).toBe(true);
    expect(view(1.8, 0.15, TOWARDS).past).toBe(false);
  });
  it("beside the doorway, off the line's ends, the side still follows the door's outward direction", () => {
    expect(view(1.85, -1.2, TOWARDS).past).toBe(false);
    expect(view(1.0, 2.0, TOWARDS).past).toBe(false);
  });
  it("facing back from the hallway: facing the room, the line ahead", () => {
    const v = view(2.6, 0.2, BACK);
    expect(v.facing).toBeLessThan(-0.99);
    expect(v.lineAhead).toBe(true);
  });
  it("with the door behind, the line is out of view", () => {
    expect(view(1.4, 0.1, BACK).inView).toBe(false);
  });
});

/** A walk from the start pose to the door, over the line, round and back: the observations a visitor makes. */
function walk(t: Trail, steps: [number, number, number][]) {
  return steps.map(([x, z, yaw]) => t.observe(view(x, z, yaw)));
}

describe("Trail", () => {
  it("opens on chapter 1 and fires nothing at the start pose (it stands further than the edge's reach)", () => {
    const t = new Trail();
    expect(view(0, 0, TOWARDS).distM).toBeGreaterThan(NEAR_LINE_M);
    expect(walk(t, [[0, 0, TOWARDS], [0.2, 0.03, TOWARDS]])).toEqual([null, null]);
    expect(t.chapter).toBe(0);
  });

  it("the edge opens chapter 2 near the line with it in view, once", () => {
    const t = new Trail();
    expect(walk(t, [[0, 0, TOWARDS], [0.6, 0.1, TOWARDS]])).toEqual([null, 1]);
    expect(t.chapter).toBe(1);
    t.goTo(0);
    expect(walk(t, [[0, 0, TOWARDS], [0.7, 0.1, TOWARDS]])).toEqual([null, null]);
    expect(t.chapter).toBe(0);
  });

  it("near the line but facing away is not the edge", () => {
    const t = new Trail();
    expect(walk(t, [[1.4, 0.1, BACK]])).toEqual([null]);
  });

  it("stepping over opens chapter 3; looking back after facing the hallway opens chapter 4", () => {
    const t = new Trail();
    const opened = walk(t, [
      [0, 0, TOWARDS], [1.2, 0.15, TOWARDS], [1.85, 0.15, TOWARDS], [2.05, 0.15, TOWARDS],
      [2.6, 0.2, TOWARDS], [2.6, 0.2, deg(-10)], [2.6, 0.2, BACK],
    ]);
    expect(opened).toEqual([null, 1, null, 2, null, null, 3]);
    expect(t.chapter).toBe(3);
  });

  it("backing over the line while facing the room is chapter 3, and chapter 4 waits for a turn", () => {
    const t = new Trail();
    expect(walk(t, [[1.7, 0.15, BACK], [2.1, 0.15, BACK], [2.3, 0.15, BACK]])).toEqual([null, 2, null]);
    expect(walk(t, [[2.3, 0.15, TOWARDS], [2.3, 0.15, BACK]])).toEqual([null, 3]);
  });

  it("stepping over needs a step from the room's side: turning the layer on in the hallway is not a crossing", () => {
    const t = new Trail();
    expect(walk(t, [[2.4, 0.15, TOWARDS], [2.5, 0.15, TOWARDS]])).toEqual([null, null]);
    expect(t.chapter).toBe(0);
  });

  it("opening the map opens chapter 5, once; one moment per observation", () => {
    const t = new Trail();
    expect(t.mapOpened()).toBe(4);
    expect(t.chapter).toBe(4);
    expect(t.mapOpened()).toBeNull();
    // The walk's moments still open their chapters after the map's.
    expect(walk(t, [[0, 0, TOWARDS], [0.6, 0.1, TOWARDS]])).toEqual([null, 1]);
  });

  it("next moves on one chapter and stops at the last; goTo jumps and clamps", () => {
    const t = new Trail();
    expect([t.next(), t.next(), t.next(), t.next(), t.next()]).toEqual([1, 2, 3, 4, 4]);
    t.goTo(2);
    expect(t.chapter).toBe(2);
    t.goTo(99);
    expect(t.chapter).toBe(4);
    t.goTo(-3);
    expect(t.chapter).toBe(0);
    expect(t.isLast).toBe(false);
  });

  it("a view with no coastline fires nothing", () => {
    const empty: LineView = { distM: Infinity, past: false, inView: false, facing: 0, lineAhead: false };
    const t = new Trail();
    expect(t.observe(empty)).toBeNull();
    expect(lineView([0, 0], 0, HALF_H, [], OUTWARD)).toEqual(empty);
  });
});
