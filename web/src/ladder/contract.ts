// The page's reading of pipeline/schema/ladder.schema.json. As with scene.json, only what the page
// relies on is checked, so an added field never breaks a published page; contract.test.ts fails if
// the schema's required lists move away from these.
import {
  Checker, checkSimilarity, ContractError, type Json, SHA256, SPLAT_FILE_REQUIRED, type SplatFile, UTC, type Vec2, type Vec3,
} from "../contract.ts";

export const RUNG_IDS = ["R1", "R2", "R4", "R4b", "R8", "R4r", "P"] as const;
export type RungId = (typeof RUNG_IDS)[number];
export const RUNG_FILE_KEYS = ["seen", "imagined", "wrong"] as const;
export type RungFileKey = (typeof RUNG_FILE_KEYS)[number];

export type LadderFile = SplatFile;
export type RungFiles = Record<RungFileKey, LadderFile>;

export interface Frustum { forward: Vec3; up: Vec3; hFovDeg: number; vFovDeg: number }

export interface LadderRung {
  id: RungId;
  label: string;
  photos: number;
  mode: "flat" | "reconstruction" | "pano";
  placed: boolean;
  /** x: share of all directions from c the inputs showed. */
  shown: number;
  /** y: share of the scored volume's directions where this world is imagined; null when not placed. */
  imagined: number | null;
  /** s: the rung's seen share of the key's scored directions; the reference line runs through (shown, 1 − s). */
  seenShareOfKey: number;
  /** The instrument's own error: where the answer key and COLMAP's points agree, within 15 and 30 cm. */
  keyAgreement: { within15: number | null; within30: number | null };
  frustums: Frustum[];
  splats?: RungFiles;
  /** Lighter files a phone loads in place of `splats`. */
  splatsPhone?: RungFiles;
  map?: { seenFloor: Vec2[][]; coastline: Vec2[][] };
  worldId: string;
  model: string;
}

export interface Ladder {
  schemaVersion: 1;
  units: "m";
  generatedAt: string;
  camera: { c: Vec3 };
  steps: RungId[];
  rungs: LadderRung[];
  credit: string;
}

export const LADDER_REQUIRED = ["schemaVersion", "units", "generatedAt", "camera", "steps", "rungs", "credit"] as const;
export const RUNG_REQUIRED = [
  "id", "label", "photos", "mode", "placed", "shown", "imagined", "seenShareOfKey", "keyAgreement", "frustums", "worldId", "model",
] as const;
export const FRUSTUM_REQUIRED = ["forward", "up", "hFovDeg", "vFovDeg"] as const;
export const MAP_REQUIRED = ["seenFloor", "coastline"] as const;
export const KEY_AGREEMENT_REQUIRED = ["within15", "within30"] as const;

/** Seen is drawn as photograph and the other two in ink; a file marked otherwise would be drawn as the wrong thing. */
const PROVENANCE: Record<RungFileKey, number> = { seen: 0, imagined: 1, wrong: 1 };

function share(c: Checker, v: Json, path: string, nullable = false) {
  if (nullable && v === null) return;
  c.num(v, path, { min: 0, max: 1 });
}

function checkFiles(c: Checker, v: Json, path: string) {
  const files = c.obj(v, path, RUNG_FILE_KEYS);
  if (!files) return;
  for (const key of RUNG_FILE_KEYS) {
    if (files[key] === undefined) continue;
    const p = `${path}.${key}`;
    const f = c.obj(files[key], p, SPLAT_FILE_REQUIRED);
    if (!f) continue;
    c.str(f.url, `${p}.url`);
    c.str(f.sha256, `${p}.sha256`, SHA256);
    c.num(f.bytes, `${p}.bytes`, { min: 1, integer: true });
    c.num(f.splats, `${p}.splats`, { min: 0, integer: true });
    c.num(f.shDegree, `${p}.shDegree`, { min: 0, max: 3, integer: true });
    c.is(f.provenance, `${p}.provenance`, [PROVENANCE[key]]);
    c.vec(f.matrix, `${p}.matrix`, 16);
    checkSimilarity(c, f.matrix, `${p}.matrix`);
  }
}

function checkPolylines(c: Checker, v: Json, path: string) {
  c.list(v, path, 0)?.forEach((line, i) => c.list(line, `${path}[${i}]`, 2)?.forEach((pt, j) => c.vec(pt, `${path}[${i}][${j}]`, 2)));
}

