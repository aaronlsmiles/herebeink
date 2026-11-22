import * as THREE from "three";
import { stepOnFloor, WALK_SPEED, type WalkController, type WalkPose, type WalkSpace } from "./walk.ts";

// Touch walking: a floating left-thumb joystick, drag to look anywhere else, optional gyro look.
// The pure parts (joystick vector, look deltas, gyro maths, safe-area clamp) are exported for tests.

export const JOY_RADIUS_PX = 56;
export const JOY_DEAD_PX = 8;
/** Radians per CSS pixel dragged; a finger sweeps a shorter arc than a mouse, so this is above the desktop's. */
export const LOOK_PER_PX_TOUCH = 0.0045;
const PITCH_LIMIT = THREE.MathUtils.degToRad(85);

export interface JoystickVector {
  /** Screen-right component, 0..1 scaled by how far past the dead zone the thumb is. */
  right: number;
  /** Walking-forward component; thumb up the screen is forward. */
  forward: number;
  /** 0 inside the dead zone, 1 at the ring's edge or beyond. */
  magnitude: number;
}

export function joystickVector(origin: readonly [number, number], touch: readonly [number, number], radius = JOY_RADIUS_PX, dead = JOY_DEAD_PX): JoystickVector {
  const dx = touch[0] - origin[0];
  const dy = touch[1] - origin[1];
  const d = Math.hypot(dx, dy);
  if (d <= dead) return { right: 0, forward: 0, magnitude: 0 };
  const magnitude = Math.min(1, (d - dead) / (radius - dead));
  return { right: (dx / d) * magnitude, forward: (-dy / d) * magnitude, magnitude };
}

/** Yaw and pitch change for a drag in CSS pixels; dragging right turns right, as the mouse does. */
export function lookDelta(dx: number, dy: number, perPx = LOOK_PER_PX_TOUCH) {
  return { dYaw: -dx * perPx, dPitch: -dy * perPx };
}

export interface SafeArea { top: number; right: number; bottom: number; left: number }

/**
 * Keeps a joystick that starts under a thumb inside the area the system leaves to the page, with
 * the whole ring clear of the gesture bar. Returned in CSS pixels.
 */
export function clampOrigin(p: readonly [number, number], width: number, height: number, inset: SafeArea, radius = JOY_RADIUS_PX, margin = 12): [number, number] {
  const minX = inset.left + radius + margin;
  const maxX = Math.max(minX, width - inset.right - radius - margin);
  const minY = inset.top + radius + margin;
  const maxY = Math.max(minY, height - inset.bottom - radius - margin - GESTURE_BAR_PX);
  return [Math.min(maxX, Math.max(minX, p[0])), Math.min(maxY, Math.max(minY, p[1]))];
}

/** Room above the safe-area inset for the home-indicator swipe, which the inset alone does not cover. */
export const GESTURE_BAR_PX = 16;

const ZEE = new THREE.Vector3(0, 0, 1);
const Q_BACK_CAMERA = new THREE.Quaternion(-Math.SQRT1_2, 0, 0, Math.SQRT1_2); // -90 degrees about X

/**
 * Camera yaw and pitch (radians; yaw about +y, pitch up positive) from a deviceorientation reading
 * and the screen's rotation angle. The reading is the W3C Z-X'-Y'' attitude; the camera is the
 * phone's back, looking out of it, and the screen angle turns that into what the user sees. (Yaw
 * and pitch are read in Y-X-Z order, so the screen's roll cannot change them; the correction keeps
 * the quaternion the true screen-up camera for anything that later wants the roll.)
 */
export function gyroToYawPitch(alphaDeg: number, betaDeg: number, gammaDeg: number, screenAngleDeg: number) {
  const d = THREE.MathUtils.degToRad;
  const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(d(betaDeg), d(alphaDeg), -d(gammaDeg), "YXZ"));
  q.multiply(Q_BACK_CAMERA);
  q.multiply(new THREE.Quaternion().setFromAxisAngle(ZEE, -d(screenAngleDeg)));
  const e = new THREE.Euler().setFromQuaternion(q, "YXZ");
  return { yaw: e.y, pitch: e.x };
}

export function wrapAngle(a: number) {
  return Math.atan2(Math.sin(a), Math.cos(a));
}

/**
 * Turns absolute gyro readings into what the walker needs: the yaw change since the last reading
 * (so drag-look and the gyro add up) and the pitch the phone is held at. Heading is arbitrary on
 * most phones, so only changes in it mean anything.
 */
export class GyroTracker {
  private lastYaw: number | null = null;

  reset() {
    this.lastYaw = null;
  }

