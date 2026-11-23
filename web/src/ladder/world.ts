import * as THREE from "three";
import { SplatMesh } from "@sparkjsdev/spark";
import { placeMesh, type SplatWorldHooks, type World, type WorldMesh } from "../scene.ts";
import { type LadderRung, RUNG_FILE_KEYS, type RungFileKey, type RungFiles } from "./contract.ts";

/**
 * One rung's world: its seen file drawn as photograph, its imagined and wrong files in ink. Built by the ladder
 * mode only after the previous world is disposed, so one rung is in memory at a time (kill rule 5).
 */
export class RungWorld implements World {
  readonly meshes = new Map<RungFileKey, WorldMesh>();
  readonly firstSplats: Promise<void>;
  readonly complete: Promise<void>;
  readonly measuredFile: string;
  private readonly pending = new Set<WorldMesh>();
  private disposed = false;

  constructor(private readonly three: THREE.Scene, readonly rung: LadderRung, private readonly files: RungFiles | undefined,
              private readonly base: URL, private readonly hooks: SplatWorldHooks) {
    this.measuredFile = `ladder ${rung.id}${files && files === rung.splatsPhone ? " (phone files)" : ""}`;
    if (!files) {
      this.firstSplats = this.complete = Promise.resolve();
      return;
    }
    const each = RUNG_FILE_KEYS.map((k) => this.bring(k));
    this.firstSplats = Promise.any(each).then(() => undefined);
    this.complete = Promise.all(each).then(() => undefined);
  }

  private async bring(key: RungFileKey): Promise<void> {
    const f = this.files![key];
    const mesh = new SplatMesh({ url: new URL(f.url, this.base).href, lod: true });
    mesh.name = `${this.rung.id}-${key}`;
    placeMesh(mesh, f);
    await mesh.initialized;
    if (this.disposed) { mesh.dispose(); return; }
    const m: WorldMesh = { key, provenance: key === "seen" ? 0 : 1, mesh, lod: true, wrong: key === "wrong" };
    this.three.add(mesh);
    this.pending.add(m);
    await new Promise<void>((done) => this.hooks.added(m, () => {
      this.pending.delete(m);
      this.meshes.set(key, m);
      done();
    }));
  }

  get splatCount() {
    let n = 0;
    for (const key of this.meshes.keys()) n += this.files![key].splats;
    return n;
  }

  /** A rung with no files (not placed) is complete as it is: there is nothing to wait for. */
  get fullyLoaded() {
    return !this.files || this.meshes.size === RUNG_FILE_KEYS.length;
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
}
