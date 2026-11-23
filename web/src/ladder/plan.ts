// A rung's seen floor on the map: a faint wash of ink inside a fine outline, under the map's own pen line.
import * as THREE from "three";
import { Line2 } from "three/addons/lines/Line2.js";
import { LineGeometry } from "three/addons/lines/LineGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import type { Vec2 } from "../contract.ts";
import { LAYER } from "../ink/layers.ts";

/** Ink over paper, light enough that the floor under it still reads. */
const WASH_OPACITY = 0.12;

export function makeSeenFloor(polylines: Vec2[][], inkHex: string, floorY: number) {
  const map = new THREE.Group();
  map.name = "ladder-seen-floor";
  const fill = new THREE.MeshBasicMaterial({ color: inkHex, transparent: true, opacity: WASH_OPACITY, depthTest: false, depthWrite: false, side: THREE.DoubleSide });
  const edge = new LineMaterial({ color: inkHex, linewidth: 1, worldUnits: false, transparent: true, opacity: 0.7, depthTest: false });
  const geoms: { dispose(): void }[] = [];
  for (const pl of polylines) {
    if (pl.length < 3) continue;
    // A shape lies in x, y; turned flat about x, its y becomes −z, so the plan's z goes in negated.
    const shape = new THREE.Shape(pl.map(([x, z]) => new THREE.Vector2(x, -z)));
    const g = new THREE.ShapeGeometry(shape);
    const mesh = new THREE.Mesh(g, fill);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.y = floorY + 0.015;
    mesh.renderOrder = 8;
    mesh.layers.set(LAYER.map);
    map.add(mesh);
    const lg = new LineGeometry();
    lg.setPositions(pl.flatMap(([x, z]) => [x, floorY + 0.016, z]));
    const line = new Line2(lg, edge);
    line.layers.set(LAYER.map);
    line.renderOrder = 8;
    map.add(line);
    geoms.push(g, lg);
  }
  map.layers.set(LAYER.map);
  return {
    walk: new THREE.Group(),
    map,
    setResolution(w: number, h: number) { edge.resolution.set(w, h); },
    setColour(hex: string) { fill.color.set(hex); edge.color.set(hex); },
    dispose() { geoms.forEach((g) => g.dispose()); fill.dispose(); edge.dispose(); },
  };
}