  update(alphaDeg: number, betaDeg: number, gammaDeg: number, screenAngleDeg: number) {
    const { yaw, pitch } = gyroToYawPitch(alphaDeg, betaDeg, gammaDeg, screenAngleDeg);
    const dYaw = this.lastYaw === null ? 0 : wrapAngle(yaw - this.lastYaw);
    this.lastYaw = yaw;
    return { dYaw, pitch };
  }
}

/** Why tilting can't be offered, or null when it can. */
export function tiltUnavailableText(o: { hasSensorApi: boolean; secure: boolean }): string | null {
  if (!o.secure) return "Tilting needs the https page; drag to look";
  if (!o.hasSensorApi) return "No tilt sensor; drag to look";
  return null;
}

type DeviceOrientationCtor = { requestPermission?: () => Promise<"granted" | "denied"> };

function safeAreaInsets(): SafeArea {
  const probe = document.createElement("div");
  probe.style.cssText = "position:fixed;visibility:hidden;pointer-events:none;padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)";
  document.body.append(probe);
  const s = getComputedStyle(probe);
  const px = (v: string) => Number.parseFloat(v) || 0;
  const inset = { top: px(s.paddingTop), right: px(s.paddingRight), bottom: px(s.paddingBottom), left: px(s.paddingLeft) };
  probe.remove();
  return inset;
}

function screenAngle(): number {
  return window.screen?.orientation?.angle ?? (window as unknown as { orientation?: number }).orientation ?? 0;
}

/**
 * Left thumb walks, any other touch looks, and an opt-in button turns the phone itself into the
 * look control. The clamp and eye height are the desktop walk's, through stepOnFloor.
 */
export class TouchWalk implements WalkController {
  private readonly p: WalkPose = { position: new THREE.Vector3(), yaw: 0, pitch: 0 };
  private engaged = false;
  private readonly ac = new AbortController();
  private joy: { id: number; origin: [number, number]; at: [number, number] } | null = null;
  private look: { id: number; at: [number, number] } | null = null;
  private pitchOffset = 0;
  private gyroOn = false;
  private gyroPitch = 0;
  private anchorPitch = false;
  private readonly gyro = new GyroTracker();
  private readonly ui: HTMLElement;
  private readonly ring: HTMLElement;
  private readonly knob: HTMLElement;
  private readonly gyroButton: HTMLButtonElement;

  constructor(private readonly element: HTMLElement, private readonly space: WalkSpace, start: { position: THREE.Vector3Like; yaw: number; pitch: number }) {
    this.setPose(start);
    const signal = this.ac.signal;
    element.style.touchAction = "none";
    element.addEventListener("pointerdown", (e) => this.down(e), { signal });
    element.addEventListener("pointermove", (e) => this.move(e), { signal });
    element.addEventListener("pointerup", (e) => this.up(e), { signal });
    element.addEventListener("pointercancel", (e) => this.up(e), { signal });
    window.addEventListener("blur", () => this.releaseAll(), { signal });

    this.ring = Object.assign(document.createElement("div"), { className: "joy-ring" });
    this.knob = Object.assign(document.createElement("div"), { className: "joy-knob" });
    this.ring.append(this.knob);
    this.ring.hidden = true;
    this.gyroButton = Object.assign(document.createElement("button"), { type: "button", className: "chip gyro-button", textContent: "Look by tilting the phone" });
    this.gyroButton.dataset.control = "gyro";
    this.gyroButton.setAttribute("aria-pressed", "false");
    this.gyroButton.addEventListener("click", () => void this.toggleGyro(), { signal });
    this.ui = Object.assign(document.createElement("div"), { className: "touch-ui" });
    this.ring.setAttribute("aria-hidden", "true");
    this.ui.hidden = true;
    this.ui.append(this.ring, this.gyroButton);
    (element.parentElement ?? document.body).append(this.ui);
  }

