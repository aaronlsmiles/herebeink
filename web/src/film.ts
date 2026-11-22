import * as THREE from "three";
import type { FilmKey, Vec3 } from "./contract.ts";
import type { Viewer } from "./viewer.ts";

export const FILM_FPS = 24;

export interface PathPose { position: Vec3; yaw: number; pitch: number }

/** Folds a yaw sequence into a continuous one: each step takes the shorter way round. */
export function unwrapDegrees(degs: readonly number[]): number[] {
  const out: number[] = [];
  for (const d of degs) {
    if (out.length === 0) { out.push(d); continue; }
    let delta = (((d - out[out.length - 1]) % 360) + 360) % 360;
    if (delta > 180) delta -= 360;
    out.push(out[out.length - 1] + delta);
  }
  return out;
}

/**
 * Catmull-Rom tangents for keys at uneven times, limited so a value never overshoots its
 * neighbours (a held position stays held), and zero at both ends so the path eases in and out.
 */
export function tangents(ts: readonly number[], ys: readonly number[]): number[] {
  const n = ts.length;
  const slope = (k: number) => (ys[k + 1] - ys[k]) / (ts[k + 1] - ts[k]);
  const m = new Array<number>(n).fill(0);
  for (let k = 1; k < n - 1; k++) {
    const a = slope(k - 1), b = slope(k);
    if (a * b <= 0) continue;
    const catmull = (ys[k + 1] - ys[k - 1]) / (ts[k + 1] - ts[k - 1]);
    m[k] = Math.sign(catmull) * Math.min(Math.abs(catmull), 3 * Math.min(Math.abs(a), Math.abs(b)));
  }
  return m;
}

function hermite(t0: number, t1: number, y0: number, y1: number, m0: number, m1: number, t: number) {
  const h = t1 - t0;
  const u = (t - t0) / h;
  const u2 = u * u, u3 = u2 * u;
  return (2 * u3 - 3 * u2 + 1) * y0 + (u3 - 2 * u2 + u) * h * m0 + (-2 * u3 + 3 * u2) * y1 + (u3 - u2) * h * m1;
}

class Curve {
  private readonly m: number[];
  constructor(private readonly ts: readonly number[], private readonly ys: readonly number[]) {
    this.m = tangents(ts, ys);
  }

  at(t: number): number {
    const { ts, ys, m } = this;
    let k = 0;
    while (k < ts.length - 2 && t > ts[k + 1]) k++;
    return hermite(ts[k], ts[k + 1], ys[k], ys[k + 1], m[k], m[k + 1], Math.min(ts[ts.length - 1], Math.max(ts[0], t)));
  }
}

/** scene.json's filmPath as a camera path: smooth in position, yaw (the short way round) and pitch. */
export class FilmPath {
  readonly start: number;
  readonly end: number;
  private readonly curves: [Curve, Curve, Curve, Curve, Curve];

  constructor(keys: readonly FilmKey[]) {
    const sorted = [...keys].sort((a, b) => a.t - b.t).filter((k, i, all) => i === 0 || k.t > all[i - 1].t);
    if (sorted.length < 2) throw new Error("filmPath needs two keys at different times");
    const ts = sorted.map((k) => k.t);
    const yaws = unwrapDegrees(sorted.map((k) => k.yawDeg));
    this.start = ts[0];
    this.end = ts[ts.length - 1];
    this.curves = [
      new Curve(ts, sorted.map((k) => k.position[0])),
      new Curve(ts, sorted.map((k) => k.position[1])),
      new Curve(ts, sorted.map((k) => k.position[2])),
      new Curve(ts, yaws),
      new Curve(ts, sorted.map((k) => k.pitchDeg)),
    ];
  }

  get duration() {
    return this.end - this.start;
  }

  frameCount(fps = FILM_FPS) {
    return Math.floor(this.duration * fps + 1e-9) + 1;
  }

  /** Pose at path time t (seconds, as the keys' own clock); radians. */
  at(t: number): PathPose {
    const [x, y, z, yaw, pitch] = this.curves.map((c) => c.at(t));
    return { position: [x, y, z], yaw: THREE.MathUtils.degToRad(yaw), pitch: THREE.MathUtils.degToRad(Math.max(-90, Math.min(90, pitch))) };
  }

