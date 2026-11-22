// The plain-words chapters follow the walk: each band opens on its own at its moment, once, read off where the
// visitor stands and faces against the floor's pen line. Pure, so the moments are tested without a browser.
import { CHAPTERS } from "./words.ts";

type P2 = readonly [number, number];

/** What the walk looks like from the pen line's point of view, on the floor plane. */
export interface LineView {
  /** Metres from the visitor to the nearest point of the line. */
  distM: number;
  /** On the drawn side: past the line, along the door's outward direction. */
  past: boolean;
  /** Some of the line lies inside the camera's horizontal field of view. */
  inView: boolean;
  /** The facing direction against the door's outward one: 1 faces the hallway, -1 faces the room. */
  facing: number;
  /** The nearest point of the line is in front of the visitor. */
  lineAhead: boolean;
}

/**
 * The deck asks for "about two metres", but the start pose stands 1.9 m from the line and faces it, so the
 * edge would open before the first step. A step and a half nearer keeps "You found it" true.
 */
export const NEAR_LINE_M = 1.5;
/** Facing within about 60° of the hallway, or of the room. */
const FACING = 0.5;

function nearestOnSegment(p: P2, a: P2, b: P2): [number, number] {
  const dx = b[0] - a[0], dz = b[1] - a[1];
  const len2 = dx * dx + dz * dz;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / len2));
  return [a[0] + t * dx, a[1] + t * dz];
}

/**
 * `yaw` in radians, 0 looking along -z (the walk's convention); `halfHfov` is half the camera's horizontal
 * field of view. "In view" is judged across the floor only: at eye height the floor line drops below the
 * frame within about 2.3 m, while the doorway it crosses is still in front of the visitor.
 */
export function lineView(pos: P2, yaw: number, halfHfov: number, polylines: readonly (readonly P2[])[], outward: P2): LineView {
  let best = Infinity;
  let nearest: [number, number] | null = null;
  for (const line of polylines) {
    for (let i = 0; i < line.length; i++) {
      const q = line.length === 1 ? line[0] : i + 1 < line.length ? nearestOnSegment(pos, line[i], line[i + 1]) : null;
      if (!q) continue;
      const d = Math.hypot(q[0] - pos[0], q[1] - pos[1]);
      if (d < best) { best = d; nearest = [q[0], q[1]]; }
    }
  }
  if (!nearest) return { distM: Infinity, past: false, inView: false, facing: 0, lineAhead: false };

  const fx = -Math.sin(yaw), fz = -Math.cos(yaw);
  const ol = Math.hypot(outward[0], outward[1]) || 1;
  const ox = outward[0] / ol, oz = outward[1] / ol;
  const cosHalf = Math.cos(halfHfov);
  const ahead = (q: P2) => {
    const dx = q[0] - pos[0], dz = q[1] - pos[1];
    const len = Math.hypot(dx, dz);
    return len > 1e-6 && (dx * fx + dz * fz) / len >= cosHalf;
  };
  return {
    distM: best,
    past: (pos[0] - nearest[0]) * ox + (pos[1] - nearest[1]) * oz > 0,
    inView: ahead(nearest) || polylines.some((l) => l.some(ahead)),
    facing: fx * ox + fz * oz,
    lineAhead: (nearest[0] - pos[0]) * fx + (nearest[1] - pos[1]) * fz > 0,
  };
}

type Moment = "edge" | "over" | "back" | "map";
const OPENS: Record<Moment, number> = { edge: 1, over: 2, back: 3, map: 4 };

/** The reader's place in the story, and which moments have already fired. */
export class Trail {
  chapter = 0;
  private readonly fired = new Set<Moment>();
  private wasPast: boolean | null = null;
  private facedAway = false;

  private fire(m: Moment) {
    this.fired.add(m);
    this.chapter = OPENS[m];
    return this.chapter;
  }

  /** One look at the walk; returns the chapter a moment opened, or null. At most one moment per look. */
  observe(v: LineView): number | null {
    if (!Number.isFinite(v.distM)) return null;
    const crossed = this.wasPast === false && v.past;
    this.wasPast = v.past;
    if (!this.fired.has("edge") && !v.past && v.distM <= NEAR_LINE_M && v.inView) return this.fire("edge");
    if (!this.fired.has("over") && crossed) return this.fire("over");
    if (this.fired.has("over") && v.past) {
      if (v.facing > FACING) this.facedAway = true;
      // "Turns to face the room": only after facing the hallway from the drawn side, so backing over the line
      // facing the room does not skip chapter 3.
      else if (!this.fired.has("back") && this.facedAway && v.facing < -FACING && v.lineAhead) return this.fire("back");
    }
    return null;
  }

  mapOpened(): number | null {
    return this.fired.has("map") ? null : this.fire("map");
  }

  get isLast() {
    return this.chapter === CHAPTERS.length - 1;
  }

  next() {
    this.goTo(this.chapter + 1);
    return this.chapter;
  }

  goTo(i: number) {
    this.chapter = Math.max(0, Math.min(CHAPTERS.length - 1, Math.round(i)));
  }
}
