import * as THREE from "three";
import type { Coastline, Scene } from "./contract.ts";
import { LAYER } from "./ink/layers.ts";

/** Splats above this world height are cut in the map, so the ceiling does not hide the floor plan. */
export const MAP_CEILING_CUT_M = 1.2;
const PAD_M = 0.6;
/** A few pixels of the measured photograph itself, as the legend's swatch for it. */
export const PHOTO_SAMPLE_PNG = "iVBORw0KGgoAAAANSUhEUgAAABIAAAAMCAIAAADgcHrrAAACEklEQVR42gXBzW7TQBAA4N3ZPydOHJIUSItUVUiAUDhx7Tty4MaBdwBxRRx4ACREVSEENFClbRo3oXHttXd3Zvg++frtO2YBkltfleXFxeLHyxdPDg72uqb2jW9aPxiNM9dj6TrK1+tyNJnW1Qass2CEUsJp6Dl79HT+/Wz14eOXsnUEzukMhFBKKSkkIyEyC2MNCMEiEUi+q7fry8X2epkNR1f1+PNJ++rN+9PFpdFWAEgFUsqExIKVMSCj4MhN04KyxWRPGiO1vDdVN9dny+UyuJ5QGpEZJINMCRETgILORwzYVE0IQkjr8sJa226uyj8n4+no/NdZQowphZiQkJhiTBpAS6mIRAhRZdq4XKSAiL6qHj+bl+tyvD9DKURKRIRCW6uJk5AZ3O7Kqt56v4vR+xC6EK3TblSYYaGNWa2uG98yYgqBmWyWYUpMpL99/WS00cbpLCPm6Otq969L2gymzd329+nP4/nh4f5BCh5ktM40tU8JdddVoRPASpLsat/d+c3mduv98+NJkeddMeAU+71sV1dJtmCGRESI0FecK2mB+kbIuinPr/A2TqEo//5tdrda6qvVuottf5AJToIQBDES5FnmnLJ9PZzkbmiTo3zsHh1M7w9gfvRglMPZYrGtmybK0CElBAAm1IlQSAYNTLg/m80ezvq9TGdGSiqKwc3msolRuaJNog2Vy9gYIMb/ZfFQMcNkdScAAAAASUVORK5CYII=";
/** Paper inside a pen outline: the map shows the drawing as bare paper, and the outline keeps it off the key's own paper. */
export const DRAWING_SWATCH = `<svg class="swatch drawing" viewBox="0 0 20 14" aria-hidden="true" focusable="false"><rect x="0.75" y="0.75" width="18.5" height="12.5" fill="var(--paper)" stroke="var(--ink)" stroke-width="1.5"/></svg>`;

export interface MapBounds { minX: number; maxX: number; minZ: number; maxZ: number }

/** The survey's extent on the floor: every walkable outline and every coastline point. */
export function mapBounds(scene: Scene, coast: Coastline): MapBounds {
  const b = { minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity };
  const take = ([x, z]: readonly [number, number]) => {
    b.minX = Math.min(b.minX, x); b.maxX = Math.max(b.maxX, x);
    b.minZ = Math.min(b.minZ, z); b.maxZ = Math.max(b.maxZ, z);
  };
  scene.walkable.polygons.forEach((p) => p.forEach(take));
  coast.polylines.forEach((l) => l.points.forEach(take));
  return { minX: b.minX - PAD_M, maxX: b.maxX + PAD_M, minZ: b.minZ - PAD_M, maxZ: b.maxZ + PAD_M };
}

/** A top-down orthographic view: +x to the right, -z up the screen. */
export class MapView {
  readonly camera: THREE.OrthographicCamera;
  readonly layerMask = (1 << LAYER.shade) | (1 << LAYER.map);
  readonly root: HTMLElement;
  private readonly dot: HTMLElement;
  private readonly bounds: MapBounds;

