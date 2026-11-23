import { describe, expect, it } from "vitest";
import type { Vec3 } from "../contract.ts";
import { axes, corners, planSpan, wedgeSegments } from "./frustums.ts";

const f = { forward: [1, 0, 0] as Vec3, up: [0, 1, 0] as Vec3, hFovDeg: 66, vFovDeg: 51.94 };
const c: Vec3 = [0, 1.6, 0];
const deg = (r: number) => (r * 180) / Math.PI;

describe("frustum wedges", () => {
  it("builds square axes, right of forward with up above", () => {
    const a = axes({ ...f, up: [0.02, 1, 0] });
    expect(a.right[2]).toBeCloseTo(1);
    expect(a.up[0]).toBeCloseTo(0);
    expect(a.up[1]).toBeCloseTo(1);
  });

  it("puts the frame's corners on the field of view's edges", () => {
    const [tl, tr, br] = corners(f, c, 1);
    expect(tl[0]).toBeCloseTo(1);
    expect(deg(Math.atan2(tr[2], tr[0]))).toBeCloseTo(33);
    expect(deg(Math.atan2(tl[2], tl[0]))).toBeCloseTo(-33);
    expect(deg(Math.atan2(tr[1] - c[1], 1))).toBeCloseTo(25.97);
    expect(br[1]).toBeLessThan(c[1]);
  });

  it("draws four rays from the camera point and the frame's four sides", () => {
    const s = wedgeSegments(f, c);
    expect(s).toHaveLength(8);
    expect(s.slice(0, 4).every(([a]) => a === c)).toBe(true);
    expect(s[7][1]).toEqual(s[4][0]);
  });

  it("spans the photo's width on the plan, either side of where it faces", () => {
    const [a, b] = planSpan({ ...f, forward: [0, 0, -1] }, c, 2);
    expect(a[0]).toEqual([0, 0]);
    expect(deg(Math.atan2(a[1][1], a[1][0]))).toBeCloseTo(-123);
    expect(deg(Math.atan2(b[1][1], b[1][0]))).toBeCloseTo(-57);
  });
});
