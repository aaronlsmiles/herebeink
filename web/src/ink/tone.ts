import { PEN } from "./pen.ts";

export type Vec3 = readonly [number, number, number];
/** 0 paper, 1 single hatch at 45°, 2 cross-hatch (45° and 135°). */
export type ToneLevel = 0 | 1 | 2;

/**
 * How lit a surface is: `n` faces the viewer (splat normals have no outside, so the G-buffer flips
 * them towards the camera); `lightTravel` is scene.json's light.direction, the way the light goes,
 * so the light comes from its negative.
 */
export function litAmount(n: Vec3, lightTravel: Vec3): number {
  const ln = Math.hypot(...lightTravel) || 1;
  const nn = Math.hypot(...n) || 1;
  const d = -(n[0] * lightTravel[0] + n[1] * lightTravel[1] + n[2] * lightTravel[2]) / (ln * nn);
  return Math.min(1, Math.max(0, d));
}

export function toneLevel(n: Vec3, lightTravel: Vec3): ToneLevel {
  const lit = litAmount(n, lightTravel);
  return lit > PEN.toneLight ? 0 : lit > PEN.toneMid ? 1 : 2;
}

/** The same rule in GLSL, for the present pass; tone.test.ts holds the two together. */
export const TONE_GLSL = /* glsl */ `
float litAmount(vec3 n, vec3 lightTravel) {
  return clamp(-dot(normalize(n), normalize(lightTravel)), 0.0, 1.0);
}
int toneLevel(vec3 n, vec3 lightTravel) {
  float lit = litAmount(n, lightTravel);
  return lit > ${PEN.toneLight.toFixed(4)} ? 0 : (lit > ${PEN.toneMid.toFixed(4)} ? 1 : 2);
}
`;
