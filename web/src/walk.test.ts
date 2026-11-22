import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { stepOnFloor, walkModeFor, type WalkPose } from "./walk.ts";

const room = { walkable: [[[-2, -2], [2, -2], [2, 2], [-2, 2]] as [number, number][]], eyeY: 1.6 };
const pose = (yawDeg: number): WalkPose => ({ position: new THREE.Vector3(0, 1.6, 0), yaw: THREE.MathUtils.degToRad(yawDeg), pitch: 0 });

describe("stepOnFloor", () => {
  it("walks forward along -z at yaw 0 and along +x at yaw -90, as scene.json's angles say", () => {
    const a = pose(0);
    stepOnFloor(a, 1, 0, room);
    expect(a.position.z).toBeCloseTo(-1, 6);
    const b = pose(-90);
    stepOnFloor(b, 1, 0, room);
    expect(b.position.x).toBeCloseTo(1, 6);
    expect(b.position.z).toBeCloseTo(0, 6);
  });

  it("strafes right at yaw 0 towards +x and keeps the eye height", () => {
    const p = pose(0);
    p.position.y = 0.3;
    stepOnFloor(p, 0, 0.5, room);
    expect(p.position.x).toBeCloseTo(0.5, 6);
    expect(p.position.y).toBe(1.6);
  });

  it("stops at the walkable edge", () => {
    const p = pose(-90);
    stepOnFloor(p, 5, 0, room);
    expect(p.position.x).toBeLessThan(2);
    expect(p.position.x).toBeGreaterThan(1.99);
  });
});

describe("walkModeFor", () => {
  it("picks touch for a coarse pointer unless told otherwise", () => {
    expect(walkModeFor(null, true)).toBe("touch");
    expect(walkModeFor(null, false)).toBe("desktop");
    expect(walkModeFor("touch", false)).toBe("touch");
    expect(walkModeFor("desktop", true)).toBe("desktop");
  });
});
