import * as THREE from "three";
import { dyno, SparkRenderer, type SplatMesh } from "@sparkjsdev/spark";
import { SPARK_PIXEL_RADIUS, type Budget } from "./device.ts";
import { makeCoastlineLines, type CoastlineLines } from "./coastline.ts";
import { DataPasses, type Twin } from "./ink/gbuffer.ts";
import { LAYER } from "./ink/layers.ts";
import { InkPass } from "./ink/outline.ts";
import { applyShade, makeShadeUniforms, srgbVector, type DynoFloat, type ShadeUniforms } from "./ink/paper.ts";
import { MAP_CEILING_CUT_M, MapView } from "./map.ts";
import type { DebugView } from "./params.ts";
import type { Coastline } from "./contract.ts";
import { type LoadedScene, SplatWorld, type SplatWorldHooks, type World, type WorldMesh } from "./scene.ts";
import type { Tokens } from "./theme/tokens.ts";
import { applyPose, createWalk, walkModeFor, type WalkController, type WalkMode } from "./walk.ts";
import { FrameWindow, type HudNumbers } from "./hud.ts";

// The G-buffer stores depth in this range, so keep it tight around a walkable flat.
const NEAR = 0.05;
const FAR = 30;
const FOV = 70;
const MAX_STD_DEV = Math.sqrt(8);
// Spark's docs allow sqrt(4)..sqrt(9); a headset draws two eyes, so it takes the cheaper end.
const MAX_STD_DEV_XR = Math.sqrt(5);
// A file whose detail cut never arrives (a failed worker) is shown anyway after this long: a coarse
// room is better than none.
const CUT_TIMEOUT_MS = 20_000;

export interface ViewerOptions {
  loaded: LoadedScene;
  budget: Budget;
  tokens: Tokens;
  ink: boolean;
  coast: boolean;
  debug: DebugView | null;
  walk?: WalkMode | null;
  /** Which file fills the measured slot (measuredKeyFor decides); the full one when absent. */
  measuredFile?: "measured" | "measuredPhone";
  /** A fixed drawing-buffer size, for frame dumps; the window's size otherwise. */
  fixedSize?: { width: number; height: number } | null;
  start: { position: THREE.Vector3Like; yaw: number; pitch: number };
  container: HTMLElement;
  /** Builds the first world; Part 1's three files when absent (the ladder passes a rung's). */
  world?: WorldFactory;
}

export type WorldFactory = (three: THREE.Scene, hooks: SplatWorldHooks) => World;

/** Pen lines laid over the world (the ladder's wedges and plan): they follow the canvas size and the scheme. */
export interface Overlay {
  setResolution(w: number, h: number): void;
  setColour(hex: string): void;
}

/**
 * The render graph: G-buffer and flag passes, edges at data resolution, the shade pass to the
 * canvas, then one full-resolution present of outlines, hatching and grain.
 */
export class Viewer {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  readonly spark: SparkRenderer;
  readonly data: DataPasses;
  readonly ink: InkPass;
  world: World;
  coast: CoastlineLines;
  readonly overlays = new Set<Overlay>();
  readonly map: MapView;
  readonly frames = new FrameWindow();
  /** The camera's parent in a headset session: the rig is what the walk moves; the headset adds the head. */
  readonly rig = new THREE.Group();
  walk: WalkController;
  readonly walkMode: WalkMode;
  /** Runs before each frame's walk update, so a caller can move the camera or sample what the frame will draw. */
  beforeFrame: ((dt: number) => void) | null = null;
  /** Called whenever the map opens or closes, however it was asked. */
  onMapChange: ((open: boolean) => void) | null = null;
  /** Measurement only: false skips the data passes and the present (the cost A/B). */
  inkPassesOn = true;
  private readonly shade: ShadeUniforms;
  private readonly twins = new Map<SplatMesh, Twin>();
  /** The red-pen flag of each mesh that has one (the ladder's wrong file): 1 while the pen is on. */
  private readonly redFlags = new Map<SplatMesh, DynoFloat>();
  private redPenOn = false;
  /** Files in the scene whose detail cut has not arrived: invisible (alpha 0) but already asking for it. */
  private readonly held = new Map<SplatMesh, { reveal: DynoFloat; shown: () => void; since: number }>();
  private readonly walkMask = (1 << LAYER.shade) | (1 << LAYER.walk);
  private budget: Budget;
  private inkOn: boolean;
  private coastOn: boolean;
  private tokens: Tokens;
  private last = 0;
  private framesDrawn = 0;
  private readyFrames = 0;
  private running = false;
  private xrOn = false;
  private beforeXr: { budget: Budget; walk: WalkController } | null = null;

