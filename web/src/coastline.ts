import * as THREE from "three";
import { Line2 } from "three/addons/lines/Line2.js";
import { LineGeometry } from "three/addons/lines/LineGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import type { Coastline } from "./contract.ts";
import { LAYER } from "./ink/layers.ts";
import { PEN } from "./ink/pen.ts";

/** Small deterministic PRNG, so the hand jitter is the same line on every visit. */
function mulberry32(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * The hand: resample the polyline every 2 cm and push each point sideways by smooth noise up to
 * `amp` metres. Smooth (a few low-frequency waves), not per-point, or it reads as a fault, not a pen.
 */
export function jitterPolyline(points: readonly (readonly [number, number])[], amp: number, seed: number, step = 0.02): [number, number][] {
  const out: [number, number][] = [];
  const rnd = mulberry32(seed);
  const waves = [0, 1, 2].map((i) => ({ k: (2 * Math.PI) / (0.15 + 0.35 * rnd()) * (1 + i * 0.7), ph: rnd() * 2 * Math.PI, w: 1 / (i + 1) }));
  const norm = waves.reduce((s, w) => s + w.w, 0);
  let travelled = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const [ax, az] = points[i], [bx, bz] = points[i + 1];
    const len = Math.hypot(bx - ax, bz - az);
    if (len === 0) continue;
    const nx = -(bz - az) / len, nz = (bx - ax) / len;
    const n = Math.max(1, Math.ceil(len / step));
    for (let j = 0; j < n; j++) {
      const t = j / n;
      const s = travelled + t * len;
      const off = (amp * waves.reduce((acc, w) => acc + w.w * Math.sin(w.k * s + w.ph), 0)) / norm;
      out.push([ax + (bx - ax) * t + nx * off, az + (bz - az) * t + nz * off]);
    }
    travelled += len;
  }
  const last = points[points.length - 1];
  out.push([last[0], last[1]]);
  return out;
}

export interface CoastlineLines {
  floor: THREE.Group;
  map: THREE.Group;
  /** LineMaterial needs the canvas size in pixels for its screen-space widths. */
  setResolution(w: number, h: number): void;
  setColour(hex: string): void;
  setVisible(on: boolean): void;
}

export function makeCoastlineLines(c: Coastline, inkHex: string, floorY: number): CoastlineLines {
  const floor = new THREE.Group();
  const map = new THREE.Group();
  floor.name = "coastline-floor";
  map.name = "coastline-map";
  // Opaque and depth-tested: furniture in front hides the line, as it would a line on the floor.
  const floorMat = new LineMaterial({ color: inkHex, linewidth: PEN.floorLineWidthM, worldUnits: true });
  const mapMat = new LineMaterial({ color: inkHex, linewidth: 3, worldUnits: false, depthTest: false });
  c.polylines.forEach((pl, i) => {
    const pts = pl.closed && pl.points.length > 2 ? [...pl.points, pl.points[0]] : pl.points;
    const jittered = jitterPolyline(pts, PEN.floorJitterM, 0x50ba5e + i);
    const floorPos = jittered.flatMap(([x, z]) => [x, floorY + PEN.floorLineY, z]);
    const g = new LineGeometry();
    g.setPositions(floorPos);
    const line = new Line2(g, floorMat);
    line.computeLineDistances();
    line.layers.set(LAYER.walk);
    floor.add(line);

    const gm = new LineGeometry();
    gm.setPositions(pts.flatMap(([x, z]) => [x, floorY + 0.01, z]));
    const ml = new Line2(gm, mapMat);
    ml.layers.set(LAYER.map);
    ml.renderOrder = 10;
    map.add(ml);
  });
  floor.layers.set(LAYER.walk);
  map.layers.set(LAYER.map);
  return {
    floor,
    map,
    setResolution(w, h) {
      floorMat.resolution.set(w, h);
      mapMat.resolution.set(w, h);
    },
    setColour(hex) {
      floorMat.color.set(hex);
      mapMat.color.set(hex);
    },
    setVisible(on) {
      floor.visible = on;
      map.visible = on;
    },
  };
}
