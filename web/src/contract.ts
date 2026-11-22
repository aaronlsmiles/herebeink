// The page's reading of pipeline/schema/scene.schema.json and coastline.schema.json.
// Only what the viewer relies on is checked, so an added field never breaks a published page;
// contract.test.ts fails if the schema's required lists move away from these.

export type Vec2 = [number, number];
export type Vec3 = [number, number, number];
export type Provenance = 0 | 0.5 | 1;

export interface SplatFile {
  url: string;
  sha256: string;
  bytes: number;
  splats: number;
  shDegree: number;
  provenance: Provenance;
  /** File frame to world, column-major (THREE.Matrix4.fromArray); a similarity. */
  matrix: number[];
}

export interface FilmKey { t: number; position: Vec3; yawDeg: number; pitchDeg: number }
export interface ScenePose { position: Vec3; yawDeg: number; pitchDeg: number }

export interface Scene {
  schemaVersion: 1;
  generatedAt: string;
  units: "m";
  frame: { up: Vec3; floorY: number; longAxis: Vec3 };
  splats: { measured: SplatFile; measuredPreview: SplatFile; overlap: SplatFile; imagined: SplatFile; measuredPhone?: SplatFile };
  radiiM: { covered: number; overlap: number };
  floor: { normal: Vec3; y: number };
  walkable: { polygons: Vec2[][]; dilationM: number };
  eyeHeightM: number;
  start: ScenePose;
  door: { centre: Vec3; widthM: number; outward: Vec3 };
  filmPath: FilmKey[];
  light: { direction: Vec3 };
  coastline: { url: string; sha256: string; bytes: number; stretches: number; lengthM: number };
  counts: { measured: number; measuredPreview: number; measuredPhone?: number; marble: number; covered: number; overlap: number; imagined: number };
  alignment: { medianCm: number; p90Cm: number; icpSet: number; gateAPass: boolean; note: string };
  sources: { measured: string; imagined: { provider: string; model: string; worldId: string } };
  credit: string;
}

export interface Coastline {
  schemaVersion: 1;
  units: "m";
  frame: string;
  gridM: number;
  floorBandM: number;
  radiiM: { covered: number; overlap: number };
  gridOrigin: Vec2;
  gridShape: Vec2;
  polylines: { closed: boolean; points: Vec2[] }[];
  lengthM: number;
}

export const SPLAT_KEYS = ["measured", "measuredPreview", "overlap", "imagined"] as const;
export type SplatKey = (typeof SPLAT_KEYS)[number];
/** Files a scene may carry beyond the four: a lighter measured file that phones load in place of the full one. */
export const OPTIONAL_SPLAT_KEYS = ["measuredPhone"] as const;

export const SCENE_REQUIRED = [
  "schemaVersion", "generatedAt", "units", "frame", "splats", "radiiM", "floor", "walkable", "eyeHeightM",
  "start", "door", "filmPath", "light", "coastline", "counts", "alignment", "sources", "credit",
] as const;
export const SPLAT_FILE_REQUIRED = ["url", "sha256", "bytes", "splats", "shDegree", "provenance", "matrix"] as const;
export const COASTLINE_REQUIRED = [
  "schemaVersion", "units", "frame", "gridM", "floorBandM", "radiiM", "gridOrigin", "gridShape", "polylines", "lengthM",
] as const;

export class ContractError extends Error {
  constructor(readonly file: string, readonly problems: string[]) {
    super(`${file} does not match the scene contract:\n- ${problems.join("\n- ")}`);
    this.name = "ContractError";
  }
}

type Json = unknown;

class Checker {
  readonly problems: string[] = [];
  private fail(path: string, what: string) { this.problems.push(`${path}: ${what}`); }

  obj(v: Json, path: string, required: readonly string[]): Record<string, Json> | null {
    if (typeof v !== "object" || v === null || Array.isArray(v)) { this.fail(path, "should be an object"); return null; }
    const o = v as Record<string, Json>;
    for (const k of required) if (!(k in o)) this.fail(path === "" ? k : `${path}.${k}`, "missing");
    return o;
  }