  constructor(private readonly o: ViewerOptions) {
    this.budget = o.budget;
    this.inkOn = o.ink;
    this.coastOn = o.coast;
    this.tokens = o.tokens;
    const { scene: contract, coastline } = o.loaded;

    // Spark's docs ask for antialias: false; splats are sorted and blended per pixel.
    this.renderer = new THREE.WebGLRenderer({ antialias: false });
    this.renderer.setPixelRatio(o.budget.pixelRatio);
    const [vw, vh] = this.viewSize();
    this.renderer.setSize(vw, vh);
    this.renderer.setClearColor(o.tokens.unscanned);
    const canvas = this.renderer.domElement;
    canvas.tabIndex = 0;
    canvas.setAttribute("role", "application");
    canvas.setAttribute("aria-label", "The walk-in world. W A S D or the arrow keys walk; the mouse looks once you are in. On a touch screen, a left thumb walks and a drag looks.");
    o.container.prepend(canvas);

    this.camera = new THREE.PerspectiveCamera(FOV, vw / vh, NEAR, FAR);
    this.camera.layers.mask = this.walkMask;

    this.spark = new SparkRenderer({
      renderer: this.renderer, maxStdDev: MAX_STD_DEV, lodSplatCount: o.budget.lodSplatCount,
      minPixelRadius: SPARK_PIXEL_RADIUS.min, maxPixelRadius: SPARK_PIXEL_RADIUS.max,
    });
    this.spark.layers.set(LAYER.shade);
    this.scene.add(this.spark, this.rig);

    const [dw, dh] = this.dataSize();
    this.data = new DataPasses(this.renderer, this.scene, {
      width: dw, height: dh, near: NEAR, far: FAR, maxStdDev: MAX_STD_DEV,
      lodSplatCount: o.budget.lodSplatCount, dataScale: o.budget.dataScale,
    });
    this.ink = new InkPass(this.data.gbufTarget.texture, this.data.flagTarget.texture, dw, dh, NEAR, FAR);
    this.shade = makeShadeUniforms(o.tokens.paper, o.ink, o.tokens.red);
    this.configureInk();

    this.coast = makeCoastlineLines(coastline, o.tokens.ink, contract.floor.y);
    this.scene.add(this.coast.floor, this.coast.map);
    this.coast.setVisible(o.coast);

    this.map = new MapView(contract, coastline, o.container);
    this.map.setCoastVisible(o.coast);

    const eyeY = contract.floor.y + contract.eyeHeightM;
    this.walkMode = o.walk ?? walkModeFor(null, window.matchMedia?.("(pointer: coarse)").matches ?? false);
    this.walk = createWalk(canvas, { walkable: contract.walkable.polygons, eyeY }, o.start, this.walkMode);

    this.world = (o.world ?? ((three, hooks) => new SplatWorld(three, o.loaded, hooks, o.measuredFile ?? "measured")))(this.scene, this.hooks);

    this.resize();
    window.addEventListener("resize", () => this.resize());
  }

  private readonly hooks: SplatWorldHooks = {
    added: (m, shown) => this.attach(m, shown),
    removed: (m) => this.detach(m),
  };

  /**
   * Drops the world being drawn and builds another in its place: the walk's three files, or a ladder rung's.
   * The old world's meshes leave the scene and free their memory before the new one fetches anything.
   */
  replaceWorld(make: WorldFactory): World {
    this.world.dispose();
    this.world = make(this.scene, this.hooks);
    return this.world;
  }

  /** The default world, for the way back from the ladder. */
  walkWorld(): WorldFactory {
    return (three, hooks) => new SplatWorld(three, this.o.loaded, hooks, this.o.measuredFile ?? "measured");
  }

  /** Swaps the floor's pen line (and the map's) for another set of polylines, keeping the switch and the scheme. */
  setCoastline(c: Pick<Coastline, "polylines">) {
    this.scene.remove(this.coast.floor, this.coast.map);
    this.coast.dispose();
    this.coast = makeCoastlineLines(c, this.tokens.ink, this.o.loaded.scene.floor.y);
    this.scene.add(this.coast.floor, this.coast.map);
    this.coast.setVisible(this.coastOn);
    const buf = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    this.coast.setResolution(buf.x, buf.y);
  }

