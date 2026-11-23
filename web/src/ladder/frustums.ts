// The inputs' frustums as faint pen wedges from the camera point: in the walk, four rays to the corners of
// the photo's frame and the frame itself, hung a little way out; on the map, each photo's horizontal span.
import * as THREE from "three";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import type { Vec2, Vec3 } from "../contract.ts";
import { LAYER } from "../ink/layers.ts";
import type { Frustum } from "./contract.ts";

/** How far out the frame hangs from the camera point, metres: near enough to stay inside a small room. */
export const FRAME_DISTANCE_M = 0.9;
/** How far each photo's span reaches across the map, metres. */
export const PLAN_REACH_M = 3;

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k];
const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: Vec3, b: Vec3): Vec3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit = (a: Vec3): Vec3 => mul(a, 1 / Math.hypot(...a));

/** The frustum's own axes: forward, right and up made square to forward (the file's up may lean a hair). */
export function axes(f: Frustum): { forward: Vec3; right: Vec3; up: Vec3 } {
  const forward = unit(f.forward);
  const up = unit(sub(f.up, mul(forward, dot(f.up, forward))));
  return { forward, right: cross(forward, up), up };
}

/** The frame's four corners at `dist` along forward, in the order top left, top right, bottom right, bottom left. */
export function corners(f: Frustum, c: Vec3, dist = FRAME_DISTANCE_M): Vec3[] {
  const { forward, right, up } = axes(f);
  const h = Math.tan(THREE.MathUtils.degToRad(f.hFovDeg / 2)) * dist;
  const v = Math.tan(THREE.MathUtils.degToRad(f.vFovDeg / 2)) * dist;
  const mid = add(c, mul(forward, dist));
  return [add(add(mid, mul(right, -h)), mul(up, v)), add(add(mid, mul(right, h)), mul(up, v)),
    add(add(mid, mul(right, h)), mul(up, -v)), add(add(mid, mul(right, -h)), mul(up, -v))];
}

/** Line segments, as pairs of points: the camera point to each corner, then the frame's four sides. */
export function wedgeSegments(f: Frustum, c: Vec3, dist = FRAME_DISTANCE_M): [Vec3, Vec3][] {
  const k = corners(f, c, dist);
  return [...k.map((p): [Vec3, Vec3] => [c, p]), ...k.map((p, i): [Vec3, Vec3] => [p, k[(i + 1) % 4]])];
}

/** The photo's horizontal span on the floor plan: two rays from the camera point, (x, z). */
export function planSpan(f: Frustum, c: Vec3, reach = PLAN_REACH_M): [Vec2, Vec2][] {
  const { forward } = axes(f);
  const yaw = Math.atan2(forward[2], forward[0]);
  const half = THREE.MathUtils.degToRad(f.hFovDeg / 2);
  return [yaw - half, yaw + half].map((a): [Vec2, Vec2] => [[c[0], c[2]], [c[0] + reach * Math.cos(a), c[2] + reach * Math.sin(a)]]);
}

export interface WedgeLines {
  walk: THREE.Object3D;
  map: THREE.Object3D;
  setResolution(w: number, h: number): void;
  setColour(hex: string): void;
  dispose(): void;
}

/** The wedges as faint pen lines: thin and half-strength, so they frame the photograph without crossing it out. */
export function makeWedges(frustums: Frustum[], c: Vec3, inkHex: string, floorY: number): WedgeLines {
  const walkMat = new LineMaterial({ color: inkHex, linewidth: 1.25, worldUnits: false, transparent: true, opacity: 0.55, depthTest: true });
  const mapMat = new LineMaterial({ color: inkHex, linewidth: 1.25, worldUnits: false, transparent: true, opacity: 0.6, depthTest: false, dashed: true, dashSize: 0.08, gapSize: 0.06 });
  const walkGeom = new LineSegmentsGeometry();
  const segs = frustums.flatMap((f) => wedgeSegments(f, c));
  walkGeom.setPositions(segs.flatMap(([a, b]) => [...a, ...b]));
  const walk = new LineSegments2(walkGeom, walkMat);
  walk.layers.set(LAYER.walk);
  walk.name = "ladder-wedges";
  const mapGeom = new LineSegmentsGeometry();
  const y = floorY + 0.02;
  mapGeom.setPositions(frustums.flatMap((f) => planSpan(f, c)).flatMap(([a, b]) => [a[0], y, a[1], b[0], y, b[1]]));
  const map = new LineSegments2(mapGeom, mapMat);
  map.computeLineDistances();
  map.layers.set(LAYER.map);
  map.renderOrder = 9;
  map.name = "ladder-wedges-map";
  if (segs.length === 0) walk.visible = false;
  return {
    walk, map,
    setResolution(w, h) { walkMat.resolution.set(w, h); mapMat.resolution.set(w, h); },
    setColour(hex) { walkMat.color.set(hex); mapMat.color.set(hex); },
    dispose() { walkGeom.dispose(); mapGeom.dispose(); walkMat.dispose(); mapMat.dispose(); },
  };
}
