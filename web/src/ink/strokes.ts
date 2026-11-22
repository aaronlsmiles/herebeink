/**
 * The ink a hatch leaves on average once its strokes are packed too close to draw one by one.
 * Strokes are spaced on the surface, so a surface seen nearly edge-on, or a depth that jumps
 * between neighbouring pixels, packs them below a pixel; their true mean would then run to solid
 * black. A pen keeps the tone instead and lays fewer strokes, so the mean is held at the closest
 * spacing that can still be drawn. strokes.test.ts holds the two versions together.
 */
export function hatchMeanInk(spacingPx: number, widthPx: number, minPx: number): number {
  return Math.min(1, Math.max(0, (0.84 * widthPx) / Math.max(spacingPx, minPx)));
}

export const HATCH_MEAN_GLSL = /* glsl */ `
float hatchMean(float spacingPx, float widthPx, float minPx) {
  return clamp(0.84 * widthPx / max(spacingPx, minPx), 0.0, 1.0);
}
`;
