// Floor-plane geometry for the walk: points are [x, z] in world metres.
export type P2 = readonly [number, number];
export type Polygon = readonly P2[];

/** Even-odd rule; a point exactly on an edge may land either side, which the clamp tolerates. */
export function pointInPolygon(p: P2, poly: Polygon): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, zi] = poly[i];
    const [xj, zj] = poly[j];
    if ((zi > p[1]) !== (zj > p[1]) && p[0] < ((xj - xi) * (p[1] - zi)) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}

export function insideAny(p: P2, polys: readonly Polygon[]): boolean {
  return polys.some((poly) => pointInPolygon(p, poly));
}

function closestOnSegment(p: P2, a: P2, b: P2): [number, number] {
  const dx = b[0] - a[0], dz = b[1] - a[1];
  const len2 = dx * dx + dz * dz;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / len2));
  return [a[0] + t * dx, a[1] + t * dz];
}

function signedArea(poly: Polygon): number {
  let s = 0;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) s += poly[j][0] * poly[i][1] - poly[i][0] * poly[j][1];
  return s / 2;
}

const INSET = 1e-3;

/**
 * Where a walker trying to reach `next` from `prev` ends up. Inside: `next`. Outside: the nearest
 * point on any edge, nudged a millimetre inward, which keeps the motion along the edge (sliding).
 * If even that is outside (a corner of a narrow neck), the walker stays at `prev`.
 */
export function clampToWalkable(prev: P2, next: P2, polys: readonly Polygon[]): [number, number] {
  if (insideAny(next, polys)) return [next[0], next[1]];
  let best: [number, number] | null = null;
  let bestD = Infinity;
  for (const poly of polys) {
    // Inward normal of an edge depends on the winding: left of the edge for anticlockwise in (x, z).
    const ccw = signedArea(poly) > 0;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const a = poly[j], b = poly[i];
      const c = closestOnSegment(next, a, b);
      const ex = b[0] - a[0], ez = b[1] - a[1];
      const len = Math.hypot(ex, ez) || 1;
      const nx = (ccw ? -ez : ez) / len, nz = (ccw ? ex : -ex) / len;
      const cand: [number, number] = [c[0] + nx * INSET, c[1] + nz * INSET];
      const d = Math.hypot(cand[0] - next[0], cand[1] - next[1]);
      if (d < bestD && insideAny(cand, polys)) { best = cand; bestD = d; }
    }
  }
  return best ?? [prev[0], prev[1]];
}