function checkRung(c: Checker, v: Json, path: string) {
  const r = c.obj(v, path, RUNG_REQUIRED);
  if (!r) return;
  c.is(r.id, `${path}.id`, RUNG_IDS);
  c.str(r.label, `${path}.label`);
  c.num(r.photos, `${path}.photos`, { min: 0, integer: true });
  c.is(r.mode, `${path}.mode`, ["flat", "reconstruction", "pano"]);
  c.bool(r.placed, `${path}.placed`);
  share(c, r.shown, `${path}.shown`);
  share(c, r.imagined, `${path}.imagined`, true);
  share(c, r.seenShareOfKey, `${path}.seenShareOfKey`);
  const ka = r.keyAgreement === undefined ? null : c.obj(r.keyAgreement, `${path}.keyAgreement`, KEY_AGREEMENT_REQUIRED);
  if (ka) { share(c, ka.within15, `${path}.keyAgreement.within15`, true); share(c, ka.within30, `${path}.keyAgreement.within30`, true); }
  c.list(r.frustums, `${path}.frustums`, 0)?.forEach((f, i) => {
    const p = `${path}.frustums[${i}]`;
    const o = c.obj(f, p, FRUSTUM_REQUIRED);
    if (!o) return;
    c.vec(o.forward, `${p}.forward`, 3);
    c.vec(o.up, `${p}.up`, 3);
    c.num(o.hFovDeg, `${p}.hFovDeg`, { exclusiveMin: 0, max: 180 });
    c.num(o.vFovDeg, `${p}.vFovDeg`, { exclusiveMin: 0, max: 180 });
  });
  if (r.splats !== undefined) checkFiles(c, r.splats, `${path}.splats`);
  if (r.splatsPhone !== undefined) checkFiles(c, r.splatsPhone, `${path}.splatsPhone`);
  const map = r.map === undefined ? null : c.obj(r.map, `${path}.map`, MAP_REQUIRED);
  if (map) { checkPolylines(c, map.seenFloor, `${path}.map.seenFloor`); checkPolylines(c, map.coastline, `${path}.map.coastline`); }
  c.str(r.worldId, `${path}.worldId`);
  c.str(r.model, `${path}.model`);
  // A placed rung is drawn and plotted; one that is not shows only its frames and the words "not placed".
  if (r.placed === true) {
    if (r.splats === undefined) c.problems.push(`${path}.splats: missing (a placed rung is drawn)`);
    if (r.imagined === null) c.problems.push(`${path}.imagined: should be a number on a placed rung (it is plotted)`);
  }
}

export function validateLadder(json: Json, file = "ladder.json"): Ladder {
  const c = new Checker();
  const o = c.obj(json, "", LADDER_REQUIRED);
  if (o) {
    c.is(o.schemaVersion, "schemaVersion", [1]);
    c.is(o.units, "units", ["m"]);
    c.str(o.generatedAt, "generatedAt", UTC);
    const cam = o.camera === undefined ? null : c.obj(o.camera, "camera", ["c"]);
    if (cam) c.vec(cam.c, "camera.c", 3);
    const steps = c.list(o.steps, "steps", 1);
    steps?.forEach((s, i) => c.is(s, `steps[${i}]`, RUNG_IDS));
    const rungs = c.list(o.rungs, "rungs", 1);
    rungs?.forEach((r, i) => checkRung(c, r, `rungs[${i}]`));
    const ids = (rungs ?? []).map((r) => (r && typeof r === "object" ? (r as { id?: unknown }).id : undefined));
    ids.forEach((id, i) => { if (ids.indexOf(id) !== i) c.problems.push(`rungs[${i}].id: ${JSON.stringify(id)} appears twice`); });
    steps?.forEach((s, i) => { if (rungs && !ids.includes(s)) c.problems.push(`steps[${i}]: no rung ${JSON.stringify(s)} in rungs`); });
    c.str(o.credit, "credit");
    if (typeof o.credit === "string" && o.credit.length === 0) c.problems.push("credit: should not be empty");
  }
  if (c.problems.length) throw new ContractError(file, c.problems, "ladder");
  return json as Ladder;
}

export function rungById(ladder: Ladder, id: string): LadderRung | undefined {
  return ladder.rungs.find((r) => r.id === id);
}

/** The files a device loads for a rung: a phone takes the lighter set when there is one. */
export function filesFor(rung: LadderRung, phone: boolean): RungFiles | undefined {
  return (phone ? rung.splatsPhone : undefined) ?? rung.splats;
}
