import { describe, expect, it } from "vitest";
import { SNAP_TURN_RAD, SnapTurn, STICK_DEAD, stickAxes, stickToWorldVelocity, turnAboutHead, XrLocomotion, yawOfDirection } from "./walk-xr.ts";
import { WALK_SPEED } from "./walk.ts";

const room = [[[-2, -2], [2, -2], [2, 2], [-2, 2]] as [number, number][]];
const deg = (r: number) => (r * 180) / Math.PI;

describe("stickAxes", () => {
  it("reads the xr-standard thumbstick from axes 2 and 3, or a two-axis pad from 0 and 1", () => {
    expect(stickAxes([0, 0, 0.5, -0.25])).toEqual([0.5, -0.25]);
    expect(stickAxes([0.1, 0.2])).toEqual([0.1, 0.2]);
    expect(stickAxes(undefined)).toEqual([0, 0]);
  });
});

describe("stickToWorldVelocity", () => {
  it("pushes forward along the head's heading: -z at yaw 0, +x at yaw -90", () => {
    const a = stickToWorldVelocity([0, -1], 0);
    expect(a[0]).toBeCloseTo(0, 9);
    expect(a[1]).toBeCloseTo(-WALK_SPEED, 9);
    const b = stickToWorldVelocity([0, -1], -Math.PI / 2);
    expect(b[0]).toBeCloseTo(WALK_SPEED, 9);
    expect(b[1]).toBeCloseTo(0, 9);
  });
  it("strafes right of the head, and walks backwards for a pull", () => {
    const r = stickToWorldVelocity([1, 0], 0);
    expect(r[0]).toBeCloseTo(WALK_SPEED, 9);
    expect(stickToWorldVelocity([0, 1], 0)[1]).toBeGreaterThan(0);
  });
  it("has a dead zone, scales up from it, and never exceeds a walk on a diagonal", () => {
    expect(stickToWorldVelocity([STICK_DEAD * 0.9, 0], 0)).toEqual([0, 0]);
    const mid = stickToWorldVelocity([0, -(STICK_DEAD + 1) / 2], 0);
    expect(Math.hypot(...mid)).toBeCloseTo(WALK_SPEED / 2, 9);
    expect(Math.hypot(...stickToWorldVelocity([1, -1], 0.7))).toBeCloseTo(WALK_SPEED, 9);
  });
});

describe("SnapTurn", () => {
  it("turns 30 degrees once per push, right for right, and needs the stick back near centre to go again", () => {
    const s = new SnapTurn();
    expect(deg(s.next(0.9))).toBeCloseTo(-30, 9);
    expect(s.next(0.95)).toBe(0);
    expect(s.next(0.5)).toBe(0); // eased but not released
    expect(s.next(0.9)).toBe(0);
    expect(s.next(0.1)).toBe(0);
    expect(deg(s.next(-0.9))).toBeCloseTo(30, 9);
  });
  it("ignores a light touch", () => {
    expect(new SnapTurn().next(0.6)).toBe(0);
  });
});

describe("turnAboutHead", () => {
  const worldOfHead = (rig: { x: number; z: number; yaw: number }, local: [number, number]) => {
    const s = Math.sin(rig.yaw), c = Math.cos(rig.yaw);
    return [rig.x + c * local[0] + s * local[1], rig.z - s * local[0] + c * local[1]];
  };
  it("keeps the head where it stands while the view turns", () => {
    const rig = { x: 1, z: -0.5, yaw: 0.4 };
    const local: [number, number] = [0.3, -0.2];
    const [hx, hz] = worldOfHead(rig, local);
    const turned = turnAboutHead(rig, hx, hz, SNAP_TURN_RAD);
    const [hx2, hz2] = worldOfHead(turned, local);
    expect(hx2).toBeCloseTo(hx, 9);
    expect(hz2).toBeCloseTo(hz, 9);
    expect(turned.yaw).toBeCloseTo(0.4 + SNAP_TURN_RAD, 9);
  });
});

describe("yawOfDirection", () => {
  it("is 0 looking along -z and -90 degrees looking along +x, and holds the last yaw looking straight up", () => {
    expect(yawOfDirection(0, -1, 9)).toBeCloseTo(0, 9);
    expect(deg(yawOfDirection(1, 0, 9))).toBeCloseTo(-90, 9);
    expect(yawOfDirection(0, 0, 1.25)).toBe(1.25);
  });
});

describe("XrLocomotion", () => {
  const still = { left: [0, 0], right: [0, 0] } as const;
  it("walks the rig along the head's heading at a walk and stops at the wall", () => {
    const l = new XrLocomotion(room, { x: 0, z: 0, yaw: 0 });
    l.step(1, { left: [0, -1], right: [0, 0] }, { x: 0, z: 0, yaw: -Math.PI / 2 });
    expect(l.rig.x).toBeCloseTo(WALK_SPEED, 9);
    expect(l.rig.z).toBeCloseTo(0, 9);
    for (let i = 0; i < 5; i++) l.step(1, { left: [0, -1], right: [0, 0] }, { x: l.rig.x, z: 0, yaw: -Math.PI / 2 });
    expect(l.rig.x).toBeLessThan(2);
    expect(l.rig.x).toBeGreaterThan(1.99);
  });
  it("snap-turns about the head and still obeys the clamp", () => {
    const l = new XrLocomotion(room, { x: 1.9, z: 0, yaw: 0 });
    l.step(0.011, { left: [0, 0], right: [1, 0] }, { x: 1.9 + 1.5, z: 0, yaw: 0 });
    expect(l.rig.yaw).toBeCloseTo(-SNAP_TURN_RAD, 9);
    expect(l.rig.x).toBeLessThanOrEqual(2);
    expect(Math.abs(l.rig.z)).toBeLessThanOrEqual(2);
  });
  it("does not move on a resting stick", () => {
    const l = new XrLocomotion(room, { x: 0.5, z: 0.5, yaw: 1 });
    l.step(1, still, { x: 0, z: 0, yaw: 1 });
    expect(l.rig).toEqual({ x: 0.5, z: 0.5, yaw: 1 });
  });
});
