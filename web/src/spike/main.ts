import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { dyno, SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import "../theme/tokens.css";
import { tokensFor } from "../theme/tokens.ts";
import {
  flagModifier, gbufferModifier, LAYER_FLAG, LAYER_GBUF, LAYER_SHADE, makeDataPass, makeSplitUniforms,
  paperModifier, renderDataPass, type DataPass,
} from "./splatPasses.ts";
import { OutlinePass, type DebugView } from "./outlinePass.ts";
import { median, PASSES, PassTimer, quantile } from "./timing.ts";

const params = new URLSearchParams(location.search);
const VIEWS: DebugView[] = ["shade", "depth", "normal", "flag", "edges", "final"];
const view = (VIEWS.find((v) => v === params.get("pass")) ?? "final") as DebugView;
const maxStdDev = params.get("stddev") === "4" ? Math.sqrt(4) : Math.sqrt(8);
const orbit = params.get("orbit") === "1";
const hud = params.get("hud") === "1";
// Spike-only knobs for repeatable measurement poses.
const angleDeg = Number(params.get("angle") ?? "0");
const dist = Number(params.get("dist") ?? "3");
const elevDeg = Number(params.get("elev") ?? "15");
const paper = params.get("paper") !== "0";
let passesOn = params.get("passes") !== "0";
const coast = params.get("coast") !== "0";
const separable = params.get("dilate") !== "brute";
let postOn = params.get("post") !== "0";
const flagOn = params.get("flagpass") !== "0";
const sortMs = Number(params.get("sortms") ?? "0");
const dataFirst = params.get("order") !== "canvas-first";
// Data passes (G-buffer, flag, edge detection) at a fraction of canvas resolution.
const gscale = Math.min(1, Math.max(0.25, Number(params.get("gscale") ?? "1")));
const sync = params.get("sync") === "1";

const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
const tokens = tokensFor(dark);

const renderer = new THREE.WebGLRenderer({ antialias: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 3));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(tokens.paper);
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
// A tight depth range keeps depth01 meaningful; the G-buffer stores it, not raw metres.
const NEAR = 0.05;
const FAR = 20;
const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, NEAR, FAR);
const target = new THREE.Vector3(0, 0, -3);

function pose(angle: number) {
  const a = THREE.MathUtils.degToRad(angle);
  const e = THREE.MathUtils.degToRad(elevDeg);
  camera.position.set(
    target.x + dist * Math.cos(e) * Math.sin(a),
    target.y + dist * Math.sin(e),
    target.z + dist * Math.cos(e) * Math.cos(a),
  );
  camera.lookAt(target);
}
pose(angleDeg);

const spark = new SparkRenderer({ renderer, maxStdDev });
spark.layers.set(LAYER_SHADE);
scene.add(spark);

const split = makeSplitUniforms(1, true);
const mesh = new SplatMesh({ url: "/sample/butterfly.spz" });
// Splat files are authored y-down; a half-turn about x stands the sample upright.
mesh.quaternion.set(1, 0, 0, 0);
mesh.position.copy(target);
mesh.layers.set(LAYER_SHADE);
if (paper) {
  // Splat rgb and the canvas are both sRGB-encoded, while THREE.Color stores linear values.
  const srgb = (hex: string) => new THREE.Color(hex).convertLinearToSRGB();
  mesh.worldModifier = paperModifier(split, srgb(tokens.paper), srgb(tokens.ink)).modifier;
  mesh.updateGenerator();
}
scene.add(mesh);
split.planeX.value = target.x;

const controls = orbit ? null : new OrbitControls(camera, renderer.domElement);
if (controls) {
  controls.target.copy(target);
  controls.update();
}

function bufferSize() {
  const v = renderer.getDrawingBufferSize(new THREE.Vector2());
  return { w: Math.round(v.x * gscale), h: Math.round(v.y * gscale) };
}

let gbuf: DataPass | null = null;
let flag: DataPass | null = null;
let outline: OutlinePass | null = null;
const near = dyno.dynoFloat(NEAR);
const far = dyno.dynoFloat(FAR);

