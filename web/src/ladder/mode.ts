// Ladder mode: Part 2's evidence ladder on the same page. The walk stays the default; this swaps the world
// for one rung's at a time, lays the rung's photo frames and seen floor over it, and keeps the panel and the
// address in step. Only one world is ever in memory: the old one is disposed before the next is fetched.
import * as THREE from "three";
import type { Coastline } from "../contract.ts";
import type { Chrome } from "../ui.ts";
import type { Viewer } from "../viewer.ts";
import { filesFor, type Ladder, type LadderRung, rungById, type RungId, validateLadder } from "./contract.ts";
import { makeWedges, type WedgeLines } from "./frustums.ts";
import { LadderPanel } from "./panel.ts";
import { makeSeenFloor } from "./plan.ts";
import { RungWorld } from "./world.ts";
import { LADDER } from "./words.ts";

type Lines = ReturnType<typeof makeSeenFloor> | WedgeLines;

export async function loadLadder(url: string, pageUrl = location.href): Promise<{ ladder: Ladder; base: URL }> {
  const base = new URL(url, pageUrl);
  const res = await fetch(base);
  if (!res.ok) throw new Error(`Could not load ${base.href}: HTTP ${res.status}`);
  let json: unknown;
  try { json = await res.json(); } catch { throw new Error(`${base.href} is not valid JSON`); }
  return { ladder: validateLadder(json, base.href), base };
}

export interface LadderModeOptions {
  viewer: Viewer;
  chrome: Chrome;
  root: HTMLElement;
  ladder: Ladder;
  base: URL;
  /** A phone loads a rung's lighter files where it has them. */
  phone: boolean;
  redPen: boolean;
  /** Part 1's coastline, put back on the way out. */
  coastline: Coastline;
}

export class LadderMode {
  readonly panel: LadderPanel;
  readonly chip: HTMLButtonElement;
  private on = false;
  private rung: LadderRung | null = null;
  private lines: Lines[] = [];
  private redPen: boolean;

  constructor(private readonly o: LadderModeOptions) {
    this.redPen = o.redPen;
    const wide = window.matchMedia("(min-width: 720px) and (min-height: 720px)").matches;
    this.panel = new LadderPanel(o.ladder, { step: (id) => this.step(id), redPen: (on) => this.setRedPen(on) }, wide);
    o.root.append(this.panel.root);
    this.chip = Object.assign(document.createElement("button"), { type: "button", className: "chip", textContent: LADDER.chip, title: LADDER.chipTitle });
    this.chip.dataset.control = "ladder";
    this.chip.setAttribute("aria-pressed", "false");
    this.chip.addEventListener("click", () => (this.on ? this.leave() : this.enter("first")));
    // After the map's tab: the ladder is another way of looking, like the map.
    o.chrome.mapButton.after(this.chip);
    this.panel.setRedPen(this.redPen);
    // The touch controls' tilt switch keeps the foot of the sheet; it rides above the panel, whatever its height.
    new ResizeObserver(() => {
      document.documentElement.style.setProperty("--ladder-h", `${this.panel.root.hidden ? 0 : this.panel.root.offsetHeight}px`);
    }).observe(this.panel.root);
  }

  get active() {
    return this.on;
  }

  get current() {
    return this.rung;
  }

  /** Into the ladder at a rung (the first step by default), standing at the camera point, facing the first photo. */
  enter(id: RungId | "first", opts: { standAtCamera?: boolean } = {}) {
    const target = id === "first" ? this.o.ladder.steps[0] : id;
    if (!rungById(this.o.ladder, target)) return;
    const { viewer, chrome } = this.o;
    if (!this.on) {
      this.on = true;
      chrome.hideIntro();
      this.panel.root.hidden = false;
      this.chip.setAttribute("aria-pressed", "true");
      viewer.map.setLegend(this.panel.mapLegend);
      viewer.setRedPen(this.redPen);
      document.documentElement.dataset.ladder = "on";
      if (opts.standAtCamera !== false) this.standAtCamera(target);
    }
    this.step(target);
  }

  private standAtCamera(id: RungId) {
    const r = rungById(this.o.ladder, id)!;
    const c = this.o.ladder.camera.c;
    const f = r.frustums[0]?.forward;
    const pose = this.o.viewer.walk.pose();
    // yaw 0 looks along −z and −90° along +x (schema README), so a forward (x, z) is yaw atan2(−x, −z).
    const yaw = f ? Math.atan2(-f[0], -f[2]) : pose.yaw;
    this.o.viewer.walk.setPose({ position: new THREE.Vector3(c[0], 0, c[2]), yaw, pitch: 0 });
  }

  step(id: RungId) {
    if (!this.on) { this.enter(id); return; }
    const r = rungById(this.o.ladder, id);
    if (!r || r === this.rung) return;
    this.rung = r;
    const { viewer } = this.o;
    const html = document.documentElement.dataset;
    html.ladderRung = r.id;
    delete html.ladderReady;
    const world = viewer.replaceWorld((three, hooks) => new RungWorld(three, r, r.placed ? filesFor(r, this.o.phone) : undefined, this.o.base, hooks));
    this.layLines(r);
    this.panel.show(r);
    this.panel.setStatus(r.placed ? LADDER.loading(r.label) : "");
    this.address();
    world.complete.then(
      () => { if (viewer.world === world) { this.panel.setStatus(""); html.ladderReady = r.id; } },
      (e: unknown) => { if (viewer.world === world) this.panel.setStatus(LADDER.failed); console.warn(e); },
    );
  }

  /** The rung's photo frames, its seen floor on the map and its coastline on the floor; the last rung's go first. */
  private layLines(r: LadderRung) {
    const { viewer } = this.o;
    this.clearLines();
    const floorY = viewer.sceneContract.floor.y;
    const ink = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#1c1a17";
    const wedges = makeWedges(r.frustums, this.o.ladder.camera.c, ink, floorY);
    const seen = makeSeenFloor(r.map?.seenFloor ?? [], ink, floorY);
    for (const l of [wedges, seen]) { viewer.addOverlay(l); this.lines.push(l); }
    viewer.setCoastline({ polylines: (r.map?.coastline ?? []).map((points) => ({ closed: false, points })) });
  }

  private clearLines() {
    for (const l of this.lines) { this.o.viewer.removeOverlay(l); l.dispose(); }
    this.lines = [];
  }

  /** Back to the walk: the rung's world goes, and Part 1's three files come back. */
  leave() {
    if (!this.on) return;
    const { viewer } = this.o;
    this.on = false;
    this.rung = null;
    this.clearLines();
    viewer.setCoastline(this.o.coastline);
    viewer.map.setLegend(null);
    viewer.setRedPen(false);
    viewer.replaceWorld(viewer.walkWorld());
    this.panel.root.hidden = true;
    this.chip.setAttribute("aria-pressed", "false");
    const html = document.documentElement.dataset;
    delete html.ladder; delete html.ladderRung; delete html.ladderReady;
    this.address();
  }

  setRedPen(on: boolean) {
    this.redPen = on;
    this.panel.setRedPen(on);
    if (this.on) this.o.viewer.setRedPen(on);
    this.address();
  }

  /** The address carries the rung and the pen, so a shared link opens the same view. */
  private address() {
    const url = new URL(location.href);
    if (this.on && this.rung) url.searchParams.set("ladder", this.rung.id);
    else url.searchParams.delete("ladder");
    if (this.on && this.redPen) url.searchParams.set("redpen", "1");
    else url.searchParams.delete("redpen");
    history.replaceState(history.state, "", url);
  }
}
