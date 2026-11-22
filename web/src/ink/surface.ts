import { PEN } from "./pen.ts";

/**
 * Whether a pixel's depth belongs to one surface. The G-buffer's depth is every splat's depth
 * blended by its share of the pixel, so where a thin measured veil lets the imagined world show
 * through, or imagined splats lie in layers, it is a depth nothing sits at, and it jumps by a metre
 * between neighbouring pixels. Strokes laid on it in world space pack into solid ink, and every
 * jump reads as a crease. Hatching and creases are drawn only where a surface is found.
 * surface.test.ts holds these and the GLSL together.
 */

/** Samples per side of the square grid around a pixel that the surface weight averages. */
export const SURFACE_GRID = 5;

const smoothstep = (e0: number, e1: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
};

/** Zero on any plane, at any angle: on a plane, 1 / view depth is affine in screen position. */
export function inverseDepthCurvature(zA: number, zCentre: number, zB: number): number {
  const i0 = 1 / zCentre;
  return Math.abs(1 / zA + 1 / zB - 2 * i0) / i0;
}

/** Depths are view depths in metres; null where the pixel is not covered, which is no evidence either way. */
export function roughness(zCentre: number | null, pairs: readonly (readonly [number | null, number | null])[]): number {
  if (zCentre === null) return 0;
  let worst = 0;
  for (const [a, b] of pairs) {
    if (a === null || b === null) continue;
    worst = Math.max(worst, inverseDepthCurvature(a, zCentre, b));
  }
  return smoothstep(PEN.roughFrom, PEN.roughTo, worst);
}

/** 1 where the grid around a pixel is a surface, 0 where most of it is rough. */
export function surfaceWeight(samples: readonly number[]): number {
  const mean = samples.reduce((s, v) => s + v, 0) / samples.length;
  return 1 - smoothstep(PEN.layeredFrom, PEN.layeredTo, mean);
}

/** For the strength pass, after DECODE and CLEAN: roughness at a data pixel, from the cleaned depth. */
export const ROUGHNESS_GLSL = /* glsl */ `
uniform int roughStride;
float invDepthAt(ivec2 q) {
  vec4 c = texelFetch(cTex, clampPx(q), 0);
  return c.r >= 0.5 ? 1.0 / cleanViewZ(c) : -1.0;
}
float roughness(ivec2 p) {
  float i0 = invDepthAt(p);
  if (i0 < 0.0) return 0.0;
  float worst = 0.0;
  for (int k = 0; k < 4; k++) {
    ivec2 e = roughStride * (k == 0 ? ivec2(1, 0) : (k == 1 ? ivec2(0, 1) : (k == 2 ? ivec2(1, 1) : ivec2(1, -1))));
    float ia = invDepthAt(p + e), ib = invDepthAt(p - e);
    if (ia < 0.0 || ib < 0.0) continue;
    worst = max(worst, abs(ia + ib - 2.0 * i0) / i0);
  }
  return smoothstep(${PEN.roughFrom.toFixed(4)}, ${PEN.roughTo.toFixed(4)}, worst);
}
`;

const HALF = (SURFACE_GRID - 1) / 2;

/** For the composite pass, after DECODE: the surface weight from the roughness the strength pass left in alpha. */
export const SURFACE_GLSL = /* glsl */ `
uniform highp sampler2D roughTex;
uniform int surfaceStep;
float surfaceWeight(ivec2 p) {
  float acc = 0.0;
  for (int j = -${HALF}; j <= ${HALF}; j++)
    for (int i = -${HALF}; i <= ${HALF}; i++)
      acc += texelFetch(roughTex, clampPx(p + surfaceStep * ivec2(i, j)), 0).a;
  return 1.0 - smoothstep(${PEN.layeredFrom.toFixed(4)}, ${PEN.layeredTo.toFixed(4)}, acc / ${(SURFACE_GRID * SURFACE_GRID).toFixed(1)});
}
`;
