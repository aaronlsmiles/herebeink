// The plain-words layer: the band that follows the walk, the notes beside the parts that confuse, and the
// top-bar switch. It mounts beside the page's own chrome and never edits it; with the layer off, every piece is
// hidden and the page reads exactly as before.
import "./plainwords.css";
import type { Coastline, Vec3 } from "../contract.ts";
import { PENCIL_SVG, type Chrome } from "../ui.ts";
import type { Viewer } from "../viewer.ts";
import { addressWithoutPlain, startMode, storeMode, type PlainMode } from "./state.ts";
import { lineView, Trail } from "./trail.ts";
import { CHAPTERS, chapterLabel, NOTES, UI, type NoteId } from "./words.ts";
import { LADDER_NOTES, type LadderNoteId } from "./ladder.ts";

export interface PlainWords {
  /** The map opened or closed, however it was asked. */
  mapChanged(open: boolean): void;
  /** The room is still arriving: the loading line's note shows only then. */
  setLoading(on: boolean): void;
}

export interface PlainOptions {
  root: HTMLElement;
  chrome: Chrome;
  viewer: Viewer;
  coastline: Coastline;
  doorOutward: Vec3;
  search: string;
  allowed: boolean;
}

const BAND_ID = "plain-words";
/** How often the walk is read for the next moment: often enough to catch a step over a 0.6 m line. */
const LOOK_MS = 150;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> & { className?: string } = {}, ...children: (Node | string)[]) {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...children);
  return e;
}

function mark() {
  const t = document.createElement("template");
  t.innerHTML = PENCIL_SVG;
  return t.content.firstElementChild!;
}

function arrow() {
  const a = el("span", {}, "→");
  a.setAttribute("aria-hidden", "true");
  return a;
}

/** A note before (or beside) the thing it explains; the label is said once, for screen readers, as the voice's name. */
function note(id: NoteId, heading?: HTMLElement) {
  return plainNote(id, NOTES[id], heading);
}

/** Any note in the layer's voice; it shows only while the layer is on (plainwords.css). */
export function plainNote(id: string, lines: readonly string[], heading?: HTMLElement) {
  const n = el("div", { className: "pw-note" });
  n.setAttribute("role", "note");
  n.dataset.note = id;
  const said = el("span", { className: "visually-hidden" }, `${UI.label}: `);
  const text = el("div", { className: "pw-text" }, ...(heading ? [heading] : []), said, ...lines.map((t) => el("p", {}, t)));
  n.append(mark(), text);
  return n;
}

/** A ladder note, by its id in LADDER_NOTES. */
export function ladderNote(id: LadderNoteId, heading?: HTMLElement) {
  return plainNote(`ladder-${id}`, LADDER_NOTES[id], heading);
}

function storage(): Storage | null {
  try { return window.localStorage; } catch { return null; }
}

