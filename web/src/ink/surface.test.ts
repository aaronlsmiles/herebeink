import { describe, expect, it } from "vitest";
import { inverseDepthCurvature, roughness, SURFACE_GRID, SURFACE_GLSL, ROUGHNESS_GLSL, surfaceWeight } from "./surface.ts";
import { PEN } from "./pen.ts";

/** View depths along a screen row for a plane: on any plane, 1 / depth is affine in screen position. */
const plane = (z0: number, z1: number, n: number) => Array.from({ length: n }, (_, i) => 1 / (1 / z0 + ((1 / z1 - 1 / z0) * i) / (n - 1)));

describe("roughness", () => {
  it("is zero on a flat wall, however steeply it is seen", () => {
    // Face on, oblique, and nearly edge-on (the hallway wall through the doorway: 3.6 m to 2.9 m in ten pixels).
    for (const [z0, z1] of [[2.87, 2.87], [2.0, 4.0], [3.61, 2.92]]) {
      const z = plane(z0, z1, 11);
      expect(inverseDepthCurvature(z[3], z[5], z[7])).toBeCloseTo(0, 9);
      expect(roughness(z[5], [[z[3], z[7]]])).toBe(0);
    }
  });

  it("is full where a thin measured veil and the imagined world behind it blend into one depth", () => {
    // The left jamb at the start view: a veil at 1.6 m over imagined splats at 3.1 to 4.4 m.
    expect(roughness(2.7, [[3.7, 2.4]])).toBe(1);
    expect(roughness(3.1, [[4.4, 3.5], [3.0, 3.8]])).toBe(1);
  });

  it("takes the roughest direction", () => {
    expect(roughness(3, [[3, 3], [1.6, 4.4]])).toBe(1);
  });

  it("ignores a pair that reaches an uncovered pixel: no evidence either way", () => {
    expect(roughness(3, [[null, 3], [3, 3]])).toBe(0);
    expect(roughness(null, [[1.6, 4.4]])).toBe(0);
  });
});

describe("surfaceWeight", () => {
  const n = SURFACE_GRID * SURFACE_GRID;
  const grid = (rough: (i: number, j: number) => number) => {
    const s: number[] = [];
    for (let j = 0; j < SURFACE_GRID; j++) for (let i = 0; i < SURFACE_GRID; i++) s.push(rough(i, j));
    return s;
  };

  it("keeps every stroke on a smooth surface", () => {
    expect(surfaceWeight(new Array(n).fill(0))).toBe(1);
  });

  it("keeps the strokes beside a real corner, which is rough only along its line", () => {
    expect(surfaceWeight(grid((i) => (i === 2 ? 1 : 0)))).toBe(1);
  });

  it("draws nothing over a patch where no single surface lies", () => {
    expect(surfaceWeight(new Array(n).fill(1))).toBe(0);
    // Streaky layering: rough in most columns, smooth in a few between them.
    expect(surfaceWeight(grid((i) => (i % 3 === 0 ? 0 : 1)))).toBe(0);
  });

  it("fades between the two, never stepping", () => {
    const half = surfaceWeight(grid((i, j) => ((i + j) % 3 === 0 ? 1 : 0)));
    expect(half).toBeGreaterThan(0);
    expect(half).toBeLessThan(1);
  });
});

describe("the GLSL", () => {
  it("carries the same thresholds and grid", () => {
    expect(ROUGHNESS_GLSL).toContain(`smoothstep(${PEN.roughFrom.toFixed(4)}, ${PEN.roughTo.toFixed(4)}, worst)`);
    expect(ROUGHNESS_GLSL).toContain("abs(ia + ib - 2.0 * i0) / i0");
    expect(SURFACE_GLSL).toContain(`smoothstep(${PEN.layeredFrom.toFixed(4)}, ${PEN.layeredTo.toFixed(4)}, acc / ${(SURFACE_GRID * SURFACE_GRID).toFixed(1)})`);
    expect(SURFACE_GLSL).toContain(`for (int j = -${(SURFACE_GRID - 1) / 2}; j <= ${(SURFACE_GRID - 1) / 2}; j++)`);
  });
});
