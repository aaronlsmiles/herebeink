import * as THREE from "three";
import { clampToWalkable, type Polygon } from "./geometry.ts";
import { TouchWalk } from "./walk-touch.ts";

/** Radians; yaw about +y with 0 looking along -z, pitch up positive (scene.json's convention). */
export interface WalkPose {
  position: THREE.Vector3;
  yaw: number;
  pitch: number;
}

/**
 * What every way of walking provides: desktop keys and mouse here, touch and gyro, and a headset
 * each implement it. The frame loop calls update(dt) then reads pose(); nothing else is shared.
 */
export interface WalkController {
  update(dt: number): void;
  pose(): Readonly<WalkPose>;
  /** Jump to a pose (film mode, ?pose=, tests); the clamp still applies on the next step. */
  setPose(p: { position: THREE.Vector3Like; yaw: number; pitch: number }): void;
  /** Start taking input (the "Walk in" button). */
  engage(): void;
  dispose(): void;
}

export interface WalkSpace {
  walkable: Polygon[];
  /** Eye height above the floor plane, world y of the eye. */
  eyeY: number;
}

export const WALK_SPEED = 1.4;
export const RUN_SPEED = 2.8;
export const TURN_RATE = Math.PI / 2;
const LOOK_PER_PX = 0.0022;
const PITCH_LIMIT = THREE.MathUtils.degToRad(85);

export function applyPose(camera: THREE.Camera, p: Readonly<WalkPose>) {
  camera.position.copy(p.position);
  camera.rotation.set(p.pitch, p.yaw, 0, "YXZ");
  camera.updateMatrixWorld();
}

/** One step on the floor: forward and right in metres, clamped to the walkable outline. */
export function stepOnFloor(pose: WalkPose, forward: number, right: number, space: WalkSpace) {
  const s = Math.sin(pose.yaw), c = Math.cos(pose.yaw);
  const nx = pose.position.x - s * forward + c * right;
  const nz = pose.position.z - c * forward - s * right;
  const [x, z] = clampToWalkable([pose.position.x, pose.position.z], [nx, nz], space.walkable);
  pose.position.set(x, space.eyeY, z);
}

type Key = "fwd" | "back" | "left" | "right" | "turnL" | "turnR" | "run";
const KEYS: Record<string, Key> = {
  KeyW: "fwd", ArrowUp: "fwd", KeyS: "back", ArrowDown: "back",
  KeyA: "left", KeyD: "right", ArrowLeft: "turnL", ArrowRight: "turnR",
  ShiftLeft: "run", ShiftRight: "run",
};

/** Pointer lock for looking; WASD and the arrows for walking, left and right arrows to turn. */
export class DesktopWalk implements WalkController {
  private readonly p: WalkPose;
  private readonly held = new Set<Key>();
  private engaged = false;
  private readonly ac = new AbortController();

  constructor(private readonly element: HTMLElement, private readonly space: WalkSpace, start: { position: THREE.Vector3Like; yaw: number; pitch: number }) {
    this.p = { position: new THREE.Vector3(), yaw: 0, pitch: 0 };
    this.setPose(start);
    const signal = this.ac.signal;
    window.addEventListener("keydown", (e) => this.key(e, true), { signal });
    window.addEventListener("keyup", (e) => this.key(e, false), { signal });
    window.addEventListener("blur", () => this.held.clear(), { signal });
    document.addEventListener("mousemove", (e) => {
      if (document.pointerLockElement !== this.element) return;
      this.p.yaw -= e.movementX * LOOK_PER_PX;
      this.p.pitch = THREE.MathUtils.clamp(this.p.pitch - e.movementY * LOOK_PER_PX, -PITCH_LIMIT, PITCH_LIMIT);
    }, { signal });
    element.addEventListener("click", () => { if (this.engaged) this.lock(); }, { signal });
  }

  private key(e: KeyboardEvent, down: boolean) {
    const k = KEYS[e.code];
    if (!k || !this.engaged) return;
    // Keys belong to the page's buttons while one has focus, except when walking in pointer lock.
    const t = e.target as HTMLElement | null;
    if (document.pointerLockElement !== this.element && t && t !== document.body && t !== this.element) return;
    if (down) this.held.add(k);
    else this.held.delete(k);
    e.preventDefault();
  }

  private lock() {
    // Pointer lock can be refused (an iframe, a browser setting); the keys still walk.
    const r = this.element.requestPointerLock?.() as Promise<void> | undefined;
    r?.catch?.(() => {});
  }

  engage() {
    this.engaged = true;
    this.element.focus({ preventScroll: true });
    this.lock();
  }

  update(dt: number) {
    const h = this.held;
    const turn = (h.has("turnL") ? 1 : 0) - (h.has("turnR") ? 1 : 0);
    this.p.yaw += turn * TURN_RATE * dt;
    const fwd = (h.has("fwd") ? 1 : 0) - (h.has("back") ? 1 : 0);
    const right = (h.has("right") ? 1 : 0) - (h.has("left") ? 1 : 0);
    if (fwd === 0 && right === 0) return;
    const speed = (h.has("run") ? RUN_SPEED : WALK_SPEED) * dt / Math.hypot(fwd, right);
    stepOnFloor(this.p, fwd * speed, right * speed, this.space);
  }

  pose(): Readonly<WalkPose> {
    return this.p;
  }

  setPose(s: { position: THREE.Vector3Like; yaw: number; pitch: number }) {
    this.p.position.set(s.position.x, this.space.eyeY, s.position.z);
    this.p.yaw = s.yaw;
    this.p.pitch = THREE.MathUtils.clamp(s.pitch, -PITCH_LIMIT, PITCH_LIMIT);
  }

  dispose() {
    this.ac.abort();
    if (document.pointerLockElement === this.element) document.exitPointerLock();
  }
}

export type WalkMode = "desktop" | "touch";

/** Coarse pointers (a phone or tablet) get the touch controller; ?walk= overrides either way. */
export function walkModeFor(requested: WalkMode | null, coarsePointer: boolean): WalkMode {
  return requested ?? (coarsePointer ? "touch" : "desktop");
}

/** The seam for ways of walking: desktop keys and mouse, or touch and gyro. WebXR has its own (walk-xr.ts). */
export function createWalk(element: HTMLElement, space: WalkSpace, start: { position: THREE.Vector3Like; yaw: number; pitch: number }, mode: WalkMode = walkModeFor(null, window.matchMedia?.("(pointer: coarse)").matches ?? false)): WalkController {
  return mode === "touch" ? new TouchWalk(element, space, start) : new DesktopWalk(element, space, start);
}