export function mountPlainWords(o: PlainOptions): PlainWords | null {
  const store = storage();
  const initial = startMode(o.search, o.allowed, store);
  if (initial === null) return null;
  const { root, chrome, viewer } = o;
  const html = document.documentElement;
  const trail = new Trail();
  let mode: PlainMode = initial;

  // The band: the chapter of the story that matches the walk, on the first screen and then at the walk's edge.
  const label = el("p", { className: "pw-label" }, mark(), el("span"));
  const title = el("h2", { className: "pw-title" });
  const head = el("div", { className: "pw-head" }, label, title);
  // A moment opens a chapter mid-walk without taking focus, which would stop the keys walking; the chapter's
  // name is announced instead.
  head.setAttribute("aria-live", "polite");
  const storyMap = el("ol", { className: "pw-trail" });
  storyMap.setAttribute("aria-label", UI.chapters);
  const steps = CHAPTERS.map((c, i) => {
    const b = el("button", { type: "button" }, c.title);
    b.addEventListener("click", () => { trail.goTo(i); render(); focusBand(); });
    storyMap.append(el("li", {}, b));
    return b;
  });
  const text = el("div", { className: "pw-text" });
  const coastNote = note("coastline");
  const nextButton = el("button", { type: "button", className: "pw-btn pw-next" });
  nextButton.addEventListener("click", () => { trail.next(); render(); focusBand(); });
  const hideButton = el("button", { type: "button", className: "pw-quiet" }, UI.hide);
  hideButton.addEventListener("click", () => { setMode("off", true); focusAway(); });
  const band = el("aside", { className: "pw-band", id: BAND_ID, tabIndex: -1, hidden: true },
    head, storyMap, text, coastNote, el("p", { className: "pw-foot" }, nextButton, hideButton));
  band.setAttribute("aria-label", UI.label);

  // The top bar's switch, which brings the layer back once it is hidden.
  const toggle = el("button", { type: "button", className: "chip pw-switch" }, mark(), UI.toggle);
  toggle.dataset.control = "plain";
  toggle.addEventListener("click", () => {
    const on = mode !== "on";
    setMode(on ? "on" : "off", true);
    if (on) focusBand();
  });
  chrome.bar.append(toggle);

  // The bar's notes, in the bar's order, folded on small screens so the room stays in view.
  const fold = el("details", { className: "pw-fold", hidden: true });
  fold.open = window.matchMedia("(min-width: 1024px) and (min-height: 700px)").matches;
  fold.append(el("summary", {}, mark(), UI.barNotes));
  const forControls: { control: string; heading: HTMLElement; n: HTMLElement }[] = [];
  const forControl = (control: string, make: (heading: HTMLElement) => HTMLElement) => {
    const heading = el("p", { className: "pw-for" });
    const n = make(heading);
    forControls.push({ control, heading, n });
    fold.append(n);
  };
  forControl("about", (h) => note("about", h));
  forControl("map", (h) => note("mapButton", h));
  forControl("ink", (h) => note("ink", h));
  forControl("xr", (h) => note("vr", h));
  forControl("ladder", (h) => ladderNote("ladderButton", h));
  /** Each heading quotes its control's live label; Enter VR's note shows only once its button does. */
  const syncFold = () => {
    for (const { control, heading, n } of forControls) {
      const b = chrome.bar.querySelector<HTMLElement>(`[data-control='${control}']`);
      n.hidden = !b;
      if (b) heading.textContent = `“${b.textContent?.trim() ?? ""}”`;
    }
  };
  syncFold();
  new MutationObserver(syncFold).observe(chrome.bar, { childList: true, subtree: true, characterData: true });

  const stack = el("div", { className: "pw-stack" }, fold);
  root.append(stack);
  // The stack starts below the bar, however many rows its buttons wrap to.
  const placeStack = () => {
    const b = chrome.bar;
    stack.hidden = b.hidden;
    root.style.setProperty("--pw-top", `${b.offsetTop + b.offsetHeight + 8}px`);
  };
  new ResizeObserver(placeStack).observe(chrome.bar);
  new MutationObserver(placeStack).observe(chrome.bar, { attributes: true, attributeFilter: ["hidden"] });

  // Notes beside the first screen's parts, the map's key and the phone's tilt switch.
  const intro = chrome.intro;
  const actions = intro.querySelector(".actions");
  actions?.before(note("walkIn"));
  const loading = note("loading");
  loading.hidden = true;
  actions?.after(loading);
  intro.querySelector(".credit")?.before(note("credit"));
  intro.querySelector(".device")?.before(note("device"));
  viewer.map.root.querySelector(".map-legend h2")?.after(note("map"));
  root.querySelector(".gyro-button")?.before(note("tilt"));

  // The band sits in the invite's place on the first screen, and at the walk's edge once the walk starts.
  const placeBand = () => {
    if (!intro.hidden) (intro.querySelector(".pw-invite") ?? intro.querySelector(".statement"))?.after(band);
    else stack.append(band);
  };
  new MutationObserver(placeBand).observe(intro, { attributes: true, attributeFilter: ["hidden"] });

  function render() {
    const i = trail.chapter;
    const c = CHAPTERS[i];
    label.lastElementChild!.textContent = chapterLabel(i);
    title.textContent = c.title;
    text.replaceChildren(...c.text.map((t) => el("p", {}, t)));
    band.dataset.chapter = String(i + 1);
    steps.forEach((b, k) => (k === i ? b.setAttribute("aria-current", "step") : b.removeAttribute("aria-current")));
    coastNote.hidden = i !== 1;
    nextButton.hidden = trail.isLast;
    if (!trail.isLast) nextButton.replaceChildren(`${UI.next} ${CHAPTERS[i + 1].title} `, arrow());
    text.scrollTop = 0;
    band.scrollTop = 0;
  }

  function focusBand() {
    requestAnimationFrame(() => band.focus({ preventScroll: true }));
  }
  /** Hiding hands focus back: to the switch where the bar shows, else to the first screen's title. */
  function focusAway() {
    requestAnimationFrame(() => {
      if (!chrome.bar.hidden) { toggle.focus({ preventScroll: true }); return; }
      const h1 = intro.querySelector("h1");
      if (h1) { h1.tabIndex = -1; h1.focus({ preventScroll: true }); }
    });
  }

  let looking: number | null = null;
  const look = () => {
    // The walk's chapters follow Part 1's pen line, which the ladder does not draw.
    if (viewer.mapOn || viewer.xrActive || html.dataset.ladder === "on") return;
    const pose = viewer.walk.pose();
    const cam = viewer.camera;
    const halfH = Math.atan(cam.aspect * Math.tan((cam.fov * Math.PI) / 360));
    const v = lineView([pose.position.x, pose.position.z], pose.yaw, halfH, o.coastline.polylines.map((l) => l.points), [o.doorOutward[0], o.doorOutward[2]]);
    if (trail.observe(v) !== null) render();
  };

  function setMode(m: PlainMode, byReader: boolean) {
    mode = m;
    html.dataset.plain = m;
    const on = m === "on";
    band.hidden = !on;
    fold.hidden = !on;
    toggle.setAttribute("aria-pressed", String(on));
    chrome.offerPlainWords(m === "unset" ? () => { setMode("on", true); focusBand(); } : null);
    if (on && looking === null) looking = window.setInterval(look, LOOK_MS);
    if (!on && looking !== null) { window.clearInterval(looking); looking = null; }
    if (byReader && m !== "unset") {
      storeMode(store, m);
      const a = addressWithoutPlain(location.href);
      if (a !== null) history.replaceState(history.state, "", a);
    }
  }

  placeStack();
  placeBand();
  render();
  setMode(mode, false);

  return {
    mapChanged(open) {
      if (open && mode === "on" && trail.mapOpened() !== null) render();
    },
    setLoading(on) {
      loading.hidden = !on;
    },
  };
}