  constructor(scene: Scene, coast: Coastline, container: HTMLElement) {
    this.bounds = mapBounds(scene, coast);
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
    const cx = (this.bounds.minX + this.bounds.maxX) / 2, cz = (this.bounds.minZ + this.bounds.maxZ) / 2;
    this.camera.position.set(cx, 40, cz);
    this.camera.up.set(0, 0, -1);
    this.camera.lookAt(cx, 0, cz);
    this.camera.layers.mask = this.layerMask;

    this.root = document.createElement("div");
    this.root.className = "map";
    this.root.hidden = true;
    this.root.innerHTML = `
      <div class="map-dot" aria-hidden="true"><span></span></div>
      <section class="map-legend" aria-label="Map legend">
        <h2>The survey from above</h2>
        <dl>
          <div><dt><span class="swatch photo"></span>Photograph</dt><dd>measured by the camera</dd></div>
          <div><dt><span class="swatch photo half"></span>Half and half</dt><dd>imagined, <span data-r="covered"></span> to <span data-r="overlap"></span> from a measured point</dd></div>
          <div><dt>${DRAWING_SWATCH}Drawing</dt><dd>imagined, more than <span data-r="overlap"></span> from anything measured</dd></div>
          <div><dt><span class="swatch unscanned"></span>Not scanned</dt><dd>nothing was captured or imagined here</dd></div>
          <div data-coast><dt><span class="swatch line"></span>Pen line</dt><dd>where the measured floor ends</dd></div>
          <div><dt><span class="swatch you"><span></span></span>You</dt><dd>where you stand</dd></div>
        </dl>
      </section>`;
    this.root.style.setProperty("--photo-sample", `url("data:image/png;base64,${PHOTO_SAMPLE_PNG}")`);
    const fmt = (m: number) => (m < 1 ? `${Math.round(m * 100)} cm` : `${m.toFixed(1)} m`);
    this.root.querySelectorAll<HTMLElement>("[data-r]").forEach((el) => {
      el.textContent = fmt(scene.radiiM[el.dataset.r as "covered" | "overlap"]);
    });
    this.dot = this.root.querySelector(".map-dot")!;
    container.appendChild(this.root);
  }

  /** Puts another key in the default one's place (the ladder's), or brings the default back with null. */
  setLegend(custom: HTMLElement | null) {
    const own = this.root.querySelector<HTMLElement>(".map-legend:not(.ladder-map-key)")!;
    this.root.querySelectorAll(".ladder-map-key").forEach((e) => { if (e !== custom) e.remove(); });
    own.hidden = custom !== null;
    if (custom && custom.parentElement !== this.root) this.root.append(custom);
  }

  setCoastVisible(on: boolean) {
    this.root.querySelector<HTMLElement>("[data-coast]")!.hidden = !on;
  }

  /** Fit the survey into the canvas at its aspect ratio. */
  resize(width: number, height: number) {
    const b = this.bounds;
    const w = b.maxX - b.minX, h = b.maxZ - b.minZ;
    const aspect = width / Math.max(1, height);
    const halfH = Math.max(h / 2, w / 2 / aspect);
    this.camera.left = -halfH * aspect;
    this.camera.right = halfH * aspect;
    this.camera.top = halfH;
    this.camera.bottom = -halfH;
    this.camera.updateProjectionMatrix();
  }

  /** Moves the visitor's dot; yaw in radians (0 looks along -z, which is up the map). */
  placeVisitor(position: THREE.Vector3, yaw: number, cssWidth: number, cssHeight: number) {
    const v = new THREE.Vector3(position.x, 0, position.z).project(this.camera);
    const x = (v.x * 0.5 + 0.5) * cssWidth, y = (-v.y * 0.5 + 0.5) * cssHeight;
    this.dot.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) rotate(${(-yaw * 180) / Math.PI}deg)`;
  }

  get visible() {
    return !this.root.hidden;
  }

  set visible(on: boolean) {
    this.root.hidden = !on;
  }
}
