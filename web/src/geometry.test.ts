import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { clampToWalkable, insideAny, pointInPolygon, type Polygon } from "./geometry.ts";

const square: Polygon = [[0, 0], [4, 0], [4, 4], [0, 4]];
// Two 4 m rooms joined by a 1 m wide, 2 m long doorway neck (x from 4 to 6, z from 1.5 to 2.5).
const twoRooms: Polygon = [
  [0, 0], [4, 0], [4, 1.5], [6, 1.5], [6, 0], [10, 0], [10, 4], [6, 4], [6, 2.5], [4, 2.5], [4, 4], [0, 4],
];

describe("pointInPolygon", () => {
  it("tells inside from outside for either winding", () => {
    expect(pointInPolygon([2, 2], square)).toBe(true);
    expect(pointInPolygon([5, 2], square)).toBe(false);
    expect(pointInPolygon([2, 2], [...square].reverse())).toBe(true);
  });
});

describe("clampToWalkable", () => {
  it("leaves a step inside alone", () => {
    expect(clampToWalkable([1, 1], [1.5, 1.2], [square])).toEqual([1.5, 1.2]);
  });

  it("stops a step out of the room on the wall", () => {
    const [x, z] = clampToWalkable([3.9, 2], [4.3, 2], [square]);
    expect(x).toBeCloseTo(4, 2);
    expect(x).toBeLessThan(4);
    expect(z).toBeCloseTo(2, 6);
  });

  it("slides along the wall, keeping the motion parallel to it", () => {
    const [x, z] = clampToWalkable([3.95, 2], [4.25, 2.3], [square]);
    expect(x).toBeLessThan(4);
    expect(z).toBeCloseTo(2.3, 6);
  });

  it("works whichever way the polygon winds", () => {
    const [x, z] = clampToWalkable([3.95, 2], [4.25, 2.3], [[...square].reverse()]);
    expect(x).toBeLessThan(4);
    expect(z).toBeCloseTo(2.3, 6);
  });

  it("lets a walker through the doorway neck and keeps them in it", () => {
    expect(clampToWalkable([3.9, 2], [4.2, 2], [twoRooms])).toEqual([4.2, 2]);
    expect(clampToWalkable([5.9, 2], [6.2, 2], [twoRooms])).toEqual([6.2, 2]);
    // Walking into the neck's side wall slides along it.
    const [x, z] = clampToWalkable([5, 2.4], [5.2, 2.7], [twoRooms]);
    expect(z).toBeLessThan(2.5);
    expect(x).toBeCloseTo(5.2, 6);
    expect(insideAny([x, z], [twoRooms])).toBe(true);
  });

  it("never leaves the walkable area from the corner where the neck meets the room", () => {
    const [x, z] = clampToWalkable([4.05, 1.55], [3.9, 1.3], [twoRooms]);
    expect(insideAny([x, z], [twoRooms])).toBe(true);
  });

  it("holds on the fixture's own walkable outline, through its doorway", () => {
    const scene = JSON.parse(readFileSync(resolve(import.meta.dirname, "../public/fixture/scene.json"), "utf8"));
    const polys = scene.walkable.polygons as Polygon[];
    expect(insideAny([0, 0], polys)).toBe(true);
    expect(insideAny([2.6, 0], polys)).toBe(true);
    expect(insideAny([2.6, -1.2], polys)).toBe(false);
    let p: [number, number] = [0, 0];
    for (let i = 0; i < 400; i++) {
      p = clampToWalkable(p, [p[0] + 0.02, p[1] - 0.01], polys);
      expect(insideAny(p, polys)).toBe(true);
    }
  });
});