  num(v: Json, path: string, opts: { min?: number; exclusiveMin?: number; max?: number; integer?: boolean } = {}) {
    if (v === undefined) return;
    if (typeof v !== "number" || !Number.isFinite(v)) { this.fail(path, `should be a number, got ${JSON.stringify(v)}`); return; }
    if (opts.integer && !Number.isInteger(v)) this.fail(path, `should be an integer, got ${v}`);
    if (opts.min !== undefined && v < opts.min) this.fail(path, `should be at least ${opts.min}, got ${v}`);
    if (opts.exclusiveMin !== undefined && v <= opts.exclusiveMin) this.fail(path, `should be more than ${opts.exclusiveMin}, got ${v}`);
    if (opts.max !== undefined && v > opts.max) this.fail(path, `should be at most ${opts.max}, got ${v}`);
  }

  str(v: Json, path: string, pattern?: RegExp) {
    if (v === undefined) return;
    if (typeof v !== "string") { this.fail(path, "should be a string"); return; }
    if (pattern && !pattern.test(v)) this.fail(path, `does not match ${pattern}`);
  }

  bool(v: Json, path: string) {
    if (v !== undefined && typeof v !== "boolean") this.fail(path, "should be true or false");
  }

  is(v: Json, path: string, allowed: readonly Json[]) {
    if (v !== undefined && !allowed.includes(v)) this.fail(path, `should be one of ${allowed.map((a) => JSON.stringify(a)).join(", ")}, got ${JSON.stringify(v)}`);
  }

  vec(v: Json, path: string, n: number) {
    if (v === undefined) return;
    if (!Array.isArray(v)) { this.fail(path, `should be a list of ${n} numbers`); return; }
    if (v.length !== n) { this.fail(path, `should have ${n} numbers, has ${v.length}`); return; }
    v.forEach((x, i) => this.num(x, `${path}[${i}]`));
  }

  list(v: Json, path: string, minItems: number): Json[] | null {
    if (v === undefined) return null;
    if (!Array.isArray(v)) { this.fail(path, "should be a list"); return null; }
    if (v.length < minItems) this.fail(path, `should have at least ${minItems} item(s), has ${v.length}`);
    return v;
  }
}

const SHA256 = /^[0-9a-f]{64}$/;
const UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

/** A film key's height may differ from eye height by this much (metres). */
const FILM_HEIGHT_TOLERANCE_M = 0.02;

/** Column lengths may differ by this fraction: the exporter writes nine significant digits. */
const SCALE_TOLERANCE = 1e-3;

/**
 * A mesh matrix is a similarity (rotation, one uniform scale, translation), column-major, as the
 * exporter writes it. Anything else would draw a file mirrored, squashed or sheared against the
 * others and the coastline, with no error to say so.
 */
function checkSimilarity(c: Checker, v: Json, path: string) {
  if (!Array.isArray(v) || v.length !== 16 || !v.every((x) => typeof x === "number" && Number.isFinite(x))) return;
  const m = v as number[];
  if (m[3] !== 0 || m[7] !== 0 || m[11] !== 0 || m[15] !== 1) c.problems.push(`${path}: last row should be 0, 0, 0, 1`);
  const [a, b, d] = [m.slice(0, 3), m.slice(4, 7), m.slice(8, 11)];
  const cross = [b[1] * d[2] - b[2] * d[1], b[2] * d[0] - b[0] * d[2], b[0] * d[1] - b[1] * d[0]];
  const det = a[0] * cross[0] + a[1] * cross[1] + a[2] * cross[2];
  if (!(det > 0)) c.problems.push(`${path}: should not mirror or flatten (determinant should be positive)`);
  const norms = [a, b, d].map((col) => Math.hypot(...col));
  const mean = (norms[0] + norms[1] + norms[2]) / 3;
  if (det > 0 && Math.max(...norms) - Math.min(...norms) > SCALE_TOLERANCE * mean) c.problems.push(`${path}: should scale evenly (column lengths differ)`);
}