  /** Pose of frame n: time is computed from the integer, so frame n is the same pose on every run. */
  frame(n: number, fps = FILM_FPS): PathPose {
    return this.at(this.start + n / fps);
  }
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function sparks(viewer: Viewer) {
  return [viewer.spark, viewer.data.gbufSpark, viewer.data.flagSpark];
}

/** What a render would change if anything were still settling: splat sets, their order and the cut. */
function signature(viewer: Viewer) {
  return sparks(viewer).map((s) => `${s.current.version}.${s.current.mappingVersion}.${s.activeSplats}`).join("/");
}

/**
 * Waits for `done`. `nudge` draws the same pose again when a cut is stalled for want of a frame
 * (no loop runs here); it must not be a frame while a sort is running, since each frame starts one
 * and the sorts would never finish.
 */
async function until(done: () => boolean, deadline: number, nudge: () => void) {
  let nudged = performance.now();
  while (!done()) {
    if (performance.now() > deadline) throw new Error("the sort did not settle for this frame");
    await sleep(10);
    if (performance.now() - nudged > 250) {
      nudge();
      nudged = performance.now();
    }
  }
}

/**
 * Draws a frame once Spark's sort and level-of-detail cut have caught up with the pose. Spark sorts
 * and refines on workers, so a frame drawn at once would carry the previous pose's order. Each
 * round renders, then waits for the sorts without rendering (a software renderer would otherwise
 * queue frames faster than it draws them, and Spark's own readback would wait behind all of them).
 * The second round in a row that changes nothing is the settled frame, and `capture` runs in that task, since
 * a WebGL canvas is cleared once its task ends.
 */
async function drawSettled(viewer: Viewer, dt: number, capture: () => void | Promise<void>, maxMs = 120_000) {
  const deadline = performance.now() + maxMs;
  const gl = viewer.renderer.getContext();
  const nudge = () => { if (viewer.lodStalled) { viewer.step(dt); gl.finish(); } };
  let quiet = 0;
  for (;;) {
    if (performance.now() > deadline) throw new Error("the sort did not settle for this frame");
    viewer.step(dt);
    gl.finish();
    await until(() => viewer.settled, deadline, nudge);
    const before = signature(viewer);
    viewer.step(dt);
    gl.finish();
    // Two quiet rounds in a row: the first can fall between a worker's answers.
    quiet = viewer.settled && signature(viewer) === before ? quiet + 1 : 0;
    if (quiet === 2) { await capture(); return; }
    await sleep(0);
  }
}

/** Waits until the level-of-detail cuts exist; before that the first sorts hold only what loaded first. */
async function warmUp(viewer: Viewer, dt: number, maxMs = 120_000) {
  const deadline = performance.now() + maxMs;
  const gl = viewer.renderer.getContext();
  const nudge = () => { if (viewer.lodStalled) { viewer.step(dt); gl.finish(); } };
  while (!viewer.lodReady) {
    if (performance.now() > deadline) throw new Error("the level-of-detail cuts did not arrive");
    viewer.step(dt);
    gl.finish();
    await until(() => viewer.settled, deadline, nudge);
    await sleep(20);
  }
}

export interface FilmOptions {
  dump: boolean;
  /** Sub-folder of film/frames/ for the dump; null writes into film/frames/ itself. */
  set: string | null;
  /** Only frames from `from` for `count` frames (to the end when null), numbered as in the whole film. */
  range?: { from: number; count: number | null } | null;
  fps?: number;
}

export interface FilmResult { frames: number; fps: number }

async function postFrame(canvas: HTMLCanvasElement, n: number, set: string | null) {
  // toBlob snapshots the drawing buffer when called, inside the task that drew it.
  const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/png"));
  if (!blob) throw new Error(`frame ${n}: the canvas gave no image`);
  const qs = new URLSearchParams({ n: String(n) });
  if (set) qs.set("set", set);
  const res = await fetch(`/frame?${qs}`, { method: "POST", headers: { "Content-Type": "image/png" }, body: blob });
  if (!res.ok) throw new Error(`frame ${n}: /frame answered ${res.status} ${await res.text()}`);
}

/**
 * The film walk. With `dump` every frame is drawn only once its sort has settled and posted to
 * the dev server; without it the path plays at real speed on the page, for a look before a dump.
 * The loop never runs: each frame is a viewer.step(), so frame n is the same pose every run.
 */
export async function runFilm(viewer: Viewer, o: FilmOptions): Promise<FilmResult> {
  const fps = o.fps ?? FILM_FPS;
  const path = new FilmPath(viewer.sceneContract.filmPath);
  const total = path.frameCount(fps);
  const dt = 1 / fps;
  // The loop runs while the files load: a file is first drawn from inside a frame, once its cut is in.
  viewer.start();
  await viewer.world.complete;
  viewer.stop();
  await warmUp(viewer, dt);
  const root = document.documentElement.dataset;
  const canvas = viewer.renderer.domElement;
  const t0 = performance.now();
  const first = Math.min(total - 1, o.range?.from ?? 0);
  const last = Math.min(total, first + (o.range?.count ?? total));
  root.filmFrames = String(last - first);
  for (let n = first; n < last; n++) {
    const p = path.frame(n, fps);
    viewer.walk.setPose({ position: { x: p.position[0], y: p.position[1], z: p.position[2] }, yaw: p.yaw, pitch: p.pitch });
    if (o.dump) {
      await drawSettled(viewer, dt, () => postFrame(canvas, n, o.set));
    } else {
      viewer.step(dt);
      const wait = t0 + ((n + 1) * 1000) / fps - performance.now();
      await sleep(Math.max(0, wait));
    }
    root.filmDone = String(n - first + 1);
  }
  root.filmComplete = "1";
  return { frames: last - first, fps };
}