  addOverlay(o: Overlay & { walk: THREE.Object3D; map: THREE.Object3D }) {
    this.scene.add(o.walk, o.map);
    this.overlays.add(o);
    const buf = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    o.setResolution(buf.x, buf.y);
    o.setColour(this.tokens.ink);
  }

  removeOverlay(o: Overlay & { walk: THREE.Object3D; map: THREE.Object3D }) {
    this.scene.remove(o.walk, o.map);
    this.overlays.delete(o);
  }

  /** The red pen: the ladder's wrong file is drawn in red ink (and a red wash in the map), or as plain imagined. */
  setRedPen(on: boolean) {
    this.redPenOn = on;
    for (const f of this.redFlags.values()) f.value = on ? 1 : 0;
    this.refreshMeshes();
    for (const t of this.twins.values()) t.flag.updateVersion();
  }

  get redPen() {
    return this.redPenOn;
  }

  private attach(m: WorldMesh, shown: () => void) {
    const reveal = dyno.dynoFloat(m.lod ? 0 : 1);
    const red = m.wrong ? dyno.dynoFloat(this.redPenOn ? 1 : 0) : undefined;
    if (red) this.redFlags.set(m.mesh, red);
    applyShade(m.mesh, this.shade, m.provenance, reveal, red);
    this.twins.set(m.mesh, this.data.addTwin(m.mesh, m.provenance, reveal, red));
    if (m.lod) this.held.set(m.mesh, { reveal, shown, since: performance.now() });
    else shown();
  }

  private detach(m: WorldMesh) {
    const t = this.twins.get(m.mesh);
    if (t) this.data.removeTwin(t);
    this.twins.delete(m.mesh);
    this.held.delete(m.mesh);
    this.redFlags.delete(m.mesh);
  }

  /** Whether a frame runs the data passes: they, and so their detail cuts, exist only then. */
  private get dataPassesRun() {
    return !this.xrOn && !this.mapOn && this.inkPassesOn && this.ink.needed && this.o.debug !== "shade";
  }

  private cutIn(mesh: SplatMesh, t: Twin) {
    return this.spark.lodInstances.has(mesh) && this.data.gbufSpark.lodInstances.has(t.gbuf) && this.data.flagSpark.lodInstances.has(t.flag);
  }

  /**
   * Shows each held file once its detail cut is in every renderer that draws it. Spark answers a
   * cut on a worker, and until it does a far-off view of the file is the tree's coarse root; the
   * world swaps its preview for the full room in the `shown` call made here, in the same frame.
   */
  private revealCuts() {
    if (this.held.size === 0) return;
    const now = performance.now();
    for (const [mesh, h] of this.held) {
      const t = this.twins.get(mesh);
      if (!t) continue;
      const cut = this.dataPassesRun ? this.cutIn(mesh, t) : this.spark.lodInstances.has(mesh);
      const overdue = now - h.since > CUT_TIMEOUT_MS;
      if (!cut && !overdue) continue;
      if (!cut) console.warn(`${mesh.name}: no level-of-detail cut after ${CUT_TIMEOUT_MS / 1000} s; showing it as it is`);
      this.held.delete(mesh);
      h.reveal.value = 1;
      mesh.updateVersion();
      t.gbuf.updateVersion();
      t.flag.updateVersion();
      h.shown();
    }
  }

  private viewSize(): [number, number] {
    const f = this.o.fixedSize;
    return f ? [f.width, f.height] : [window.innerWidth, window.innerHeight];
  }

  private dataSize(): [number, number] {
    const v = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    return [Math.max(1, Math.round(v.x * this.budget.dataScale)), Math.max(1, Math.round(v.y * this.budget.dataScale))];
  }

  private configureInk() {
    this.ink.configure({
      dataScale: this.budget.dataScale,
      dpr: this.renderer.getPixelRatio(),
      ink: this.tokens.ink,
      red: this.tokens.red,
      paper: this.tokens.paper,
      lightTravel: this.o.loaded.scene.light.direction,
      inkOn: this.inkOn,
      coast: this.coastOn,
      debug: this.o.debug,
    });
  }

