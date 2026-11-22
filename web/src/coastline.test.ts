import { describe, expect, it } from "vitest";
import { jitterPolyline } from "./coastline.ts";

describe("jitterPolyline", () => {
  const line = [[0, 0], [1, 0], [1, 1]] as const;

  it("keeps the hand within the jitter and the ends where they were", () => {
    const j = jitterPolyline(line, 0.002, 7);
    expect(j[0][0]).toBeCloseTo(0, 2);
    expect(j[j.length - 1]).toEqual([1, 1]);
    for (const [x, z] of j) {
      const off = z <= 0.0021 && x <= 1 ? Math.abs(z) : Math.abs(x - 1);
      expect(off).toBeLessThanOrEqual(0.0021);
    }
  });

  it("draws the same line for the same seed and a different one for another", () => {
    expect(jitterPolyline(line, 0.002, 7)).toEqual(jitterPolyline(line, 0.002, 7));
    expect(jitterPolyline(line, 0.002, 8)).not.toEqual(jitterPolyline(line, 0.002, 7));
  });

  it("samples about every 2 cm", () => {
    expect(jitterPolyline(line, 0.002, 7).length).toBe(101);
  });
});