  private pointOf(e: PointerEvent): [number, number] {
    const r = this.element.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  private down(e: PointerEvent) {
    if (!this.engaged || e.pointerType === "mouse") return;
    const at = this.pointOf(e);
    const width = this.element.clientWidth, height = this.element.clientHeight;
    this.element.setPointerCapture?.(e.pointerId);
    if (at[0] < width / 2 && this.joy === null) {
      const origin = clampOrigin(at, width, height, safeAreaInsets());
      this.joy = { id: e.pointerId, origin, at: origin };
      this.ring.hidden = false;
      this.placeRing();
    } else if (this.look === null) {
      this.look = { id: e.pointerId, at };
    }
    e.preventDefault();
  }

  private move(e: PointerEvent) {
    const at = this.pointOf(e);
    if (this.joy?.id === e.pointerId) {
      this.joy.at = at;
      this.placeRing();
    } else if (this.look?.id === e.pointerId) {
      const d = lookDelta(at[0] - this.look.at[0], at[1] - this.look.at[1]);
      this.p.yaw += d.dYaw;
      if (this.gyroOn) {
        this.pitchOffset = clampPitch(this.pitchOffset + d.dPitch);
        this.p.pitch = clampPitch(this.gyroPitch + this.pitchOffset);
      } else {
        this.p.pitch = clampPitch(this.p.pitch + d.dPitch);
      }
      this.look.at = at;
    }
  }

  private up(e: PointerEvent) {
    if (this.joy?.id === e.pointerId) {
      this.joy = null;
      this.ring.hidden = true;
    }
    if (this.look?.id === e.pointerId) this.look = null;
  }

  private releaseAll() {
    this.joy = null;
    this.look = null;
    this.ring.hidden = true;
  }

  private placeRing() {
    const j = this.joy;
    if (!j) return;
    const v = joystickVector(j.origin, j.at);
    this.ring.style.transform = `translate(${j.origin[0] - JOY_RADIUS_PX}px, ${j.origin[1] - JOY_RADIUS_PX}px)`;
    this.knob.style.transform = `translate(${v.right * (JOY_RADIUS_PX - JOY_DEAD_PX)}px, ${-v.forward * (JOY_RADIUS_PX - JOY_DEAD_PX)}px)`;
  }

  private readonly onOrientation = (e: DeviceOrientationEvent) => {
    // Desktop Chrome fires one event with nulls; there is nothing to follow in that.
    if (e.alpha === null || e.beta === null || e.gamma === null) return;
    const g = this.gyro.update(e.alpha, e.beta, e.gamma, screenAngle());
    this.p.yaw += g.dYaw;
    this.gyroPitch = g.pitch;
    // The first reading anchors the view: switching tilt on must not jump it to wherever the phone points.
    if (this.anchorPitch) { this.pitchOffset = this.p.pitch - g.pitch; this.anchorPitch = false; }
    this.p.pitch = clampPitch(this.gyroPitch + this.pitchOffset);
  };

  private setGyroLabel(on: boolean, text?: string) {
    this.gyroButton.setAttribute("aria-pressed", String(on));
    this.gyroButton.textContent = text ?? (on ? "Tilting looks: on" : "Look by tilting the phone");
  }

  /** The tap is the opt-in; iOS only shows its permission prompt from inside a tap handler. */
  private async toggleGyro() {
    if (this.gyroOn) {
      window.removeEventListener("deviceorientation", this.onOrientation);
      this.gyroOn = false;
      this.pitchOffset = 0;
      this.setGyroLabel(false);
      return;
    }
    const ctor = (window as unknown as { DeviceOrientationEvent?: DeviceOrientationCtor }).DeviceOrientationEvent;
    const why = tiltUnavailableText({ hasSensorApi: !!ctor, secure: window.isSecureContext });
    if (why || !ctor) { this.gyroUnavailable(why ?? undefined); return; }
    try {
      if (typeof ctor.requestPermission === "function" && (await ctor.requestPermission()) !== "granted") {
        this.gyroUnavailable("Tilting is off; drag to look");
        return;
      }
    } catch {
      this.gyroUnavailable("Tilting is off; drag to look");
      return;
    }
    this.gyro.reset();
    this.anchorPitch = true;
    window.addEventListener("deviceorientation", this.onOrientation);
    this.gyroOn = true;
    this.setGyroLabel(true);
  }

  private gyroUnavailable(text = "No tilt sensor; drag to look") {
    this.gyroButton.disabled = true;
    this.setGyroLabel(false, text);
  }

  engage() {
    this.engaged = true;
    this.ui.hidden = false;
  }

  update(dt: number) {
    const j = this.joy;
    if (!j) return;
    const v = joystickVector(j.origin, j.at);
    if (v.magnitude === 0) return;
    // The vector's length is the thumb's travel past the dead zone, so speed is proportional up to a walk.
    const k = WALK_SPEED * dt;
    stepOnFloor(this.p, v.forward * k, v.right * k, this.space);
  }

  pose(): Readonly<WalkPose> {
    return this.p;
  }

  setPose(s: { position: THREE.Vector3Like; yaw: number; pitch: number }) {
    this.p.position.set(s.position.x, this.space.eyeY, s.position.z);
    this.p.yaw = s.yaw;
    this.p.pitch = clampPitch(s.pitch);
    this.pitchOffset = clampPitch(this.p.pitch - this.gyroPitch);
  }

  dispose() {
    this.ac.abort();
    window.removeEventListener("deviceorientation", this.onOrientation);
    this.ui.remove();
  }
}

function clampPitch(p: number) {
  return THREE.MathUtils.clamp(p, -PITCH_LIMIT, PITCH_LIMIT);
}
