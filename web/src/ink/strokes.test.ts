import { describe, expect, it } from "vitest";
import { HATCH_MEAN_GLSL, hatchMeanInk } from "./strokes.ts";
import { PEN } from "./pen.ts";

describe("hatchMeanInk", () => {
  const atDpr = (dpr: number) => ({ width: PEN.hatchCssPx * dpr, min: PEN.hatchMinSpacingPx * dpr });

  it("is the strokes' own share of the paper while they can be told apart", () => {
    const { width, min } = atDpr(1);
    expect(hatchMeanInk(2 * min, width, min)).toBeCloseTo((0.84 * width) / (2 * min), 6);
  });

  it("holds the tone of the closest resolvable spacing when strokes pack tighter, as a pen lays fewer strokes", () => {
    for (const dpr of [1, 2, 3]) {
      const { width, min } = atDpr(dpr);
      const held = hatchMeanInk(min, width, min);
      for (const spacing of [min * 0.75, min / 2, 1, 0.25, 1e-3, 0]) {
        expect(hatchMeanInk(spacing, width, min)).toBeCloseTo(held, 6);
      }
    }
  });

  it("never fills a hatched surface solid, however steeply it is seen or however its depth jumps", () => {
    for (const dpr of [1, 2, 3]) {
      const { width, min } = atDpr(dpr);
      expect(hatchMeanInk(1e-6, width, min)).toBeLessThan(0.5);
    }
  });

  it("puts the same rule into the GLSL", () => {
    expect(HATCH_MEAN_GLSL).toContain("0.84 * widthPx / max(spacingPx, minPx)");
  });
});