  resize() {
    // A headset session owns the drawing buffer; resizing it mid-session only produces warnings.
    if (this.renderer.xr.isPresenting) return;
    const [w, h] = this.viewSize();
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    const [dw, dh] = this.dataSize();
    this.data.setSize(dw, dh);
    this.ink.setSize(dw, dh);
    const buf = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    this.coast.setResolution(buf.x, buf.y);
    for (const o of this.overlays) o.setResolution(buf.x, buf.y);
    this.map.resize(w, h);
  }

  /** Flips the imagined half between ink and the plain filter (the switch, ?ink=off). */
  setInk(on: boolean) {
    this.inkOn = on;
    this.shade.ink.value = on ? 1 : 0;
    this.refreshMeshes();
    this.configureInk();
  }

  setCoast(on: boolean) {
    this.coastOn = on;
    this.coast.setVisible(on);
    this.map.setCoastVisible(on);
    this.configureInk();
  }

  setTokens(t: Tokens) {
    this.tokens = t;
    this.renderer.setClearColor(t.unscanned);
    this.shade.paper.value = srgbVector(t.paper);
    this.shade.red.value = srgbVector(t.red);
    this.coast.setColour(t.ink);
    for (const o of this.overlays) o.setColour(t.ink);
    this.refreshMeshes();
    this.configureInk();
  }

  /** A new device class (a headset session) brings its own splat budget and data scale. */
  setBudget(b: Budget) {
    this.budget = b;
    this.spark.lodSplatCount = b.lodSplatCount;
    this.data.setLod(b.lodSplatCount, b.dataScale);
    this.renderer.setPixelRatio(b.pixelRatio);
    this.resize();
    this.configureInk();
  }

  /**
   * Each SparkRenderer has finished sorting, and its level-of-detail worker has answered, for the
   * view it was last given. Until the worker answers, a far-off view shows the tree's coarse root.
   */
  get settled() {
    return [this.spark, this.data.gbufSpark, this.data.flagSpark].every((s) => !s.sorting && !s.sortDirty && s.sortTimeoutId === undefined
      && !s.lodDirty && s.lodInitQueue.length === 0 && s.currentLod === s.lastLod);
  }

  /**
   * A cut was asked for while another was in flight, and nothing is sorting that a frame could
   * disturb: Spark asks again only from inside a frame, so with no loop running it waits for one.
   */
  get lodStalled() {
    const all = [this.spark, this.data.gbufSpark, this.data.flagSpark];
    return all.some((s) => s.lodDirty) && all.every((s) => !s.sorting && !s.sortDirty && s.sortTimeoutId === undefined);
  }

  /** Every mesh has a level-of-detail cut in each of the three renderers (film mode waits for this before its first frame). */
  get lodReady() {
    if (this.twins.size === 0) return false;
    for (const [mesh, t] of this.twins) if (!this.cutIn(mesh, t)) return false;
    return true;
  }

  get sceneContract() {
    return this.o.loaded.scene;
  }

  get xrActive() {
    return this.xrOn;
  }

  /**
   * Switches to and from the headset configuration: the XR budget, Spark set as its docs ask for XR,
   * the camera inside the rig, and the headset's walk. The screen-space ink passes are off in a
   * headset (they would need per-eye targets): the photograph and the paper draw per eye, and the
   * floor coastline, being world geometry, stays. `xr` is null to leave.
   */
  setXr(xr: { budget: Budget; walk: WalkController } | null) {
    if ((xr !== null) === this.xrOn) return;
    if (xr) {
      if (this.mapOn) this.setMap(false);
      this.beforeXr = { budget: this.budget, walk: this.walk };
      this.setBudget(xr.budget);
      this.xrOn = true;
      this.spark.preUpdate = false;
      this.spark.maxStdDev = MAX_STD_DEV_XR;
      this.data.setVisible(false);
      this.rig.add(this.camera);
      this.walk = xr.walk;
    } else {
      this.xrOn = false;
      const back = this.beforeXr;
      this.beforeXr = null;
      this.spark.preUpdate = true;
      this.spark.maxStdDev = MAX_STD_DEV;
      this.data.setVisible(true);
      this.rig.remove(this.camera);
      this.camera.position.set(0, 0, 0);
      if (back) {
        this.walk = back.walk;
        this.setBudget(back.budget);
      }
    }
    this.refreshMeshes();
  }

