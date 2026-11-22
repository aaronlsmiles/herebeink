import { describe, expect, it } from "vitest";
import { litAmount, TONE_GLSL, toneLevel } from "./tone.ts";
import { PEN } from "./pen.ts";

// The fixture's light: in through the doorway (+x) and down.
const L = [-0.819152, -0.573576, -0.000297] as const;

describe("toneLevel", () => {
  it("leaves a wall facing the doorway as bare paper", () => {
    expect(litAmount([1, 0, 0], L)).toBeCloseTo(0.819, 3);
    expect(toneLevel([1, 0, 0], L)).toBe(0);
  });

  it("hatches the floor once", () => {
    expect(litAmount([0, 1, 0], L)).toBeCloseTo(0.574, 3);
    expect(toneLevel([0, 1, 0], L)).toBe(1);
  });

  it("cross-hatches a wall the light runs along", () => {
    expect(toneLevel([0, 0, 1], L)).toBe(2);
  });

  it("cross-hatches a face turned away from the light rather than lighting it from behind", () => {
    expect(litAmount([-1, 0, 0], L)).toBe(0);
    expect(toneLevel([-1, 0, 0], L)).toBe(2);
  });

  it("does not care about the length of either vector", () => {
    expect(toneLevel([0, 5, 0], [L[0] * 3, L[1] * 3, L[2] * 3])).toBe(1);
  });

  it("puts the same thresholds into the GLSL", () => {
    expect(TONE_GLSL).toContain(`lit > ${PEN.toneLight.toFixed(4)} ? 0`);
    expect(TONE_GLSL).toContain(`lit > ${PEN.toneMid.toFixed(4)} ? 1 : 2`);
    expect(TONE_GLSL).toContain("-dot(normalize(n), normalize(lightTravel))");
  });
});