function checkPose(c: Checker, v: Json, path: string) {
  const o = c.obj(v, path, ["position", "yawDeg", "pitchDeg"]);
  if (!o) return;
  c.vec(o.position, `${path}.position`, 3);
  c.num(o.yawDeg, `${path}.yawDeg`);
  c.num(o.pitchDeg, `${path}.pitchDeg`, { min: -90, max: 90 });
}

function checkRadii(c: Checker, v: Json, path: string) {
  const o = c.obj(v, path, ["covered", "overlap"]);
  if (!o) return;
  c.num(o.covered, `${path}.covered`, { exclusiveMin: 0 });
  c.num(o.overlap, `${path}.overlap`, { exclusiveMin: 0 });
}

export function validateScene(json: Json, file = "scene.json"): Scene {
  const c = new Checker();
  const s = c.obj(json, "", SCENE_REQUIRED);
  if (s) {
    c.is(s.schemaVersion, "schemaVersion", [1]);
    c.str(s.generatedAt, "generatedAt", UTC);
    c.is(s.units, "units", ["m"]);
    const frame = s.frame === undefined ? null : c.obj(s.frame, "frame", ["up", "floorY", "longAxis"]);
    if (frame) { c.vec(frame.up, "frame.up", 3); c.num(frame.floorY, "frame.floorY"); c.vec(frame.longAxis, "frame.longAxis", 3); }
    const splats = s.splats === undefined ? null : c.obj(s.splats, "splats", SPLAT_KEYS);
    if (splats) {
      for (const key of [...SPLAT_KEYS, ...OPTIONAL_SPLAT_KEYS]) {
        if (splats[key] === undefined) continue;
        const path = `splats.${key}`;
        const f = c.obj(splats[key], path, SPLAT_FILE_REQUIRED);
        if (!f) continue;
        c.str(f.url, `${path}.url`);
        c.str(f.sha256, `${path}.sha256`, SHA256);
        c.num(f.bytes, `${path}.bytes`, { min: 1, integer: true });
        c.num(f.splats, `${path}.splats`, { min: 0, integer: true });
        c.num(f.shDegree, `${path}.shDegree`, { min: 0, max: 3, integer: true });
        c.is(f.provenance, `${path}.provenance`, [0, 0.5, 1]);
        c.vec(f.matrix, `${path}.matrix`, 16);
        checkSimilarity(c, f.matrix, `${path}.matrix`);
      }
    }
    if (s.radiiM !== undefined) checkRadii(c, s.radiiM, "radiiM");
    const floor = s.floor === undefined ? null : c.obj(s.floor, "floor", ["normal", "y"]);
    if (floor) { c.vec(floor.normal, "floor.normal", 3); c.num(floor.y, "floor.y"); }
    const walkable = s.walkable === undefined ? null : c.obj(s.walkable, "walkable", ["polygons", "dilationM"]);
    if (walkable) {
      const polys = c.list(walkable.polygons, "walkable.polygons", 1);
      polys?.forEach((poly, i) => c.list(poly, `walkable.polygons[${i}]`, 3)?.forEach((pt, j) => c.vec(pt, `walkable.polygons[${i}][${j}]`, 2)));
      c.num(walkable.dilationM, "walkable.dilationM", { min: 0 });
    }
    c.num(s.eyeHeightM, "eyeHeightM", { exclusiveMin: 0 });
    if (s.start !== undefined) checkPose(c, s.start, "start");
    const door = s.door === undefined ? null : c.obj(s.door, "door", ["centre", "widthM", "outward"]);
    if (door) { c.vec(door.centre, "door.centre", 3); c.num(door.widthM, "door.widthM", { exclusiveMin: 0 }); c.vec(door.outward, "door.outward", 3); }
    // The walk stands at eye height whatever a pose says, so a film path with other heights would
    // be flattened without a word.
    const eyeY = floor && typeof floor.y === "number" && typeof s.eyeHeightM === "number" ? floor.y + s.eyeHeightM : null;
    c.list(s.filmPath, "filmPath", 2)?.forEach((k, i) => {
      const path = `filmPath[${i}]`;
      const o = c.obj(k, path, ["t", "position", "yawDeg", "pitchDeg"]);
      if (!o) return;
      c.num(o.t, `${path}.t`, { min: 0 });
      checkPose(c, o, path);
      const y = Array.isArray(o.position) ? o.position[1] : undefined;
      if (eyeY !== null && typeof y === "number" && Math.abs(y - eyeY) > FILM_HEIGHT_TOLERANCE_M) {
        c.problems.push(`${path}.position[1]: should be the eye height ${eyeY} (film mode walks at eye height), got ${y}`);
      }
    });
    const light = s.light === undefined ? null : c.obj(s.light, "light", ["direction"]);
    if (light) c.vec(light.direction, "light.direction", 3);
    const coast = s.coastline === undefined ? null : c.obj(s.coastline, "coastline", ["url", "sha256", "bytes", "stretches", "lengthM"]);
    if (coast) {
      c.str(coast.url, "coastline.url");
      c.str(coast.sha256, "coastline.sha256", SHA256);
      c.num(coast.bytes, "coastline.bytes", { min: 1, integer: true });
      c.num(coast.stretches, "coastline.stretches", { min: 0, integer: true });
      c.num(coast.lengthM, "coastline.lengthM", { min: 0 });
    }
    const counts = s.counts === undefined ? null : c.obj(s.counts, "counts", ["measured", "measuredPreview", "marble", "covered", "overlap", "imagined"]);
    if (counts) for (const [k, v] of Object.entries(counts)) c.num(v, `counts.${k}`, { min: 0, integer: true });
    const al = s.alignment === undefined ? null : c.obj(s.alignment, "alignment", ["medianCm", "p90Cm", "icpSet", "gateAPass", "note"]);
    if (al) {
      c.num(al.medianCm, "alignment.medianCm", { min: 0 });
      c.num(al.p90Cm, "alignment.p90Cm", { min: 0 });
      c.num(al.icpSet, "alignment.icpSet", { min: 0, integer: true });
      c.bool(al.gateAPass, "alignment.gateAPass");
      c.str(al.note, "alignment.note");
    }
    const src = s.sources === undefined ? null : c.obj(s.sources, "sources", ["measured", "imagined"]);
    if (src) {
      c.str(src.measured, "sources.measured");
      const im = src.imagined === undefined ? null : c.obj(src.imagined, "sources.imagined", ["provider", "model", "worldId"]);
      if (im) { c.str(im.provider, "sources.imagined.provider"); c.str(im.model, "sources.imagined.model"); c.str(im.worldId, "sources.imagined.worldId"); }
    }
    c.str(s.credit, "credit");
    if (typeof s.credit === "string" && s.credit.length === 0) c.problems.push("credit: should not be empty");
  }
  if (c.problems.length) throw new ContractError(file, c.problems);
  return json as Scene;
}