  setMap(on: boolean) {
    this.map.visible = on;
    this.shade.clipY.value = on ? this.o.loaded.scene.floor.y + MAP_CEILING_CUT_M : 1e6;
    this.refreshMeshes();
    this.onMapChange?.(on);
  }

  get mapOn() {
    return this.map.visible;
  }

  /** Dyno uniforms apply at Spark's next generate, which a still camera never triggers by itself. */
  private refreshMeshes() {
    for (const mesh of this.twins.keys()) mesh.updateVersion();
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.last = performance.now();
    this.renderer.setAnimationLoop((now) => this.frame(now));
  }

  stop() {
    this.running = false;
    this.renderer.setAnimationLoop(null);
  }

  /** One frame without the animation loop, at a fixed dt, so a frame dump is the same pose on every run. */
  step(dtSeconds: number) {
    this.render(dtSeconds, this.last + dtSeconds * 1000);
    this.last += dtSeconds * 1000;
  }

  private frame(now: number) {
    const dt = Math.min(0.1, Math.max(0, (now - this.last) / 1000));
    this.frames.push(now, now - this.last);
    this.last = now;
    this.render(dt, now);
  }

  private render(dt: number, now: number) {
    this.revealCuts();
    this.beforeFrame?.(dt);
    this.walk.update(dt);
    const pose = this.walk.pose();
    const r = this.renderer;

    if (this.xrOn) {
      this.rig.position.copy(pose.position);
      this.rig.rotation.set(0, pose.yaw, 0);
      // Without a headset (?xr=mock) the camera stands in at eye height; with one, three sets it per eye.
      if (!r.xr.isPresenting) {
        this.camera.position.set(0, this.o.loaded.scene.eyeHeightM, 0);
        this.camera.rotation.set(0, 0, 0);
      }
      this.rig.updateMatrixWorld(true);
      this.camera.layers.mask = this.walkMask;
      // The XR manager binds its own framebuffer for the frame; resetting the target would unbind it.
      if (!r.xr.isPresenting) r.setRenderTarget(null);
      r.render(this.scene, this.camera);
    } else if (this.mapOn) {
      applyPose(this.camera, pose);
      r.setRenderTarget(null);
      r.render(this.scene, this.map.camera);
      this.map.placeVisitor(pose.position, pose.yaw, ...this.viewSize());
    } else {
      applyPose(this.camera, pose);
      const inkPasses = this.dataPassesRun && this.twins.size > 0;
      if (inkPasses) {
        this.data.render(this.camera, this.walkMask);
        this.ink.detect(r);
      }
      this.camera.layers.mask = this.walkMask;
      r.setRenderTarget(null);
      r.render(this.scene, this.camera);
      if (inkPasses) this.ink.present(r, this.camera);
    }
    this.framesDrawn++;
    this.markProgress(now);
  }

  /** Test and measurement hooks read these; tests never read a half-drawn frame. */
  private markProgress(now: number) {
    const root = document.documentElement.dataset;
    if (this.spark.activeSplats > 0 && root.firstSplats === undefined) root.firstSplats = now.toFixed(0);
    const passes = this.mapOn || !this.ink.needed || (this.data.activeSplats.gbuf > 0 && this.data.activeSplats.flag > 0);
    if (this.world.fullyLoaded && this.spark.activeSplats > 0 && passes) this.readyFrames++;
    if (this.readyFrames >= 3 && root.ready !== "1") root.ready = "1";
  }

  get frameCount() {
    return this.framesDrawn;
  }

  hudNumbers(): HudNumbers {
    const s = this.frames.stats();
    const buf = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    const [dw, dh] = this.dataSize();
    return {
      medianFrameMs: s.median,
      p90FrameMs: s.p90,
      frames: s.frames,
      windowS: s.windowS,
      splatsRendered: this.spark.activeSplats,
      splatsLoaded: this.world.splatCount,
      lod: { enabled: this.spark.enableLod, splatBudget: this.budget.lodSplatCount, deviceClass: this.budget.deviceClass },
      measuredFile: this.world.measuredFile,
      dataScale: this.budget.dataScale,
      dataPassPx: [dw, dh],
      canvasPx: [buf.x, buf.y],
      dpr: this.renderer.getPixelRatio(),
      ink: this.inkOn,
      userAgent: navigator.userAgent,
    };
  }
}
