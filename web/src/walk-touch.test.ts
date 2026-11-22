import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { clampOrigin, GESTURE_BAR_PX, GyroTracker, gyroToYawPitch, JOY_DEAD_PX, JOY_RADIUS_PX, joystickVector, lookDelta, tiltUnavailableText, wrapAngle } from "./walk-touch.ts";

const deg = (r: number) => (r * 180) / Math.PI;

describe("joystickVector", () => {
  const o: [number, number] = [100, 400];
  it("is still inside the dead zone", () => {
    expect(joystickVector(o, [100 + JOY_DEAD_PX - 1, 400]).magnitude).toBe(0);
  });
  it("pushes forward for a thumb up the screen and right for a thumb to the right", () => {
    const up = joystickVector(o, [100, 400 - JOY_RADIUS_PX]);
    expect(up.forward).toBeCloseTo(1, 6);
    expect(up.right).toBeCloseTo(0, 6);
    const right = joystickVector(o, [100 + JOY_RADIUS_PX, 400]);
    expect(right.right).toBeCloseTo(1, 6);
    expect(right.forward).toBeCloseTo(0, 6);
    expect(joystickVector(o, [100, 450]).forward).toBeLessThan(0);
  });
  it("is proportional between the dead zone and the ring, and capped beyond it", () => {
    const mid = joystickVector(o, [100, 400 - (JOY_DEAD_PX + JOY_RADIUS_PX) / 2]);
    expect(mid.magnitude).toBeCloseTo(0.5, 6);
    expect(joystickVector(o, [100, 400 - 500]).magnitude).toBe(1);
  });
});

describe("lookDelta", () => {
  it("turns right for a drag right and up for a drag up", () => {
    const d = lookDelta(100, 0);
    expect(d.dYaw).toBeLessThan(0);
    expect(d.dPitch).toBeCloseTo(0, 12);
    expect(lookDelta(0, -50).dPitch).toBeGreaterThan(0);
    expect(lookDelta(-100, 0).dYaw).toBeCloseTo(-d.dYaw, 9);
  });
});

describe("clampOrigin", () => {
  const inset = { top: 59, right: 0, bottom: 34, left: 0 };
  it("leaves a comfortable touch alone", () => {
    expect(clampOrigin([90, 500], 393, 852, inset)).toEqual([90, 500]);
  });
  it("keeps the whole ring clear of the gesture bar and the screen edge", () => {
    const [x, y] = clampOrigin([2, 850], 393, 852, inset);
    expect(y + JOY_RADIUS_PX).toBeLessThanOrEqual(852 - 34 - GESTURE_BAR_PX);
    expect(x - JOY_RADIUS_PX).toBeGreaterThanOrEqual(0);
  });
});

describe("gyroToYawPitch", () => {
  it("reads heading as yaw and tilt as pitch for a phone held upright in portrait", () => {
    expect(deg(gyroToYawPitch(0, 90, 0, 0).yaw)).toBeCloseTo(0, 6);
    expect(deg(gyroToYawPitch(90, 90, 0, 0).yaw)).toBeCloseTo(90, 6);
    expect(deg(gyroToYawPitch(0, 90, 0, 0).pitch)).toBeCloseTo(0, 6);
    expect(deg(gyroToYawPitch(0, 120, 0, 0).pitch)).toBeCloseTo(30, 6);
    expect(deg(gyroToYawPitch(0, 60, 0, 0).pitch)).toBeCloseTo(-30, 6);
  });
  // Readings for a phone held upright and looking straight ahead, turned in the plane of its screen:
  // derived from R = Rz(alpha) Rx(beta) Ry(gamma) for Rx(90 degrees) turned about the screen normal.
  it("landscape either way still looks straight ahead", () => {
    const ccw = gyroToYawPitch(90, 0, -90, 90);
    expect(deg(ccw.yaw)).toBeCloseTo(0, 6);
    expect(deg(ccw.pitch)).toBeCloseTo(0, 6);
    const cw = gyroToYawPitch(270, 0, 90, 270);
    expect(deg(cw.yaw)).toBeCloseTo(0, 6);
    expect(deg(cw.pitch)).toBeCloseTo(0, 6);
  });

  // Readings are built from the attitude
  // R = Rz(yaw) Rx(90 + pitch) Rz(screen angle) by the W3C Z-X'-Y'' inversion.
  it("recovers yaw and pitch when the phone is tilted in any screen orientation", () => {
    const rad = (d: number) => (d * Math.PI) / 180;
    const rz = (a: number) => new THREE.Matrix4().makeRotationZ(rad(a));
    const rx = (a: number) => new THREE.Matrix4().makeRotationX(rad(a));
    for (const angle of [0, 90, 270]) {
      for (const [yaw, pitch] of [[0, 30], [40, -20], [-120, 45], [170, 10]]) {
        const m = rz(yaw).multiply(rx(90 + pitch)).multiply(rz(angle)).elements;
        const at = (r: number, c: number) => m[c * 4 + r];
        const beta = Math.asin(at(2, 1));
        const alpha = Math.atan2(-at(0, 1), at(1, 1));
        const gamma = Math.atan2(-at(2, 0), at(2, 2));
        const got = gyroToYawPitch(deg(alpha), deg(beta), deg(gamma), angle);
        expect(deg(got.yaw)).toBeCloseTo(yaw, 4);
        expect(deg(got.pitch)).toBeCloseTo(pitch, 4);
      }
    }
  });
});

describe("GyroTracker", () => {
  it("reports yaw changes only, wrapped the short way round", () => {
    const g = new GyroTracker();
    expect(g.update(10, 90, 0, 0).dYaw).toBe(0);
    expect(deg(g.update(40, 90, 0, 0).dYaw)).toBeCloseTo(30, 6);
    const w = new GyroTracker();
    w.update(350, 90, 0, 0);
    expect(deg(w.update(10, 90, 0, 0).dYaw)).toBeCloseTo(20, 6);
    g.reset();
    expect(g.update(200, 90, 0, 0).dYaw).toBe(0);
  });
  it("wrapAngle folds into -pi..pi", () => {
    expect(wrapAngle(3 * Math.PI)).toBeCloseTo(Math.PI, 9);
    expect(wrapAngle(-Math.PI / 2)).toBeCloseTo(-Math.PI / 2, 9);
  });
});

describe("tiltUnavailableText", () => {
  it("offers tilting when the page can read the sensor", () => {
    expect(tiltUnavailableText({ hasSensorApi: true, secure: true })).toBeNull();
  });
  it("blames the plain-http page, not the phone, when the page is not secure", () => {
    // iOS hides the orientation API entirely on an http page, which looks like a phone with no sensor.
    expect(tiltUnavailableText({ hasSensorApi: false, secure: false })).toBe("Tilting needs the https page; drag to look");
    expect(tiltUnavailableText({ hasSensorApi: true, secure: false })).toBe("Tilting needs the https page; drag to look");
  });
  it("says there is no sensor only on a secure page without the API", () => {
    expect(tiltUnavailableText({ hasSensorApi: false, secure: true })).toBe("No tilt sensor; drag to look");
  });
});