void mesh.initialized.then(() => {
  const { w, h } = bufferSize();
  gbuf = makeDataPass({
    renderer, scene, source: mesh, layer: LAYER_GBUF, width: w, height: h, maxStdDev, halfFloat: true, minSortIntervalMs: sortMs,
    modifier: (m) => gbufferModifier(m, near, far),
  });
  flag = makeDataPass({
    renderer, scene, source: mesh, layer: LAYER_FLAG, width: w, height: h, maxStdDev, halfFloat: false, minSortIntervalMs: sortMs,
    modifier: () => flagModifier(split),
  });
  outline = new OutlinePass(gbuf.target.texture, flag.target.texture, w, h, NEAR, FAR);
  outline.configure({ scale: gscale, dpr: renderer.getPixelRatio(), ink: tokens.ink, paper: tokens.paper, view, dist, coast, separable });
});

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  const { w, h } = bufferSize();
  // SparkRenderer has no resize for its target; the WebGLRenderTarget itself resizes cleanly.
  gbuf?.target.setSize(w, h);
  flag?.target.setSize(w, h);
  outline?.setSize(w, h);
});

const timer = new PassTimer(renderer.getContext() as WebGL2RenderingContext, sync, params.get("gputimer") === "1");
const hudEl = hud ? document.createElement("pre") : null;
if (hudEl) {
  hudEl.style.cssText = `position:fixed;left:12px;top:12px;margin:0;padding:8px 10px;font:12px/1.4 var(--font-mono);
    color:${tokens.ink};background:${tokens.paper}cc;pointer-events:none;white-space:pre`;
  document.body.appendChild(hudEl);
}

let frameCount = 0;
let readyFrames = 0;
let last = performance.now();
let hudSince = performance.now();
const ORBIT_DEG_PER_FRAME = 0.25;

function stats() {
  const fmt = (xs: number[]) => xs.length ? `${median(xs).toFixed(2)} (p90 ${quantile(xs, 0.9).toFixed(2)}, n ${xs.length})` : "n/a";
  const lines = [`frame ms   ${fmt(timer.frame)}`];
  for (const p of PASSES) lines.push(`${p.padEnd(6)} gpu ${fmt(timer.gpu[p])}${sync ? `  wall ${fmt(timer.wall[p])}` : ""}`);
  lines.push(`timer query ${timer.hasGpuTimer ? "yes" : "no"}  dpr ${renderer.getPixelRatio()}  view ${view}`);
  return lines.join("\n");
}

renderer.setAnimationLoop(() => {
  const now = performance.now();
  const frameMs = now - last;
  last = now;
  frameCount++;
  if (orbit) pose(angleDeg + frameCount * ORBIT_DEG_PER_FRAME);
  else controls?.update();

  const ready = gbuf !== null && flag !== null && outline !== null;
  const showShade = view === "shade" || view === "final";

  const g = gbuf, f = flag, o = outline;
  const extra = passesOn && g !== null && f !== null && o !== null;
  const drawShade = () => {
    timer.begin("shade");
    camera.layers.set(LAYER_SHADE);
    renderer.setRenderTarget(null);
    if (showShade) renderer.render(scene, camera);
    else renderer.clear();
    timer.end("shade");
  };

  // Off-screen work first, then the two canvas draws back to back, so a tiled GPU opens the
  // canvas once a frame. On the M5 the order made no difference within the noise (?order=canvas-first).
  if (!dataFirst) drawShade();
  if (extra) {
    timer.begin("gbuf");
    renderDataPass(g, renderer, scene, camera, LAYER_GBUF);
    timer.end("gbuf");
    timer.begin("flag");
    if (flagOn) renderDataPass(f, renderer, scene, camera, LAYER_FLAG);
    timer.end("flag");
  }
  const post = extra && view !== "shade" && postOn ? o : null;
  if (post) { timer.begin("post"); post.detect(renderer); timer.end("post"); }
  if (dataFirst) drawShade();
  if (post) post.present(renderer);
  timer.poll(frameMs);

  if (hudEl && now - hudSince > 5000) {
    hudEl.textContent = stats();
    hudSince = now;
  }

  // Ready once every pass has sorted its splats at least once, so tests never read a half frame.
  const sorted = (!showShade || spark.activeSplats > 0) && (!passesOn || (gbuf?.spark.activeSplats ?? 0) > 0 && (!flagOn || (flag?.spark.activeSplats ?? 0) > 0));
  if (ready && sorted) readyFrames++;
  if (readyFrames >= 3 && document.documentElement.dataset.ready !== "1") {
    document.documentElement.dataset.ready = "1";
  }
});

