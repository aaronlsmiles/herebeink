import * as THREE from "three";
import { SplatMesh } from "@sparkjsdev/spark";
import { type Coastline, type Scene, type SplatFile, type SplatKey, validateCoastline, validateScene } from "./contract.ts";

export interface LoadedScene {
  scene: Scene;
  coastline: Coastline;
  /** scene.json's own URL: every file URL in it is relative to this. */
  base: URL;
  /** The preview's bytes, fetched beside the coastline so the first splats wait on nothing else. */
  previewBytes?: ArrayBuffer;
}

async function fetchJson(url: URL): Promise<unknown> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not load ${url.href}: HTTP ${res.status}`);
  try {
    return await res.json();
  } catch {
    throw new Error(`${url.href} is not valid JSON`);
  }
}

/** Fetches and checks scene.json, then its coastline. sha256 is the pipeline's check, not the browser's. */
export async function loadScene(sceneUrl: string, pageUrl = location.href, opts: { preview?: boolean } = {}): Promise<LoadedScene> {
  const base = new URL(sceneUrl, pageUrl);
  const scene = validateScene(await fetchJson(base), base.href);
  const coastUrl = new URL(scene.coastline.url, base);
  const previewUrl = new URL(scene.splats.measuredPreview.url, base);
  // A page opened straight into the ladder draws no Part 1 splats, so it skips the preview's bytes.
  const preview = opts.preview === false ? Promise.resolve(undefined) : fetch(previewUrl).then((r) => {
    if (!r.ok) throw new Error(`Could not load ${previewUrl.href}: HTTP ${r.status}`);
    return r.arrayBuffer();
  });
  const [coastJson, previewBytes] = await Promise.all([fetchJson(coastUrl), preview]);
  const coastline = validateCoastline(coastJson, coastUrl.href);
  return { scene, coastline, base, previewBytes };
}

/** Places a file's mesh in the world frame: each file keeps its own frame, scene.json gives the similarity. */
export function placeMesh(mesh: THREE.Object3D, f: SplatFile) {
  new THREE.Matrix4().fromArray(f.matrix).decompose(mesh.position, mesh.quaternion, mesh.scale);
  mesh.updateMatrixWorld(true);
}

export interface WorldMesh {
  /** Part 1's file keys, or the ladder's (seen, imagined, wrong). */
  key: string;
  provenance: number;
  mesh: SplatMesh;
  /** Whether the file carries a level-of-detail tree, so its first draw must wait for a cut. */
  lod: boolean;
  /** The ladder's wrong file: drawn as imagined, and in red while the red pen is on. */
  wrong?: boolean;
}

/** What the viewer draws: Part 1's three files, or one ladder rung's. */
export interface World {
  readonly meshes: ReadonlyMap<string, WorldMesh>;
  readonly firstSplats: Promise<void>;
  readonly complete: Promise<void>;
  /** For the HUD: which measured file fills the photograph's slot, or the rung being drawn. */
  readonly measuredFile: string;
  readonly splatCount: number;
  readonly fullyLoaded: boolean;
  /** Takes every mesh out of the scene and frees its memory; a file still arriving is dropped when it lands. */
  dispose(): void;
}

export interface SplatWorldHooks {
  /**
   * A mesh has its splats and is in the scene: attach dynos and data-pass twins, and call `shown`
   * when the mesh may be drawn. That is at once for a file with no detail tree, and for one with a
   * tree only once its cut is in every renderer that draws it; until then it would be a coarse blob.
   */
  added(m: WorldMesh, shown: () => void): void;
  /** A mesh is leaving the scene (the preview, once the full measured file is in). */
  removed(m: WorldMesh): void;
}

/**
 * The three files a visitor walks through. The measured room arrives twice: a 40k-splat preview
 * first, so the first screen is light, then the measured file (the full one, or on a phone the
 * lighter one), which replaces it at the moment it is first drawn, never before.
 */
export class SplatWorld implements World {
  /** The files being drawn: a file joins when its hook calls `shown`. */
  readonly meshes = new Map<SplatKey, WorldMesh>();
  /** In the scene but held until their detail cut arrives. */
  private readonly pending = new Set<WorldMesh>();
  private disposed = false;
  readonly firstSplats: Promise<void>;
  readonly complete: Promise<void>;
  /** The file that fills the "measured" slot, never one the scene lacks. */
  readonly measuredFile: "measured" | "measuredPhone";

  constructor(private readonly three: THREE.Scene, private readonly loaded: LoadedScene, private readonly hooks: SplatWorldHooks,
              /** The file that fills the "measured" slot: the full one, or the lighter one a phone loads. */
              measuredFile: "measured" | "measuredPhone" = "measured") {
    this.measuredFile = loaded.scene.splats[measuredFile] ? measuredFile : "measured";
    const preview = this.bring("measuredPreview");
    this.firstSplats = preview.then(() => undefined);
    // The rest waits for the preview, so on a slow line the preview has the bandwidth to itself.
    this.complete = preview.then(async () => {
      await Promise.all([this.bring("overlap"), this.bring("imagined"), this.bring("measured", () => this.retirePreview())]);
    });
  }

  dispose() {
    this.disposed = true;
    for (const m of [...this.meshes.values(), ...this.pending]) {
      this.hooks.removed(m);
      this.three.remove(m.mesh);
      m.mesh.dispose();
    }
    this.meshes.clear();
    this.pending.clear();
  }

  private retirePreview() {
    const old = this.meshes.get("measuredPreview");
    if (!old) return;
    this.hooks.removed(old);
    this.three.remove(old.mesh);
    this.meshes.delete("measuredPreview");
    old.mesh.dispose();
  }

  private file(key: SplatKey) {
    const s = this.loaded.scene.splats;
    return key === "measured" ? s[this.measuredFile]! : s[key];
  }

  private async make(key: SplatKey): Promise<WorldMesh> {
    const f = this.file(key);
    const url = new URL(f.url, this.loaded.base).href;
    // The preview is small enough to draw whole; building its LoD tree would only delay it.
    const preview = key === "measuredPreview";
    // The world can be built twice (back from the ladder); Spark may hand the first copy's buffer to a worker.
    const kept = this.loaded.previewBytes;
    const bytes = preview && kept && kept.byteLength > 0 ? kept.slice(0) : undefined;
    const mesh = bytes
      ? new SplatMesh({ fileBytes: bytes, fileName: f.url, lod: false })
      : new SplatMesh({ url, lod: !preview });
    mesh.name = key;
    placeMesh(mesh, f);
    await mesh.initialized;
    return { key, provenance: f.provenance, mesh, lod: !preview };
  }

  /** Loads a file, puts it in the scene, and resolves once it is being drawn; `onShown` runs at that moment. */
  private async bring(key: SplatKey, onShown?: () => void): Promise<WorldMesh> {
    if (this.disposed) return new Promise<WorldMesh>(() => {});
    const m = await this.make(key);
    if (this.disposed) { m.mesh.dispose(); return m; }
    this.three.add(m.mesh);
    this.pending.add(m);
    return new Promise<WorldMesh>((done) => {
      this.hooks.added(m, () => {
        this.pending.delete(m);
        this.meshes.set(key, m);
        onShown?.();
        done(m);
      });
    });
  }

  /** Splats in the files currently in the scene, before LoD (Spark keeps only the LoD tree in memory). */
  get splatCount() {
    let n = 0;
    for (const key of this.meshes.keys()) n += this.file(key).splats;
    return n;
  }

  get fullyLoaded() {
    return this.meshes.has("measured") && this.meshes.has("overlap") && this.meshes.has("imagined");
  }
}
