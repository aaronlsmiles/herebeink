import { RUNG_IDS, type RungId } from "./ladder/contract.ts";

export type DebugView = "shade" | "depth" | "normal" | "flag" | "edges";
const DEBUG_VIEWS: readonly DebugView[] = ["shade", "depth", "normal", "flag", "edges"];

export interface Pose {
  position: [number, number, number];
  yawDeg: number;
  pitchDeg: number;
}

export interface Params {
  sceneUrl: string;
  ink: boolean;
  coast: boolean;
  hud: boolean;
  map: boolean;
  /** Splat budget override; null means the device class decides. */
  lod: number | null;
  /** Data-pass scale override; null means the device class decides. */
  gscale: number | null;
  /** Pixel-ratio override (1 to 3); null means the device's own. */
  dpr: number | null;
  /** ?measured=phone|full: which measured file to load; null lets the device class decide. */
  measured: "phone" | "full" | null;
  pose: Pose | null;
  debug: DebugView | null;
  /** Forces a controller; null lets the pointer type decide. */
  walk: "desktop" | "touch" | null;
  /** "mock" shows the VR button and switches to the headset configuration without a headset. */
  xr: "mock" | null;
  /** ?path=film: the camera follows scene.json's filmPath and the chrome is hidden. */
  film: boolean;
  /** ?dump=1 with film: every settled frame is posted to the dev server's /frame. */
  dump: boolean;
  /** Names a sub-folder of film/frames/ for a dump; a plain name only. */
  frameSet: string | null;
  /** ?from= and ?frames=: only that range of the film's frames, with their real numbers (checks and re-takes). */
  frameRange: { from: number; count: number | null } | null;
  /** ?w= and ?h=: a fixed canvas size at device pixel ratio 1, for a frame dump. */
  size: { width: number; height: number } | null;
  /** ?ladder=<rung id> opens the ladder on that rung; ?ladder=1 on its first step; null keeps the walk. */
  ladder: RungId | "first" | null;
  /** ?redpen=1: the ladder's imagined splats that landed wrong are drawn in red. */
  redPen: boolean;
}

export const DEFAULT_LADDER_URL = "/fixture-ladder/ladder.json";

/**
 * Where ladder.json is: the build's own address for it, else beside the scene (…/v3/scene.json →
 * …/v3/ladder/ladder.json, where the pipeline publishes it). The dev fixture scene has its fixture ladder
 * apart, since the scene fixture's folder is rebuilt whole by make_fixture.py.
 */
export function ladderUrlFor(sceneUrl: string, envLadderUrl: string | undefined, origin: string): string {
  if (envLadderUrl) return envLadderUrl;
  if (sceneUrl === DEFAULT_SCENE_URL) return DEFAULT_LADDER_URL;
  return new URL("ladder/ladder.json", new URL(sceneUrl, origin)).href;
}

function parseLadder(v: string | null): RungId | "first" | null {
  if (v === null) return null;
  if (v === "" || v === "1") return "first";
  return RUNG_IDS.find((id) => id.toLowerCase() === v.toLowerCase()) ?? null;
}

export const DEFAULT_SCENE_URL = "/fixture/scene.json";

/** Where the page is running, which decides what `?scene=` may name. */
export interface SceneEnv {
  /** A production build only reads scenes from its own origin or the build's. */
  production: boolean;
  /** The page's origin, against which a relative `?scene=` resolves. */
  origin: string;
}

const STRICT_ENV: SceneEnv = { production: true, origin: "http://localhost" };

/**
 * A link can carry `?scene=`, so on a published page it must not point the viewer at somebody
 * else's files: only the page's own origin, or the origin of the scene the build was made for.
 */
function sceneAllowed(candidate: string, envSceneUrl: string | undefined, env: SceneEnv): boolean {
  if (!env.production) return true;
  try {
    const url = new URL(candidate, env.origin);
    if (url.protocol !== "https:" && url.protocol !== "http:") return false;
    const allowed = new Set([new URL(env.origin).origin]);
    if (envSceneUrl) allowed.add(new URL(envSceneUrl, env.origin).origin);
    return allowed.has(url.origin);
  } catch {
    return false;
  }
}

function finiteNumber(s: string | null): number | null {
  if (s === null || s.trim() === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function parsePose(s: string | null): Pose | null {
  if (!s) return null;
  const xs = s.split(",").map((v) => finiteNumber(v));
  if (xs.length !== 5 || xs.some((v) => v === null)) return null;
  const [x, y, z, yaw, pitch] = xs as number[];
  return { position: [x, y, z], yawDeg: yaw, pitchDeg: Math.max(-90, Math.min(90, pitch)) };
}

function parseRange(from: string | null, count: string | null) {
  const f = finiteNumber(from), c = finiteNumber(count);
  const fromOk = f !== null && Number.isInteger(f) && f >= 0;
  const countOk = c !== null && Number.isInteger(c) && c >= 1;
  if (!fromOk && !countOk) return null;
  return { from: fromOk ? f : 0, count: countOk ? c : null };
}

function parseSize(w: string | null, h: string | null) {
  const a = finiteNumber(w), b = finiteNumber(h);
  if (a === null || b === null || !Number.isInteger(a) || !Number.isInteger(b)) return null;
  return a >= 16 && a <= 8192 && b >= 16 && b <= 8192 ? { width: a, height: b } : null;
}

/** Off only for an explicit "off", "0" or "false", so a bare `?ink` keeps the default. */
function flagOn(v: string | null): boolean {
  return v === null || !["off", "0", "false"].includes(v.toLowerCase());
}

export function parseParams(search: string, envSceneUrl?: string, env: SceneEnv = STRICT_ENV): Params {
  const p = new URLSearchParams(search);
  const asked = p.get("scene");
  const lod = finiteNumber(p.get("lod"));
  const gscale = finiteNumber(p.get("gscale"));
  const dpr = finiteNumber(p.get("dpr"));
  const debug = p.get("debug");
  return {
    sceneUrl: (asked && sceneAllowed(asked, envSceneUrl, env) ? asked : null) || envSceneUrl || DEFAULT_SCENE_URL,
    ink: flagOn(p.get("ink")),
    coast: flagOn(p.get("coast")),
    hud: p.get("hud") === "1",
    map: p.get("map") === "1",
    lod: lod !== null && lod >= 1 ? Math.round(lod) : null,
    gscale: gscale !== null && gscale > 0 ? gscale : null,
    dpr: dpr !== null && dpr > 0 ? dpr : null,
    measured: p.get("measured") === "phone" ? "phone" : p.get("measured") === "full" ? "full" : null,
    pose: parsePose(p.get("pose")),
    debug: DEBUG_VIEWS.find((v) => v === debug) ?? null,
    xr: p.get("xr") === "mock" ? "mock" : null,
    film: p.get("path") === "film",
    dump: p.get("dump") === "1",
    frameSet: /^[a-z0-9][a-z0-9-]{0,31}$/.test(p.get("set") ?? "") ? p.get("set") : null,
    frameRange: parseRange(p.get("from"), p.get("frames")),
    size: parseSize(p.get("w"), p.get("h")),
    walk: p.get("walk") === "touch" ? "touch" : p.get("walk") === "desktop" ? "desktop" : null,
    ladder: parseLadder(p.get("ladder")),
    redPen: p.get("redpen") === "1",
  };
}