// Measurement hooks for the spike's Playwright scripts; harmless in a production build.
(window as unknown as { __spike: unknown }).__spike = {
  renderer, scene, camera, spark, mesh,
  get gbuf() { return gbuf; },
  get flag() { return flag; },
  get outline() { return outline; },
  stats, timer,
  resetTimers: () => timer.reset(),
  setPasses: (on: boolean) => { passesOn = on; },
  setPost: (on: boolean) => { postOn = on; },
  // Each pass run back to back between two forced syncs, the camera stepping 0.5° each time so
  // Spark regenerates its splats as it would while walking. Sync overhead is paid once per batch.
  bench: (iterations = 40) => {
    if (!gbuf || !flag || !outline) return null;
    const g = gbuf, f = flag, o = outline;
    const gl = renderer.getContext();
    const px = new Uint8Array(4);
    const syncGpu = () => {
      const bound = gl.getParameter(gl.FRAMEBUFFER_BINDING) as WebGLFramebuffer | null;
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      gl.bindFramebuffer(gl.FRAMEBUFFER, bound);
    };
    const pos = camera.position.clone();
    const quat = camera.quaternion.clone();
    const run = (fn: () => void) => {
      syncGpu();
      const t0 = performance.now();
      for (let i = 0; i < iterations; i++) {
        pose(angleDeg + frameCount * ORBIT_DEG_PER_FRAME + i * 0.5);
        fn();
      }
      syncGpu();
      return (performance.now() - t0) / iterations;
    };
    const result = {
      empty: run(() => {}),
      shade: run(() => { camera.layers.set(LAYER_SHADE); renderer.setRenderTarget(null); renderer.render(scene, camera); }),
      gbuf: run(() => renderDataPass(g, renderer, scene, camera, LAYER_GBUF)),
      flag: run(() => renderDataPass(f, renderer, scene, camera, LAYER_FLAG)),
      post: run(() => { o.detect(renderer); o.present(renderer); }),
    };
    camera.position.copy(pos);
    camera.quaternion.copy(quat);
    return result;
  },
  // Softness of the silhouette: pixels with partial coverage per pixel of the coverage = 0.5 contour,
  // i.e. the mean width in device pixels of the 10–90 % coverage ramp.
  coverageRamp: () => {
    if (!gbuf) return null;
    const { width: w, height: h } = gbuf.target;
    const buf = new Uint16Array(w * h * 4);
    renderer.readRenderTargetPixels(gbuf.target, 0, 0, w, h, buf);
    const a = (x: number, y: number) => THREE.DataUtils.fromHalfFloat(buf[(y * w + x) * 4 + 3]);
    let ramp = 0, contour = 0;
    for (let y = 1; y < h - 1; y++) {
      for (let x = 1; x < w - 1; x++) {
        const v = a(x, y);
        if (v > 0.1 && v < 0.9) ramp++;
        if (v >= 0.5 && (a(x + 1, y) < 0.5 || a(x - 1, y) < 0.5 || a(x, y + 1) < 0.5 || a(x, y - 1) < 0.5)) contour++;
      }
    }
    return { rampPx: ramp / Math.max(1, contour), contour, ramp };
  },
  frame: () => frameCount,
  // Screen x (CSS px) where the splitting plane crosses the mesh centre, for the e2e half check.
  planeScreenX: () => {
    const v = new THREE.Vector3(split.planeX.value, target.y, target.z).project(camera);
    return (v.x * 0.5 + 0.5) * window.innerWidth;
  },
  splatCount: () => mesh.packedSplats?.numSplats ?? 0,
};
