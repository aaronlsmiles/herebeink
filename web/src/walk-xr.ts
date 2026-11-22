import * as THREE from "three";
import { clampToWalkable, type Polygon } from "./geometry.ts";
import { WALK_SPEED, type WalkController, type WalkPose } from "./walk.ts";

// Walking in a headset. The page moves a rig (a group the camera sits in); the headset supplies
// the head's own pose inside it, so the rig is the thing the walkable clamp applies to.

export const STICK_DEAD = 0.15;
export const SNAP_TURN_RAD = THREE.MathUtils.degToRad(30);
/** A snap fires past this deflection and re-arms once the stick is back under the release level. */
export const SNAP_FIRE = 0.7;
export const SNAP_RELEASE = 0.3;

export type Stick = readonly [number, number];

/** Where the rig stands: x, z in metres, yaw in radians about +y (0 looks along -z). */
export interface RigPose { x: number; z: number; yaw: number }

/** An xr-standard thumbstick is axes 2 and 3; some pads report it as 0 and 1. Up is negative y. */
export function stickAxes(axes: readonly number[] | undefined): Stick {
  if (!axes) return [0, 0];
  return axes.length >= 4 ? [axes[2] ?? 0, axes[3] ?? 0] : [axes[0] ?? 0, axes[1] ?? 0];
}

/** World velocity in m/s (x, z) for a stick pushed relative to where the head looks. */
export function stickToWorldVelocity(stick: Stick, headYaw: number, speed = WALK_SPEED): [number, number] {
  const mag = Math.hypot(stick[0], stick[1]);
  if (mag <= STICK_DEAD) return [0, 0];
  // Rescale so the dead zone's edge is zero speed and a full push is a full walk.
  const scale = Math.min(1, (mag - STICK_DEAD) / (1 - STICK_DEAD)) * speed / mag;
  const right = stick[0] * scale;
  const forward = -stick[1] * scale;
  const s = Math.sin(headYaw), c = Math.cos(headYaw);
  return [-s * forward + c * right, -c * forward - s * right];
}

/** Yaw of a world-space viewing direction, the same convention as the walk's pose. */
export function yawOfDirection(dx: number, dz: number, fallback: number): number {
  return Math.hypot(dx, dz) < 1e-4 ? fallback : Math.atan2(-dx, -dz);
}

export class SnapTurn {
  private armed = true;

  /** Radians to add to the yaw for this stick reading: stick right turns right (yaw falls). */
  next(x: number): number {
    if (Math.abs(x) < SNAP_RELEASE) { this.armed = true; return 0; }
    if (!this.armed || Math.abs(x) < SNAP_FIRE) return 0;
    this.armed = false;
    return x > 0 ? -SNAP_TURN_RAD : SNAP_TURN_RAD;
  }
}

/** Turns the rig about the head's floor point, so the view turns without the head sliding. */
export function turnAboutHead(rig: RigPose, headX: number, headZ: number, dYaw: number): RigPose {
  const s = Math.sin(dYaw), c = Math.cos(dYaw);
  const rx = rig.x - headX, rz = rig.z - headZ;
  return { x: headX + c * rx + s * rz, z: headZ - s * rx + c * rz, yaw: rig.yaw + dYaw };
}

export interface XrInput { left: Stick; right: Stick }
export interface HeadPose { x: number; z: number; yaw: number }

/** The locomotion state and rules, with no WebXR in it: tests drive this directly. */
export class XrLocomotion {
  readonly rig: RigPose;
  private readonly snap = new SnapTurn();

  constructor(private readonly walkable: readonly Polygon[], start: RigPose) {
    this.rig = { ...start };
  }

  step(dt: number, input: XrInput, head: HeadPose) {
    const turn = this.snap.next(input.right[0]);
    if (turn !== 0) Object.assign(this.rig, this.clamp(turnAboutHead(this.rig, head.x, head.z, turn)));
    const [vx, vz] = stickToWorldVelocity(input.left, head.yaw + turn);
    if (vx === 0 && vz === 0) return;
    const [x, z] = clampToWalkable([this.rig.x, this.rig.z], [this.rig.x + vx * dt, this.rig.z + vz * dt], this.walkable);
    this.rig.x = x;
    this.rig.z = z;
  }

  /** A turn that carries the rig origin out of the walkable area slides it back in, like a step. */
  private clamp(p: RigPose): RigPose {
    const [x, z] = clampToWalkable([this.rig.x, this.rig.z], [p.x, p.z], this.walkable);
    return { x, z, yaw: p.yaw };
  }
}

/** What the viewer lends the controller each frame: the session's inputs and the head's world pose. */
export interface XrSource {
  inputs(): XrInput;
  head(): HeadPose | null;
}

/** The viewer's rig takes its pose from pose(); position.y is the scene's floor, since the headset measures height from it. */
export class XrWalk implements WalkController {
  private readonly loco: XrLocomotion;
  private readonly out: WalkPose = { position: new THREE.Vector3(), yaw: 0, pitch: 0 };
  private lastYaw = 0;

  constructor(private readonly source: XrSource, walkable: readonly Polygon[], private readonly floorY: number, start: { position: THREE.Vector3Like; yaw: number }) {
    this.loco = new XrLocomotion(walkable, { x: start.position.x, z: start.position.z, yaw: start.yaw });
    this.lastYaw = start.yaw;
    this.sync();
  }

  private sync() {
    const r = this.loco.rig;
    this.out.position.set(r.x, this.floorY, r.z);
    this.out.yaw = r.yaw;
  }

  update(dt: number) {
    const head = this.source.head() ?? { x: this.loco.rig.x, z: this.loco.rig.z, yaw: this.lastYaw };
    this.lastYaw = head.yaw;
    this.loco.step(dt, this.source.inputs(), head);
    this.sync();
  }

  pose(): Readonly<WalkPose> {
    return this.out;
  }

  setPose(p: { position: THREE.Vector3Like; yaw: number }) {
    this.loco.rig.x = p.position.x;
    this.loco.rig.z = p.position.z;
    this.loco.rig.yaw = p.yaw;
    this.sync();
  }

  engage() {}
  dispose() {}
}

/** Thumbsticks and the head's pose out of a live three.js XR session. */
export function sessionSource(xr: THREE.WebXRManager): XrSource {
  const dir = new THREE.Vector3();
  const pos = new THREE.Vector3();
  let lastYaw = 0;
  return {
    inputs() {
      const out = { left: [0, 0] as Stick, right: [0, 0] as Stick };
      for (const src of xr.getSession()?.inputSources ?? []) {
        const axes = stickAxes(src.gamepad?.axes);
        if (src.handedness === "left") out.left = axes;
        else if (src.handedness === "right") out.right = axes;
      }
      return out;
    },
    head() {
      if (!xr.isPresenting) return null;
      const cam = xr.getCamera();
      cam.getWorldPosition(pos);
      cam.getWorldDirection(dir);
      lastYaw = yawOfDirection(dir.x, dir.z, lastYaw);
      return { x: pos.x, z: pos.z, yaw: lastYaw };
    },
  };
}