export function validateCoastline(json: Json, file = "coastline.json"): Coastline {
  const c = new Checker();
  const o = c.obj(json, "", COASTLINE_REQUIRED);
  if (o) {
    c.is(o.schemaVersion, "schemaVersion", [1]);
    c.is(o.units, "units", ["m"]);
    c.str(o.frame, "frame");
    c.num(o.gridM, "gridM", { exclusiveMin: 0 });
    c.num(o.floorBandM, "floorBandM", { exclusiveMin: 0 });
    if (o.radiiM !== undefined) checkRadii(c, o.radiiM, "radiiM");
    c.vec(o.gridOrigin, "gridOrigin", 2);
    c.vec(o.gridShape, "gridShape", 2);
    c.list(o.polylines, "polylines", 0)?.forEach((pl, i) => {
      const path = `polylines[${i}]`;
      const p = c.obj(pl, path, ["closed", "points"]);
      if (!p) return;
      c.bool(p.closed, `${path}.closed`);
      c.list(p.points, `${path}.points`, 2)?.forEach((pt, j) => c.vec(pt, `${path}.points[${j}]`, 2));
    });
    c.num(o.lengthM, "lengthM", { min: 0 });
  }
  if (c.problems.length) throw new ContractError(file, c.problems);
  return json as Coastline;
}
